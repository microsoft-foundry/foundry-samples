import os, sys, time, json, argparse, subprocess, requests, re
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from azure.cosmos import CosmosClient, exceptions
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
# Subscription / workspace defaults are intentionally unset so the script fails fast
# when required configuration is missing, rather than silently targeting the wrong
# Azure environment. Set the corresponding env vars or pass values via CLI flags.
SUBSCRIPTION_ID = os.getenv("AGENTS_SUBSCRIPTION") or None
RESOURCE_GROUP = os.getenv("AGENTS_RESOURCE_GROUP") or None
RESOURCE_GROUP_V2 = os.getenv("AGENTS_RESOURCE_GROUP_V2") or None
WORKSPACE = os.getenv("AGENTS_WORKSPACE") or None
WORKSPACE_V2 = os.getenv("AGENTS_WORKSPACE_V2") or None
API_VERSION = os.getenv("AGENTS_API_VERSION") or "2025-05-15-preview"
# SOURCE_API_VERSION is used when reading from legacy openai.azure.com endpoints.
# Legacy OpenAI-kind resources only support older API versions (e.g. 2024-05-01-preview),
# not the newer 2025-xx-xx-preview Azure ML / AIServices versions.
SOURCE_API_VERSION = os.getenv("SOURCE_API_VERSION") or None  # None = auto-detect per endpoint
TOKEN = os.getenv("AZ_TOKEN")
TOKEN_SCOPE = os.getenv("AZ_TOKEN_SCOPE") or None
OPENAI_COMPAT_TOKEN = os.getenv("OPENAI_COMPAT_TOKEN")
OPENAI_COMPAT_TOKEN_SCOPE = os.getenv("OPENAI_COMPAT_TOKEN_SCOPE") or None
LAST_LEGACY_OPENAI_QUERY_ERROR: Optional[str] = None

# Source Tenant Configuration (for reading v1 assistants from source tenant)
# Defaults to None; the Azure SDK will use the caller's default tenant unless overridden
# via the SOURCE_TENANT / AGENTS_TENANT environment variables or the --source-tenant flag.
SOURCE_TENANT = os.getenv("SOURCE_TENANT") or os.getenv("AGENTS_TENANT") or None

# Production Resource Configuration
PRODUCTION_RESOURCE = os.getenv("PRODUCTION_RESOURCE")  # e.g., "<your-resource-name>"
PRODUCTION_SUBSCRIPTION = os.getenv("PRODUCTION_SUBSCRIPTION")  # e.g., "<your-subscription-id>"
PRODUCTION_TENANT = os.getenv("PRODUCTION_TENANT")  # e.g., "<your-tenant-id>"
PRODUCTION_TOKEN = os.getenv("PRODUCTION_TOKEN")  # Production token from PowerShell script
PRODUCTION_ENDPOINT_OVERRIDE = os.getenv("PRODUCTION_ENDPOINT")  # Optional: full endpoint URL override

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
        resource_name: The Azure AI resource name (e.g., "<your-resource-name>")
        subscription_id: The subscription ID for production
        project_name: The project name (e.g., "<your-project-name>")
    
    Returns:
        The production v2 API base URL
    """
    # Production format: https://{resource}.services.ai.azure.com/api/projects/{project}/agents/{agent}/versions
    # Avoid double "-resource" suffix if the resource name already ends with it
    if resource_name.endswith("-resource"):
        hostname = f"{resource_name}.services.ai.azure.com"
    else:
        hostname = f"{resource_name}-resource.services.ai.azure.com"
    return f"https://{hostname}/api/projects/{project_name}"


def sanitize_agent_name(agent_name: str) -> str:
    """
    Normalize an agent name to the v2 API constraints.

    The v2 API accepts only lowercase alphanumerics and hyphens, with a
    maximum length of 63 characters.
    """
    normalized_name = (agent_name or "").lower().replace('_', '-')
    normalized_name = re.sub(r"[^a-z0-9-]", "-", normalized_name)
    normalized_name = re.sub(r"-+", "-", normalized_name).strip('-')
    normalized_name = normalized_name[:63].rstrip('-')
    return normalized_name or "agent"
def get_target_openai_endpoint(production_resource: Optional[str] = None, production_endpoint: Optional[str] = None) -> Optional[str]:
    """
    Derive the OpenAI-compatible endpoint (``*.openai.azure.com/openai``)
    for the target resource.  Kept for reference / fallback.
    """
    if production_endpoint:
        import re
        m = re.match(r"https://([^.]+)\.", production_endpoint)
        if m:
            return f"https://{m.group(1)}.openai.azure.com/openai"
    if production_resource:
        if production_resource.endswith("-resource"):
            hostname = production_resource
        else:
            hostname = f"{production_resource}-resource"
        return f"https://{hostname}.openai.azure.com/openai"
    return None


def _is_foundry_host(url: Optional[str]) -> bool:
    """
    Return True if *url*'s hostname is a Foundry project endpoint
    (``*.services.ai.azure.com``). Files/vector stores uploaded anywhere
    else (legacy ``*.openai.azure.com`` / ``*.cognitiveservices.azure.com``)
    are invisible to the Foundry agent runtime.
    """
    if not url:
        return False
    host = (urlparse(url).hostname or "").lower()
    return host == "services.ai.azure.com" or host.endswith(".services.ai.azure.com")


def get_target_foundry_endpoint(production_resource: Optional[str] = None, production_endpoint: Optional[str] = None) -> Optional[str]:
    """
    Return the Foundry endpoint for file uploads and vector-store creation.

    Files and vector stores **must** be created through the Foundry
    (``*.services.ai.azure.com``) endpoint so they live in the same
    namespace the Foundry agent runtime uses.  Resources created via the
    legacy OpenAI endpoint (``*.openai.azure.com``) are invisible to agents
    running in the Foundry portal.
    """
    if production_endpoint:
        # Already a Foundry URL — return it directly
        # e.g. "https://res-resource.services.ai.azure.com/api/projects/proj"
        return production_endpoint.rstrip('/')
    if production_resource:
        if production_resource.endswith("-resource"):
            hostname = production_resource
        else:
            hostname = f"{production_resource}-resource"
        # Default project name = resource name without the -resource suffix
        project = production_resource.replace("-resource", "") if production_resource.endswith("-resource") else production_resource
        return f"https://{hostname}.services.ai.azure.com/api/projects/{project}"
    return None


def _source_endpoint_as_dedupe_target(project_endpoint: Optional[str]) -> Optional[str]:
    """
    For an in-place upgrade (source project == target project), return the
    source *project_endpoint* normalized for use as the dedupe target, but only
    when it is a Foundry endpoint (``*.services.ai.azure.com``).

    Returns *None* for non-Foundry sources (Cosmos DB, the legacy v1 API, or an
    OpenAI-compatible endpoint), where no target can be inferred from the
    source and an explicit ``--production-*`` target is required.
    """
    if not project_endpoint:
        return None
    host = (urlparse(project_endpoint).hostname or "").lower()
    if host.endswith(".services.ai.azure.com"):
        return project_endpoint.rstrip('/')
    return None

# Production authentication is now handled by the PowerShell wrapper
# which generates both AZ_TOKEN and PRODUCTION_TOKEN environment variables

def _infer_scope_for_url(url: Optional[str]) -> str:
    """
    Pick the correct AAD audience based on the target endpoint URL.
    """
    if not url:
        return "https://ai.azure.com/.default"

    host = (urlparse(url).hostname or "").lower()
    if (
        host == "cognitiveservices.azure.com"
        or host.endswith(".cognitiveservices.azure.com")
        or host == "openai.azure.com"
        or host.endswith(".openai.azure.com")
    ):
        return "https://cognitiveservices.azure.com/.default"
    if host == "management.azure.com" or host.endswith(".management.azure.com"):
        return "https://management.azure.com/.default"
    return "https://ai.azure.com/.default"


def _get_env_token_for_url(url: str) -> Optional[str]:
    """
    Prefer explicit env-provided tokens so Docker behaves exactly like the
    working host PowerShell path.
    """
    host = (urlparse(url or "").hostname or "").lower()
    if (
        host == "cognitiveservices.azure.com"
        or host.endswith(".cognitiveservices.azure.com")
        or host == "openai.azure.com"
        or host.endswith(".openai.azure.com")
    ):
        return OPENAI_COMPAT_TOKEN or TOKEN
    return TOKEN


def get_token_from_az(tenant_id: Optional[str] = None, scope: Optional[str] = None) -> Optional[str]:
    """
    Runs the az CLI to get an access token for the requested resource scope.
    Returns the token string on success, or None on failure.
    
    Args:
        tenant_id: Optional tenant ID to authenticate with
        scope: Optional AAD scope to request
    """
    try:
        effective_scope = scope or "https://ai.azure.com/.default"
        cmd = [
            "az", "account", "get-access-token",
            "--scope", effective_scope,
            "--query", "accessToken",
            "-o", "tsv"
        ]
        
        # Add tenant parameter if provided
        if tenant_id:
            cmd.extend(["--tenant", tenant_id])
            print(f"🔐 Requesting token for tenant: {tenant_id}")
        print(f"   🔑 Requested token scope: {effective_scope}")
        
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

def set_api_token(force_refresh: bool = False, tenant_id: Optional[str] = None, scope: Optional[str] = None) -> bool:
    """
    Ensure we have a valid bearer token for API calls.
    Returns True if a token is set, False otherwise.
    
    Args:
        force_refresh: If True, ignore existing tokens and get a fresh one from az CLI
        tenant_id: Optional tenant ID to authenticate with (uses SOURCE_TENANT if not provided)
    """
    global TOKEN, TOKEN_SCOPE
    
    # If force refresh is requested, skip environment variable and get fresh token
    if not force_refresh:
        # Check environment variable first
        env_token = os.getenv("AZ_TOKEN")
        if env_token:
            TOKEN = env_token
            TOKEN_SCOPE = os.getenv("AZ_TOKEN_SCOPE") or scope or TOKEN_SCOPE
            return True
    
    # Use provided tenant or default to SOURCE_TENANT
    if tenant_id is None:
        tenant_id = SOURCE_TENANT
    
    # Try az CLI (either forced or as fallback) with tenant
    effective_scope = scope or "https://ai.azure.com/.default"
    token = get_token_from_az(tenant_id, effective_scope)
    if token:
        TOKEN = token
        TOKEN_SCOPE = effective_scope
        print(f"🔄 Token refreshed from az CLI for tenant: {tenant_id}")
        return True
    return False

# ─── RBAC / Auth error guidance ──────────────────────────────────────
RBAC_DOCS = (
    "📖 Foundry RBAC docs : https://learn.microsoft.com/azure/ai-foundry/concepts/rbac-ai-foundry\n"
    "📖 OpenAI RBAC docs  : https://learn.microsoft.com/azure/ai-services/openai/how-to/role-based-access-control"
)

def _print_rbac_guidance(status_code: int, url: str, method: str = "GET"):
    """
    Print actionable RBAC guidance when an API call returns 401 or 403.
    Inspects the URL and HTTP method to determine which role is needed.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    is_write = method.upper() in ("POST", "PUT", "PATCH", "DELETE")
    is_foundry = host == "services.ai.azure.com" or host.endswith(".services.ai.azure.com")
    is_openai  = host == "openai.azure.com" or host.endswith(".openai.azure.com")
    is_arm     = host == "management.azure.com" or host.endswith(".management.azure.com")
    is_files   = "/files" in path
    is_agents  = "/agents" in path
    is_assistants = "/assistants" in path

    print("")
    print("╔══════════════════════════════════════════════════════════════════════╗")
    if status_code == 401:
        print("║  🔐  401 UNAUTHORIZED — Your token was rejected.                   ║")
        print("║  Possible causes:                                                  ║")
        print("║    • Token expired — rerun  az login  and try again                ║")
        print("║    • Wrong tenant — check --source-tenant / --production-tenant    ║")
        print("║    • Token audience mismatch — scope should be                     ║")
        print("║      https://ai.azure.com/.default  (data plane)                   ║")
        print("║      https://management.azure.com/.default  (ARM only)             ║")
    elif status_code == 403:
        print("║  🚫  403 FORBIDDEN — Token valid but missing permissions.           ║")
        print("║  You need the following RBAC role(s) on the Azure resource:         ║")
        print("║                                                                    ║")
        if is_arm:
            print("║    Operation : ARM management (connections, resource info)         ║")
            print("║    Role      : Contributor  or  Cognitive Services Contributor     ║")
            print("║    Scope     : Resource / resource-group                           ║")
        elif is_files and is_write:
            print("║    Operation : Upload files to target                              ║")
            print("║    Role      : Foundry User  (dataActions: CognitiveServices/*)    ║")
            print("║    Scope     : Foundry resource or project                         ║")
        elif is_files:
            print("║    Operation : Download/list files from source                     ║")
            print("║    Role      : Foundry User  or  Cognitive Services OpenAI User    ║")
            print("║    Scope     : Source AI resource                                  ║")
        elif (is_agents or is_assistants) and is_write:
            print("║    Operation : Create/write v2 agents                              ║")
            print("║    Role      : Foundry User  (dataActions: CognitiveServices/*)    ║")
            print("║    Scope     : Foundry resource or project                         ║")
            print("║    NOTE      : 'Cognitive Services OpenAI User' IS sufficient for  ║")
            print("║                assistants/* but Foundry User is recommended.        ║")
        elif is_agents or is_assistants:
            print("║    Operation : Read assistants / agents                            ║")
            print("║    Role      : Foundry User  or  Cognitive Services OpenAI User    ║")
            print("║    Scope     : Source or target AI resource                        ║")
        else:
            print("║    Operation : General data-plane call                             ║")
            print("║    Role      : Foundry User  (recommended minimum for Foundry)     ║")
        print("║                                                                    ║")
    print("╠══════════════════════════════════════════════════════════════════════╣")
    print("║  Assign roles: Azure portal → Resource → Access control (IAM)      ║")
    print("║  Or: az role assignment create --role 'Foundry User'               ║")
    print("║        --assignee <email> --scope /subscriptions/<sub>/...         ║")
    print(f"║  {RBAC_DOCS.splitlines()[0]:<67s}║")
    print(f"║  {RBAC_DOCS.splitlines()[1]:<67s}║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print("")


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
        if resp.status_code in (401, 403):
            _print_rbac_guidance(resp.status_code, url, method)
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
    token_for_request = _get_env_token_for_url(url)
    if token_for_request:
        headers["Authorization"] = f"Bearer {token_for_request}"
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
            _print_rbac_guidance(401, url, method)
            time.sleep(5)
            refresh_scope = _infer_scope_for_url(url)
            print(f"🔄 Refreshing token for audience: {refresh_scope}")
            if set_api_token(force_refresh=True, scope=refresh_scope):  # Force refresh from az CLI on 401
                refreshed_token = _get_env_token_for_url(url) or TOKEN
                headers["Authorization"] = f"Bearer {refreshed_token}"
                kwargs["headers"] = headers
                resp = requests.request(method, url, **kwargs)
            else:
                print("Token refresh failed.")
        
        if resp.status_code == 403:
            _print_rbac_guidance(403, url, method)
        
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

# Platform tool types that require project-level connections to function
PLATFORM_TOOL_TYPES = {
    "bing_grounding": "Bing Search",
    "bing_custom_search": "Bing Custom Search",
    "azure_ai_search": "Azure AI Search",
    "openapi": "OpenAPI",
    "fabric_dataagent": "Microsoft Fabric Data Agent",
    "sharepoint_grounding": "SharePoint",
}


def list_connections_from_project(project_endpoint: str, token: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List all connections configured in a project.
    Uses the project endpoint connections API.
    
    Args:
        project_endpoint: The project endpoint URL (e.g., "https://...services.ai.azure.com/api/projects/proj")
        token: Optional bearer token. If not provided, uses global TOKEN.
    
    Returns:
        List of connection objects
    """
    api_url = project_endpoint.rstrip('/') + '/connections'
    params = {"api-version": API_VERSION}
    
    print(f"🔗 Listing connections from: {api_url}")
    
    try:
        if token:
            response = do_api_request_with_token("GET", api_url, token, params=params)
        else:
            response = do_api_request("GET", api_url, params=params)
        
        data = response.json()
        
        # Handle different response envelope formats
        if isinstance(data, dict):
            connections = data.get("value", data.get("data", data.get("connections", [])))
            # If none of the known keys worked and data looks like a single connection, wrap it
            if not connections and "name" in data:
                connections = [data]
        elif isinstance(data, list):
            connections = data
        else:
            connections = []
        
        print(f"   Found {len(connections)} connections")
        return connections
    except Exception as e:
        print(f"   ⚠️  Failed to list connections: {e}")
        return []


def get_connection_detail(project_endpoint: str, connection_name: str, token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a specific connection.
    
    Args:
        project_endpoint: The project endpoint URL
        connection_name: Name of the connection to retrieve
        token: Optional bearer token
    
    Returns:
        Connection detail dict, or None on failure
    """
    api_url = project_endpoint.rstrip('/') + f'/connections/{connection_name}'
    params = {"api-version": API_VERSION}
    
    try:
        if token:
            response = do_api_request_with_token("GET", api_url, token, params=params)
        else:
            response = do_api_request("GET", api_url, params=params)
        return response.json()
    except Exception as e:
        print(f"   ⚠️  Failed to get connection '{connection_name}': {e}")
        return None


def get_agent_required_connections(v1_assistant: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Identify which platform connections a v1 assistant requires.
    Returns a list of dicts with tool_type, friendly_name, and any connection_id hint.
    """
    tools = v1_assistant.get("tools", [])
    if isinstance(tools, str):
        try:
            tools = json.loads(tools)
        except:
            tools = []
    if not isinstance(tools, list):
        tools = []
    
    required = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        tool_type = tool.get("type", "")
        if tool_type in PLATFORM_TOOL_TYPES:
            entry = {
                "tool_type": tool_type,
                "friendly_name": PLATFORM_TOOL_TYPES[tool_type],
            }
            # Extract any connection hints from the tool object itself
            for key in ["connection_id", "connection_name", "project_connection_id"]:
                if key in tool and tool[key]:
                    entry["connection_id"] = str(tool[key])
                    break
            # For azure_ai_search, capture index config
            if tool_type == "azure_ai_search":
                for key in ["index_asset_id", "index_connection_id", "index_name"]:
                    if key in tool:
                        entry[key] = str(tool[key])
            # For openapi, capture spec info
            if tool_type == "openapi":
                for key in ["spec", "auth", "connection_id"]:
                    if key in tool:
                        entry[key] = str(tool[key]) if not isinstance(tool[key], dict) else json.dumps(tool[key])
            required.append(entry)
    return required


def create_connection_in_target(target_endpoint: str, connection_data: Dict[str, Any], token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Attempt to create a connection in the target project.
    
    Args:
        target_endpoint: The target project endpoint URL
        connection_data: Connection definition (from source)
        token: Optional bearer token
    
    Returns:
        Created connection data, or None on failure
    """
    connection_name = connection_data.get("name", "")
    if not connection_name:
        print("   ❌ Connection has no name, cannot create")
        return None
    
    api_url = target_endpoint.rstrip('/') + f'/connections/{connection_name}'
    params = {"api-version": API_VERSION}
    
    # Build the creation payload — strip read-only fields
    payload = {}
    for key in ["name", "properties", "type", "target", "metadata", "credentials"]:
        if key in connection_data:
            payload[key] = connection_data[key]
    
    print(f"   🔗 Creating connection '{connection_name}' in target...")
    
    try:
        if token:
            response = do_api_request_with_token("PUT", api_url, token, params=params, json=payload)
        else:
            response = do_api_request("PUT", api_url, params=params, json=payload)
        
        result = response.json()
        print(f"   ✅ Connection '{connection_name}' created/updated")
        return result
    except Exception as e:
        print(f"   ❌ Failed to create connection '{connection_name}': {e}")
        print(f"   💡 You may need to create this connection manually in the target project")
        return None


def _extract_arm_info_from_endpoint(project_endpoint: str) -> Optional[Dict[str, str]]:
    """
    Extract ARM routing info from a project endpoint URL.
    E.g., "https://myresource-resource.services.ai.azure.com/api/projects/myproject"
    -> {"account_host": "myresource-resource.services.ai.azure.com", "project_name": "myproject"}
    
    Returns None if the URL can't be parsed.
    """
    import re
    m = re.match(r'https://([^/]+\.services\.ai\.azure\.com)/api/projects/([^/]+)', project_endpoint)
    if m:
        return {"account_host": m.group(1), "project_name": m.group(2)}
    return None


def _derive_connection_display_name(connection: Dict[str, Any]) -> Optional[str]:
    """
    Derive an appropriate displayName for a connection from its metadata.
    Uses the resource name from the ResourceId if available, otherwise
    falls back to the connection name.
    
    NOTE: The derived displayName uses hyphens (not underscores) since the v2
    agent runtime enforces that project_connection_id values contain only
    alphanumerics and hyphens.
    
    Supported resource types:
    - Microsoft.Bing/accounts/{name}
    - Microsoft.Search/searchServices/{name}
    - Microsoft.Fabric/capacities/{name}
    
    Returns the displayName string, or None if unable to derive one.
    """
    metadata = connection.get('metadata', {})
    resource_id = metadata.get('ResourceId', '')
    
    # Extract resource name from common ARM ResourceId patterns
    raw_name = None
    for pattern in ['/accounts/', '/searchServices/', '/capacities/']:
        if pattern in resource_id:
            raw_name = resource_id.split(pattern)[-1]
            break
    
    # Fallback: use the last segment of ResourceId
    if not raw_name and resource_id and '/' in resource_id:
        raw_name = resource_id.split('/')[-1]
    
    # Final fallback: use connection name as-is
    if not raw_name:
        raw_name = connection.get('name', '')
    
    # Replace underscores with hyphens (v2 project_connection_id validation requires hyphens)
    return raw_name.replace('_', '-') if raw_name else raw_name


def ensure_connection_display_names(
    connections: List[Dict[str, Any]],
    subscription_id: str,
    resource_group: str,
    account_name: str,
    token: Optional[str] = None,
) -> Dict[str, str]:
    """
    Ensure all connections have a metadata.displayName set.
    The v2 agent runtime resolves project_connection_id by displayName,
    not by the raw connection name. Connections without a displayName
    will fail with "connection ID not found" in v2 portal.
    
    For connections that lack a displayName, this function:
    1. Derives an appropriate displayName (from the Bing account ResourceId or connection name)
    2. PATCHes the connection via the ARM API to set the displayName
    
    Args:
        connections: List of connection objects from the data-plane API
        subscription_id: Azure subscription ID for the target project
        resource_group: Resource group name
        account_name: AI Services account name (e.g., "<your-resource-name>")
        token: Optional ARM bearer token. If not provided, tries to acquire one.
        
    Returns:
        Dict mapping connection name -> v2 displayName (after any fixes)
    """
    result_map: Dict[str, str] = {}
    arm_api_version = "2025-04-01-preview"
    
    # Get ARM token
    arm_token = token
    if not arm_token:
        try:
            from azure.identity import DefaultAzureCredential
            credential = DefaultAzureCredential()
            arm_token = credential.get_token("https://management.azure.com/.default").token
        except Exception as e:
            print(f"   ⚠️  Could not acquire ARM token for displayName patching: {e}")
            # Return what we can without patching
            for c in connections:
                cname = c.get('name', '')
                dn = c.get('metadata', {}).get('displayName', '')
                result_map[cname] = dn if dn else cname
            return result_map
    
    arm_headers = {"Authorization": f"Bearer {arm_token}", "Content-Type": "application/json"}
    
    for conn in connections:
        conn_name = conn.get('name', '')
        conn_type = conn.get('type', '')
        metadata = conn.get('metadata', {})
        existing_dn = metadata.get('displayName', '')
        
        if existing_dn and '_' not in existing_dn:
            # Already has a valid displayName (no underscores) — no action needed
            result_map[conn_name] = existing_dn  # Use the existing displayName
            continue
        
        if existing_dn and '_' in existing_dn:
            print(f"   🔧 Connection '{conn_name}' has displayName with underscores ('{existing_dn}') — re-patching with hyphens")
        
        # Only patch Bing/tool connections that need displayName for v2
        tool_type = metadata.get('type', '')
        if tool_type not in ('bing_grounding', 'bing_custom_search', 'microsoft_fabric', 'sharepoint_grounding', 'azure_ai_search'):
            result_map[conn_name] = conn_name
            continue
        
        # Derive a displayName
        derived_dn = _derive_connection_display_name(conn)
        if not derived_dn and existing_dn and '_' in existing_dn:
            # Fallback: fix underscores in the existing displayName directly
            derived_dn = existing_dn.replace('_', '-')
            print(f"   🔧 Falling back to underscore-fixed displayName: '{existing_dn}' -> '{derived_dn}'")
        if not derived_dn:
            print(f"   ⚠️  Cannot derive displayName for '{conn_name}', using name as-is")
            result_map[conn_name] = conn_name
            continue
        
        # PATCH via ARM to set displayName
        arm_conn_url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
            f"/connections/{conn_name}"
        )
        
        patch_body = {
            "properties": {
                "authType": metadata.get('authType', conn.get('credentials', {}).get('type', 'ApiKey')),
                "category": conn_type,
                "target": conn.get('target', ''),
                "metadata": {**metadata, "displayName": derived_dn}
            }
        }
        
        try:
            resp = requests.patch(
                f"{arm_conn_url}?api-version={arm_api_version}",
                headers=arm_headers,
                json=patch_body,
                timeout=30
            )
            if resp.ok:
                # Prefer the displayName returned by ARM if present; otherwise fall back to derived_dn
                final_display_name = derived_dn
                try:
                    resp_body = resp.json()
                    final_display_name = (
                        resp_body.get("properties", {})
                        .get("metadata", {})
                        .get("displayName", derived_dn)
                    )
                except Exception:
                    # If the response body cannot be parsed, keep using derived_dn
                    final_display_name = derived_dn
                result_map[conn_name] = final_display_name
                print(
                    f"   ✅ Set displayName on '{conn_name}' -> '{final_display_name}' "
                    f"(raw name '{conn_name}' is the project_connection_id)"
                )
            else:
                print(f"   ⚠️  Failed to set displayName on '{conn_name}': {resp.status_code} {resp.text[:200]}")
                print(f"      Connection will not be resolvable in v2 portal")
                result_map[conn_name] = conn_name
        except Exception as e:
            print(f"   ⚠️  Failed to PATCH displayName on '{conn_name}': {e}")
            result_map[conn_name] = conn_name
    
    return result_map


def _set_target_arm_prefix(target_endpoint: str, subscription_id: Optional[str] = None) -> bool:
    """
    Parse the target project endpoint URL and set TARGET_PROJECT_ARM_PREFIX globally.
    
    The ARM prefix takes the form:
      /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices
      /accounts/{acc}/projects/{proj}
    
    This is required so that get_v2_connection_id() and resolve_connection_id() can
    build full ARM paths for project_connection_id values (required by portal agent runner).
    
    Returns True if the prefix was set successfully.
    """
    global TARGET_PROJECT_ARM_PREFIX
    import re
    
    m = re.match(r'https://([^.]+)\.services\.ai\.azure\.com/api/projects/([^/?]+)', target_endpoint)
    if not m:
        return False
    
    account_name = m.group(1)  # e.g., "<your-resource-name>"
    project_name = m.group(2)  # e.g., "<your-project-name>"
    
    # Try to get RG from connection ARM IDs or fall back to deriving from account name pattern
    rg_name = None
    sub_id = subscription_id
    
    if not rg_name and account_name:
        # Common pattern: account name contains a suffix like "-resource"; RG often prefixed "rg-"
        # We'll fill in when we have a connection list — leave partial prefix for now
        pass
    
    if sub_id and rg_name:
        TARGET_PROJECT_ARM_PREFIX = (
            f"/subscriptions/{sub_id}/resourceGroups/{rg_name}"
            f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
            f"/projects/{project_name}"
        )
        print(f"   🔑 Target ARM prefix set: {TARGET_PROJECT_ARM_PREFIX}")
        return True
    
    return False


def _set_target_arm_prefix_from_connections(
    target_endpoint: str,
    target_connections: List[Dict[str, Any]],
    subscription_id: Optional[str] = None,
) -> bool:
    """
    Set TARGET_PROJECT_ARM_PREFIX by parsing the target endpoint + extracting RG from
    connection ARM IDs. Returns True if prefix was set.
    """
    global TARGET_PROJECT_ARM_PREFIX
    import re
    
    m = re.match(r'https://([^.]+)\.services\.ai\.azure\.com/api/projects/([^/?]+)', target_endpoint)
    if not m:
        print("   ⚠️  Could not parse target endpoint, ARM prefix not set")
        return False
    
    account_name = m.group(1)
    project_name = m.group(2)
    sub_id = subscription_id
    rg_name = None
    
    # Extract sub/RG from connection ARM IDs
    for c in target_connections:
        cid = c.get('id', '')
        arm_match = re.match(r'/subscriptions/([^/]+)/resourceGroups/([^/]+)/', cid)
        if arm_match:
            if not sub_id:
                sub_id = arm_match.group(1)
            rg_name = arm_match.group(2)
            break
    
    if not sub_id or not rg_name:
        print("   ⚠️  Could not determine subscription/RG, ARM prefix not set (project_connection_id will use raw name fallback)")
        return False
    
    TARGET_PROJECT_ARM_PREFIX = (
        f"/subscriptions/{sub_id}/resourceGroups/{rg_name}"
        f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
        f"/projects/{project_name}"
    )
    print(f"   🔑 Target ARM prefix: {TARGET_PROJECT_ARM_PREFIX}")
    return True


def _try_ensure_display_names(
    target_endpoint: str,
    target_connections: List[Dict[str, Any]],
    subscription_id: Optional[str] = None,
) -> None:
    """
    Best-effort attempt to ensure all target connections have displayName set.
    Parses the target endpoint URL to extract ARM routing info, then calls
    ensure_connection_display_names to patch any connections that lack one.
    
    Also sets TARGET_PROJECT_ARM_PREFIX so that project_connection_id values are built
    as full ARM paths (required by portal agent runner).
    
    This modifies the target_connections list in-place (updating metadata).
    """
    import re
    
    # Parse endpoint to get account name and try to determine resource group
    m = re.match(r'https://([^.]+)\.services\.ai\.azure\.com/api/projects/([^/]+)', target_endpoint)
    if not m:
        print("   ⚠️  Could not parse target endpoint for ARM routing, skipping displayName enforcement")
        return
    
    account_name = m.group(1)  # e.g., "<your-resource-name>"
    
    # Try to determine subscription and resource group from connection ARM IDs
    sub_id = subscription_id
    rg_name = None
    for c in target_connections:
        cid = c.get('id', '')
        arm_match = re.match(r'/subscriptions/([^/]+)/resourceGroups/([^/]+)/', cid)
        if arm_match:
            if not sub_id:
                sub_id = arm_match.group(1)
            rg_name = arm_match.group(2)
            break
    
    # Always set TARGET_PROJECT_ARM_PREFIX if we have enough info (needed for project_connection_id)
    _set_target_arm_prefix_from_connections(target_endpoint, target_connections, sub_id)
    
    # Check if any connections actually need fixing
    needs_fix = [c for c in target_connections 
                 if (not c.get('metadata', {}).get('displayName')
                     or '_' in c.get('metadata', {}).get('displayName', ''))
                 and c.get('metadata', {}).get('type') in ('bing_grounding', 'bing_custom_search', 'microsoft_fabric', 'sharepoint_grounding', 'azure_ai_search')]
    
    if not needs_fix:
        return
    
    print(f"\n   🔧 {len(needs_fix)} connection(s) need displayName fix (required for v2 runtime)")
    
    if not sub_id or not rg_name:
        print(f"   ⚠️  Could not determine subscription/RG from connection IDs, skipping displayName enforcement")
        print(f"      Connections without displayName may fail in v2 portal. Fix manually or use --connection-map.")
        return
    
    print(f"   📡 Patching via ARM: subscription={sub_id}, RG={rg_name}, account={account_name}")
    display_name_map = ensure_connection_display_names(
        needs_fix, sub_id, rg_name, account_name
    )
    
    # Update the connection objects in-place so build_connection_map sees the displayNames
    for c in target_connections:
        cname = c.get('name', '')
        if cname in display_name_map:
            if 'metadata' not in c or not isinstance(c['metadata'], dict):
                c['metadata'] = {}
            c['metadata']['displayName'] = display_name_map[cname]


def print_connection_migration_report(assistants: List[Dict[str, Any]], source_connections: List[Dict[str, Any]]):
    """
    Print a summary report of which connections each agent needs and whether they exist in source.
    """
    print("\n" + "=" * 60)
    print("🔗 CONNECTION MIGRATION REPORT")
    print("=" * 60)
    
    # Build a lookup of source connections by name and type
    conn_by_name = {c.get("name", ""): c for c in source_connections}
    conn_by_type = {}
    for c in source_connections:
        ctype = c.get("properties", {}).get("category", c.get("type", c.get("metadata", {}).get("type", "unknown")))
        conn_by_type.setdefault(ctype, []).append(c)
    
    all_needed_connections = set()
    
    for assistant in assistants:
        name = assistant.get("name", "unknown")
        required = get_agent_required_connections(assistant)
        if not required:
            continue
        
        print(f"\n   🤖 {name} (ID: {assistant.get('id', 'unknown')})")
        for req in required:
            tool_type = req["tool_type"]
            friendly = req["friendly_name"]
            conn_id = req.get("connection_id", "(not specified in tool)")
            print(f"      • {friendly} ({tool_type})")
            print(f"        Connection ref: {conn_id}")
            if conn_id != "(not specified in tool)" and conn_id in conn_by_name:
                src_conn = conn_by_name[conn_id]
                print(f"        ✅ Found in source: {src_conn.get('name', 'N/A')} (type: {src_conn.get('type', 'N/A')})")
                all_needed_connections.add(conn_id)
            else:
                # Try matching by tool type
                matched = False
                for c in source_connections:
                    c_meta_type = c.get("metadata", {}).get("type", "")
                    c_category = c.get("properties", {}).get("category", "")
                    if tool_type in [c_meta_type, c_category]:
                        print(f"        🔍 Possible match in source: '{c.get('name', 'N/A')}' (type: {c.get('type', 'N/A')})")
                        all_needed_connections.add(c.get("name", ""))
                        matched = True
                if not matched:
                    print(f"        ⚠️  No matching connection found in source")
            
            # Print extra config hints
            for extra_key in ["index_asset_id", "index_connection_id", "index_name", "spec"]:
                if extra_key in req:
                    print(f"        Config: {extra_key} = {req[extra_key]}")
    
    if all_needed_connections:
        print(f"\n   📋 Connections that should exist in target project:")
        for cn in sorted(all_needed_connections):
            print(f"      - {cn}")
    
    print("\n" + "=" * 60)


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

def _get_source_api_version(project_endpoint: str) -> str:
    """
    Return the API version to use when reading from a source project endpoint.
    Legacy openai.azure.com endpoints only support older API versions.
    """
    if SOURCE_API_VERSION:
        return SOURCE_API_VERSION
    # Parse the endpoint to extract the hostname for a safe check.
    # A plain substring test (e.g. '"openai.azure.com" in url') would
    # also match crafted URLs like evil-openai.azure.com.attacker.com.
    parsed = urlparse(project_endpoint)
    host = parsed.hostname if parsed.hostname else project_endpoint.strip('/')
    if host == "cognitiveservices.azure.com" or host.endswith(".cognitiveservices.azure.com"):
        return OPENAI_COMPAT_API_VERSION
    if host == "openai.azure.com" or host.endswith(".openai.azure.com"):
        # Legacy OpenAI-kind resource — use the last known compatible version
        return "2024-05-01-preview"
    return API_VERSION


# ── File Migration Helpers ────────────────────────────────────────────
# These functions handle downloading files from a v1 source environment
# and re-uploading them to the v2 target, including vector-store creation.
# Without this step, migrated agents that use file_search or
# code_interpreter will have broken references (source file IDs / vector
# store IDs don't exist on the target).
# ──────────────────────────────────────────────────────────────────────

def download_file_from_source(
    source_endpoint: str,
    file_id: str,
    source_token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Download a file's metadata and content from the source endpoint.

    Returns a dict with keys ``id``, ``filename``, ``bytes``, ``purpose``,
    and ``content`` (raw bytes), or *None* on failure.
    """
    token = source_token or TOKEN
    if not token:
        print(f"   ⚠️  No token available for file download")
        return None

    api_version = _get_source_api_version(source_endpoint)
    base = source_endpoint.rstrip('/')
    headers = {"Authorization": f"Bearer {token}"}
    params = {"api-version": api_version}

    # 1. Get metadata
    try:
        meta_r = requests.get(f"{base}/files/{file_id}", headers=headers, params=params, timeout=30)
        meta_r.raise_for_status()
        meta = meta_r.json()
    except Exception as e:
        print(f"   ❌ Failed to get metadata for file {file_id}: {e}")
        return None

    # 2. Download content
    try:
        content_r = requests.get(f"{base}/files/{file_id}/content", headers=headers, params=params, timeout=60)
        content_r.raise_for_status()
    except Exception as e:
        print(f"   ❌ Failed to download content for file {file_id}: {e}")
        return None

    result = {
        "id": file_id,
        "filename": meta.get("filename", f"file_{file_id}"),
        "bytes": meta.get("bytes", len(content_r.content)),
        "purpose": meta.get("purpose", "assistants"),
        "content": content_r.content,
    }
    print(f"   📥 Downloaded {result['filename']} ({len(content_r.content)}B)")
    return result


# Retry / polling configuration for file upload and vector-store ingestion.
# Override via environment variables without code changes.
FILE_UPLOAD_MAX_RETRIES = int(os.getenv("MIGRATION_FILE_UPLOAD_RETRIES", "3"))
FILE_UPLOAD_BACKOFF_SECONDS = float(os.getenv("MIGRATION_FILE_UPLOAD_BACKOFF", "2"))
VECTOR_STORE_FILE_POLL_ATTEMPTS = int(os.getenv("MIGRATION_VS_FILE_POLL_ATTEMPTS", "30"))
VECTOR_STORE_FILE_POLL_INTERVAL = float(os.getenv("MIGRATION_VS_FILE_POLL_INTERVAL", "2"))

# HTTP status codes that indicate a transient failure worth retrying.
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def upload_file_to_target(
    target_endpoint: str,
    filename: str,
    content: bytes,
    purpose: str = "assistants",
    target_token: Optional[str] = None,
    max_retries: int = FILE_UPLOAD_MAX_RETRIES,
) -> tuple[Optional[str], Optional[str]]:
    """
    Upload a file to the target endpoint, retrying transient failures with
    exponential backoff.

    Retries on network errors and transient HTTP status codes (408/429/5xx).
    Does **not** retry client errors such as 400/415 (for example, an
    unsupported file type), where a retry cannot succeed.

    Returns a ``(file_id, None)`` tuple on success, or ``(None, reason)`` on
    failure, where *reason* is a human-readable error string suitable for
    surfacing to the user (terminal, failed_files list, JSON report).
    """
    token = target_token or PRODUCTION_TOKEN or TOKEN
    if not token:
        print(f"   ⚠️  No token available for file upload")
        return None, "no token available for file upload"

    base = target_endpoint.rstrip('/')
    headers = {"Authorization": f"Bearer {token}"}
    # Use the target API version (not the source one).
    # API_VERSION is 2025-05-15-preview for the Foundry project endpoint (*.services.ai.azure.com).
    # The REST quickstart uses api-version=v1 but targets the legacy OpenAI-compatible endpoint (*.openai.azure.com),
    # which is a different API surface.
    params = {"api-version": API_VERSION}

    last_error = "unknown error"
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                f"{base}/files",
                headers=headers,
                params=params,
                data={"purpose": purpose},
                files={"file": (filename, content)},
                timeout=60,
            )
        except requests.exceptions.RequestException as e:
            # Network/timeout error (no HTTP response) — treat as transient.
            last_error = f"network error: {e}"
        else:
            if resp.status_code < 400:
                try:
                    body = resp.json()
                except ValueError:
                    last_error = f"non-JSON success response: {resp.text[:200]}"
                else:
                    new_id = body.get("id") if isinstance(body, dict) else None
                    if new_id:
                        suffix = f" (attempt {attempt})" if attempt > 1 else ""
                        print(f"   📤 Uploaded {filename} -> {new_id}{suffix}")
                        return new_id, None
                    last_error = f"success response missing file id: {resp.text[:200]}"
            elif resp.status_code not in _RETRYABLE_STATUS:
                # Client error (e.g. 400/415 unsupported type) — retrying won't help.
                print(f"   ❌ Failed to upload {filename}: HTTP {resp.status_code}")
                print(f"      {resp.text[:300]}")
                return None, f"HTTP {resp.status_code}: {resp.text[:300]}"
            else:
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"

        if attempt < max_retries:
            delay = FILE_UPLOAD_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(f"   🔁 Upload of {filename} failed (attempt {attempt}/{max_retries}); "
                  f"retrying in {delay:.0f}s … [{last_error}]")
            time.sleep(delay)

    print(f"   ❌ Failed to upload {filename} after {max_retries} attempt(s): {last_error}")
    return None, last_error


def list_vector_store_files(
    source_endpoint: str,
    vector_store_id: str,
    source_token: Optional[str] = None,
) -> List[str]:
    """
    Return the list of file IDs inside a source vector store.
    """
    token = source_token or TOKEN
    if not token:
        return []

    api_version = _get_source_api_version(source_endpoint)
    base = source_endpoint.rstrip('/')
    headers = {"Authorization": f"Bearer {token}"}
    params = {"api-version": api_version}

    try:
        resp = requests.get(
            f"{base}/vector_stores/{vector_store_id}/files",
            headers=headers, params=params, timeout=30,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        file_ids = [f.get("id") for f in data if f.get("id")]
        print(f"   📋 Vector store {vector_store_id} contains {len(file_ids)} file(s)")
        return file_ids
    except Exception as e:
        print(f"   ⚠️  Could not list files in vector store {vector_store_id}: {e}")
        return []


def _add_file_to_vector_store_and_poll(
    base: str,
    headers: Dict[str, str],
    params: Dict[str, str],
    vector_store_id: str,
    file_id: str,
    max_retries: int = FILE_UPLOAD_MAX_RETRIES,
    poll_attempts: int = VECTOR_STORE_FILE_POLL_ATTEMPTS,
    poll_interval: float = VECTOR_STORE_FILE_POLL_INTERVAL,
) -> Optional[str]:
    """
    Attach a single *file_id* to *vector_store_id* and poll until ingestion
    reaches a terminal state (``completed`` or ``failed``).

    This mirrors the SDK ``vector_stores.files.upload_and_poll`` helper: each
    file is ingested and polled individually, so a single file's failure is
    isolated and retryable instead of being hidden behind an aggregate
    vector-store status.

    Returns *None* on success, or a human-readable failure reason on failure.
    The whole add-and-poll is retried up to *max_retries* times.
    """
    last_reason = "unknown error"
    for attempt in range(1, max_retries + 1):
        # On a retry, clear any prior (failed) association so the re-add is clean.
        if attempt > 1:
            try:
                requests.delete(
                    f"{base}/vector_stores/{vector_store_id}/files/{file_id}",
                    headers=headers, params=params, timeout=15,
                )
            except Exception:
                pass

        # 1. Attach the file to the vector store.
        try:
            add = requests.post(
                f"{base}/vector_stores/{vector_store_id}/files",
                headers=headers, params=params,
                json={"file_id": file_id},
                timeout=30,
            )
            add.raise_for_status()
        except requests.exceptions.HTTPError as e:
            resp_obj = getattr(e, "response", None)
            status = getattr(resp_obj, "status_code", None)
            text = resp_obj.text[:200] if resp_obj is not None else str(e)
            last_reason = f"attach failed: HTTP {status} {text}"
            if status is not None and status not in _RETRYABLE_STATUS:
                # Permanent client error (e.g. 400/415 unsupported file type) —
                # retrying will never succeed, so fail fast like the upload path.
                print(f"   ❌ File {file_id} cannot be ingested (HTTP {status}); not retrying.")
                return last_reason
        except Exception as e:
            resp_obj = getattr(e, "response", None)
            if resp_obj is not None:
                last_reason = f"attach failed: HTTP {resp_obj.status_code} {resp_obj.text[:200]}"
            else:
                last_reason = f"attach failed: {e}"
        else:
            # 2. Poll this file's ingestion status until terminal.
            status = "in_progress"
            for _ in range(poll_attempts):
                time.sleep(poll_interval)
                try:
                    check = requests.get(
                        f"{base}/vector_stores/{vector_store_id}/files/{file_id}",
                        headers=headers, params=params, timeout=15,
                    )
                except Exception:
                    continue
                if check.status_code >= 400:
                    if check.status_code in _RETRYABLE_STATUS:
                        last_reason = f"poll transient error: HTTP {check.status_code} {check.text[:200]}"
                        continue
                    last_reason = f"poll failed: HTTP {check.status_code} {check.text[:200]}"
                    return last_reason
                body = check.json() if check.content else {}
                status = body.get("status", "unknown") if isinstance(body, dict) else "unknown"
                if status == "completed":
                    suffix = f" (attempt {attempt})" if attempt > 1 else ""
                    print(f"   ✅ Ingested file {file_id}{suffix}")
                    return None
                if status == "failed":
                    err = body.get("last_error") or {}
                    if isinstance(err, dict):
                        # Surface both the error code and message so callers
                        # get an actionable reason (e.g. "[invalid_file] ...").
                        code = err.get("code")
                        message = err.get("message") or "ingestion failed"
                        last_reason = f"[{code}] {message}" if code else message
                    else:
                        last_reason = str(err) or "ingestion failed"
                    break
            else:
                last_reason = f"ingestion did not complete (last status: {status})"

        if attempt < max_retries:
            delay = FILE_UPLOAD_BACKOFF_SECONDS * (2 ** (attempt - 1))
            print(f"   🔁 File {file_id} ingestion failed (attempt {attempt}/{max_retries}); "
                  f"retrying in {delay:.0f}s … [{last_reason}]")
            time.sleep(delay)

    return last_reason


def create_vector_store_on_target(
    target_endpoint: str,
    file_ids: List[str],
    name: str = "migrated-vector-store",
    target_token: Optional[str] = None,
    max_file_retries: int = FILE_UPLOAD_MAX_RETRIES,
) -> Optional[Dict[str, Any]]:
    """
    Create a vector store on the target and ingest *file_ids* one at a time
    using an add-and-poll pattern.

    Each file is added individually and polled until its ingestion finishes,
    so per-file failures are visible and retried (up to *max_file_retries*).
    Files that still fail are reported but do not abort the migration: the
    vector store is created and attached with whatever files ingested
    successfully.

    Returns a dict::

        {
            "id":        vector_store_id,
            "succeeded": [file_id, ...],
            "failed":    [{"file_id": ..., "reason": ...}, ...],
        }

    or *None* if the vector store itself could not be created.
    """
    token = target_token or PRODUCTION_TOKEN or TOKEN
    if not token or not file_ids:
        return None

    base = target_endpoint.rstrip('/')
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # Use the target API version for the Foundry project endpoint (*.services.ai.azure.com).
    # This is 2025-05-15-preview, not the legacy api-version=v1 from the REST quickstart
    # (which targets a different OpenAI-compatible endpoint).
    params = {"api-version": API_VERSION}

    # Create an empty vector store first, then ingest files one by one so that
    # individual ingestion failures can be observed and retried. The bulk
    # "file_ids" create only exposes an aggregate status and hides which files
    # failed — the exact problem customers hit when some files showed as not
    # succeeded in the UI.
    try:
        resp = requests.post(
            f"{base}/vector_stores",
            headers=headers, params=params,
            json={"name": name},
            timeout=30,
        )
        resp.raise_for_status()
        vs = resp.json()
        vs_id = vs.get("id")
        print(f"   🗄️  Created vector store {vs_id}")
    except Exception as e:
        print(f"   ❌ Failed to create vector store: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"      {e.response.text[:300]}")
        return None

    succeeded: List[str] = []
    failed: List[Dict[str, str]] = []

    for fid in file_ids:
        reason = _add_file_to_vector_store_and_poll(
            base, headers, params, vs_id, fid, max_retries=max_file_retries,
        )
        if reason is None:
            succeeded.append(fid)
        else:
            failed.append({"file_id": fid, "reason": reason})

    if failed:
        print(f"   ⚠️  Vector store {vs_id}: {len(succeeded)} file(s) ingested, "
              f"{len(failed)} failed:")
        for f in failed:
            print(f"        ❌ {f['file_id']}: {f['reason']}")
    else:
        print(f"   ✅ Vector store {vs_id} ready ({len(succeeded)} file(s) ingested)")

    return {"id": vs_id, "succeeded": succeeded, "failed": failed}


def migrate_assistant_files(
    source_endpoint: str,
    target_endpoint: str,
    v1_assistant: Dict[str, Any],
    source_token: Optional[str] = None,
    target_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Download every file referenced by *v1_assistant* from *source_endpoint*
    and re-upload to *target_endpoint*.  Creates new vector stores on the
    target for any ``file_search`` vector-store references.

    Returns a **remapping dict**::

        {
            "file_id_map":   {old_id: new_id, ...},
            "vs_id_map":     {old_vs_id: new_vs_id, ...},
            "failed_files":  [{"scope": ..., "file_id": ..., "reason": ...}, ...],
        }

    The caller should use the maps to rewrite IDs in the v2 tool
    definitions before posting to the target API, and surface
    ``failed_files`` so any file that did not migrate is flagged for
    manual follow-up.
    """
    file_id_map: Dict[str, str] = {}
    vs_id_map: Dict[str, str] = {}
    failed_files: List[Dict[str, str]] = []

    tool_resources = v1_assistant.get("tool_resources", {})
    if isinstance(tool_resources, str):
        try:
            tool_resources = json.loads(tool_resources)
        except (json.JSONDecodeError, TypeError):
            tool_resources = {}
    if not isinstance(tool_resources, dict):
        tool_resources = {}

    print(f"\n   📦 Migrating files for assistant {v1_assistant.get('id', '?')}")

    # ── 1. code_interpreter files ─────────────────────────────────────
    ci_file_ids = tool_resources.get("code_interpreter", {}).get("file_ids", [])
    if ci_file_ids:
        print(f"   🔧 code_interpreter: {len(ci_file_ids)} file(s) to migrate")
        for fid in ci_file_ids:
            if fid in file_id_map:
                continue  # already migrated (shared with VS)
            downloaded = download_file_from_source(source_endpoint, fid, source_token)
            if not downloaded:
                failed_files.append({"scope": "code_interpreter", "file_id": fid, "reason": "download failed"})
                continue
            new_id, upload_err = upload_file_to_target(
                target_endpoint, downloaded["filename"], downloaded["content"],
                purpose="assistants", target_token=target_token,
            )
            if new_id:
                file_id_map[fid] = new_id
            else:
                failed_files.append({"scope": "code_interpreter", "file_id": fid, "reason": upload_err or "upload failed after retries"})

    # ── 2. file_search vector stores ──────────────────────────────────
    vs_ids = tool_resources.get("file_search", {}).get("vector_store_ids", [])
    if vs_ids:
        print(f"   🔍 file_search: {len(vs_ids)} vector store(s) to migrate")
        for vs_id in vs_ids:
            # List files in the source VS
            vs_file_ids = list_vector_store_files(source_endpoint, vs_id, source_token)
            new_vs_file_ids = []
            # Map each target file ID back to its source file ID so ingestion
            # failures can be reported against the original source file.
            target_to_source: Dict[str, str] = {}
            for fid in vs_file_ids:
                if fid in file_id_map:
                    new_vs_file_ids.append(file_id_map[fid])
                    target_to_source[file_id_map[fid]] = fid
                    continue
                downloaded = download_file_from_source(source_endpoint, fid, source_token)
                if not downloaded:
                    failed_files.append({"scope": "file_search", "file_id": fid, "reason": f"download failed (vector store {vs_id})"})
                    continue
                new_id, upload_err = upload_file_to_target(
                    target_endpoint, downloaded["filename"], downloaded["content"],
                    purpose="assistants", target_token=target_token,
                )
                if new_id:
                    file_id_map[fid] = new_id
                    new_vs_file_ids.append(new_id)
                    target_to_source[new_id] = fid
                else:
                    failed_files.append({"scope": "file_search", "file_id": fid, "reason": upload_err or f"upload failed after retries (vector store {vs_id})"})
            # Create new VS on target and ingest the uploaded files one by one
            # (add-and-poll) so individual ingestion failures are surfaced.
            if new_vs_file_ids:
                vs_result = create_vector_store_on_target(
                    target_endpoint, new_vs_file_ids,
                    name=f"migrated-{vs_id}",
                    target_token=target_token,
                )
                if vs_result and vs_result.get("id"):
                    vs_id_map[vs_id] = vs_result["id"]
                    for f in vs_result.get("failed", []):
                        src_fid = target_to_source.get(f["file_id"], f["file_id"])
                        failed_files.append({
                            "scope": "file_search",
                            "file_id": str(src_fid),
                            "reason": f"ingestion failed (vector store {vs_id}): {f['reason']}",
                        })

    if file_id_map or vs_id_map:
        print(f"   📊 File migration summary: {len(file_id_map)} file(s), {len(vs_id_map)} vector store(s) remapped")
    else:
        print(f"   ℹ️  No files to migrate for this assistant")

    if failed_files:
        print(f"   ⚠️  {len(failed_files)} file(s) did not migrate successfully and need manual follow-up:")
        for f in failed_files:
            print(f"        ❌ [{f['scope']}] {f['file_id']}: {f['reason']}")

    return {"file_id_map": file_id_map, "vs_id_map": vs_id_map, "failed_files": failed_files}


# Path of the JSON report that accumulates per-file migration failures.
# Override via env without code changes; the migration appends to this file so
# any file that did not migrate is captured for manual follow-up after the run.
FILE_FAILURE_REPORT_PATH = os.getenv("MIGRATION_FILE_FAILURE_REPORT", "migration_failed_files.json")


def record_file_migration_failures(
    assistant_id: str,
    failed_files: List[Dict[str, str]],
    report_path: str = FILE_FAILURE_REPORT_PATH,
) -> None:
    """
    Append *failed_files* for *assistant_id* to the JSON failure report.

    The report is a JSON list of records ``{assistant_id, file_id, scope,
    reason, recorded_at}``.  It is read-modify-written so failures accumulate
    across every assistant processed in a run.  Best-effort: any I/O error is
    logged and swallowed so reporting never aborts the migration.
    """
    if not failed_files:
        return
    try:
        existing: List[Dict[str, Any]] = []
        if os.path.exists(report_path):
            try:
                with open(report_path, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, list):
                    existing = loaded
            except (json.JSONDecodeError, OSError):
                # Corrupt/unreadable report — start fresh rather than fail.
                existing = []

        recorded_at = int(time.time())
        for f in failed_files:
            existing.append({
                "assistant_id": assistant_id,
                "file_id": f.get("file_id"),
                "scope": f.get("scope"),
                "reason": f.get("reason"),
                "recorded_at": recorded_at,
            })

        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(existing, fh, indent=2)
        print(f"   📝 Recorded {len(failed_files)} file failure(s) to {report_path}")
    except Exception as e:
        print(f"   ⚠️  Could not write file-failure report to {report_path}: {e}")


def apply_file_id_remapping(
    v2_agent_data: Dict[str, Any],
    file_id_map: Dict[str, str],
    vs_id_map: Dict[str, str],
) -> Dict[str, Any]:
    """
    Rewrite file IDs and vector-store IDs in a v2 agent payload using
    the maps produced by :func:`migrate_assistant_files`.

    Modifies *v2_agent_data* in place and returns it.
    """
    definition = v2_agent_data.get("v2_agent_version", {}).get("definition", {})
    tools = definition.get("tools", [])

    for tool in tools:
        ttype = tool.get("type")

        if ttype == "file_search" and "vector_store_ids" in tool:
            tool["vector_store_ids"] = [
                vs_id_map.get(vid, vid) for vid in tool["vector_store_ids"]
            ]

        if ttype == "code_interpreter" and "container" in tool:
            container = tool["container"]
            if "file_ids" in container:
                container["file_ids"] = [
                    file_id_map.get(fid, fid) for fid in container["file_ids"]
                ]

    return v2_agent_data
def get_assistant_from_project(project_endpoint: str, assistant_id: str, subscription_id: Optional[str] = None, resource_group_name: Optional[str] = None, project_name: Optional[str] = None) -> Dict[str, Any]:
    """Get v1 assistant details from project endpoint using direct API calls (bypassing AIProjectClient SDK bug)."""
    
    # Since direct API calls work and AIProjectClient has issues, use direct REST API
    print(f"   🌐 Using direct API call to project endpoint (bypassing AIProjectClient SDK)")
    
    # Build the direct API URL
    if not project_endpoint.endswith('/'):
        project_endpoint = project_endpoint + '/'
    
    # Remove trailing slash if present, then add the assistants path
    api_url = project_endpoint.rstrip('/') + f'/assistants/{assistant_id}'
    
    # Auto-detect the right API version for this endpoint
    effective_api_version = _get_source_api_version(project_endpoint)
    params = {"api-version": effective_api_version}
    
    print(f"   📞 Making direct API call to: {api_url}")
    print(f"   🔧 Using API version: {effective_api_version}")
    
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
                subscription_id = subscription_id or os.getenv("AGENTS_SUBSCRIPTION")
                resource_group_name = resource_group_name or os.getenv("AGENTS_RESOURCE_GROUP")
                
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
    
    # Auto-detect the right API version for this endpoint
    effective_api_version = _get_source_api_version(project_endpoint)
    params = {"api-version": effective_api_version, "limit": "100"}
    
    print(f"   📞 Making direct API call to: {api_url}")
    print(f"   🔧 Using API version: {effective_api_version}")
    
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


def _derive_openai_endpoint(project_endpoint: str) -> Optional[str]:
    """
    Derive the legacy OpenAI-compatible cognitiveservices endpoint from a
    Foundry project endpoint.

    The Foundry portal has TWO separate backends:
      - NEW ("agents" page):  {resource}.services.ai.azure.com/api/projects/{project}/assistants
                               uses api-version like 2025-05-15-preview
      - OLD ("assistants" page): {resource}.cognitiveservices.azure.com/openai/assistants
                               uses api-version like 2024-12-01-preview

    These are completely separate storage silos.  Items created on the old
    portal experience only appear on the cognitiveservices endpoint.

        Given a project endpoint like
            https://<your-resource-name>.services.ai.azure.com/api/projects/<your-project-name>
        returns
            https://<your-resource-name>.cognitiveservices.azure.com/openai
    """
    parsed = urlparse(project_endpoint)
    host = parsed.hostname or ""
    # Expected: {resource}.services.ai.azure.com
    suffix = ".services.ai.azure.com"
    if host.endswith(suffix):
        resource_name = host[: -len(suffix)]
        return f"https://{resource_name}.cognitiveservices.azure.com/openai"
    return None


# The API version that works on the old cognitiveservices /openai/assistants endpoint.
# Most 2024/2025 preview versions work; use a fairly recent one.
OPENAI_COMPAT_API_VERSION = "2024-12-01-preview"


def list_v1_assistants_from_openai_endpoint(project_endpoint: str) -> List[Dict[str, Any]]:
    """
    List v1 assistants from the legacy OpenAI-compatible cognitiveservices endpoint.

    The Foundry portal's "Assistants" page (ai.azure.com/resource/assistants)
    reads from:  {resource}.cognitiveservices.azure.com/openai/assistants
    using an older API version (e.g. 2024-12-01-preview).

    These items do NOT appear on the newer Foundry
    {resource}.services.ai.azure.com/api/projects/{project}/assistants endpoint.

    Returns a list of assistant dicts.  Each dict gets an extra key
    '_source_endpoint' set to 'openai' so callers can distinguish them.
    """
    global LAST_LEGACY_OPENAI_QUERY_ERROR
    LAST_LEGACY_OPENAI_QUERY_ERROR = None

    openai_base_url = _derive_openai_endpoint(project_endpoint)
    if not openai_base_url:
        print("   ⚠️  Could not derive cognitiveservices URL from project endpoint")
        return []

    openai_url = f"{openai_base_url.rstrip('/')}/assistants"

    print(f"   🌐 Querying legacy OpenAI-compatible endpoint")
    print(f"   📞 {openai_url}")
    print(f"   🔧 Using API version: {OPENAI_COMPAT_API_VERSION}")

    params = {"api-version": OPENAI_COMPAT_API_VERSION, "limit": "100"}

    try:
        # Ensure we have the correct audience for legacy OpenAI-compatible endpoints.
        openai_scope = _infer_scope_for_url(openai_url)
        if OPENAI_COMPAT_TOKEN and OPENAI_COMPAT_TOKEN_SCOPE == openai_scope:
            global TOKEN, TOKEN_SCOPE
            TOKEN = OPENAI_COMPAT_TOKEN
            TOKEN_SCOPE = OPENAI_COMPAT_TOKEN_SCOPE
        elif TOKEN_SCOPE != openai_scope:
            if not set_api_token(force_refresh=True, scope=openai_scope):
                raise RuntimeError(f"Unable to obtain token for scope {openai_scope}")

        response = do_api_request("GET", openai_url, params=params)
        result = response.json()

        if isinstance(result, dict):
            if "data" in result:
                items = result["data"]
            elif "assistants" in result:
                items = result["assistants"]
            else:
                items = []
        elif isinstance(result, list):
            items = result
        else:
            items = []

        # Tag each item
        for item in items:
            item['_source_endpoint'] = 'openai'

        print(f"   ✅ Found {len(items)} v1 assistants on cognitiveservices endpoint")
        return items

    except Exception as e:
        error_str = str(e)
        if "404" in error_str or "NotFound" in error_str:
            LAST_LEGACY_OPENAI_QUERY_ERROR = None
            print(f"   ℹ️  cognitiveservices OpenAI endpoint not available (404) — skipping")
        elif "401" in error_str or "Unauthorized" in error_str:
            LAST_LEGACY_OPENAI_QUERY_ERROR = error_str
            print(f"   ⚠️  cognitiveservices endpoint returned 401 — auth failed even with cognitiveservices scope")
        else:
            LAST_LEGACY_OPENAI_QUERY_ERROR = error_str
            print(f"   ⚠️  cognitiveservices endpoint query failed: {e} — skipping")
        return []


def get_v1_assistant_from_openai_endpoint(project_endpoint: str, assistant_id: str) -> Dict[str, Any]:
    """
    Get a specific v1 assistant from the legacy OpenAI-compatible endpoint.

    This is used as a fallback when a caller provides an assistant ID that
    exists only on the older cognitiveservices backend and not on the Foundry
    project endpoint.
    """
    openai_base_url = _derive_openai_endpoint(project_endpoint)
    if not openai_base_url:
        raise RuntimeError("Could not derive cognitiveservices URL from project endpoint")

    openai_url = f"{openai_base_url.rstrip('/')}/assistants/{assistant_id}"
    print(f"   🌐 Querying legacy OpenAI-compatible endpoint for assistant: {assistant_id}")
    print(f"   📞 {openai_url}")
    print(f"   🔧 Using API version: {OPENAI_COMPAT_API_VERSION}")

    params = {"api-version": OPENAI_COMPAT_API_VERSION}
    openai_scope = _infer_scope_for_url(openai_url)

    if OPENAI_COMPAT_TOKEN and OPENAI_COMPAT_TOKEN_SCOPE == openai_scope:
        global TOKEN, TOKEN_SCOPE
        TOKEN = OPENAI_COMPAT_TOKEN
        TOKEN_SCOPE = OPENAI_COMPAT_TOKEN_SCOPE
    elif TOKEN_SCOPE != openai_scope:
        if not set_api_token(force_refresh=True, scope=openai_scope):
            raise RuntimeError(f"Unable to obtain token for scope {openai_scope}")

    result = do_api_request("GET", openai_url, params=params).json()
    if isinstance(result, dict):
        result['_source_endpoint'] = 'openai'
    print(f"   ✅ Successfully retrieved assistant from legacy OpenAI endpoint")
    return result


def list_v2_agents_from_project(project_endpoint: str, token: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """
    List v2 named agents from the target project endpoint.

    Uses the /agents surface (not /assistants) and paginates using the
    `after` cursor when available.
    """
    api_url = project_endpoint.rstrip('/') + '/agents'
    after: Optional[str] = None
    agents: List[Dict[str, Any]] = []

    while True:
        params: Dict[str, Any] = {"api-version": API_VERSION, "limit": str(limit)}
        if after:
            params["after"] = after

        if token:
            response = do_api_request_with_token("GET", api_url, token, params=params)
        else:
            response = do_api_request("GET", api_url, params=params)

        result = response.json()
        page = result.get("data", []) if isinstance(result, dict) else []
        if isinstance(page, list):
            agents.extend(page)

        has_more = bool(result.get("has_more")) if isinstance(result, dict) else False
        after = result.get("last_id") if isinstance(result, dict) else None
        if not has_more or not after:
            break

    return agents


def list_agent_versions_from_project(project_endpoint: str, agent_name: str, token: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """
    List versions for a specific v2 agent.
    """
    safe_agent_name = sanitize_agent_name(agent_name)
    api_url = project_endpoint.rstrip('/') + f'/agents/{safe_agent_name}/versions'
    after: Optional[str] = None
    versions: List[Dict[str, Any]] = []

    while True:
        params: Dict[str, Any] = {"api-version": API_VERSION, "limit": str(limit)}
        if after:
            params["after"] = after

        if token:
            response = do_api_request_with_token("GET", api_url, token, params=params)
        else:
            response = do_api_request("GET", api_url, params=params)

        result = response.json()
        page = result.get("data", []) if isinstance(result, dict) else []
        if isinstance(page, list):
            versions.extend(page)

        has_more = bool(result.get("has_more")) if isinstance(result, dict) else False
        after = result.get("last_id") if isinstance(result, dict) else None
        if not has_more or not after:
            break

    return versions


def get_existing_migrated_agents_by_v1_id(project_endpoint: str, token: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Build an index of existing migrated v2 agents keyed by original v1 assistant ID.
    """
    existing: Dict[str, Dict[str, Any]] = {}
    for agent in list_v2_agents_from_project(project_endpoint, token=token):
        versions = agent.get("versions", {})
        latest = versions.get("latest", {}) if isinstance(versions, dict) else {}
        metadata = latest.get("metadata", {}) if isinstance(latest, dict) else {}
        if not isinstance(metadata, dict):
            continue

        original_v1_id = metadata.get("original_v1_id")
        if not original_v1_id:
            continue

        existing[str(original_v1_id)] = {
            "agent_id": agent.get("id", ""),
            "agent_name": agent.get("name", ""),
            "latest_version_id": latest.get("id", ""),
            "latest_version": str(latest.get("version", "")),
            "raw": agent,
        }

    return existing


def get_next_agent_version(project_endpoint: str, agent_name: str, token: Optional[str] = None) -> str:
    """
    Compute the next version string for an existing v2 agent.

    If existing versions are numeric strings, increments the max numeric
    version; otherwise falls back to a timestamp-based version string.
    """
    versions = list_agent_versions_from_project(project_endpoint, agent_name, token=token)
    numeric_versions: List[int] = []
    for version in versions:
        value = str(version.get("version", "")).strip()
        if value.isdigit():
            numeric_versions.append(int(value))

    if numeric_versions:
        return str(max(numeric_versions) + 1)

    return str(int(time.time()))


def create_agent_version_via_api(agent_name: str, agent_version_data: Dict[str, Any], production_resource: Optional[str] = None, production_subscription: Optional[str] = None, production_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a v2 agent version using the v2 API endpoint.
    
    Args:
        agent_name: The agent name (without version)
        agent_version_data: The agent version payload matching v2 API format
        production_resource: Optional production resource name (e.g., "<your-resource-name>")
        production_subscription: Optional production subscription ID
        production_token: Optional production token for authentication
    
    Returns:
        API response data
    """
    # Build the v2 API endpoint URL based on mode (production vs local)
    # Ensure agent name satisfies the v2 API constraints before using it in the URL.
    agent_name = sanitize_agent_name(agent_name)
    
    if PRODUCTION_ENDPOINT_OVERRIDE:
        # Direct endpoint override — use as-is
        url = f"{PRODUCTION_ENDPOINT_OVERRIDE.rstrip('/')}/agents/{agent_name}/versions"
        print(f"🏭 Using PRODUCTION endpoint (direct override)")
    elif production_resource and production_subscription:
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
        effective_token = production_token or PRODUCTION_TOKEN
        if production_resource and effective_token:
            print(f"   🔑 Using production token for authentication")
            response = do_api_request_with_token("POST", url, effective_token, params=params, json=agent_version_data)
        else:
            print(f"   🔑 Using standard token for authentication")
            response = do_api_request("POST", url, params=params, json=agent_version_data)
        result = response.json()
        
        print(f"✅ Successfully created agent version via v2 API")
        print(f"   Response ID: {result.get('id', 'N/A')}")
        
        return result
        
    except requests.exceptions.HTTPError as e:
        print(f"❌ Failed to create agent version via v2 API: {e}")
        if hasattr(e, 'response') and e.response is not None:
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

# Global connection mapping: source connection name -> target project_connection_id
# Populated by --connection-map arg or auto-discovery
# IMPORTANT: The v2 portal agent runner resolves project_connection_id by FULL ARM PATH, e.g.:
#   /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices
#   /accounts/{acc}/projects/{proj}/connections/{conn_name}
# Short names and displayNames only work for the Responses API, NOT the portal agent runner.
CONNECTION_MAP: Dict[str, str] = {}

# Target project ARM path prefix — set by _build_target_arm_prefix() when target endpoint is known.
# Used to build full ARM paths for project_connection_id values.
TARGET_PROJECT_ARM_PREFIX: str = ""  # e.g. '/subscriptions/.../projects/proj'


def extract_connection_name_from_arm_path(arm_path: str) -> str:
    """
    Extract the connection name from a full ARM resource path.
    E.g., '/subscriptions/.../connections/hengylbinggrounding' -> 'hengylbinggrounding'
    """
    if '/connections/' in arm_path:
        return arm_path.split('/connections/')[-1]
    return arm_path


def get_v2_connection_id(connection: Dict[str, Any]) -> str:
    """
    Get the correct v2 project_connection_id for a connection object.
    
    The v2 portal agent runner resolves project_connection_id by FULL ARM PATH:
      /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices
      /accounts/{acc}/projects/{proj}/connections/{conn_name}
    
    Short names and displayNames only work for the Responses API (different code path).
    This function builds the full ARM path using TARGET_PROJECT_ARM_PREFIX if set,
    otherwise falls back to the raw connection name with a warning.
    
    Args:
        connection: A connection object from the connections API
        
    Returns:
        The full ARM path to use as project_connection_id in v2 agent definitions
    """
    conn_name = connection.get('name', '')
    
    if TARGET_PROJECT_ARM_PREFIX:
        return f"{TARGET_PROJECT_ARM_PREFIX}/connections/{conn_name}"
    
    # Fallback: no prefix set — warn and return raw name
    print(f"   ⚠️  TARGET_PROJECT_ARM_PREFIX not set; returning raw name '{conn_name}' as project_connection_id (may fail in portal agent runner)")
    return conn_name


def resolve_connection_id(v1_connection_id: str) -> str:
    """
    Resolve a v1 connection_id (full ARM path) to a v2 project_connection_id.
    
    1. If the connection name is in CONNECTION_MAP, use the mapped target connection name
       and build a full ARM path via TARGET_PROJECT_ARM_PREFIX.
    2. Otherwise, extract the connection name from the ARM path and build the ARM path.
    
    The v2 portal agent runner requires a full ARM path as project_connection_id.
    """
    source_name = extract_connection_name_from_arm_path(v1_connection_id)
    
    if source_name in CONNECTION_MAP:
        target_conn_name = CONNECTION_MAP[source_name]
        # Strip any existing ARM prefix from the mapped value (it should be just a name)
        target_conn_name = extract_connection_name_from_arm_path(target_conn_name)
        if TARGET_PROJECT_ARM_PREFIX:
            full_path = f"{TARGET_PROJECT_ARM_PREFIX}/connections/{target_conn_name}"
            print(f"     🔗 Connection mapped: '{source_name}' -> '{full_path}'")
            return full_path
        print(f"     🔗 Connection mapped: '{source_name}' -> '{target_conn_name}' (no ARM prefix set)")
        return target_conn_name
    
    # No mapping — build ARM path from source name directly
    if TARGET_PROJECT_ARM_PREFIX:
        full_path = f"{TARGET_PROJECT_ARM_PREFIX}/connections/{source_name}"
        print(f"     ⚠️  No mapping for '{source_name}', using ARM path: '{full_path}'")
        return full_path
    
    print(f"     ⚠️  Connection '{source_name}' (no mapping, no ARM prefix — may fail in v2 portal)")
    return source_name


def remap_connection_ids_in_tool(tool_data: Any) -> Any:
    """
    Recursively walk a tool data structure and:
    - Rename 'connection_id' and 'index_connection_id' keys to 'project_connection_id'
    - Resolve ARM paths to short connection names via CONNECTION_MAP
    """
    if isinstance(tool_data, dict):
        result = {}
        for key, value in tool_data.items():
            if key in ('connection_id', 'index_connection_id'):
                # Rename and resolve
                resolved = resolve_connection_id(str(value)) if value else value
                result['project_connection_id'] = resolved
            else:
                result[key] = remap_connection_ids_in_tool(value)
        return result
    elif isinstance(tool_data, list):
        return [remap_connection_ids_in_tool(item) for item in tool_data]
    return tool_data


def _normalize_bing_search_configurations(
    bing_config: Dict[str, Any],
    *,
    default_values: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Normalize Bing tool config into v2 ``search_configurations`` format."""
    default_values = default_values or {}
    raw_configs = bing_config.get("search_configurations")

    if isinstance(raw_configs, list) and raw_configs:
        normalized_configs: List[Dict[str, Any]] = []
        for raw_config in raw_configs:
            if not isinstance(raw_config, dict):
                continue

            connection_id = (
                raw_config.get("connection_id")
                or raw_config.get("project_connection_id")
                or bing_config.get("connection_id")
                or ""
            )
            normalized = {
                "project_connection_id": resolve_connection_id(connection_id) if connection_id else connection_id
            }
            for key, value in default_values.items():
                normalized[key] = raw_config.get(key, value)
            for key, value in raw_config.items():
                if key in {"connection_id", "project_connection_id"}:
                    continue
                if value is not None:
                    normalized[key] = value
            normalized_configs.append(normalized)

        if normalized_configs:
            return normalized_configs

    connection_id = bing_config.get("connection_id", "")
    normalized = {
        "project_connection_id": resolve_connection_id(connection_id) if connection_id else connection_id
    }
    for key, value in default_values.items():
        normalized[key] = bing_config.get(key, value)
    return [normalized]


def build_connection_map_from_projects(
    source_connections: List[Dict[str, Any]], 
    target_connections: List[Dict[str, Any]]
) -> Dict[str, str]:
    """
    Auto-build a connection map by matching source connections to target connections
    by type/category. Returns a dict of source_name -> target_v2_id.

    The values are full ARM paths (when TARGET_PROJECT_ARM_PREFIX is set), as returned
    by get_v2_connection_id(). They are used directly as project_connection_id in v2
    agent definitions and do not need further processing by resolve_connection_id().
    """
    mapping: Dict[str, str] = {}
    
    # Build target lookup by type
    target_by_type: Dict[str, List[Dict[str, Any]]] = {}
    for tc in target_connections:
        ctype = tc.get('properties', {}).get('category', tc.get('type', 'unknown'))
        meta_type = tc.get('metadata', {}).get('type', '')
        for t in [ctype, meta_type]:
            if t:
                target_by_type.setdefault(t, []).append(tc)
    
    # Log all target connections with their v2 IDs for debugging
    print("   📋 Target connections (v2 resolution):")
    for tc in target_connections:
        tc_name = tc.get('name', '')
        tc_v2_id = get_v2_connection_id(tc)
        tc_type = tc.get('properties', {}).get('category', tc.get('type', 'unknown'))
        display_note = f" (v2_id: '{tc_v2_id}')" if tc_v2_id != tc_name else " (v2_id: same as name)"
        print(f"      • {tc_name}{display_note} [{tc_type}]")
    
    # Match source to target by type
    for sc in source_connections:
        src_name = sc.get('name', '')
        src_type = sc.get('properties', {}).get('category', sc.get('type', 'unknown'))
        src_meta_type = sc.get('metadata', {}).get('type', '')
        
        # Try matching by category first, then metadata type
        for match_type in [src_type, src_meta_type]:
            if match_type and match_type in target_by_type:
                candidates = target_by_type[match_type]
                
                # Filter to candidates that have a displayName set (preferred for v2)
                candidates_with_display = [c for c in candidates if c.get('metadata', {}).get('displayName')]
                
                if len(candidates_with_display) == 1:
                    # Prefer the candidate with a displayName (known to work in v2 runtime)
                    tgt = candidates_with_display[0]
                    tgt_v2_id = get_v2_connection_id(tgt)
                    mapping[src_name] = tgt_v2_id
                    print(f"   🔗 Auto-mapped: '{src_name}' ({match_type}) -> '{tgt_v2_id}' (displayName of '{tgt.get('name', '')}')")
                    break
                elif len(candidates) == 1:
                    # Only one candidate total — use its v2 ID
                    tgt = candidates[0]
                    tgt_v2_id = get_v2_connection_id(tgt)
                    mapping[src_name] = tgt_v2_id
                    print(f"   🔗 Auto-mapped: '{src_name}' ({match_type}) -> '{tgt_v2_id}'")
                    break
                elif len(candidates) > 1:
                    # Multiple candidates — prefer one with displayName, then exact name match
                    if len(candidates_with_display) > 0:
                        # Use the first candidate with a displayName
                        tgt = candidates_with_display[0]
                        tgt_v2_id = get_v2_connection_id(tgt)
                        mapping[src_name] = tgt_v2_id
                        print(f"   🔗 Auto-mapped (displayName preferred): '{src_name}' ({match_type}) -> '{tgt_v2_id}' (from {len(candidates)} candidates)")
                    else:
                        # No displayNames — try exact name match
                        exact = [c for c in candidates if c.get('name', '') == src_name]
                        if exact:
                            tgt_v2_id = get_v2_connection_id(exact[0])
                            mapping[src_name] = tgt_v2_id
                            print(f"   🔗 Auto-mapped (exact name): '{src_name}' ({match_type}) -> '{tgt_v2_id}'")
                        else:
                            tgt = candidates[0]
                            tgt_v2_id = get_v2_connection_id(tgt)
                            mapping[src_name] = tgt_v2_id
                            print(f"   ⚠️  Auto-mapped (first of {len(candidates)}, no displayName): '{src_name}' ({match_type}) -> '{tgt_v2_id}'")
                    break
        else:
            print(f"   ⚠️  No target match for source connection '{src_name}' (type: {src_type})")
    
    return mapping


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
        v1_name = v1_assistant.get("name")
        if v1_name:
            agent_name = v1_name
        else:
            # Build from ID: strip common prefixes (asst_, agent_) and use hyphens
            raw_id = v1_assistant.get('id', 'unknown')
            # Remove leading 'asst_' prefix if present
            clean_id = raw_id[5:] if raw_id.startswith('asst_') else raw_id
            # Replace underscores with hyphens for v2 API compliance
            clean_id = clean_id.replace('_', '-')
            agent_name = f"agent-{clean_id}"
    
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
                    # v2 API requires a top-level 'name' on the tool object
                    fn_name = tool["function"].get("name", "")
                    if fn_name:
                        transformed_tool["name"] = fn_name
            
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
                # v2 API requires 'azure_function' sub-object with:
                #   - function: {name, description, parameters}
                #   - input_binding:  {type: "storage_queue", storage_queue: {queue_service_endpoint, queue_name}}
                #   - output_binding: {type: "storage_queue", storage_queue: {queue_service_endpoint, queue_name}}
                af_config: Dict[str, Any] = {}

                # Build the 'function' sub-object from v1's top-level name/description/parameters
                fn_def: Dict[str, Any] = {}
                for key in ["name", "description", "parameters"]:
                    if key in tool:
                        fn_def[key] = tool[key]
                if fn_def:
                    af_config["function"] = fn_def

                # Map input_queue -> input_binding with storage_queue wrapper
                if "input_queue" in tool:
                    iq = tool["input_queue"]
                    af_config["input_binding"] = {
                        "type": "storage_queue",
                        "storage_queue": {
                            "queue_service_endpoint": iq.get("storage_service_endpoint", ""),
                            "queue_name": iq.get("queue_name", ""),
                        }
                    }
                # Map output_queue -> output_binding with storage_queue wrapper
                if "output_queue" in tool:
                    oq = tool["output_queue"]
                    af_config["output_binding"] = {
                        "type": "storage_queue",
                        "storage_queue": {
                            "queue_service_endpoint": oq.get("storage_service_endpoint", ""),
                            "queue_name": oq.get("queue_name", ""),
                        }
                    }

                transformed_tool["azure_function"] = af_config
                print(f"     Added Azure Function tool properties (nested): {list(af_config.keys())}")
            
            # Handle azure_ai_search tools — merge tool_resources inline
            elif tool_type == "azure_ai_search":
                # In v1, azure_ai_search config can be:
                # a) Inline in the tool object (tool.azure_ai_search.indexes)
                # b) In tool_resources.azure_ai_search.indexes (tool is bare {"type": "azure_ai_search"})
                # In v2, it must always be inline in the tool.
                search_config = tool.get("azure_ai_search", {})
                
                # If no inline config, pull from tool_resources
                if not search_config or not search_config.get("indexes"):
                    tr_search = v1_tool_resources.get("azure_ai_search", {})
                    if tr_search and tr_search.get("indexes"):
                        search_config = tr_search
                        print(f"     Merged azure_ai_search config from tool_resources")
                
                if search_config:
                    # Remap any connection_id fields in the search config
                    remapped = remap_connection_ids_in_tool(search_config)
                    indexes = remapped.get("indexes", [])
                    if isinstance(indexes, list):
                        cleaned_indexes = []
                        for idx in indexes:
                            if isinstance(idx, dict):
                                cleaned_indexes.append({k: v for k, v in idx.items() if v is not None})
                            else:
                                cleaned_indexes.append(idx)
                        remapped["indexes"] = cleaned_indexes
                    transformed_tool["azure_ai_search"] = remapped
                    
                    # Log what we found
                    indexes = remapped.get("indexes", [])
                    for idx in indexes:
                        if idx.get("index_asset_id"):
                            print(f"     azure_ai_search index: asset_id='{idx['index_asset_id']}'")
                        elif idx.get("project_connection_id") or idx.get("index_project_connection_id"):
                            conn_id = idx.get("project_connection_id", idx.get("index_project_connection_id", ""))
                            print(f"     azure_ai_search index: connection='{conn_id}', name='{idx.get('index_name', '')}'")
                else:
                    print(f"     ⚠️  azure_ai_search tool has no config in tool or tool_resources")
            
            # Handle fabric_dataagent tools — v1 uses connections[], v2 uses fabric_dataagent_preview.project_connections[]
            elif tool_type == "fabric_dataagent":
                # v1 format:
                #   fabric_dataagent.connections[].connection_id  (full ARM path already)
                # v2 format:
                #   fabric_dataagent_preview.project_connections[].project_connection_id
                v1_fabric = tool.get("fabric_dataagent", {})
                v1_connections = v1_fabric.get("connections", [])
                
                v2_project_connections = []
                for conn in v1_connections:
                    conn_id = conn.get("connection_id", "")
                    # connection_id in v1 Fabric is already a full ARM path — use as-is
                    entry: Dict[str, Any] = {"project_connection_id": conn_id}
                    if conn.get("instructions"):
                        entry["instructions"] = conn["instructions"]
                    v2_project_connections.append(entry)
                    print(f"     fabric_dataagent connection: '{conn_id}'")
                
                transformed_tool["fabric_dataagent_preview"] = {
                    "project_connections": v2_project_connections
                }
                
                # Copy any top-level instructions from the fabric config if present
                if v1_fabric.get("instructions"):
                    transformed_tool["fabric_dataagent_preview"]["instructions"] = v1_fabric["instructions"]
                
                print(f"     Transformed fabric_dataagent: {len(v2_project_connections)} connection(s) -> fabric_dataagent_preview")
            
            # Handle bing_grounding — v2 requires search_configurations array
            elif tool_type == "bing_grounding":
                v1_bing = tool.get("bing_grounding", {})
                transformed_tool["bing_grounding"] = {
                    "search_configurations": _normalize_bing_search_configurations(
                        v1_bing,
                        default_values={
                            "market": "en-us",
                            "set_lang": "en",
                            "count": 5,
                        },
                    )
                }
                print(
                    "     bing_grounding: normalized "
                    f"{len(transformed_tool['bing_grounding']['search_configurations'])} search configuration(s)"
                )

            # Handle bing_custom_search — v2 requires search_configurations array
            elif tool_type == "bing_custom_search":
                v1_bcs = tool.get("bing_custom_search", {})
                transformed_tool["bing_custom_search"] = {
                    "search_configurations": _normalize_bing_search_configurations(v1_bcs)
                }
                print(
                    "     bing_custom_search: normalized "
                    f"{len(transformed_tool['bing_custom_search']['search_configurations'])} search configuration(s)"
                )

            # Handle sharepoint_grounding — remap connection_id to project_connection_id
            elif tool_type == "sharepoint_grounding":
                v1_sp = tool.get("sharepoint_grounding", {})
                conn_id = v1_sp.get("connection_id", "")
                resolved_conn = resolve_connection_id(conn_id) if conn_id else conn_id
                transformed_tool["sharepoint_grounding"] = {
                    "project_connection_id": resolved_conn
                }
                print(f"     sharepoint_grounding: remapped connection '{resolved_conn}'")

            # Handle other platform tools that need connection_id -> project_connection_id remapping
            elif tool_type in PLATFORM_TOOL_TYPES:
                # Copy all properties except 'type', but remap connection_id -> project_connection_id
                for key, value in tool.items():
                    if key == "type":
                        continue
                    # Recursively remap connection_ids in nested structures
                    transformed_tool[key] = remap_connection_ids_in_tool(value)
                print(f"     Added platform tool '{tool_type}' with connection_id -> project_connection_id remapping")
            
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

def process_v1_assistants_to_v2_agents(args=None, assistant_id: Optional[str] = None, cosmos_connection_string: Optional[str] = None, use_api: bool = False, project_endpoint: Optional[str] = None, project_connection_string: Optional[str] = None, project_subscription: Optional[str] = None, project_resource_group: Optional[str] = None, project_name: Optional[str] = None, production_resource: Optional[str] = None, production_subscription: Optional[str] = None, production_tenant: Optional[str] = None, source_tenant: Optional[str] = None, only_with_tools: bool = False, only_without_tools: bool = False, migrate_connections: bool = False, production_endpoint: Optional[str] = None, migrate_files: bool = True, overwrite_already_migrated: bool = False):
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
        only_with_tools: If True, only migrate assistants that have at least one tool
        only_without_tools: If True, only migrate assistants that have no tools
        migrate_connections: If True, attempt to discover and recreate connections in target project
        production_endpoint: Optional full production URL (overrides production_resource URL construction)
        migrate_files: If True, download files and vector stores from the source and re-upload
            them via the target Foundry project endpoint so that file_search/code_interpreter references
            remain valid for agents.
        overwrite_already_migrated: If True, remigrate assistants that already have a
            v2 target agent with matching metadata.original_v1_id by creating a new version.
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
                print(f"   ⚠️  Failed to fetch assistant {assistant_id} from Foundry endpoint: {e}")
                print(f"   🔄 Attempting legacy OpenAI endpoint fallback...")
                try:
                    assistant_data = get_v1_assistant_from_openai_endpoint(project_endpoint, assistant_id)
                    v1_assistants = [assistant_data]
                except Exception as legacy_error:
                    print(f"❌ Failed to fetch assistant {assistant_id} from project: {legacy_error}")
                    return
        else:
            print("📊 Fetching all assistants from project")
            try:
                v1_assistants = list_assistants_from_project(project_endpoint, project_subscription, project_resource_group, project_name)
            except Exception as e:
                print(f"❌ Failed to fetch assistants from project: {e}")
                return
            
            # Also query the legacy OpenAI cognitiveservices endpoint to
            # pick up real v1 assistants that don't appear on the Foundry
            # endpoint.  These are stored on a completely separate backend.
            try:
                openai_assistants = list_v1_assistants_from_openai_endpoint(project_endpoint)
                if openai_assistants:
                    existing_ids = {a.get("id") or a.get("name") for a in v1_assistants}
                    added = 0
                    for asst in openai_assistants:
                        asst_id = asst.get("id") or asst.get("name") or ""
                        if asst_id and asst_id not in existing_ids:
                            v1_assistants.append(asst)
                            existing_ids.add(asst_id)
                            added += 1
                    if added:
                        print(f"   ➕ Added {added} v1 assistants from legacy OpenAI endpoint")
            except Exception as e2:
                print(f"   ⚠️  Could not query legacy OpenAI endpoint: {e2}")
        
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
    
    # ── Tool-based filtering ──────────────────────────────────────────
    if only_with_tools or only_without_tools:
        def _has_tools(assistant: Dict[str, Any]) -> bool:
            tools = assistant.get("tools", [])
            if isinstance(tools, str):
                try:
                    tools = json.loads(tools)
                except:
                    tools = []
            return isinstance(tools, list) and len(tools) > 0
        
        before_count = len(v1_assistants)
        if only_with_tools:
            v1_assistants = [a for a in v1_assistants if _has_tools(a)]
            print(f"🔧 --only-with-tools: filtered {before_count} → {len(v1_assistants)} assistants (keeping only those WITH tools)")
        else:
            v1_assistants = [a for a in v1_assistants if not _has_tools(a)]
            print(f"🔧 --only-without-tools: filtered {before_count} → {len(v1_assistants)} assistants (keeping only those WITHOUT tools)")
        
        if not v1_assistants:
            print("❌ No assistants remain after filtering. Nothing to migrate.")
            return
    
    # ── Connection discovery & migration ──────────────────────────────
    source_connections: List[Dict[str, Any]] = []
    if migrate_connections or only_with_tools:
        # Try to discover connections from the source project
        source_endpoint = project_endpoint  # connections API needs a project endpoint
        if source_endpoint:
            print("\n🔗 Discovering connections from source project...")
            source_connections = list_connections_from_project(source_endpoint)
            for conn in source_connections:
                conn_name = conn.get("name", "N/A")
                conn_type = conn.get("properties", {}).get("category", conn.get("type", "unknown"))
                conn_target = conn.get("properties", {}).get("target", conn.get("target", "N/A"))
                print(f"   • {conn_name} (type: {conn_type}, target: {conn_target})")
        else:
            print("\n⚠️  Cannot discover connections: --project-endpoint is required to read source connections.")
            print("   Connection migration requires reading from the source project's connections API.")
    
    # Print connection report for agents with tools
    if (migrate_connections or only_with_tools) and v1_assistants:
        agents_with_tools = [a for a in v1_assistants if get_agent_required_connections(a)]
        if agents_with_tools:
            print_connection_migration_report(agents_with_tools, source_connections)
    
    # Discover target connections for any assistants that rely on connection-backed tools.
    # This is needed even when source connection discovery was skipped, because the v2 portal
    # runner expects full ARM project_connection_id values and valid metadata.displayName.
    target_connections: List[Dict[str, Any]] = []
    assistants_requiring_connections = [a for a in v1_assistants if get_agent_required_connections(a)]
    if assistants_requiring_connections:
        if production_endpoint:
            target_ep = production_endpoint
        elif production_resource and production_subscription:
            target_ep = get_production_v2_base_url(production_resource, production_subscription, production_resource)
        else:
            target_ep = None

        if target_ep:
            print("\n🔗 Discovering target connections for runtime compatibility...")
            prod_token = PRODUCTION_TOKEN or TOKEN
            target_connections = list_connections_from_project(target_ep, prod_token)
            if target_connections:
                # Ensure all target connections have displayName set (required for v2 runtime)
                # and set TARGET_PROJECT_ARM_PREFIX so resolve_connection_id emits full ARM paths.
                _try_ensure_display_names(target_ep, target_connections, production_subscription)

    # Auto-build connection map if we have both source and target connections
    if source_connections and target_connections and not CONNECTION_MAP:
        auto_map = build_connection_map_from_projects(source_connections, target_connections)
        # Merge auto-map with explicit CLI mappings (CLI takes precedence)
        for k, v in auto_map.items():
            if k not in CONNECTION_MAP:
                CONNECTION_MAP[k] = v
        print(f"   📋 Connection map ({len(CONNECTION_MAP)} entries): {CONNECTION_MAP}")
    
    # Attempt to create connections in target if requested
    if migrate_connections and source_connections:
        # Determine target endpoint
        if production_endpoint:
            target_ep = production_endpoint
        elif production_resource and production_subscription:
            target_ep = get_production_v2_base_url(production_resource, production_subscription, production_resource)
        else:
            target_ep = None
        
        if target_ep:
            prod_token = PRODUCTION_TOKEN or TOKEN
            print(f"\n🔗 Attempting to create connections in target project...")
            print(f"   Target: {target_ep}")
            created_count = 0
            failed_count = 0
            for conn in source_connections:
                result = create_connection_in_target(target_ep, conn, prod_token)
                if result:
                    created_count += 1
                else:
                    failed_count += 1
            print(f"\n   📊 Connection migration: {created_count} created, {failed_count} failed")
            if failed_count > 0:
                print(f"   💡 Failed connections may need secrets (API keys) added manually in the target project portal")
        else:
            print("\n⚠️  Cannot create connections: need --production-endpoint or --production-resource to determine target")
    
    # Ensure we have API authentication for v2 API saving
    # Use source tenant for authentication (for reading v1 assistants)
    # Force refresh if we have production resource (might have switched tenants)
    force_refresh = production_resource is not None
    tenant_for_auth = source_tenant if source_tenant else SOURCE_TENANT
    if not TOKEN and not set_api_token(force_refresh=force_refresh, tenant_id=tenant_for_auth):
        print("❌ Error: Unable to obtain API authentication token for v2 API saving")
        print("Set AZ_TOKEN env var or ensure az CLI is installed and logged in")
        sys.exit(1)

    target_v2_endpoint = get_target_foundry_endpoint(
        production_resource=production_resource,
        production_endpoint=production_endpoint,
    )

    # Although a target endpoint using the legacy OpenAI-compatible host
    # (*.openai.azure.com) or the raw Cognitive Services host
    # (*.cognitiveservices.azure.com) WILL BE ACCEPTED for migration — those
    # hosts return HTTP 200 for the file/vector-store upload calls, so nothing
    # in the migration "fails" — it will NOT actually migrate files/vector
    # stores: the uploads land in a namespace the Foundry agent runtime can't
    # see, so file_search/code_interpreter stay broken on the migrated agent.
    # This wrong-but-accepted endpoint case is called out as a warning during
    # migration (printed up front and repeated in the final summary) rather
    # than treated as fatal, since callers who passed --no-migrate-files don't
    # care about this at all.
    file_migration_endpoint_warning: Optional[str] = None
    if migrate_files and target_v2_endpoint and not _is_foundry_host(target_v2_endpoint):
        file_migration_endpoint_warning = (
            f"--production-endpoint ({target_v2_endpoint}) is a legacy OpenAI-compatible "
            "(*.openai.azure.com) or Cognitive Services (*.cognitiveservices.azure.com) host, "
            "not a Foundry (*.services.ai.azure.com) host. This endpoint WILL BE ACCEPTED for "
            "migration — the upload calls succeed — but it will NOT migrate files/vector stores; "
            "they end up invisible to the Foundry agent runtime. Re-run with a Foundry-format "
            "--production-endpoint (or --production-resource) to migrate files successfully, "
            "or pass --no-migrate-files if you don't need files migrated."
        )
        print(f"\n⚠️  {file_migration_endpoint_warning}\n")

    # In-place upgrade (source == target): when no explicit target was supplied
    # but the source project is itself a Foundry endpoint, reuse it as the target
    # so the duplicate-migration guard still runs. Without this, re-running the
    # migration against the same project would create duplicate v2 agents.
    if not target_v2_endpoint:
        inplace_target = _source_endpoint_as_dedupe_target(project_endpoint)
        if inplace_target:
            target_v2_endpoint = inplace_target
            print(f"ℹ️  No explicit target; using source Foundry endpoint as target for dedupe: {target_v2_endpoint}")

    existing_migrations: Dict[str, Dict[str, Any]] = {}
    target_api_token = PRODUCTION_TOKEN
    if not target_api_token and target_v2_endpoint:
        target_scope = _infer_scope_for_url(target_v2_endpoint)
        if TOKEN_SCOPE != target_scope:
            set_api_token(force_refresh=True, scope=target_scope)
        target_api_token = TOKEN
    if target_v2_endpoint:
        try:
            existing_migrations = get_existing_migrated_agents_by_v1_id(target_v2_endpoint, token=target_api_token)
            if existing_migrations:
                print(f"📚 Found {len(existing_migrations)} existing migrated v2 agent(s) in target project")
        except Exception as e:
            print(f"⚠️  Could not inspect existing migrated v2 agents: {e}")
            print("   Continuing without duplicate-migration safeguards")
            existing_migrations = {}
    
    # Now we have uniform v1_assistants list regardless of source
    # Process each v1 assistant
    processed_count = 0
    skipped_existing_count = 0
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
            
            assistant_id = str(v1_assistant.get('id', 'unknown'))

            existing_target = existing_migrations.get(assistant_id)
            forced_agent_name: Optional[str] = None
            target_version = "1"
            if existing_target:
                if not overwrite_already_migrated:
                    print(
                        f"   ⏭️  Skipping already migrated assistant '{assistant_id}' -> "
                        f"agent '{existing_target.get('agent_name', '?')}' "
                        f"(latest version {existing_target.get('latest_version', '?')})"
                    )
                    skipped_existing_count += 1
                    continue

                forced_agent_name = existing_target.get('agent_name') or None
                if target_v2_endpoint and forced_agent_name:
                    target_version = get_next_agent_version(target_v2_endpoint, forced_agent_name, token=target_api_token)
                else:
                    target_version = "2"
                print(
                    f"   ♻️  Re-migrating already migrated assistant '{assistant_id}' into "
                    f"agent '{forced_agent_name or v1_assistant.get('name', '?')}' as version {target_version}"
                )
            
            print(f"   Assistant ID: {assistant_id}")
            print(f"   Assistant Name: {v1_assistant.get('name', 'N/A')}")
            print(f"   Assistant Model: {v1_assistant.get('model', 'N/A')}")
            
            # Preview the detected agent kind
            detected_kind = determine_agent_kind(v1_assistant)
            print(f"   🔍 Detected Agent Kind: {detected_kind}")
            
            # Convert v1 to v2
            v2_agent = v1_assistant_to_v2_agent(v1_assistant, agent_name=forced_agent_name, version=target_version)
            
            # ── File migration ────────────────────────────────────
            # Download files / vector stores from the source endpoint
            # and re-upload to the target's Foundry endpoint so that
            # file_search and code_interpreter references resolve.
            # NOTE: Files MUST be uploaded via the Foundry endpoint
            # (*.services.ai.azure.com), NOT the OpenAI endpoint
            # (*.openai.azure.com). The Foundry agent runtime only
            # sees resources in the Foundry namespace.
            file_id_map: Dict[str, str] = {}
            vs_id_map: Dict[str, str] = {}
            if migrate_files:
                # Determine source endpoint based on where the v1 assistant was discovered.
                source_origin = v1_assistant.get("_source_endpoint")
                if source_origin == "openai" and project_endpoint:
                    source_ep = _derive_openai_endpoint(project_endpoint)
                    source_token = OPENAI_COMPAT_TOKEN or TOKEN
                else:
                    source_ep = project_endpoint or (f"https://{HOST}/openai" if HOST else None)
                    source_token = TOKEN
                target_foundry_ep = get_target_foundry_endpoint(production_resource, production_endpoint)
                if source_ep and target_foundry_ep:
                    remap = migrate_assistant_files(
                        source_endpoint=source_ep,
                        target_endpoint=target_foundry_ep,
                        v1_assistant=v1_assistant,
                        source_token=source_token,
                        target_token=PRODUCTION_TOKEN or TOKEN,
                    )
                    file_id_map = remap.get("file_id_map", {})
                    vs_id_map = remap.get("vs_id_map", {})
                    remap_failures = remap.get("failed_files", [])
                    if remap_failures:
                        print(f"   ⚠️  {len(remap_failures)} file(s) failed to migrate for this assistant — see details above; these need manual follow-up.")
                        record_file_migration_failures(v1_assistant.get("id", "unknown"), remap_failures)
                elif not source_ep:
                    print("   ⚠️  Cannot migrate files: no source endpoint available")
                elif not target_foundry_ep:
                    print("   ⚠️  Cannot migrate files: unable to derive target Foundry endpoint")
            
            # Apply remapping to v2 agent payload
            if file_id_map or vs_id_map:
                v2_agent = apply_file_id_remapping(v2_agent, file_id_map, vs_id_map)
            
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
    if skipped_existing_count:
        print(f"   Already migrated records skipped: {skipped_existing_count}")
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

    if file_migration_endpoint_warning:
        print(f"\n⚠️  File/vector-store migration warning: {file_migration_endpoint_warning}")


def _classify_v1_item(item: Dict[str, Any]) -> str:
    """
    Classify a v1 item as 'agent' (has platform/integration tools) or 'assistant' (plain / code-only).
    
    In the v1 API, both "assistants" and "agents" are returned by GET /assistants
    with IDs starting with 'asst_'. They are the same object type at the API level.
    
    The distinction is a UX/branding concept:
    - "Assistant": a plain conversational model, OR one with only OpenAI-native tools
      like code_interpreter and file_search (retrieval).
    - "Agent": has platform-level tools like bing_grounding, azure_ai_search,
      openapi, azure_function, connected_agent, fabric_dataagent, etc.
    """
    tools = item.get("tools", [])
    if isinstance(tools, str):
        try:
            tools = json.loads(tools)
        except:
            tools = []
    if not isinstance(tools, list):
        tools = []
    
    # OpenAI-native tools (don't make it an "agent" in Foundry terms)
    NATIVE_TOOL_TYPES = {"code_interpreter", "file_search", "retrieval", "function"}
    
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        tool_type = tool.get("type", "")
        if tool_type and tool_type not in NATIVE_TOOL_TYPES:
            return "agent"
    
    return "assistant"


def _format_tools_list(item: Dict[str, Any]) -> str:
    """Return a compact summary of tools on a v1 item."""
    tools = item.get("tools", [])
    if isinstance(tools, str):
        try:
            tools = json.loads(tools)
        except:
            tools = []
    if not isinstance(tools, list):
        return "(none)"
    if not tools:
        return "(none)"
    
    types = []
    for t in tools:
        if isinstance(t, dict):
            tt = t.get("type", "?")
            if tt == "function":
                fname = t.get("function", {}).get("name", "?")
                tt = f"function:{fname}"
            types.append(tt)
    return ", ".join(types)


def list_project_inventory(project_endpoint: str, source_tenant: Optional[str] = None) -> None:
    """
    List all v1 items in a project, showing everything that needs migration.
    This is the handler for --list mode.

    Queries TWO separate backends to get the full picture — both contain
    v1-style items that need migration to the v2 named-agent/versioned model
    (``project_client.agents.create_version(...)``):

      1. Foundry endpoint (portal "agents" page):
         {resource}.services.ai.azure.com/api/projects/{project}/assistants
         → Items created through the Foundry portal's agents experience.

      2. Legacy OpenAI endpoint (portal "assistants" page):
         {resource}.cognitiveservices.azure.com/openai/assistants
         → Items created through the older OpenAI-compatible experience.

    Items that appear on both are deduplicated by ID.
    """
    print("")
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║              📋  PROJECT INVENTORY  (read-only)                     ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print(f"   Endpoint: {project_endpoint}")
    print("")

    # Ensure we have a token for the source
    tenant_for_auth = source_tenant if source_tenant else SOURCE_TENANT
    if not TOKEN and not set_api_token(tenant_id=tenant_for_auth):
        print("❌ Error: Unable to obtain API authentication token")
        print("Set AZ_TOKEN env var or ensure az CLI is installed and logged in")
        sys.exit(1)

    had_endpoint_error = False

    # ── 1. Query Foundry endpoint (portal "agents" page) ──────────────
    print("   ── Querying Foundry endpoint (portal agents page) ──")
    try:
        foundry_items = list_assistants_from_project(project_endpoint)
        for item in foundry_items:
            if '_source_endpoint' not in item:
                item['_source_endpoint'] = 'foundry'
    except Exception as e:
        print(f"   ⚠️  Failed to list from Foundry endpoint: {e}")
        foundry_items = []
        had_endpoint_error = True

    # ── 2. Query legacy OpenAI endpoint (portal "assistants" page) ────
    print("   ── Querying legacy OpenAI endpoint (portal assistants page) ──")
    openai_items = list_v1_assistants_from_openai_endpoint(project_endpoint)
    if LAST_LEGACY_OPENAI_QUERY_ERROR:
        had_endpoint_error = True

    # ── Merge & deduplicate ───────────────────────────────────────────
    seen_ids = set()
    merged = []

    for item in foundry_items:
        item_id = item.get("id") or item.get("name") or ""
        if item_id and item_id not in seen_ids:
            seen_ids.add(item_id)
            merged.append(item)

    for item in openai_items:
        item_id = item.get("id") or item.get("name") or ""
        if item_id and item_id not in seen_ids:
            seen_ids.add(item_id)
            merged.append(item)
        elif not item_id:
            merged.append(item)

    items = merged

    if not items:
        if had_endpoint_error:
            print("   ❌ Unable to build a complete inventory because one or more endpoint queries failed.")
            sys.exit(1)
        print("   (no items found on either endpoint)")
        return

    # ── Separate by source for display ────────────────────────────────
    from_foundry = [i for i in items if i.get('_source_endpoint') != 'openai']
    from_openai  = [i for i in items if i.get('_source_endpoint') == 'openai']

    # Summary
    total = len(items)
    print(f"   Total v1 items found: {total}  (all need migration to v2)")
    if from_foundry:
        print(f"   ├─ From Foundry endpoint  (portal agents page):      {len(from_foundry)}")
    if from_openai:
        print(f"   ├─ From OpenAI endpoint   (portal assistants page):  {len(from_openai)}")
    print(f"   └─ v2 agents use named agents with versions — these items are all v1.")
    print("")

    # ── Print helper ──────────────────────────────────────────────────
    def _print_item(index: int, a: Dict[str, Any], show_source: bool = False) -> None:
        aid = a.get("id", "?")
        name = a.get("name", "(unnamed)")
        model = a.get("model", "?")
        tools_str = _format_tools_list(a)
        created = a.get("created_at", "")
        source = a.get("_source_endpoint", "?")
        print(f"   {index}. {aid}")
        print(f"      Name : {name}")
        print(f"      Model: {model}")
        if tools_str != "(none)":
            print(f"      Tools: {tools_str}")
        if show_source:
            source_label = "Foundry (agents page)" if source != 'openai' else "OpenAI (assistants page)"
            print(f"      Source: {source_label}")
        if created:
            if isinstance(created, (int, float)):
                from datetime import datetime
                created = datetime.fromtimestamp(created).strftime('%Y-%m-%d %H:%M')
            print(f"      Created: {created}")
        print("")

    # If items came from both sources, show them in separate sections
    if from_foundry and from_openai:
        print("─── 🤖 FROM FOUNDRY ENDPOINT (portal agents page) ───────────────────")
        print("   Created through the Foundry agents experience.  Needs migration to v2.")
        print("")
        for i, a in enumerate(from_foundry, 1):
            _print_item(i, a)

        print("─── 💬 FROM OPENAI ENDPOINT (portal assistants page) ─────────────────")
        print("   Created through the older assistants experience.  Needs migration to v2.")
        print("")
        for i, a in enumerate(from_openai, 1):
            _print_item(i, a)
    else:
        # Only one source — show a single flat list
        source_label = "Foundry agents page" if from_foundry else "OpenAI assistants page"
        print(f"─── 📋 MIGRATION CANDIDATES (from {source_label}) ───────────────────")
        print(f"   All items need migration to v2 named agents.")
        print("")
        for i, a in enumerate(items, 1):
            _print_item(i, a)

    # Migration hints
    print("─── 💡 NEXT STEPS ──────────────────────────────────────────────────")
    print(f"   Migrate ALL:            migrate.ps1 --resource-id <your-resource-id>")
    print(f"   Migrate agents only:    migrate.ps1 --resource-id <your-resource-id> --only-with-tools")
    print(f"   Migrate assistants only: migrate.ps1 --resource-id <your-resource-id> --only-without-tools")
    print(f"   Migrate one by ID:      migrate.ps1 --resource-id <your-resource-id> asst_xxxxx")
    print("")


def main():
    """
    Main function to orchestrate the v1 to v2 migration.
    """
    parser = argparse.ArgumentParser(
        description="Migrate v1 OpenAI Assistants to v2 Azure ML Agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Migrate ONLY agents with tools from source project to target (with direct endpoint)
  python v1_to_v2_migration.py --only-with-tools \\
    --project-endpoint "https://<source-resource>.services.ai.azure.com/api/projects/<source-project>" \\
    --production-endpoint "https://<target-resource>.services.ai.azure.com/api/projects/<target-project>" \\
    --production-resource <target-resource> \\
    --production-subscription <your-subscription-id> \\
    --production-tenant <your-tenant-id>
  
  # Migrate agents with tools AND attempt to copy connections
  python v1_to_v2_migration.py --only-with-tools --migrate-connections \\
    --project-endpoint "https://<source-resource>.services.ai.azure.com/api/projects/<source-project>" \\
    --production-endpoint "https://<target-resource>.services.ai.azure.com/api/projects/<target-project>" \\
    --production-resource <target-resource> \\
    --production-subscription <your-subscription-id> \\
    --production-tenant <your-tenant-id>
  
  # Migrate ONLY plain agents (no tools)
  python v1_to_v2_migration.py --only-without-tools \\
    --production-resource <your-resource-name> \\
    --production-subscription <your-subscription-id> \\
    --production-tenant <your-tenant-id>
  
  # Migrate from v1 API to production v2 API (REQUIRED production parameters)
  python v1_to_v2_migration.py --use-api \\
    --source-tenant <your-source-tenant-id> \\
    --production-resource <your-resource-name> \\
    --production-subscription <your-subscription-id> \\
    --production-tenant <your-tenant-id> \\
    asst_xxxxxxxxxxxxxxxxxxxxxxxx
  
  # Migrate all assistants from Cosmos DB to production v2 API
  python v1_to_v2_migration.py \\
    --production-resource <your-resource-name> \\
    --production-subscription <your-subscription-id> \\
    --production-tenant <your-tenant-id>
  
  # Migrate from project endpoint using direct production endpoint (no URL guessing)
  python v1_to_v2_migration.py \\
    --project-endpoint "https://your-project.api.azure.com/api/projects/p-3" \\
    --production-endpoint "https://target-resource.services.ai.azure.com/api/projects/target" \\
    --production-resource target-resource \\
    --production-subscription <your-subscription-id> \\
    --production-tenant <your-tenant-id> \\
    asst_abc123
  
  # Note: Use run-migration-docker-auth.ps1 for automatic dual-tenant authentication
  
  # Read from project connection string (requires azure-ai-projects==1.0.0b10)
  python v1_to_v2_migration.py --project-connection-string "eastus.api.azureml.ms;subscription-id;resource-group;project-name"
  python v1_to_v2_migration.py asst_abc123 --project-connection-string "eastus.api.azureml.ms;subscription-id;resource-group;project-name"
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
        '--list',
        action='store_true',
        help='List all v1 assistants/agents in the project WITHOUT migrating. '
             'Shows a categorized inventory: assistants (no tools) vs agents (with tools). '
             'Does not require --production-resource/subscription/tenant.'
    )

    # Tool filtering arguments (mutually exclusive)
    tools_filter_group = parser.add_mutually_exclusive_group()
    tools_filter_group.add_argument(
        '--only-with-tools',
        action='store_true',
        help='Only migrate agents that have at least one tool configured (e.g., bing_grounding, file_search, etc.).'
    )
    tools_filter_group.add_argument(
        '--only-without-tools',
        action='store_true',
        help='Only migrate agents that have NO tools configured (plain conversational agents).'
    )
    
    parser.add_argument(
        '--migrate-connections',
        action='store_true',
        help='Attempt to discover connections from the source project and recreate them in the target project. '
             'Requires --project-endpoint for the source. Secrets (API keys) may not transfer and will need manual entry.'
    )
    
    parser.add_argument(
        '--connection-map',
        type=str,
        action='append',
        metavar='SOURCE=TARGET',
        help='Map a source connection name to a target connection identifier. '
             'The TARGET value should be either the connection name (short name) or a full ARM resource ID for the '
             'connection. When using a target project ARM prefix, a short TARGET value will be appended as '
             '"/connections/{TARGET}" to the prefix. Can be specified multiple times. '
             'Example: --connection-map hengylbinggrounding=hengyl-binggrounding'
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
    
    # Production Resource Arguments (required for migration, NOT required for --list)
    parser.add_argument(
        '--production-resource',
        type=str,
        help='Production Azure AI resource name (required for migration). Example: "<your-resource-name>". '
             'If the name already ends with "-resource", it will NOT be doubled.'
    )
    
    parser.add_argument(
        '--production-subscription', 
        type=str,
        help='Production subscription ID (required for migration). Example: "<your-subscription-id>"'
    )
    
    parser.add_argument(
        '--production-tenant',
        type=str,
        help='Production tenant ID for Azure authentication (required for migration). Example: "<your-tenant-id>"'
    )
    
    parser.add_argument(
        '--production-endpoint',
        type=str,
        help='Full production v2 API base URL (overrides --production-resource URL construction). '
             'Example: "https://<your-resource-name>.services.ai.azure.com/api/projects/<your-project-name>"'
    )
    
    parser.add_argument(
        '--source-tenant',
        type=str,
        help='Source tenant ID for reading v1 assistants. If not provided, uses the SOURCE_TENANT or AGENTS_TENANT environment variable, or falls back to the caller\'s default tenant. Example: "<your-tenant-id>"'
    )
    
    # File migration is enabled by default; use --no-migrate-files to disable it.
    parser.set_defaults(migrate_files=True)
    parser.add_argument(
        '--no-migrate-files',
        dest='migrate_files',
        action='store_false',
        help='Skip file/vector-store migration. By default, files and vector stores are '
             'downloaded from the source and re-uploaded via the target Foundry project '
             'endpoint (*.services.ai.azure.com) so that file_search/code_interpreter '
             'references remain valid. Pass this flag to copy agent definitions only '
             '(source file IDs will be broken on the target).'
    )

    parser.add_argument(
        '--overwrite-already-migrated',
        action='store_true',
        help='By default, assistants that already have a migrated v2 agent in the target '
             'project are skipped based on metadata.original_v1_id. Pass this flag to '
             're-migrate them by creating a new version on the existing target agent.'
    )
    
    args = parser.parse_args()
    
    # Handle empty string as None for assistant_id
    assistant_id = args.assistant_id if args.assistant_id and args.assistant_id.strip() else None
    cosmos_connection_string = args.cosmos_endpoint if args.cosmos_endpoint and args.cosmos_endpoint.strip() else None
    
    # Validate production args are present when NOT in --list mode
    if not args.list:
        missing = []
        if not args.production_resource:     missing.append('--production-resource')
        if not args.production_subscription: missing.append('--production-subscription')
        if not args.production_tenant:       missing.append('--production-tenant')
        if missing:
            parser.error(f"The following arguments are required for migration: {', '.join(missing)}\n"
                         f"Tip: use --list to preview what's in the project without migrating.")
    
    # Set global production endpoint override if provided
    global PRODUCTION_ENDPOINT_OVERRIDE, CONNECTION_MAP
    if args.production_endpoint:
        PRODUCTION_ENDPOINT_OVERRIDE = args.production_endpoint
    
    # Parse connection map from CLI args
    if args.connection_map:
        for mapping in args.connection_map:
            if '=' in mapping:
                src, tgt = mapping.split('=', 1)
                CONNECTION_MAP[src.strip()] = tgt.strip()
                print(f"🔗 Connection mapping: '{src.strip()}' -> '{tgt.strip()}'")
            else:
                print(f"⚠️  Invalid connection mapping (expected SOURCE=TARGET): {mapping}")
    
    # ── List mode: show inventory and exit ──────────────────────────────
    if args.list:
        endpoint = args.project_endpoint or args.production_endpoint
        if not endpoint:
            # Try to construct from production-resource if provided
            if args.production_resource:
                res = args.production_resource
                endpoint = f"https://{res}.services.ai.azure.com/api/projects/{res}"
            else:
                parser.error("--list requires --project-endpoint (or --production-endpoint, or --production-resource) "
                             "to know which project to list.\n"
                             "Example: --list --project-endpoint \"https://my-resource.services.ai.azure.com/api/projects/my-project\"")
        list_project_inventory(endpoint, source_tenant=args.source_tenant)
        return
    
    print("🚀 Starting v1 to v2 Agent Migration")
    print("=" * 50)
    
    # Production parameters are required
    print(f"🏭 Production v2 API Configuration:")
    print(f"   🎯 Resource: {args.production_resource}")
    print(f"   📋 Subscription: {args.production_subscription}")
    print(f"   🔐 Tenant: {args.production_tenant}")
    if args.production_endpoint:
        print(f"   🌐 Endpoint Override: {args.production_endpoint}")
    else:
        # Show the URL that will be constructed
        computed_url = get_production_v2_base_url(args.production_resource, args.production_subscription, args.production_resource)
        print(f"   🌐 Computed URL: {computed_url}")
    
    if PRODUCTION_TOKEN:
        print(f"   ✅ Production token available (length: {len(PRODUCTION_TOKEN)})")
    else:
        print("   ⚠️  No PRODUCTION_TOKEN environment variable found")
        print("   💡 Use run-migration-docker-auth.ps1 for automatic dual-token authentication")
    
    if args.only_with_tools:
        print("🔧 Filter: --only-with-tools (agents WITH tools only)")
    elif args.only_without_tools:
        print("🔧 Filter: --only-without-tools (agents WITHOUT tools only)")
    
    if args.migrate_connections:
        print("🔗 Connection migration: ENABLED")
    
    if args.migrate_files:
        target_foundry = get_target_foundry_endpoint(args.production_resource, args.production_endpoint)
        print(f"📂 File migration: ENABLED (target Foundry endpoint: {target_foundry})")
    else:
        print("📂 File migration: DISABLED (--no-migrate-files)")
    
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
    if args.production_endpoint:
        print(f"🏭 Saving agents via PRODUCTION v2 API (endpoint: {args.production_endpoint})")
    elif args.production_resource:
        print(f"🏭 Saving agents via PRODUCTION v2 API (resource: {args.production_resource})")
        print(f"   📋 Production subscription: {args.production_subscription}")
    else:
        print("🚀 Saving agents via PROD v2 API")
    
    print("=" * 50)
    
    process_v1_assistants_to_v2_agents(
        args, assistant_id, cosmos_connection_string, args.use_api, 
        args.project_endpoint, args.project_connection_string, args.project_subscription, 
        args.project_resource_group, args.project_name, args.production_resource, 
        args.production_subscription, args.production_tenant, args.source_tenant,
        only_with_tools=args.only_with_tools,
        only_without_tools=args.only_without_tools,
        migrate_connections=args.migrate_connections,
        production_endpoint=args.production_endpoint,
        migrate_files=args.migrate_files,
        overwrite_already_migrated=args.overwrite_already_migrated,
    )

if __name__ == "__main__":
    main()