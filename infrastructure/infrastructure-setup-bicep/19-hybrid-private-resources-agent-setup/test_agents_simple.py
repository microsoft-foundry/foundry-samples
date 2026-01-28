#!/usr/bin/env python3
"""
Simple Agents v2 Test Script
Tests different endpoint formats to find the correct one.
"""

import os
import ssl
import urllib.request
from azure.identity import DefaultAzureCredential

# Configuration
ACCOUNT_NAME = "aiservicesaxy3"
PROJECT_NAME = "projectaxy3"
MODEL_NAME = "gpt-4o-mini"
MCP_SERVER_URL = "https://mcp-test-server.jollydune-20a0f709.westus2.azurecontainerapps.io"

# Possible endpoint formats
ENDPOINTS = [
    f"https://{ACCOUNT_NAME}.cognitiveservices.azure.com",
    f"https://{ACCOUNT_NAME}.openai.azure.com", 
    f"https://{ACCOUNT_NAME}.services.ai.azure.com",
]


def test_mcp_connectivity():
    """Test MCP server connectivity."""
    print("\n" + "="*60)
    print("TEST 1: MCP Server Connectivity")
    print("="*60)
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    try:
        req = urllib.request.Request(MCP_SERVER_URL)
        with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
            print(f"✓ MCP Server reachable: HTTP {response.getcode()}")
            return True
    except Exception as e:
        print(f"✗ MCP Server failed: {e}")
        return False


def test_endpoint_connectivity():
    """Test which endpoints are reachable."""
    print("\n" + "="*60)
    print("TEST 2: AI Services Endpoint Connectivity")
    print("="*60)
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    for endpoint in ENDPOINTS:
        try:
            req = urllib.request.Request(endpoint)
            with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
                print(f"✓ {endpoint}: HTTP {response.getcode()}")
        except urllib.error.HTTPError as e:
            print(f"~ {endpoint}: HTTP {e.code} (reachable but error: {e.reason})")
        except Exception as e:
            print(f"✗ {endpoint}: {type(e).__name__}")


def test_agents_with_projects_client():
    """Test using AIProjectClient."""
    print("\n" + "="*60)
    print("TEST 3: AIProjectClient (azure-ai-projects)")
    print("="*60)
    
    from azure.ai.projects import AIProjectClient
    
    for endpoint in ENDPOINTS:
        print(f"\nTrying: {endpoint}")
        try:
            client = AIProjectClient(
                credential=DefaultAzureCredential(),
                endpoint=endpoint,
            )
            
            # Try to create an agent
            agent = client.agents.create_agent(
                model=MODEL_NAME,
                name="test-agent",
                instructions="Say hello.",
            )
            print(f"✓ SUCCESS! Created agent: {agent.id}")
            
            # Cleanup
            client.agents.delete_agent(agent.id)
            print(f"  Deleted agent")
            return endpoint
            
        except Exception as e:
            print(f"✗ Failed: {type(e).__name__}: {str(e)[:100]}")
    
    return None


def test_agents_direct():
    """Test using AgentsClient directly."""
    print("\n" + "="*60)
    print("TEST 4: AgentsClient (azure-ai-agents direct)")
    print("="*60)
    
    try:
        from azure.ai.agents import AgentsClient
    except ImportError:
        print("  AgentsClient not available in this SDK version")
        return None
    
    for endpoint in ENDPOINTS:
        print(f"\nTrying: {endpoint}")
        try:
            client = AgentsClient(
                credential=DefaultAzureCredential(),
                endpoint=endpoint,
            )
            
            agent = client.create_agent(
                model=MODEL_NAME,
                name="test-agent",
                instructions="Say hello.",
            )
            print(f"✓ SUCCESS! Created agent: {agent.id}")
            
            client.delete_agent(agent.id)
            print(f"  Deleted agent")
            return endpoint
            
        except Exception as e:
            print(f"✗ Failed: {type(e).__name__}: {str(e)[:100]}")
    
    return None


def test_rest_api_directly():
    """Test the REST API directly to understand the error."""
    print("\n" + "="*60)
    print("TEST 5: Direct REST API Call")
    print("="*60)
    
    import json
    
    credential = DefaultAzureCredential()
    token = credential.get_token("https://cognitiveservices.azure.com/.default")
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    # Try different API paths
    api_paths = [
        "/openai/assistants?api-version=2024-05-01-preview",
        "/agents?api-version=2024-12-01-preview",
        "/openai/agents?api-version=2024-12-01-preview",
    ]
    
    for endpoint in ENDPOINTS:
        print(f"\nEndpoint: {endpoint}")
        for path in api_paths:
            url = f"{endpoint}{path}"
            try:
                req = urllib.request.Request(url, method="GET")
                req.add_header("Authorization", f"Bearer {token.token}")
                req.add_header("Content-Type", "application/json")
                
                with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
                    print(f"  ✓ {path}: HTTP {response.getcode()}")
                    
            except urllib.error.HTTPError as e:
                body = e.read().decode('utf-8')[:200] if e.fp else ""
                print(f"  ~ {path}: HTTP {e.code} - {body}")
            except Exception as e:
                print(f"  ✗ {path}: {type(e).__name__}")


def main():
    print("="*60)
    print("AGENTS V2 ENDPOINT DISCOVERY TEST")
    print("="*60)
    
    test_mcp_connectivity()
    test_endpoint_connectivity()
    test_agents_with_projects_client()
    test_agents_direct()
    test_rest_api_directly()
    
    print("\n" + "="*60)
    print("DONE")
    print("="*60)


if __name__ == "__main__":
    main()
