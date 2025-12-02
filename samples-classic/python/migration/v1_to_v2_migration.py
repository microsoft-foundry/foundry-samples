import os, sys, time, json, argparse, subprocess, requests
from typing import List, Dict, Any, Optional
from azure.cosmos import CosmosClient, exceptions
from read_cosmos_data import fetch_data
from azure.ai.agents.models import AzureFunctionStorageQueue, AzureFunctionTool

# Import AIProjectClient for project endpoint support
try:
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential, AzureCliCredential
    from azure.core.credentials import AccessToken
    PROJECT_CLIENT_AVAILABLE = True
except ImportError:
    PROJECT_CLIENT_AVAILABLE = False
    print("⚠️  Warning: azure-ai-projects package not available. Project endpoint functionality disabled.")

# Cosmos DB Configuration
COSMOS_CONNECTION_STRING = os.getenv("COSMOS_CONNECTION_STRING") or None
DATABASE_NAME = "testDB2"
WRITE_DATABASE_NAME = "agents"
SOURCE_CONTAINER = "testContainer1"  # Where v1 assistants and agents are stored
TARGET_CONTAINER = "agent-definitions"  # Where v2 agents will be stored

# API Configuration
HOST = os.getenv("AGENTS_HOST") or "eastus.api.azureml.ms"
# Use host.docker.internal for Docker containers to access Windows host
LOCAL_HOST = os.getenv("LOCAL_HOST") or "host.docker.internal:5001" #"localhost:5001"#
SUBSCRIPTION_ID = os.getenv("AGENTS_SUBSCRIPTION") or "921496dc-987f-410f-bd57-426eb2611356"
RESOURCE_GROUP = os.getenv("AGENTS_RESOURCE_GROUP") or "agents-e2e-tests-eastus"
RESOURCE_GROUP_V2 = os.getenv("AGENTS_RESOURCE_GROUP_V2") or "agents-e2e-tests-westus2"
WORKSPACE = os.getenv("AGENTS_WORKSPACE") or "basicaccountjqqa@e2e-tests@AML"
WORKSPACE_V2 = os.getenv("AGENTS_WORKSPACE_V2") or "e2e-tests-westus2-account@e2e-tests-westus2@AML"
API_VERSION = os.getenv("AGENTS_API_VERSION") or "2025-05-15-preview"
TOKEN = os.getenv("AZ_TOKEN")

# Source Tenant Configuration (for reading v1 assistants from source tenant)
SOURCE_TENANT = os.getenv("SOURCE_TENANT") or os.getenv("AGENTS_TENANT") or "72f988bf-86f1-41af-91ab-2d7cd011db47"  # Microsoft tenant

# Production Resource Configuration
PRODUCTION_RESOURCE = os.getenv("PRODUCTION_RESOURCE")  # e.g., "nextgen-eastus"
PRODUCTION_SUBSCRIPTION = os.getenv("PRODUCTION_SUBSCRIPTION")  # e.g., "b1615458-c1ea-49bc-8526-cafc948d3c25"
PRODUCTION_TENANT = os.getenv("PRODUCTION_TENANT")  # e.g., "33e577a9-b1b8-4126-87c0-673f197bf624"
PRODUCTION_TOKEN = os.getenv("PRODUCTION_TOKEN")  # Production token from PowerShell script

# v1 API base URL
BASE_V1 = f"https://{HOST}/agents/v1.0/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{RESOURCE_GROUP}/providers/Microsoft.MachineLearningServices/workspaces/{WORKSPACE}"
# v2 API base URL - will be determined based on production vs local mode
BASE_V2 = None  # Will be set dynamically based on production resource configuration

def create_cosmos_client_from_connection_string(connection_string: str):
    """
    Create a Cosmos DB client using a connection string.
    """
    try:
        return CosmosClient.from_connection_string(connection_string)
    except Exception as e:
        print(f"Failed to create Cosmos client from connection string: {e}")
        raise

def ensure_database_and_container(client, database_name: str, container_name: str):
    """
    Ensure the database and container exist, create them if they don't.
    """
    try:
        database = client.get_database_client(database_name)
        print(f"Database '{database_name}' found")
    except exceptions.CosmosResourceNotFoundError:
        print(f"Creating database '{database_name}'")
        database = client.create_database_if_not_exists(id=database_name)
    
    try:
        container = database.get_container_client(container_name)
        print(f"Container '{container_name}' found")
    except exceptions.CosmosResourceNotFoundError:
        print(f"Creating container '{container_name}'")
        container = database.create_container_if_not_exists(
            id=container_name,
            partition_key={'paths': ['/id'], 'kind': 'Hash'}
        )
    
    return database, container

def get_production_v2_base_url(resource_name: str, subscription_id: str, project_name: str) -> str:
    """
    Build the production v2 API base URL for Azure AI services.
    
    Args:
        resource_name: The Azure AI resource name (e.g., "nextgen-eastus")
        subscription_id: The subscription ID for production
        project_name: The project name (e.g., "nextgen-eastus")
    
    Returns:
        The production v2 API base URL
    """
    # Production format: https://{resource}-resource.services.ai.azure.com/api/projects/{project}/agents/{agent}/versions
    return f"https://{resource_name}-resource.services.ai.azure.com/api/projects/{project_name}"

# Production token handling removed - now handled by PowerShell wrapper
# which provides PRODUCTION_TOKEN environment variable

# Production authentication is now handled by the PowerShell wrapper
# which generates both AZ_TOKEN and PRODUCTION_TOKEN environment variables

def get_token_from_az(tenant_id: Optional[str] = None) -> Optional[str]:
    """
    Runs the az CLI to get an access token for the AI resource scope.
    Returns the token string on success, or None on failure.
    
    Args:
        tenant_id: Optional tenant ID to authenticate with
    """
    try:
        cmd = [
            "az", "account", "get-access-token",
            "--scope", "https://ai.azure.com/.default",
            "--query", "accessToken",
            "-o", "tsv"
        ]
        
        # Add tenant parameter if provided
        if tenant_id:
            cmd.extend(["--tenant", tenant_id])
            print(f"🔐 Requesting token for tenant: {tenant_id}")
        
        # capture output (shell=True needed for Windows)
        proc = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        if proc.returncode != 0:
            print("az CLI returned non-zero exit code when fetching token:", proc.stderr.strip())
            return None
        
        # Clean the token output - get only the last non-empty line that looks like a token
        lines = [line.strip() for line in proc.stdout.strip().split('\n') if line.strip()]
        if not lines:
            print("az CLI returned empty token.")
            return None
        
        # JWT tokens start with 'ey' or are long strings (>100 chars)
        token = None
        for line in reversed(lines):
            if line.startswith('ey') or len(line) > 100:
                token = line
                break
        
        if not token:
            # Fallback to the last line if no obvious token found
            token = lines[-1]
            
        return token
    except FileNotFoundError:
        print("az CLI not found on PATH. Please install Azure CLI or set AZ_TOKEN env var.")
        return None
    except Exception as ex:
        print("Unexpected error while running az CLI:", ex)
        return None

class ManualAzureCliCredential:
    """
    A custom credential class that uses our manual az CLI token extraction.
    This works around issues with the azure-identity AzureCliCredential in containers.
    """
    def get_token(self, *scopes, **kwargs):
        """Get an access token using az CLI."""
        try:
            # Try different scopes based on what's requested
            if scopes:
                scope = scopes[0]
            else:
                # Default to Azure AI scope for Azure AI Projects (confirmed correct audience)
                scope = "https://ai.azure.com/.default"
            
            cmd = [
                "az", "account", "get-access-token",
                "--scope", scope,
                "--query", "accessToken",
                "-o", "tsv"
            ]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, shell=True)
            if proc.returncode != 0:
                # Try without suppressing stderr to get the actual error
                proc_debug = subprocess.run(cmd, capture_output=True, text=True, shell=True)
                raise Exception(f"az CLI returned error: {proc_debug.stderr.strip()}")
            
            # Clean the token output - get only the last non-empty line (the actual token)
            lines = [line.strip() for line in proc.stdout.strip().split('\n') if line.strip()]
            if not lines:
                raise Exception("az CLI returned empty token")
            
            # The token should be the last line that looks like a token (starts with ey)
            token = None
            for line in reversed(lines):
                if line.startswith('ey') or len(line) > 50:  # JWT tokens start with 'ey' or are long strings
                    token = line
                    break
            
            if not token:
                # Fallback to the last line if no obvious token found
                token = lines[-1]
            
            # Return a proper AccessToken object
            import time
            # Token expires in 1 hour (3600 seconds)
            expires_on = int(time.time()) + 3600
            return AccessToken(token, expires_on)
            
        except Exception as e:
            raise Exception(f"Failed to get token via az CLI: {e}")

class StaticTokenCredential:
    """
    A credential class that uses a pre-provided static token.
    Useful when we have a token from AZ_TOKEN environment variable.
    """
    def __init__(self, token: str):
        self.token = token
        
    def get_token(self, *scopes, **kwargs):
        """Return the static token."""
        import time
        # Assume token expires in 1 hour (3600 seconds)
        expires_on = int(time.time()) + 3600
        return AccessToken(self.token, expires_on)

def get_azure_credential():
    """
    Get the appropriate Azure credential for the current environment.
    Prefers static token credential when AZ_TOKEN is available.
    """
    if not PROJECT_CLIENT_AVAILABLE:
        raise ImportError("azure-identity package is required for credential functionality")
    
    # Check if we have a static token from environment variable (highest priority)
    static_token = os.environ.get('AZ_TOKEN')
    if static_token:
        print("🔑 Using static token from AZ_TOKEN environment variable")
        return StaticTokenCredential(static_token)
    
    # Check if we're likely in a container environment
    is_container = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER') == 'true'
    
    if is_container:
        # In container, use DefaultAzureCredential which has better fallback handling for version mismatches
        try:
            print("🐳 Container environment detected, using DefaultAzureCredential for better compatibility")
            return DefaultAzureCredential()
        except Exception as e:
            print(f"⚠️  DefaultAzureCredential failed: {e}")
            print("💡 Falling back to manual Azure CLI credential")
            try:
                return ManualAzureCliCredential()
            except Exception as e2:
                print(f"⚠️  Manual Azure CLI credential also failed: {e2}")
                print("💡 This might be due to Azure CLI version mismatch between host and container")
                raise Exception(f"All credential methods failed. Host CLI: 2.77.0, Container CLI: 2.78.0. Try: az upgrade")
    else:
        # On host system, use default credential chain
        print("🖥️  Host environment detected, using default credential chain")
        return DefaultAzureCredential()

def set_api_token(force_refresh: bool = False, tenant_id: Optional[str] = None) -> bool:
    """
    Ensure we have a valid bearer token for API calls.
    Returns True if a token is set, False otherwise.
    
    Args:
        force_refresh: If True, ignore existing tokens and get a fresh one from az CLI
        tenant_id: Optional tenant ID to authenticate with (uses SOURCE_TENANT if not provided)
    """
    global TOKEN
    
    # If force refresh is requested, skip environment variable and get fresh token
    if not force_refresh:
        # Check environment variable first
        env_token = os.getenv("AZ_TOKEN")
        if env_token:
            TOKEN = env_token
            return True
    
    # Use provided tenant or default to SOURCE_TENANT
    if tenant_id is None:
        tenant_id = SOURCE_TENANT
    
    # Try az CLI (either forced or as fallback) with tenant
    token = get_token_from_az(tenant_id)
    if token:
        TOKEN = token
        print(f"🔄 Token refreshed from az CLI for tenant: {tenant_id}")
        return True
    return False

def do_api_request_with_token(method: str, url: str, token: str, **kwargs) -> requests.Response:
    """
    Wrapper around requests.request with specific token authentication.
    """
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    headers["Accept"] = "application/json"
    kwargs["headers"] = headers

    # Set longer timeout for localhost/local development (servers may be slower)
    if "localhost" in url or "host.docker.internal" in url:
        kwargs["timeout"] = 120  # 2 minutes for local development
        kwargs["verify"] = False
        # Suppress the SSL warning for localhost/local development
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        host_type = "localhost" if "localhost" in url else "host.docker.internal (Docker)"
        print(f"🏠 Making request to {host_type} with extended timeout and no SSL verification: {url}")
    elif "timeout" not in kwargs:
        kwargs["timeout"] = 30

    try:
        resp = requests.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp
    
    except requests.exceptions.Timeout as e:
        print(f"⏰ Request timed out: {e}")
        print("💡 This usually means:")
        print("   - The server is not running")
        print("   - The server is overloaded")
        print("   - The endpoint doesn't exist")
        if "localhost" in url or "host.docker.internal" in url:
            print("   - Check if the v2 API server is running")
        raise
    except requests.exceptions.ConnectionError as e:
        print(f"🔌 Connection failed: {e}")
        if "localhost" in url or "host.docker.internal" in url:
            print("💡 Make sure the v2 API server is running")
        raise
    except requests.exceptions.RequestException as e:
        print(f"❌ API request failed: {e}")
        raise

def do_api_request(method: str, url: str, **kwargs) -> requests.Response:
    """
    Wrapper around requests.request with authentication and retry logic.
    """
    headers = kwargs.pop("headers", {})
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    headers["Accept"] = "application/json"
    kwargs["headers"] = headers

    # Set longer timeout for localhost/local development (servers may be slower)
    if "localhost" in url or "host.docker.internal" in url:
        kwargs["timeout"] = 120  # 2 minutes for local development
        kwargs["verify"] = False
        # Suppress the SSL warning for localhost/local development
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        host_type = "localhost" if "localhost" in url else "host.docker.internal (Docker)"
        print(f"🏠 Making request to {host_type} with extended timeout and no SSL verification: {url}")
    elif "timeout" not in kwargs:
        kwargs["timeout"] = 30

    try:
        resp = requests.request(method, url, **kwargs)
        if resp.status_code == 401:
            print("Received 401 Unauthorized. Trying to refresh token...")
            time.sleep(5)
            if set_api_token(force_refresh=True):  # Force refresh from az CLI on 401
                headers["Authorization"] = f"Bearer {TOKEN}"
                kwargs["headers"] = headers
                resp = requests.request(method, url, **kwargs)
            else:
                print("Token refresh failed.")
        
        resp.raise_for_status()
        return resp
    
    except requests.exceptions.Timeout as e:
        print(f"⏰ Request timed out: {e}")
        print("💡 This usually means:")
        print("   - The server is not running")
        print("   - The server is overloaded")
        print("   - The endpoint doesn't exist")
        if "localhost" in url or "host.docker.internal" in url:
            print("   - Check if the v2 API server is running")
        raise
    except requests.exceptions.ConnectionError as e:
        print(f"🔌 Connection failed: {e}")
        if "localhost" in url or "host.docker.internal" in url:
            print("💡 Make sure the v2 API server is running")
        raise
    except requests.exceptions.RequestException as e:
        print(f"❌ API request failed: {e}")
        raise

def test_v2_api_connectivity() -> bool:
    """Test if the local v2 API server is reachable."""
    # Build local development URL for testing
    local_base = f"https://{LOCAL_HOST}/agents/v2.0/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{RESOURCE_GROUP_V2}/providers/Microsoft.MachineLearningServices/workspaces/{WORKSPACE_V2}"
    
    try:
        # Try a simple GET request to the base URL
        print(f"🔍 Testing connectivity to {local_base}...")
        response = requests.get(local_base, verify=False, timeout=10)
        print(f"✅ Server responded with status code: {response.status_code}")
        return True
    except requests.exceptions.Timeout:
        print(f"⏰ Timeout connecting to {local_base}")
        print("💡 The server might not be running or is too slow to respond")
        return False
    except requests.exceptions.ConnectionError:
        print(f"🔌 Cannot connect to {local_base}")
        print("💡 Make sure the v2 API server is running")
        return False
    except Exception as e:
        print(f"❌ Unexpected error testing connectivity: {e}")
        return False

def get_assistant_from_api(assistant_id: str) -> Dict[str, Any]:
    """Get v1 assistant details from API including internal metadata."""
    url = f"{BASE_V1}/assistants/{assistant_id}"
    params = {"api-version": API_VERSION, "include[]": "internal_metadata"}
    r = do_api_request("GET", url, params=params)
    return r.json()

def list_assistants_from_api() -> List[Dict[str, Any]]:
    """List all v1 assistants from API."""
    url = f"{BASE_V1}/assistants"
    params = {"api-version": API_VERSION, "limit": "100", "include[]": "internal_metadata"}
    r = do_api_request("GET", url, params=params)
    response_data = r.json()
    
    # Handle different response formats
    if isinstance(response_data, dict):
        if "data" in response_data:
            return response_data["data"]
        elif "assistants" in response_data:
            return response_data["assistants"]
        elif "items" in response_data:
            return response_data["items"]
    elif isinstance(response_data, list):
        return response_data
    
    # If we can't find a list, return empty
    print(f"Warning: Unexpected API response format: {type(response_data)}")
    return []

def ensure_project_connection_package():
    """Ensure the correct azure-ai-projects version is installed for project connection string functionality."""
    try:
        # Test if we have the from_connection_string method
        from azure.ai.projects import AIProjectClient
        if hasattr(AIProjectClient, 'from_connection_string'):
            print("✅ Correct azure-ai-projects version already installed (1.0.0b10)")
            return True
        else:
            print("⚠️  Current azure-ai-projects version doesn't support from_connection_string")
            print("🔄 Upgrading to azure-ai-projects==1.0.0b10...")
            
            import subprocess
            import sys
            
            # Upgrade to the beta version
            result = subprocess.run([
                sys.executable, "-m", "pip", "install", "--upgrade", "azure-ai-projects==1.0.0b10"
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ Successfully upgraded to azure-ai-projects==1.0.0b10")
                # Force reimport after upgrade
                import importlib
                import azure.ai.projects
                importlib.reload(azure.ai.projects)
                return True
            else:
                print(f"❌ Failed to upgrade package: {result.stderr}")
                return False
                
    except ImportError:
        print("❌ azure-ai-projects package not found")
        print("🔄 Installing azure-ai-projects==1.0.0b10...")
        
        import subprocess
        import sys
        
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", "azure-ai-projects==1.0.0b10"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Successfully installed azure-ai-projects==1.0.0b10")
            return True
        else:
            print(f"❌ Failed to install package: {result.stderr}")
            return False

def get_assistant_from_project_connection(project_connection_string: str, assistant_id: str) -> Dict[str, Any]:
    """Get v1 assistant details from AIProjectClient using connection string."""
    global AIProjectClient, PROJECT_CLIENT_AVAILABLE
    
    if not PROJECT_CLIENT_AVAILABLE:
        print("❌ azure-ai-projects package is required for project connection string functionality")
        print("🔄 Attempting to install the correct version...")
        if not ensure_project_connection_package():
            raise ImportError("Failed to install azure-ai-projects==1.0.0b10")

        # Re-import after installation
        try:
            from azure.ai.projects import AIProjectClient
            PROJECT_CLIENT_AVAILABLE = True
        except ImportError:
            raise ImportError("Failed to import AIProjectClient after installation")    # Ensure we have the correct version
    if not ensure_project_connection_package():
        raise ImportError("azure-ai-projects==1.0.0b10 is required for project connection string functionality")
    
    # Try to use from_connection_string method (available in beta versions)
    try:
        project_client = AIProjectClient.from_connection_string(
            credential=get_azure_credential(),
            conn_str=project_connection_string
        )
        print("✅ Using AIProjectClient.from_connection_string method")
    except AttributeError:
        # This shouldn't happen now, but keep as fallback
        print("⚠️  from_connection_string not available after upgrade")
        raise ImportError("azure-ai-projects==1.0.0b10 is required for project connection string functionality")
    
    with project_client:
        agent = project_client.agents.get_agent(assistant_id)
        # Convert the agent object to dictionary format with proper JSON serialization
        if hasattr(agent, 'model_dump'):
            return json.loads(json.dumps(agent.model_dump(), default=str))
        else:
            return json.loads(json.dumps(dict(agent), default=str))

def list_assistants_from_project_connection(project_connection_string: str) -> List[Dict[str, Any]]:
    """List all v1 assistants from AIProjectClient using connection string."""
    global AIProjectClient, PROJECT_CLIENT_AVAILABLE
    
    if not PROJECT_CLIENT_AVAILABLE:
        print("❌ azure-ai-projects package is required for project connection string functionality")
        print("🔄 Attempting to install the correct version...")
        if not ensure_project_connection_package():
            raise ImportError("Failed to install azure-ai-projects==1.0.0b10")

        # Re-import after installation
        try:
            from azure.ai.projects import AIProjectClient
            PROJECT_CLIENT_AVAILABLE = True
        except ImportError:
            raise ImportError("Failed to import AIProjectClient after installation")    # Ensure we have the correct version
    if not ensure_project_connection_package():
        raise ImportError("azure-ai-projects==1.0.0b10 is required for project connection string functionality")
    
    # Try to use from_connection_string method (available in beta versions)
    try:
        project_client = AIProjectClient.from_connection_string(
            credential=get_azure_credential(),
            conn_str=project_connection_string
        )
        print("✅ Using AIProjectClient.from_connection_string method")
    except AttributeError:
        # This shouldn't happen now, but keep as fallback
        print("⚠️  from_connection_string not available after upgrade")
        raise ImportError("azure-ai-projects==1.0.0b10 is required for project connection string functionality")
    
    with project_client:
        agents = project_client.agents.list_agents()
        # Convert agent objects to dictionary format with proper JSON serialization
        agent_list = []
        for agent in agents:
            if hasattr(agent, 'model_dump'):
                agent_dict = json.loads(json.dumps(agent.model_dump(), default=str))
            else:
                agent_dict = json.loads(json.dumps(dict(agent), default=str))
            agent_list.append(agent_dict)
        return agent_list

def get_assistant_from_project(project_endpoint: str, assistant_id: str, subscription_id: Optional[str] = None, resource_group_name: Optional[str] = None, project_name: Optional[str] = None) -> Dict[str, Any]:
    """Get v1 assistant details from project endpoint using direct API calls (bypassing AIProjectClient SDK bug)."""
    
    # Since direct API calls work and AIProjectClient has issues, use direct REST API
    print(f"   🌐 Using direct API call to project endpoint (bypassing AIProjectClient SDK)")
    
    # Build the direct API URL
    if not project_endpoint.endswith('/'):
        project_endpoint = project_endpoint + '/'
    
    # Remove trailing slash if present, then add the assistants path
    api_url = project_endpoint.rstrip('/') + f'/assistants/{assistant_id}'
    
    # Add API version parameter
    params = {"api-version": API_VERSION}
    
    print(f"   📞 Making direct API call to: {api_url}")
    print(f"   🔧 Using API version: {API_VERSION}")
    
    try:
        # Make the direct API request
        response = do_api_request("GET", api_url, params=params)
        result = response.json()
        
        print(f"   ✅ Successfully retrieved assistant via direct API call")
        print(f"   📋 Assistant ID: {result.get('id', 'N/A')}")
        print(f"   📋 Assistant Name: {result.get('name', 'N/A')}")
        
        return result
        
    except Exception as e:
        print(f"   ❌ Direct API call failed: {e}")
        
        # Fallback to AIProjectClient if available (for debugging)
        if PROJECT_CLIENT_AVAILABLE:
            print(f"   🔄 Attempting fallback to AIProjectClient...")
            
            # Extract project information from endpoint if not provided
            if not subscription_id or not resource_group_name or not project_name:
                print(f"   🔍 Some project parameters missing, attempting to extract from endpoint or environment...")
                
                # Use environment variables as fallbacks
                subscription_id = subscription_id or os.getenv("AGENTS_SUBSCRIPTION") or "921496dc-987f-410f-bd57-426eb2611356"
                resource_group_name = resource_group_name or os.getenv("AGENTS_RESOURCE_GROUP") or "agents-e2e-tests-eastus"
                
                # Try to extract project name from endpoint URL
                if not project_name:
                    import re
                    project_match = re.search(r'/projects/([^/?]+)', project_endpoint)
                    if project_match:
                        project_name = project_match.group(1)
                        print(f"   📝 Extracted project name from endpoint: {project_name}")
                    else:
                        project_name = "default-project"
                        print(f"   ⚠️  Could not extract project name from endpoint, using default: {project_name}")
                
                print(f"   📋 Using: subscription={subscription_id[:8]}..., resource_group={resource_group_name}, project={project_name}")
            
            # Initialize AIProjectClient with all required parameters
            try:
                project_client = AIProjectClient(
                    endpoint=project_endpoint,
                    credential=get_azure_credential(),
                    subscription_id=subscription_id,
                    resource_group_name=resource_group_name,
                    project_name=project_name
                )
                
                with project_client:
                    agent = project_client.agents.get_agent(assistant_id)
                    # Convert the agent object to dictionary format with proper JSON serialization
                    if hasattr(agent, 'model_dump'):
                        return json.loads(json.dumps(agent.model_dump(), default=str))
                    else:
                        return json.loads(json.dumps(dict(agent), default=str))
                        
            except Exception as client_error:
                print(f"   ❌ AIProjectClient fallback also failed: {client_error}")
                raise RuntimeError(f"Both direct API call and AIProjectClient failed. Direct API error: {e}, AIProjectClient error: {client_error}")
        else:
            raise

def list_assistants_from_project(project_endpoint: str, subscription_id: Optional[str] = None, resource_group_name: Optional[str] = None, project_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all v1 assistants from project endpoint using direct API calls (bypassing AIProjectClient SDK bug)."""
    
    # Since direct API calls work and AIProjectClient has issues, use direct REST API
    print(f"   🌐 Using direct API call to project endpoint (bypassing AIProjectClient SDK)")
    
    # Build the direct API URL
    if not project_endpoint.endswith('/'):
        project_endpoint = project_endpoint + '/'
    
    # Remove trailing slash if present, then add the assistants path
    api_url = project_endpoint.rstrip('/') + '/assistants'
    
    # Add API version parameter
    params = {"api-version": API_VERSION, "limit": "100"}
    
    print(f"   📞 Making direct API call to: {api_url}")
    print(f"   🔧 Using API version: {API_VERSION}")
    
    try:
        # Make the direct API request
        response = do_api_request("GET", api_url, params=params)
        result = response.json()
        
        # Handle different response formats (same logic as list_assistants_from_api)
        if isinstance(result, dict):
            if "data" in result:
                agent_list = result["data"]
            elif "assistants" in result:
                agent_list = result["assistants"]
            elif "items" in result:
                agent_list = result["items"]
            else:
                # If we can't find a list, return empty
                print(f"   ⚠️  Unexpected API response format: {type(result)}")
                agent_list = []
        elif isinstance(result, list):
            agent_list = result
        else:
            # If we can't find a list, return empty
            print(f"   ⚠️  Unexpected API response format: {type(result)}")
            agent_list = []
        
        print(f"   ✅ Successfully retrieved {len(agent_list)} assistants via direct API call")
        
        return agent_list
        
    except Exception as e:
        print(f"   ❌ Direct API call failed: {e}")
        
        # Fallback to AIProjectClient if available (for debugging)
        if PROJECT_CLIENT_AVAILABLE:
            print(f"   🔄 Attempting fallback to AIProjectClient...")
            
            # Try different AIProjectClient constructor patterns for different versions
            try:
                # Try the newer constructor with additional parameters (if provided)
                if subscription_id and resource_group_name and project_name:
                    project_client = AIProjectClient(
                        endpoint=project_endpoint,
                        credential=get_azure_credential(),
                        subscription_id=subscription_id,
                        resource_group_name=resource_group_name,
                        project_name=project_name
                    )
                else:
                    # Fallback to the original constructor (should work with most versions)
                    project_client = AIProjectClient(
                        endpoint=project_endpoint,
                        credential=get_azure_credential(),
                    )
            except TypeError as type_error:
                # If that fails, try with just endpoint and credential
                print(f"   ⚠️  Trying alternative AIProjectClient constructor due to: {type_error}")
                try:
                    project_client = AIProjectClient(
                        endpoint=project_endpoint,
                        credential=get_azure_credential(),
                    )
                except Exception as fallback_error:
                    raise RuntimeError(f"Could not initialize AIProjectClient with any constructor pattern. Original error: {type_error}, Fallback error: {fallback_error}")
            
            with project_client:
                agents = project_client.agents.list_agents()
                # Convert agent objects to dictionary format with proper JSON serialization
                agent_list = []
                for agent in agents:
                    if hasattr(agent, 'model_dump'):
                        agent_dict = json.loads(json.dumps(agent.model_dump(), default=str))
                    else:
                        agent_dict = json.loads(json.dumps(dict(agent), default=str))
                    agent_list.append(agent_dict)
                return agent_list
        else:
            raise

def create_agent_version_via_api(agent_name: str, agent_version_data: Dict[str, Any], production_resource: Optional[str] = None, production_subscription: Optional[str] = None, production_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a v2 agent version using the v2 API endpoint.
    
    Args:
        agent_name: The agent name (without version)
        agent_version_data: The agent version payload matching v2 API format
        production_resource: Optional production resource name (e.g., "nextgen-eastus")
        production_subscription: Optional production subscription ID
        production_token: Optional production token for authentication
    
    Returns:
        API response data
    """
    # Build the v2 API endpoint URL based on mode (production vs local)
    # Ensure agent name is lowercase for API compliance
    agent_name = agent_name.lower()
    
    if production_resource and production_subscription:
        # Production mode: use Azure AI services endpoint format
        base_url = get_production_v2_base_url(production_resource, production_subscription, production_resource)
        url = f"{base_url}/agents/{agent_name}/versions"
        print(f"🏭 Using PRODUCTION endpoint")
    else:
        # Local development mode: use the existing BASE_V2 format
        if BASE_V2 is None:
            # Fallback to local development URL if not set
            local_base = f"https://{LOCAL_HOST}/agents/v2.0/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{RESOURCE_GROUP_V2}/providers/Microsoft.MachineLearningServices/workspaces/{WORKSPACE_V2}"
            url = f"{local_base}/agents/{agent_name}/versions"
        else:
            url = f"{BASE_V2}/agents/{agent_name}/versions"
        print(f"🏠 Using LOCAL development endpoint")
    
    params = {"api-version": API_VERSION}
    
    print(f"🌐 Creating agent version via v2 API:")
    print(f"   URL: {url}")
    print(f"   Agent Name: {agent_name}")
    print(f"   API Version: {API_VERSION}")
    print(f"   Full params: {params}")
    
    # Debug: Show the actual request body
    print(f"🔍 Request Body Debug:")
    print(f"   Type: {type(agent_version_data)}")
    print(f"   Keys: {list(agent_version_data.keys()) if isinstance(agent_version_data, dict) else 'Not a dict'}")
    if isinstance(agent_version_data, dict):
        import json
        print(f"   Full JSON payload:")
        print(json.dumps(agent_version_data, indent=2, default=str)[:2000] + "..." if len(str(agent_version_data)) > 2000 else json.dumps(agent_version_data, indent=2, default=str))
    
    try:
        # Make the POST request to create the agent version with appropriate token
        # Use production token from environment if available and production resource is specified
        if production_resource and PRODUCTION_TOKEN:
            print(f"   🔑 Using production token for authentication")
            response = do_api_request_with_token("POST", url, PRODUCTION_TOKEN, params=params, json=agent_version_data)
        else:
            print(f"   🔑 Using standard token for authentication")
            response = do_api_request("POST", url, params=params, json=agent_version_data)
        result = response.json()
        
        print(f"✅ Successfully created agent version via v2 API")
        print(f"   Response ID: {result.get('id', 'N/A')}")
        
        return result
        
    except requests.exceptions.HTTPError as e:
        print(f"❌ Failed to create agent version via v2 API: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"🔍 Response Status Code: {e.response.status_code}")
            try:
                error_response = e.response.json()
                print(f"🔍 Error Response JSON:")
                import json
                print(json.dumps(error_response, indent=2))
            except:
                print(f"🔍 Error Response Text: {e.response.text[:1000]}")
        raise
    except Exception as e:
        print(f"❌ Failed to create agent version via v2 API: {e}")
        raise

def prepare_v2_api_payload(v2_agent_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare the payload for v2 API from our transformed agent data.
    Converts our internal format to the v2 API expected format and includes flattened migration metadata.
    All metadata values are converted to strings as required by the API.
    """
    agent_version = v2_agent_data['v2_agent_version']
    migration_notes = v2_agent_data['migration_notes']
    
    # Start with the existing metadata and enhance it with migration info
    enhanced_metadata = agent_version.get("metadata", {}).copy()
    
    # Convert any existing metadata values to strings
    string_metadata = {}
    for key, value in enhanced_metadata.items():
        if key == "feature_flags" and isinstance(value, dict):
            # Convert feature flags to comma-separated string
            flag_list = [f"{k}={v}" for k, v in value.items()]
            string_metadata[key] = ",".join(flag_list)
        elif isinstance(value, (dict, list)):
            # Convert complex objects to JSON strings
            string_metadata[key] = json.dumps(value)
        else:
            # Convert everything else to string
            string_metadata[key] = str(value) if value is not None else ""
    
    # Add flattened migration information to metadata (all as strings)
    current_timestamp = int(time.time() * 1000)  # Milliseconds
    string_metadata.update({
        "migrated_from": "v1_assistant_via_api_migration_script",  # Combined migration_source and migrated_from
        "migration_timestamp": str(current_timestamp),
        "original_v1_id": str(migration_notes['original_v1_id']),
        "new_v2_format": str(migration_notes['new_v2_format']),
        "migration_changes": ",".join(migration_notes['changes'])
        # Removed migrated_at as requested
    })
    
    # Extract the core fields that the v2 API expects
    api_payload = {
        "description": agent_version.get("description"),
        "metadata": string_metadata,
        "definition": agent_version.get("definition", {})
    }
    
    # Remove None values to keep payload clean
    api_payload = {k: v for k, v in api_payload.items() if v is not None}
    
    print(f"🔧 Prepared v2 API payload:")
    print(f"   Description: {api_payload.get('description', 'N/A')}")
    print(f"   Metadata keys: {list(api_payload.get('metadata', {}).keys())}")
    print(f"   Definition kind: {api_payload.get('definition', {}).get('kind', 'N/A')}")
    print(f"   Migration info: Original v1 ID = {migration_notes['original_v1_id']}")
    print(f"   All metadata values converted to strings")
    
    return api_payload

def determine_agent_kind(v1_assistant: Dict[str, Any]) -> str:
    """
    Determine the appropriate v2 agent kind based on v1 assistant properties.
    
    Possible v2 kinds:
    - "prompt": Standard conversational agent (default)
    - "hosted": Hosted external service
    - "container_app": Container-based agent
    - "workflow": Multi-step workflow agent
    """
    # For now, all assistants will be migrated as "prompt" agents
    # Uncomment the detection logic below if you need to differentiate agent kinds in the future
    
    # # Check for workflow indicators
    # tools = v1_assistant.get("tools", [])
    # if any(tool.get("type") == "function" for tool in tools if isinstance(tool, dict)):
    #     # If it has function tools, it might be a workflow
    #     if len(tools) > 3:  # Arbitrary threshold for complex workflows
    #         return "workflow"
    # 
    # # Check for hosted service indicators
    # metadata = v1_assistant.get("metadata", {})
    # if metadata.get("service_type") == "hosted" or metadata.get("external_service"):
    #     return "hosted"
    # 
    # # Check for container indicators
    # if metadata.get("deployment_type") == "container" or metadata.get("container_image"):
    #     return "container_app"
    
    # Default to prompt agent for all assistants (test assumption: all are prompt agents)
    return "prompt"

def v1_assistant_to_v2_agent(v1_assistant: Dict[str, Any], agent_name: Optional[str] = None, version: str = "1") -> Dict[str, Any]:
    """
    Transform a v1 assistant object to v2 agent structure.
    Based on the migration document mapping from v1 Agent to v2 AgentObject + AgentVersionObject.
    """
    # Validate tools - check for unsupported tool types
    v1_tools = v1_assistant.get("tools", [])
    
    # Handle string-encoded tools (from project client serialization)
    if isinstance(v1_tools, str):
        try:
            v1_tools = json.loads(v1_tools)
        except json.JSONDecodeError:
            print(f"   ⚠️  Warning: Could not parse tools string: {v1_tools}")
            v1_tools = []
    
    # Ensure v1_tools is a list
    if not isinstance(v1_tools, list):
        v1_tools = []
    
    # Check for unsupported tool types and log warnings
    assistant_id = v1_assistant.get("id", "unknown")
    assistant_name = v1_assistant.get("name", "unknown")
    unsupported_tools = []
    
    for tool in v1_tools:
        if not isinstance(tool, dict):
            continue
            
        tool_type = tool.get("type")
        
        if tool_type == "connected_agent":
            unsupported_tools.append(tool_type)
            print(f"   ⚠️  WARNING: Your classic agent includes connected agents, which aren't supported in the new experience.")
            print(f"   ℹ️  These connected agents won't be carried over when you create the new agent.")
            print(f"   💡 To orchestrate multiple agents, use a workflow instead.")
        elif tool_type == "event_binding":
            unsupported_tools.append(tool_type)
            print(f"   ⚠️  WARNING: Your classic agent uses 'event_binding' which isn't supported in the new experience.")
            print(f"   ℹ️  This tool won't be carried over when you create the new agent.")
        elif tool_type == "output_binding":
            unsupported_tools.append(tool_type)
            print(f"   ⚠️  WARNING: Your classic agent uses 'output_binding' which isn't supported in the new experience.")
            print(f"   ℹ️  This tool won't be carried over when you create the new agent.")
            print(f"   💡 Consider using 'capture_structured_outputs' in your new agent instead.")
    
    if unsupported_tools:
        print(f"   📋 Unsupported tools that will be skipped: {', '.join(unsupported_tools)}")
    
    # Derive agent name if not provided
    if not agent_name:
        agent_name = v1_assistant.get("name") or f"agent_{v1_assistant.get('id', 'unknown')}"
    
    # Determine the appropriate agent kind
    agent_kind = determine_agent_kind(v1_assistant)
    
    # Extract and preserve feature flags from v1 data
    v1_metadata = v1_assistant.get("metadata", {})
    
    # Ensure v1_metadata is a dictionary (defensive programming)
    if not isinstance(v1_metadata, dict):
        print(f"   ⚠️  Warning: metadata is not a dict (type: {type(v1_metadata)}), using empty dict")
        v1_metadata = {}
    
    feature_flags = {}
    
    # Look for feature flags in various locations
    if isinstance(v1_metadata, dict) and "feature_flags" in v1_metadata:
        potential_flags = v1_metadata.get("feature_flags", {})
        if isinstance(potential_flags, dict):
            feature_flags = potential_flags
    elif "internal_metadata" in v1_assistant and isinstance(v1_assistant["internal_metadata"], dict):
        potential_flags = v1_assistant["internal_metadata"].get("feature_flags", {})
        if isinstance(potential_flags, dict):
            feature_flags = potential_flags
    
    # Build enhanced metadata for v2 that includes feature flags
    enhanced_metadata = v1_metadata.copy() if isinstance(v1_metadata, dict) else {}
    if feature_flags and isinstance(feature_flags, dict):
        enhanced_metadata["feature_flags"] = feature_flags
        print(f"   🚩 Preserving {len(feature_flags)} feature flags: {list(feature_flags.keys())}")
    
    # Create the v2 AgentObject (metadata level)
    agent_object = {
        "object": "agent",  # Changed from "assistant" to "agent"
        "id": f"{agent_name}:{version}",  # New format: {name}:{version}
        "name": agent_name,
        "labels": []  # New: Label associations (empty for now)
    }

     # Transform tools and merge with tool_resources
    # Note: v1_tools already validated and parsed above during connected_agent check
    v1_tool_resources = v1_assistant.get("tool_resources", {})

    # Handle string-encoded tool_resources (from project client serialization)
    if isinstance(v1_tool_resources, str):
        try:
            v1_tool_resources = json.loads(v1_tool_resources)
        except json.JSONDecodeError:
            # Try eval as fallback for string representations
            try:
                v1_tool_resources = eval(v1_tool_resources) if v1_tool_resources.strip().startswith('{') else {}
            except:
                print(f"   ⚠️  Could not parse tool_resources string: {v1_tool_resources}")
                v1_tool_resources = {}
    
    # Ensure v1_tool_resources is a dict
    if not isinstance(v1_tool_resources, dict):
        v1_tool_resources = {}

    # DEBUG: Print the actual tools and tool_resources structure
    print(f"🔧 DEBUG - Tools transformation:")
    print(f"   v1_tools: {v1_tools}")
    print(f"   v1_tools type: {type(v1_tools)}")
    print(f"   v1_tool_resources: {v1_tool_resources}")
    print(f"   v1_tool_resources type: {type(v1_tool_resources)}")
       
    # Transform tools to v2 format by merging with tool_resources
    transformed_tools = []
    for i, tool in enumerate(v1_tools):
        print(f"   Processing tool {i}: {tool} (type: {type(tool)})")
        # Handle string-encoded individual tools
        if isinstance(tool, str):
            try:
                tool = json.loads(tool)
            except json.JSONDecodeError:
                try:
                    tool = eval(tool) if tool.strip().startswith('{') else {}
                except:
                    print(f"     ⚠️  Could not parse tool string: {tool}")
                    continue
        
        if isinstance(tool, dict):
            tool_type = tool.get("type")
            
            # Skip unsupported tools
            if tool_type in ["connected_agent", "event_binding", "output_binding"]:
                print(f"     ⏭️  Skipping unsupported tool type: {tool_type}")
                continue
            transformed_tool = {"type": tool_type}
            
            # Handle file_search tool
            if tool_type == "file_search" and "file_search" in v1_tool_resources:
                file_search_resources = v1_tool_resources["file_search"]
                print(f"     Found file_search resources: {file_search_resources}")
                if "vector_store_ids" in file_search_resources:
                    transformed_tool["vector_store_ids"] = file_search_resources["vector_store_ids"]
                    print(f"     Added vector_store_ids: {file_search_resources['vector_store_ids']}")
            
            # Handle code_interpreter tool
            elif tool_type == "code_interpreter" and "code_interpreter" in v1_tool_resources:
                code_resources = v1_tool_resources["code_interpreter"]
                print(f"     Found code_interpreter resources: {code_resources}")
                if "file_ids" in code_resources:
                    # Add container with auto type and file_ids for v2 format
                    transformed_tool["container"] = {
                        "type": "auto",
                        "file_ids": code_resources["file_ids"]
                    }
                    print(f"     Added container with auto type and file_ids: {code_resources['file_ids']}")
                else:
                    # If no file_ids, still add container with auto type
                    transformed_tool["container"] = {"type": "auto"}
                    print(f"     Added container with auto type (no file_ids)")
            
            # Handle code_interpreter tool without resources
            elif tool_type == "code_interpreter":
                # If no tool_resources, still add container with auto type
                transformed_tool["container"] = {"type": "auto"}
                print(f"     Added container with auto type (no resources)")
            
            # Handle function tools (no resources typically)
            elif tool_type == "function":
                # Copy function definition if present
                if "function" in tool:
                    transformed_tool["function"] = tool["function"]
            
            # Handle MCP tools
            elif tool_type == "mcp":
                # Copy all MCP-specific properties that actually exist (don't copy None/null values)
                for key in ["server_label", "server_description", "server_url", "require_approval", "project_connection_id"]:
                    if key in tool and tool[key] is not None:
                        transformed_tool[key] = tool[key]
                print(f"     Added MCP tool properties: {[k for k in tool.keys() if k != 'type' and tool[k] is not None]}")
            
            # Handle computer_use_preview tools
            elif tool_type == "computer_use_preview":
                # Copy all computer use specific properties
                for key in ["display_width", "display_height", "environment"]:
                    if key in tool:
                        transformed_tool[key] = tool[key]
                print(f"     Added computer use tool properties: {[k for k in tool.keys() if k != 'type']}")
            
            # Handle image_generation tools
            elif tool_type == "image_generation":
                # Copy any image generation specific properties (currently none, but future-proof)
                for key, value in tool.items():
                    if key != "type":
                        transformed_tool[key] = value
                print(f"     Added image generation tool properties: {[k for k in tool.keys() if k != 'type']}")
            
            # Handle azure_function tools
            elif tool_type == "azure_function":
                # Copy all azure function specific properties
                for key in ["name", "description", "parameters", "input_queue", "output_queue"]:
                    if key in tool:
                        transformed_tool[key] = tool[key]
                print(f"     Added Azure Function tool properties: {[k for k in tool.keys() if k != 'type']}")
            
            # Handle any other tool types by copying all properties except 'type'
            else:
                for key, value in tool.items():
                    if key != "type":
                        transformed_tool[key] = value
                print(f"     Added generic tool properties for {tool_type}: {[k for k in tool.keys() if k != 'type']}")
            
            transformed_tools.append(transformed_tool)

        print(f"   Final transformed_tools: {transformed_tools}")
        print(f"   Transformed tools count: {len(transformed_tools)}")
    
    # Create the v2 AgentVersionObject (definition level)
    agent_version = {
        "object": "agent.version",  # New object type
        "id": f"{agent_name}:{version}",
        "name": agent_name,
        "version": version,
        "created_at": v1_assistant.get("created_at"),
        "description": v1_assistant.get("description"),
        "metadata": enhanced_metadata,  # Use enhanced metadata with feature flags
        "labels": [],  # Associated labels for this version
        "status": "active",  # New: Agent status tracking
        "definition": {
            "kind": agent_kind,  # Dynamically determined based on v1 assistant properties
            "model": v1_assistant.get("model"),
            "instructions": v1_assistant.get("instructions"),
            "tools": transformed_tools,  # Use transformed tools with embedded resources
            "temperature": v1_assistant.get("temperature"),
            "top_p": v1_assistant.get("top_p"),
            "response_format": v1_assistant.get("response_format")
        }
    }
    
    # Handle tool_resources - this is a breaking change in v2
    # if "tool_resources" in v1_assistant:
    #     agent_version["definition"]["tool_resources_legacy"] = v1_assistant["tool_resources"]
    
    # Remove None values from definition to keep it clean
    definition = agent_version["definition"]
    agent_version["definition"] = {k: v for k, v in definition.items() if v is not None}
    
    return {
        "v2_agent_object": agent_object,
        "v2_agent_version": agent_version,
        "migration_notes": {
            "original_v1_id": v1_assistant.get("id"),
            "new_v2_format": f"{agent_name}:{version}",
            "migrated_at": int(time.time()),
            "changes": [
                "Object type changed from 'assistant' to 'agent'",
                "ID format changed to name:version",
                "Definition fields moved to nested definition object",
                "Tool resources structure changed (stored as legacy)",
                "Added versioning and labeling support"
            ]
        }
    }

def save_v2_agent_to_cosmos(v2_agent_data: Dict[str, Any], connection_string: str, database_name: str, container_name: str, project_id: Optional[str] = None, feature_flags: Optional[Dict[str, Any]] = None):
    """
    Save the v2 agent data to Cosmos DB with proper partition key structure.
    Matches existing container format with composite partition key: /object.project_id, /object.agent_name
    """
    client = create_cosmos_client_from_connection_string(connection_string)
    
    # Don't create container - use existing one with composite partition key
    database = client.get_database_client(database_name)
    container = database.get_container_client(container_name)
    
    # Use default project_id if not provided (matching existing data format)
    if not project_id:
        project_id = "e2e-tests-westus2-account@e2e-tests-westus2@AML"  # Default from example
    
    # Get agent info - restore colon format to match existing data
    agent_name = v2_agent_data['v2_agent_object']['name']
    version = v2_agent_data['v2_agent_version']['version']
    agent_id_with_version = f"{agent_name}:{version}"
    
    # Create AgentVersionObject document matching existing format
    v2_data = v2_agent_data['v2_agent_version'].copy()  # Make a copy to avoid modifying original
    
    # Build the object structure with all fields including object_type
    object_structure = {
        "id": agent_id_with_version,  # ID inside object
        "metadata": v2_data.get("metadata", {}),  # Original agent metadata (without v1 ID)
        "description": v2_data.get("description"),
        "definition": v2_data.get("definition"),
        "agent_name": agent_name,   # Required for partition key
        "version": v2_data.get("version"),
        "project_id": project_id,  # Required for partition key
        "object_type": "agent.version"  # object_type inside object
    }
    
    # Build the document with object containing all data
    current_timestamp = int(time.time() * 1000)  # Milliseconds like in example
    agent_version_doc = {
        "id": agent_id_with_version,  # Top-level ID for document
        "info": {
            "created_at": current_timestamp,
            "updated_at": current_timestamp,
            "deleted": False
        },
        "metadata": {
            "migration_info": {
                "migrated_from": "v1_assistant_via_api_migration_script",  # Combined source info
                "migration_timestamp": current_timestamp,
                "original_v1_id": v2_agent_data['migration_notes']['original_v1_id'],
                "has_feature_flags": bool(feature_flags) if feature_flags else False,
                "feature_flag_count": len(feature_flags) if feature_flags else 0,
                "feature_flags": feature_flags if feature_flags else {}
            }
        },  # Document-level metadata with migration info
        "object": object_structure,  # All data inside object
        "migrated_at": int(time.time())  # Keep our migration timestamp too
    }
    
    print(f"🔍 Document structure for partition key:")
    print(f"   - id: {agent_version_doc['id']}")
    print(f"   - object: {agent_version_doc['object']}")
    print(f"   - object type: {type(agent_version_doc['object'])}")
    if isinstance(agent_version_doc['object'], dict):
        print(f"   - object.project_id: {agent_version_doc['object']['project_id']}")
        print(f"   - object.agent_name: {agent_version_doc['object']['agent_name']}")
        print(f"   - object.object_type: {agent_version_doc['object']['object_type']}")
    else:
        print(f"   ❌ ERROR: 'object' field is not a dict: {agent_version_doc['object']}")
    
    # Also save migration metadata (optional)
    migration_timestamp = int(time.time() * 1000)  # Milliseconds like in example
    migration_doc = {
        "id": f"migration_{v2_agent_data['migration_notes']['original_v1_id']}",
        "info": {
            "created_at": migration_timestamp,
            "updated_at": migration_timestamp,
            "deleted": False
        },
        "metadata": {},  # Empty metadata object at same level as object
        "object": {
            "project_id": project_id,
            "agent_name": f"migration_{agent_name}",
            "object_type": "migration_metadata",  # object_type inside object
            "original_v1_id": v2_agent_data['migration_notes']['original_v1_id'],
            "new_v2_format": v2_agent_data['migration_notes']['new_v2_format'],
            "migrated_at": int(time.time()),
            "data": v2_agent_data['migration_notes']
        }
    }
    
    try:
        # Debug: Print document IDs and partition key values
        print(f"🔍 Attempting to save documents:")
        print(f"   - Agent Version ID: {agent_version_doc['id']}")
        print(f"   - Migration ID: {migration_doc['id']}")
        
        # Save documents one by one with error handling
        print("   - Saving Agent Version (main document)...")
        agent_version_result = container.upsert_item(agent_version_doc)
        print("   ✅ Agent Version saved")
        
        print("   - Saving Migration Metadata...")
        migration_result = container.upsert_item(migration_doc)
        print("   ✅ Migration Metadata saved")
        
        print(f"✅ Successfully saved v2 agent '{v2_agent_data['v2_agent_object']['name']}' to Cosmos DB")
        print(f"   - Agent Version: {agent_version_doc['id']}")
        print(f"   - Migration Metadata: {migration_doc['id']}")
        
        return {
            "agent_version": agent_version_result,
            "migration": migration_result
        }
    except Exception as e:
        print(f"❌ Failed to save v2 agent to Cosmos DB: {e}")
        print(f"❌ Error type: {type(e)}")
        print(f"❌ Document that failed:")
        print(f"   Agent Version Doc: {agent_version_doc}")
        print(f"   Migration Doc: {migration_doc}")
        raise

def process_v1_assistants_to_v2_agents(args=None, assistant_id: Optional[str] = None, cosmos_connection_string: Optional[str] = None, use_api: bool = False, project_endpoint: Optional[str] = None, project_connection_string: Optional[str] = None, project_subscription: Optional[str] = None, project_resource_group: Optional[str] = None, project_name: Optional[str] = None, production_resource: Optional[str] = None, production_subscription: Optional[str] = None, production_tenant: Optional[str] = None, source_tenant: Optional[str] = None):
    """
    Main processing function that reads v1 assistants from Cosmos DB, API, Project endpoint, or Project connection string,
    converts them to v2 agents, and saves via v2 API.
    
    Args:
        assistant_id: Optional specific assistant ID to migrate (if not provided, migrates all)
        cosmos_connection_string: Optional Cosmos connection string (if not provided, uses environment variable)
        use_api: If True, read v1 assistants from API instead of Cosmos DB
        project_endpoint: Optional project endpoint for AIProjectClient (e.g., "https://...api/projects/p-3")
        project_connection_string: Optional project connection string for AIProjectClient (e.g., "eastus.api.azureml.ms;...;...;...")
        source_tenant: Optional source tenant ID for authentication when reading v1 assistants
    """
    
    # Handle package version management based on usage
    need_beta_version = os.environ.get('NEED_BETA_VERSION') == 'true' or project_connection_string is not None
    
    if need_beta_version:
        print("🔧 Project connection string detected - ensuring beta version is installed...")
        if not ensure_project_connection_package():
            print("❌ Failed to install required beta version")
            sys.exit(1)
    if project_connection_string:
        print(f"🏢 Reading v1 assistants from Project Connection String")
        if not PROJECT_CLIENT_AVAILABLE:
            print("❌ Error: azure-ai-projects package is required for project connection string functionality")
            print("Install with: pip install azure-ai-projects==1.0.0b10")
            sys.exit(1)
        
        # Get assistants from Project Client using connection string
        if assistant_id:
            print(f"🎯 Fetching specific assistant from project connection: {assistant_id}")
            try:
                assistant_data = get_assistant_from_project_connection(project_connection_string, assistant_id)
                v1_assistants = [assistant_data]
            except Exception as e:
                print(f"❌ Failed to fetch assistant {assistant_id} from project connection: {e}")
                return
        else:
            print("📊 Fetching all assistants from project connection")
            try:
                v1_assistants = list_assistants_from_project_connection(project_connection_string)
            except Exception as e:
                print(f"❌ Failed to fetch assistants from project connection: {e}")
                return
        
        if not v1_assistants:
            print("❌ No v1 assistants found from project connection")
            return
        
        print(f"📊 Found {len(v1_assistants)} v1 assistant records from project connection")
        
    elif project_endpoint:
        print(f"🏢 Reading v1 assistants from Project Endpoint: {project_endpoint}")
        if not PROJECT_CLIENT_AVAILABLE:
            print("❌ Error: azure-ai-projects package is required for project endpoint functionality")
            print("Install with: pip install azure-ai-projects")
            sys.exit(1)
        
        # Get assistants from Project Client
        if assistant_id:
            print(f"🎯 Fetching specific assistant from project: {assistant_id}")
            try:
                assistant_data = get_assistant_from_project(project_endpoint, assistant_id, project_subscription, project_resource_group, project_name)
                v1_assistants = [assistant_data]
            except Exception as e:
                print(f"❌ Failed to fetch assistant {assistant_id} from project: {e}")
                return
        else:
            print("📊 Fetching all assistants from project")
            try:
                v1_assistants = list_assistants_from_project(project_endpoint, project_subscription, project_resource_group, project_name)
            except Exception as e:
                print(f"❌ Failed to fetch assistants from project: {e}")
                return
        
        if not v1_assistants:
            print("❌ No v1 assistants found from project")
            return
        
        print(f"📊 Found {len(v1_assistants)} v1 assistant records from project")
        
    elif use_api:
        print("🌐 Reading v1 assistants from API")
        # Ensure we have API authentication
        if not TOKEN and not set_api_token():
            print("❌ Error: Unable to obtain API authentication token")
            print("Set AZ_TOKEN env var or ensure az CLI is installed and logged in")
            sys.exit(1)
        
        # Get assistants from API
        if assistant_id:
            print(f"🎯 Fetching specific assistant from API: {assistant_id}")
            try:
                assistant_data = get_assistant_from_api(assistant_id)
                v1_assistants = [assistant_data]
            except Exception as e:
                print(f"❌ Failed to fetch assistant {assistant_id} from API: {e}")
                return
        else:
            print("📊 Fetching all assistants from API")
            try:
                v1_assistants = list_assistants_from_api()
            except Exception as e:
                print(f"❌ Failed to fetch assistants from API: {e}")
                return
        
        if not v1_assistants:
            print("❌ No v1 assistants found from API")
            return
        
        print(f"📊 Found {len(v1_assistants)} v1 assistant records from API")
        
    else:
        print(f"📖 Reading v1 assistants from Cosmos DB: {DATABASE_NAME}/{SOURCE_CONTAINER}")
        # Use provided connection string or fall back to environment variable
        connection_string = cosmos_connection_string or COSMOS_CONNECTION_STRING
        
        if not connection_string:
            print("Error: COSMOS_CONNECTION_STRING environment variable must be set or provided as parameter")
            print("Set it with: $env:COSMOS_CONNECTION_STRING='AccountEndpoint=...;AccountKey=...'")
            print("Or provide it as command line argument: python v1_to_v2_migration.py <assistant_id> <cosmos_connection_string>")
            sys.exit(1)
        
        # Build query - filter by assistant_id if provided
        if assistant_id:
            query = f"SELECT * FROM c WHERE c.object_type = 'v1_assistant' AND c.data.id = '{assistant_id}'"
            print(f"🎯 Filtering for specific assistant ID: {assistant_id}")
        else:
            query = "SELECT * FROM c WHERE c.object_type = 'v1_assistant'"
            print("📊 Processing all v1 assistants")
        
        # Read v1 assistant data from source container
        v1_data = fetch_data(
            database_name=DATABASE_NAME,
            container_name=SOURCE_CONTAINER,
            connection_string=connection_string,
            query=query
        )
        
        if v1_data is None or v1_data.empty:
            print("❌ No v1 assistant data found in source container")
            return
        
        print(f"📊 Found {len(v1_data)} v1 assistant records from Cosmos DB")
        
        # Convert pandas DataFrame to list for uniform processing
        v1_assistants = []
        for idx, (index, row) in enumerate(v1_data.iterrows()):
            # Process Cosmos DB row format (same logic as before)
            v1_assistant = {}
            
            # Check if we have flattened 'data.*' columns
            data_columns = [col for col in row.keys() if col.startswith('data.')]
            
            if data_columns:
                # Reconstruct nested structure
                for col in data_columns:
                    field_name = col[5:]  # Remove 'data.' (5 characters)
                    value = row[col]
                    
                    # Handle nested fields like 'internal_metadata.feature_flags'
                    if '.' in field_name:
                        parts = field_name.split('.')
                        current = v1_assistant
                        for part in parts[:-1]:
                            if part not in current:
                                current[part] = {}
                            current = current[part]
                        current[parts[-1]] = value
                    else:
                        v1_assistant[field_name] = value
                        
            elif 'data' in row and row['data'] is not None:
                raw_data = row['data']
                if isinstance(raw_data, str):
                    v1_assistant = json.loads(raw_data)
                elif isinstance(raw_data, dict):
                    v1_assistant = raw_data
                else:
                    continue
            else:
                continue
            
            # Clean up None values
            v1_assistant = {k: v for k, v in v1_assistant.items() if v is not None}
            v1_assistants.append(v1_assistant)
    
    # Ensure we have API authentication for v2 API saving
    # Use source tenant for authentication (for reading v1 assistants)
    # Force refresh if we have production resource (might have switched tenants)
    force_refresh = production_resource is not None
    tenant_for_auth = source_tenant if source_tenant else SOURCE_TENANT
    if not TOKEN and not set_api_token(force_refresh=force_refresh, tenant_id=tenant_for_auth):
        print("❌ Error: Unable to obtain API authentication token for v2 API saving")
        print("Set AZ_TOKEN env var or ensure az CLI is installed and logged in")
        sys.exit(1)
    
    # Now we have uniform v1_assistants list regardless of source
    # Process each v1 assistant
    processed_count = 0
    for idx, v1_assistant in enumerate(v1_assistants):
        try:
            print(f"\n🔄 Processing record {idx + 1}/{len(v1_assistants)}")
            
            if project_connection_string:
                print(f"   ✅ Processing Project Connection data for assistant: {v1_assistant.get('id', 'unknown')}")
            elif project_endpoint:
                print(f"   ✅ Processing Project Endpoint data for assistant: {v1_assistant.get('id', 'unknown')}")
            elif use_api:
                print(f"   ✅ Processing API data for assistant: {v1_assistant.get('id', 'unknown')}")
            else:
                print(f"   ✅ Processing Cosmos DB data for assistant: {v1_assistant.get('id', 'unknown')}")
            
            # Clean up None values
            v1_assistant = {k: v for k, v in v1_assistant.items() if v is not None}
            
            # Helper function to ensure tools array exists and is properly formatted
            def ensure_tools_array():
                if "tools" not in v1_assistant:
                    v1_assistant["tools"] = []
                elif isinstance(v1_assistant["tools"], str):
                    # Handle string-encoded tools
                    try:
                        v1_assistant["tools"] = json.loads(v1_assistant["tools"])
                    except:
                        v1_assistant["tools"] = []
                
                # Ensure tools is a list
                if not isinstance(v1_assistant["tools"], list):
                    v1_assistant["tools"] = []
            
            # Add test tools if requested
            if args:
                # Add test function tool
                if hasattr(args, 'add_test_function') and args.add_test_function:
                    print("🧪 Adding test function tool for testing...")
                    test_function_tool = {
                        "type": "function",
                        "function": {
                            "name": "get_current_temperature",
                            "description": "Get the current temperature for a specific location",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "location": {
                                        "type": "string",
                                        "description": "The city and state, e.g., San Francisco, CA"
                                    },
                                    "unit": {
                                        "type": "string",
                                        "enum": ["Celsius", "Fahrenheit"],
                                        "description": "The temperature unit to use. Infer this from the user's location."
                                    }
                                },
                                "required": ["location", "unit"]
                            }
                        }
                    }
                    ensure_tools_array()
                    v1_assistant["tools"].append(test_function_tool)
                    print(f"   ✅ Added test function tool: {test_function_tool['function']['name']}")
                
                # Add test MCP tool
                if hasattr(args, 'add_test_mcp') and args.add_test_mcp:
                    print("🧪 Adding test MCP tool for testing...")
                    test_mcp_tool = {
                        "type": "mcp",
                        "server_label": "dmcp",
                        "server_description": "A Dungeons and Dragons MCP server to assist with dice rolling.",
                        "server_url": "https://dmcp-server.deno.dev/sse",
                        "require_approval": "never",
                    }
                    ensure_tools_array()
                    v1_assistant["tools"].append(test_mcp_tool)
                    print(f"   ✅ Added test MCP tool: {test_mcp_tool['server_label']}")
                
                # Add test image generation tool
                if hasattr(args, 'add_test_imagegen') and args.add_test_imagegen:
                    print("🧪 Adding test image generation tool for testing...")
                    test_imagegen_tool = {
                        "type": "image_generation"
                    }
                    ensure_tools_array()
                    v1_assistant["tools"].append(test_imagegen_tool)
                    print(f"   ✅ Added test image generation tool")
                
                # Add test computer use tool
                if hasattr(args, 'add_test_computer') and args.add_test_computer:
                    print("🧪 Adding test computer use tool for testing...")
                    test_computer_tool = {
                        "type": "computer_use_preview",
                        "display_width": 1024,
                        "display_height": 768,
                        "environment": "browser"  # other possible values: "mac", "windows", "ubuntu"
                    }
                    ensure_tools_array()
                    v1_assistant["tools"].append(test_computer_tool)
                    print(f"   ✅ Added test computer use tool: {test_computer_tool['environment']} environment")
                
                # Add test Azure Function tool
                if hasattr(args, 'add_test_azurefunction') and args.add_test_azurefunction:
                    print("🧪 Adding test Azure Function tool for testing...")
                    # Using your local Azurite instance
                    storage_service_endpoint = "https://127.0.0.1:8001"
                    test_azurefunction_tool = {
                        "type": "azure_function",
                        "name": "foo",
                        "description": "Get answers from the foo bot.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string", 
                                    "description": "The question to ask."
                                },
                                "outputqueueuri": {
                                    "type": "string", 
                                    "description": "The full output queue URI."
                                }
                            },
                            "required": ["query"]
                        },
                        "input_queue": {
                            "queue_name": "azure-function-foo-input",
                            "storage_service_endpoint": storage_service_endpoint
                        },
                        "output_queue": {
                            "queue_name": "azure-function-foo-output", 
                            "storage_service_endpoint": storage_service_endpoint
                        }
                    }
                    ensure_tools_array()
                    v1_assistant["tools"].append(test_azurefunction_tool)
                    print(f"   ✅ Added test Azure Function tool: {test_azurefunction_tool['name']} (using Azurite at {storage_service_endpoint})")
            
            # Pretty print the full v1 object for inspection
            print(f"\n📋 Full v1 Assistant Object:")
            print("=" * 60)
            import pprint
            pprint.pprint(v1_assistant, indent=2, width=80)
            print("=" * 60)
            
            assistant_id = v1_assistant.get('id', 'unknown')
            
            print(f"   Assistant ID: {assistant_id}")
            print(f"   Assistant Name: {v1_assistant.get('name', 'N/A')}")
            print(f"   Assistant Model: {v1_assistant.get('model', 'N/A')}")
            
            # Preview the detected agent kind
            detected_kind = determine_agent_kind(v1_assistant)
            print(f"   🔍 Detected Agent Kind: {detected_kind}")
            
            # Convert v1 to v2
            v2_agent = v1_assistant_to_v2_agent(v1_assistant)
            
            # Save to target container with proper project_id
            # You can customize this project_id as needed
            project_id = "e2e-tests-westus2-account@e2e-tests-westus2@AML"  # Match existing data format
            
            # Extract feature flags to pass to save function
            v1_metadata = v1_assistant.get("metadata", {})
            assistant_feature_flags = {}
            if "feature_flags" in v1_metadata:
                assistant_feature_flags = v1_metadata.get("feature_flags", {})
            elif "internal_metadata" in v1_assistant and isinstance(v1_assistant["internal_metadata"], dict):
                assistant_feature_flags = v1_assistant["internal_metadata"].get("feature_flags", {})
            
            # Save the v2 agent via v2 API
            print("🌐 Saving via v2 API...")
            # Extract agent name (without version) for the API endpoint
            agent_name = v2_agent['v2_agent_object']['name']
            
            # Prepare the payload for v2 API
            api_payload = prepare_v2_api_payload(v2_agent)
            
            # Create the agent version via v2 API
            # Production token is provided via environment variable
            if production_resource and not PRODUCTION_TOKEN:
                print(f"❌ Production resource specified but no PRODUCTION_TOKEN environment variable found. Skipping v2 API save.")
                print("💡 Use run-migration-docker-auth.ps1 for automatic dual-token authentication")
                continue
            
            api_result = create_agent_version_via_api(agent_name, api_payload, production_resource, production_subscription)
            print(f"✅ Agent version created via v2 API: {api_result.get('id', 'N/A')}")
            
            processed_count += 1
            
        except KeyError as ke:
            print(f"❌ KeyError processing record {idx + 1}: {ke}")
            print(f"   Assistant data keys: {list(v1_assistant.keys()) if v1_assistant else 'N/A'}")
            continue
        except json.JSONDecodeError as je:
            print(f"❌ JSON decode error processing record {idx + 1}: {je}")
            continue
        except Exception as e:
            print(f"❌ Error processing record {idx + 1}: {e}")
            print(f"   Error type: {type(e)}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"\n🎉 Migration completed!")
    print(f"   Total records processed: {processed_count}/{len(v1_assistants)}")
    if project_connection_string:
        print(f"   Source: Project Connection String")
    elif project_endpoint:
        print(f"   Source: Project Endpoint ({project_endpoint})")
    elif use_api:
        print(f"   Source: API ({HOST})")
    else:
        print(f"   Source: Cosmos DB ({DATABASE_NAME}/{SOURCE_CONTAINER})")
    
    # Always using v2 API
    print(f"   Target: v2 API ({BASE_V2})")

def main():
    """
    Main function to orchestrate the v1 to v2 migration.
    """
    parser = argparse.ArgumentParser(
        description="Migrate v1 OpenAI Assistants to v2 Azure ML Agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Migrate from v1 API to production v2 API (REQUIRED production parameters)
  python v1_to_v2_migration.py --use-api \\
    --source-tenant 72f988bf-86f1-41af-91ab-2d7cd011db47 \\
    --production-resource nextgen-eastus \\
    --production-subscription b1615458-c1ea-49bc-8526-cafc948d3c25 \\
    --production-tenant 33e577a9-b1b8-4126-87c0-673f197bf624 \\
    asst_wBMH6Khnqbo1J7W1G6w3p1rN
  
  # Migrate all assistants from Cosmos DB to production v2 API
  python v1_to_v2_migration.py \\
    --production-resource nextgen-eastus \\
    --production-subscription b1615458-c1ea-49bc-8526-cafc948d3c25 \\
    --production-tenant 33e577a9-b1b8-4126-87c0-673f197bf624
  
  # Migrate from project endpoint to production v2 API
  python v1_to_v2_migration.py \\
    --project-endpoint "https://your-project.api.azure.com/api/projects/p-3" \\
    --production-resource nextgen-eastus \\
    --production-subscription b1615458-c1ea-49bc-8526-cafc948d3c25 \\
    --production-tenant 33e577a9-b1b8-4126-87c0-673f197bf624 \\
    asst_abc123
  
  # Note: Use run-migration-docker-auth.ps1 for automatic dual-tenant authentication
  
  # Read from project connection string (requires azure-ai-projects==1.0.0b10)
  python v1_to_v2_migration.py --project-connection-string "eastus.api.azureml.ms;subscription-id;resource-group;project-name"
  python v1_to_v2_migration.py asst_abc123 --project-connection-string "eastus.api.azureml.ms;subscription-id;resource-group;project-name"
  
  # Production deployment: migrate to production Azure AI resource
  python v1_to_v2_migration.py --project-endpoint "https://source-project.api.azure.com/api/projects/p-3" --production-resource "nextgen-eastus" --production-subscription "b1615458-c1ea-49bc-8526-cafc948d3c25" --production-tenant "33e577a9-b1b8-4126-87c0-673f197bf624" asst_abc123
        """
    )
    
    parser.add_argument(
        'assistant_id', 
        nargs='?', 
        default=None,
        help='Optional: Specific assistant ID to migrate (e.g., asst_abc123). If not provided, migrates all assistants.'
    )
    
    parser.add_argument(
        'cosmos_endpoint', 
        nargs='?', 
        default=None,
        help='Optional: Cosmos DB connection string. If not provided, uses COSMOS_CONNECTION_STRING environment variable.'
    )
    
    parser.add_argument(
        '--use-api',
        action='store_true',
        help='Read v1 assistants from v1 API instead of Cosmos DB.'
    )
    
    parser.add_argument(
        '--project-endpoint',
        type=str,
        help='Project endpoint for AIProjectClient (e.g., "https://...api/projects/p-3"). If provided, reads assistants from project instead of API or Cosmos DB.'
    )
    
    parser.add_argument(
        '--project-subscription',
        type=str,
        help='Azure subscription ID for project endpoint (optional, only needed for certain azure-ai-projects versions).'
    )
    
    parser.add_argument(
        '--project-resource-group',
        type=str,
        help='Azure resource group name for project endpoint (optional, only needed for certain azure-ai-projects versions).'
    )
    
    parser.add_argument(
        '--project-name',
        type=str,
        help='Project name for project endpoint (optional, only needed for certain azure-ai-projects versions).'
    )
    
    parser.add_argument(
        '--project-connection-string',
        type=str,
        help='Project connection string for AIProjectClient (e.g., "eastus.api.azureml.ms;...;...;..."). Requires azure-ai-projects==1.0.0b10. If provided, reads assistants from project connection instead of other methods.'
    )
    
    parser.add_argument(
        '--add-test-function',
        action='store_true',
        help='Add a test function tool to the assistant for testing function tool transformation. Adds get_current_temperature function.'
    )
    
    parser.add_argument(
        '--add-test-mcp',
        action='store_true',
        help='Add a test MCP tool to the assistant for testing MCP tool transformation. Adds D&D dice rolling MCP server.'
    )
    
    parser.add_argument(
        '--add-test-imagegen',
        action='store_true',
        help='Add a test image generation tool to the assistant for testing image generation tool transformation.'
    )
    
    parser.add_argument(
        '--add-test-computer',
        action='store_true',
        help='Add a test computer use tool to the assistant for testing computer use tool transformation.'
    )
    
    parser.add_argument(
        '--add-test-azurefunction',
        action='store_true',
        help='Add a test Azure Function tool to the assistant for testing Azure Function tool transformation.'
    )
    
    # Production Resource Arguments (REQUIRED for v2 API)
    parser.add_argument(
        '--production-resource',
        type=str,
        required=True,
        help='Production Azure AI resource name (REQUIRED). Example: "nextgen-eastus"'
    )
    
    parser.add_argument(
        '--production-subscription', 
        type=str,
        required=True,
        help='Production subscription ID (REQUIRED). Example: "b1615458-c1ea-49bc-8526-cafc948d3c25"'
    )
    
    parser.add_argument(
        '--production-tenant',
        type=str,
        required=True,
        help='Production tenant ID for Azure authentication (REQUIRED). Example: "33e577a9-b1b8-4126-87c0-673f197bf624"'
    )
    
    parser.add_argument(
        '--source-tenant',
        type=str,
        help='Source tenant ID for reading v1 assistants. If not provided, uses SOURCE_TENANT environment variable or defaults to Microsoft tenant (72f988bf-86f1-41af-91ab-2d7cd011db47). Example: "72f988bf-86f1-41af-91ab-2d7cd011db47"'
    )
    
    args = parser.parse_args()
    
    # Handle empty string as None for assistant_id
    assistant_id = args.assistant_id if args.assistant_id and args.assistant_id.strip() else None
    cosmos_connection_string = args.cosmos_endpoint if args.cosmos_endpoint and args.cosmos_endpoint.strip() else None
    
    # Production arguments are now required, so no additional validation needed
    
    print("🚀 Starting v1 to v2 Agent Migration")
    print("=" * 50)
    
    # Production parameters are required
    print(f"🏭 Production v2 API Configuration:")
    print(f"   🎯 Resource: {args.production_resource}")
    print(f"   📋 Subscription: {args.production_subscription}")
    print(f"   🔐 Tenant: {args.production_tenant}")
    
    if PRODUCTION_TOKEN:
        print(f"   ✅ Production token available (length: {len(PRODUCTION_TOKEN)})")
    else:
        print("   ⚠️  No PRODUCTION_TOKEN environment variable found")
        print("   💡 Use run-migration-docker-auth.ps1 for automatic dual-token authentication")
    
    if assistant_id:
        print(f"🎯 Target Assistant ID: {assistant_id}")
    else:
        print("📊 Processing all assistants")
        
    if cosmos_connection_string:
        print("🔗 Using provided Cosmos connection string")
    else:
        print("🔗 Using COSMOS_CONNECTION_STRING environment variable")
    
    if args.project_connection_string:
        print(f"🏢 Reading assistants from Project Connection String")
    elif args.project_endpoint:
        print(f"🏢 Reading assistants from Project Endpoint: {args.project_endpoint}")
    elif args.use_api:
        print("🌐 Reading assistants from v1 API")
    else:
        print("💾 Reading assistants from Cosmos DB")
    
    # Always using v2 API (required)
    if args.production_resource:
        print(f"🏭 Saving agents via PRODUCTION v2 API (resource: {args.production_resource})")
        print(f"   📋 Production subscription: {args.production_subscription}")
    else:
        print("🚀 Saving agents via PROD v2 API")
    
    print("=" * 50)
    
    process_v1_assistants_to_v2_agents(
        args, assistant_id, cosmos_connection_string, args.use_api, 
        args.project_endpoint, args.project_connection_string, args.project_subscription, 
        args.project_resource_group, args.project_name, args.production_resource, 
        args.production_subscription, args.production_tenant, args.source_tenant
    )

if __name__ == "__main__":
    main()