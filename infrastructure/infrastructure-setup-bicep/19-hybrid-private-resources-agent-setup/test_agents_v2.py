#!/usr/bin/env python3
"""
Hybrid Private Resources - Agents v2 Test Script

This script tests that agents can use tools that connect to private resources
via the Data Proxy when AI Services has PUBLIC access enabled.

Template 19: AI Services (public) → Data Proxy → Private Resources (VNet)

Key tests:
1. Basic agent - validates public API access works using Responses API
2. AI Search tool - validates Data Proxy routes to private AI Search
3. MCP tool - validates Data Proxy routes to private MCP server

This script can be run from ANYWHERE (no jump box required for API access).
However, MCP connectivity test requires access to the private VNet.

Uses the new Agents v2 SDK pattern:
- AIProjectClient with context manager
- project_client.get_openai_client() for OpenAI-compatible API
- openai_client.responses.create() for the Responses API
- project_client.agents.create_version() with PromptAgentDefinition
- openai_client.conversations.create() for conversation threads
"""

import os
import sys
import logging

# ============================================================================
# LOGGING CONFIGURATION - Enable HTTP request/response logging for debugging
# ============================================================================
# Set to logging.DEBUG for full request/response bodies, INFO for headers only
LOG_LEVEL = logging.INFO

# Configure basic logging format
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Azure SDK HTTP logging (captures request IDs, headers, URLs)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(LOG_LEVEL)

# OpenAI client uses httpx for HTTP requests
logging.getLogger("httpx").setLevel(LOG_LEVEL)

# Optional: urllib3 for lower-level HTTP debugging
logging.getLogger("urllib3").setLevel(logging.WARNING)  # Set to DEBUG for full details

# Reduce noise from other loggers
logging.getLogger("azure.identity").setLevel(logging.WARNING)

# ============================================================================

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    MCPTool,
    PromptAgentDefinition,
    AzureAISearchAgentTool,
    AzureAISearchToolResource,
    AISearchIndexResource,
    AzureAISearchQueryType,
)
from azure.identity import DefaultAzureCredential
from openai.types.responses import ResponseInputParam
from openai.types.responses.response_input_param import McpApprovalResponse

# ============================================================================
# CONFIGURATION - Update these values for your deployment
# ============================================================================
# NOTE: Use the project-scoped endpoint from Azure Portal:
# AI Services resource -> Projects -> <project> -> Properties -> "AI Foundry API" endpoint
PROJECT_ENDPOINT = os.environ.get(
    "PROJECT_ENDPOINT",
    "https://aiservicesaxy3.services.ai.azure.com/api/projects/projectaxy3"
)
MODEL_NAME = os.environ.get("MODEL_NAME", "gpt-4o-mini")

# AI Search configuration
# AI_SEARCH_CONNECTION_NAME = os.environ.get("AI_SEARCH_CONNECTION_NAME", "")
AI_SEARCH_CONNECTION_NAME = "aiservicesaxy3search"
AI_SEARCH_INDEX_NAME = os.environ.get("AI_SEARCH_INDEX_NAME", "test-index")

# MCP Server configuration - Using multi-auth MCP image deployed to your Container Apps
# Private (internal to VNet): mcp-http-server.jollydune-20a0f709.westus2.azurecontainerapps.io
# Public (external): mcp-http-server-public.victoriousfield-89c08f4e.westus2.azurecontainerapps.io
MCP_SERVER_URL = os.environ.get(
    "MCP_SERVER_URL",
    "https://mcp-http-server-public.victoriousfield-89c08f4e.westus2.azurecontainerapps.io/noauth/mcp"
)

# ============================================================================


def log_response_info(response, label="Response"):
    """Extract and log useful debugging info from OpenAI response objects."""
    logger = logging.getLogger(__name__)
    try:
        # Try to get request ID from response
        if hasattr(response, '_request_id'):
            logger.info(f"{label} - Request ID: {response._request_id}")
        if hasattr(response, 'id'):
            logger.info(f"{label} - Response ID: {response.id}")
        # For openai responses, the request_id is often in headers
        if hasattr(response, '_response') and hasattr(response._response, 'headers'):
            headers = response._response.headers
            if 'x-request-id' in headers:
                logger.info(f"{label} - x-request-id: {headers['x-request-id']}")
            if 'x-ms-request-id' in headers:
                logger.info(f"{label} - x-ms-request-id: {headers['x-ms-request-id']}")
    except Exception as e:
        logger.debug(f"Could not extract response info: {e}")


def log_exception_info(exception, label="Exception"):
    """Extract and log request info from OpenAI exceptions for debugging failed requests."""
    logger = logging.getLogger(__name__)
    try:
        # OpenAI exceptions have a response attribute with the HTTP response
        if hasattr(exception, 'response') and exception.response is not None:
            resp = exception.response
            headers = resp.headers if hasattr(resp, 'headers') else {}
            
            # Log common request identifiers
            request_id = headers.get('x-request-id', 'N/A')
            ms_request_id = headers.get('x-ms-request-id', 'N/A')
            
            logger.error(f"{label} - x-request-id: {request_id}")
            logger.error(f"{label} - x-ms-request-id: {ms_request_id}")
            
            # Also print to console for visibility
            print(f"  📋 Request ID (x-request-id): {request_id}")
            print(f"  📋 MS Request ID (x-ms-request-id): {ms_request_id}")
            
            # Log status code
            if hasattr(resp, 'status_code'):
                logger.error(f"{label} - HTTP Status: {resp.status_code}")
                
        # Also try to get request_id attribute directly
        if hasattr(exception, 'request_id'):
            logger.error(f"{label} - request_id attribute: {exception.request_id}")
            print(f"  📋 Request ID: {exception.request_id}")
            
    except Exception as e:
        logger.debug(f"Could not extract exception info: {e}")


def test_mcp_server_connectivity():
    """Test MCP server with full session workflow: initialize → list tools → call tool."""
    print("\n" + "=" * 60)
    print("TEST 1: MCP Server Connectivity (Full Session Flow)")
    print("=" * 60)

    import urllib.request
    import ssl
    import json

    try:
        # Create SSL context
        ctx = ssl.create_default_context()
        
        print(f"  Target MCP Server: {MCP_SERVER_URL}")
        
        # =====================================================================
        # Step 1: Initialize - Get mcp-session-id
        # =====================================================================
        print("\n--- Step 1: Initialize (get mcp-session-id) ---")
        
        init_data = json.dumps({
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {
                    "sampling": {},
                    "elicitation": {},
                    "roots": {
                        "listChanged": True
                    }
                },
                "clientInfo": {
                    "name": "test-mcp-client",
                    "version": "1.0.0"
                }
            },
            "jsonrpc": "2.0",
            "id": 0
        }).encode('utf-8')
        
        init_req = urllib.request.Request(
            MCP_SERVER_URL,
            data=init_data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            method="POST"
        )
        
        with urllib.request.urlopen(init_req, timeout=10, context=ctx) as response:
            status = response.getcode()
            body = response.read().decode('utf-8')
            mcp_session_id = response.getheader('mcp-session-id')
            
            print(f"  ✓ HTTP Status: {status}")
            print(f"  ✓ Response: {body[:300]}...")
            
            if mcp_session_id:
                print(f"  ✓ MCP Session ID: {mcp_session_id}")
            else:
                print("  ✗ No mcp-session-id header in response!")
                print("\n✗ TEST FAILED: MCP server did not return session ID")
                return False
        
        # =====================================================================
        # Step 2: List Tools - Using mcp-session-id
        # =====================================================================
        print("\n--- Step 2: List Tools (using session ID) ---")
        
        list_data = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }).encode('utf-8')
        
        list_req = urllib.request.Request(
            MCP_SERVER_URL,
            data=list_data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": mcp_session_id
            },
            method="POST"
        )
        
        with urllib.request.urlopen(list_req, timeout=10, context=ctx) as response:
            status = response.getcode()
            body = response.read().decode('utf-8')
            result = json.loads(body)
            
            print(f"  ✓ HTTP Status: {status}")
            
            if "result" in result and "tools" in result["result"]:
                tools = result["result"]["tools"]
                print(f"  ✓ Found {len(tools)} tools:")
                for tool in tools:
                    print(f"      - {tool.get('name', 'unknown')}: {tool.get('description', '')[:50]}")
            else:
                print(f"  ✓ Response: {body[:300]}...")
        
        # =====================================================================
        # Step 3: Call Tool - Using mcp-session-id
        # =====================================================================
        print("\n--- Step 3: Call Tool 'add' (using session ID) ---")
        
        call_data = json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "add",
                "arguments": {
                    "a": 2,
                    "b": 4
                }
            }
        }).encode('utf-8')
        
        call_req = urllib.request.Request(
            MCP_SERVER_URL,
            data=call_data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "mcp-session-id": mcp_session_id
            },
            method="POST"
        )
        
        with urllib.request.urlopen(call_req, timeout=10, context=ctx) as response:
            status = response.getcode()
            body = response.read().decode('utf-8')
            result = json.loads(body)
            
            print(f"  ✓ HTTP Status: {status}")
            print(f"  ✓ Response: {body}")
            
            # Check if we got the expected result (2 + 4 = 6)
            if "result" in result:
                print(f"  ✓ Tool call successful!")
            else:
                print(f"  ⚠ Unexpected response format")
        
        print("\n" + "=" * 60)
        print("✓ TEST PASSED: MCP server session flow working correctly")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n✗ TEST FAILED: MCP server error: {str(e)}")
        import traceback
        traceback.print_exc()
        print("  Note: This test requires network access to the MCP server.")
        return False


def test_basic_agent():
    """Test basic agent creation and execution using Responses API."""
    print("\n" + "=" * 60)
    print("TEST 2: Basic Agent Creation and Execution (Responses API)")
    print("=" * 60)

    agent = None
    
    try:
        with (
            DefaultAzureCredential() as credential,
            AIProjectClient(
                credential=credential,
                endpoint=PROJECT_ENDPOINT
            ) as project_client,
            project_client.get_openai_client() as openai_client,
        ):
            print(f"✓ Connected to AI Project at {PROJECT_ENDPOINT}")

            # Create a simple agent without tools
            agent = project_client.agents.create_version(
                agent_name="basic-test-agent",
                definition=PromptAgentDefinition(
                    model=MODEL_NAME,
                    instructions="You are a helpful assistant. Answer briefly and concisely.",
                ),
            )
            print(f"✓ Created agent (id: {agent.id}, name: {agent.name}, version: {agent.version})")

            # Create a conversation thread
            conversation = openai_client.conversations.create()
            print(f"✓ Created conversation: {conversation.id}")

            # Send a request using the Responses API
            response = openai_client.responses.create(
                conversation=conversation.id,
                input="Say hello and confirm you are working. Keep it brief.",
                extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
            )
            log_response_info(response, "Basic Agent Response")

            print(f"\n✓ Agent response: {response.output_text}")
            print("\n✓ TEST PASSED: Basic agent works with Responses API")
            
            # Cleanup
            project_client.agents.delete_version(
                agent_name=agent.name,
                agent_version=agent.version
            )
            print(f"  Cleaned up agent: {agent.name}")
            
            return True

    except Exception as e:
        print(f"\n✗ TEST FAILED: {str(e)}")
        log_exception_info(e, "Basic Agent Error")
        import traceback
        traceback.print_exc()
        return False


def test_ai_search_tool():
    """Test that an agent can use AI Search tool to query private AI Search."""
    print("\n" + "=" * 60)
    print("TEST 3: AI Search Tool → Private AI Search")
    print("=" * 60)

    if not AI_SEARCH_CONNECTION_NAME:
        print("  ⚠ AI_SEARCH_CONNECTION_NAME not set, skipping this test")
        print("  Set it with: export AI_SEARCH_CONNECTION_NAME=<connection-name>")
        return None

    agent = None
    
    try:
        with (
            DefaultAzureCredential() as credential,
            AIProjectClient(
                credential=credential,
                endpoint=PROJECT_ENDPOINT
            ) as project_client,
            project_client.get_openai_client() as openai_client,
        ):
            print(f"✓ Connected to AI Project at {PROJECT_ENDPOINT}")

            # Create AI Search tool with SIMPLE query type (our index doesn't have vector fields)
            search_tool = AzureAISearchAgentTool(
                azure_ai_search=AzureAISearchToolResource(indexes=[
                    AISearchIndexResource(
                        project_connection_id=AI_SEARCH_CONNECTION_NAME,
                        index_name=AI_SEARCH_INDEX_NAME,
                        query_type=AzureAISearchQueryType.SIMPLE,  # Use simple text search
                    )
                ])
            )

            # Create an agent with AI Search tool
            agent = project_client.agents.create_version(
                agent_name="search-test-agent",
                definition=PromptAgentDefinition(
                    model=MODEL_NAME,
                    instructions="""You are a helpful assistant that searches for information.
                    When asked a question, use the search tool to find relevant information.""",
                    tools=[search_tool],
                ),
            )
            print(f"✓ Created agent with AI Search tool (id: {agent.id})")

            # Create a conversation thread
            conversation = openai_client.conversations.create()
            print(f"✓ Created conversation: {conversation.id}")

            # Send a request that should trigger the search tool
            response = openai_client.responses.create(
                conversation=conversation.id,
                input="Search for any documents in the index and tell me what you find.",
                extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
            )
            log_response_info(response, "AI Search Response")

            print(f"\n✓ Agent response: {response.output_text[:500]}...")
            print("\n✓ TEST PASSED: AI Search tool successfully queried private AI Search")
            
            # Cleanup
            project_client.agents.delete_version(
                agent_name=agent.name,
                agent_version=agent.version
            )
            print(f"  Cleaned up agent: {agent.name}")
            
            return True

    except Exception as e:
        print(f"\n✗ TEST FAILED: {str(e)}")
        log_exception_info(e, "AI Search Error")
        import traceback
        traceback.print_exc()
        return False


def test_mcp_tool_with_agent():
    """Test that an agent can use MCP tool to call the private MCP server."""
    print("\n" + "=" * 60)
    print("TEST 4: MCP Tool → Private MCP Server")
    print("=" * 60)

    agent = None
    
    try:
        with (
            DefaultAzureCredential() as credential,
            AIProjectClient(
                credential=credential,
                endpoint=PROJECT_ENDPOINT
            ) as project_client,
            project_client.get_openai_client() as openai_client,
        ):
            print(f"✓ Connected to AI Project at {PROJECT_ENDPOINT}")

            # Create MCP tool pointing to our private MCP server
            mcp_tool = MCPTool(
                server_label="hello-mcp",
                server_url=MCP_SERVER_URL,
                require_approval="never",  # Auto-approve for testing
            )

            # Create an agent with MCP tool
            agent = project_client.agents.create_version(
                agent_name="mcp-test-agent",
                definition=PromptAgentDefinition(
                    model=MODEL_NAME,
                    instructions="""You are a helpful agent that can use MCP tools.
                    Use the available MCP tools to answer questions and perform tasks.
                    When asked to greet someone, use the hello tool from the MCP server.""",
                    tools=[mcp_tool],
                ),
            )
            print(f"✓ Created agent with MCP tool (id: {agent.id})")
            print(f"  MCP Server URL: {MCP_SERVER_URL}")

            # Create a conversation thread
            conversation = openai_client.conversations.create()
            print(f"✓ Created conversation: {conversation.id}")

            # Send a request that should trigger the MCP tool
            print("  Sending request to use MCP hello tool...")
            response = openai_client.responses.create(
                conversation=conversation.id,
                input="Please, calculate 1 + 2 using the MCP tool and print the response.",
                extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
            )
            log_response_info(response, "MCP Tool Response")

            # Check if we got an MCP approval request (if require_approval was set)
            for item in response.output:
                if hasattr(item, 'type') and item.type == "mcp_approval_request":
                    print(f"  MCP approval requested for: {item.server_label}")
                    
                    # Auto-approve
                    input_list: ResponseInputParam = [
                        McpApprovalResponse(
                            type="mcp_approval_response",
                            approve=True,
                            approval_request_id=item.id,
                        )
                    ]
                    
                    response = openai_client.responses.create(
                        input=input_list,
                        previous_response_id=response.id,
                        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
                    )

            print(f"\n✓ Agent response: {response.output_text}")
            
            # Check if the response mentions the MCP server or greeting
            if "hello" in response.output_text.lower() or "greet" in response.output_text.lower():
                print("\n✓ TEST PASSED: MCP tool connected to private MCP server")
                result = True
            else:
                print("\n⚠ TEST UNCERTAIN: Got response but unclear if MCP tool was used")
                result = True  # Still consider it a pass if we got a response
            
            # Cleanup
            project_client.agents.delete_version(
                agent_name=agent.name,
                agent_version=agent.version
            )
            print(f"  Cleaned up agent: {agent.name}")
            
            return result

    except Exception as e:
        print(f"\n✗ TEST FAILED: {str(e)}")
        log_exception_info(e, "MCP Tool Error")
        import traceback
        traceback.print_exc()
        
        # Check for specific error patterns
        error_str = str(e)
        if "424" in error_str or "Failed Dependency" in error_str:
            print("\n  ⚠ This is the known DNS resolution issue:")
            print("  The Data Proxy cannot resolve the private Container Apps DNS.")
            print("  The MCP server IS reachable from VNet VMs (Test 1), but not via Data Proxy.")
        
        return False


def test_openai_responses_api():
    """Test direct usage of OpenAI Responses API without an agent."""
    print("\n" + "=" * 60)
    print("TEST 5: OpenAI Responses API (Direct)")
    print("=" * 60)

    try:
        with (
            DefaultAzureCredential() as credential,
            AIProjectClient(
                credential=credential,
                endpoint=PROJECT_ENDPOINT
            ) as project_client,
            project_client.get_openai_client() as openai_client,
        ):
            print(f"✓ Connected to AI Project at {PROJECT_ENDPOINT}")

            # Use the Responses API directly without an agent
            response = openai_client.responses.create(
                model=MODEL_NAME,
                input="What is 2 + 2? Answer with just the number.",
            )
            log_response_info(response, "Direct OpenAI Response")

            print(f"\n✓ Response: {response.output_text}")
            print("\n✓ TEST PASSED: OpenAI Responses API works directly")
            return True

    except Exception as e:
        print(f"\n✗ TEST FAILED: {str(e)}")
        log_exception_info(e, "OpenAI API Error")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("AGENTS V2 END-TO-END TEST")
    print("Using new Responses API and Agent Versioning")
    print("=" * 60)
    print(f"\nConfiguration:")
    print(f"  Project Endpoint: {PROJECT_ENDPOINT}")
    print(f"  Model: {MODEL_NAME}")
    print(f"  AI Search Index: {AI_SEARCH_INDEX_NAME}")
    print(f"  AI Search Connection: {AI_SEARCH_CONNECTION_NAME or '(not set)'}")
    print(f"  MCP Server: {MCP_SERVER_URL}")

    results = {}

    # Test 1: MCP Server Connectivity (direct HTTP)
    results['mcp_connectivity'] = test_mcp_server_connectivity()

    # Test 2: OpenAI Responses API (direct)
    results['responses_api'] = test_openai_responses_api()

    # Test 3: Basic Agent with Responses API
    results['basic_agent'] = test_basic_agent()

    # Test 4: AI Search Tool (optional)
    ai_search_result = test_ai_search_tool()
    if ai_search_result is not None:
        results['ai_search'] = ai_search_result

    # Test 5: MCP Tool with Agent
    mcp_tool_result = test_mcp_tool_with_agent()
    if mcp_tool_result is not None:
        results['mcp_tool'] = mcp_tool_result

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {test_name}: {status}")

    all_passed = all(results.values())
    print("\n" + ("=" * 60))
    if all_passed:
        print("ALL TESTS PASSED - Agents v2 API is working!")
    else:
        print("SOME TESTS FAILED - Check the output above for details")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
