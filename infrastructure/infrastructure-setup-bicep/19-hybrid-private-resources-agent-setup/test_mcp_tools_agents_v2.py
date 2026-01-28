#!/usr/bin/env python3
"""
MCP Tools Test Script

This script focuses on testing MCP (Model Context Protocol) tool integration
with Azure AI Foundry Agents v2.

Tests:
1. MCP Connectivity (Direct HTTP) - Direct session flow test to MCP server
2. MCP Tool via Agent (Public) - Test MCP tool via public Container App
3. MCP Tool via Agent (Private) - Test MCP tool via private Container App (VNet)

Note: Tests 2 and 3 may intermittently fail due to known Hyena cluster routing
issue where ~50% of requests hit a scale unit without Data Proxy deployed.
"""

import os
import sys
import logging
import argparse

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
LOG_LEVEL = logging.INFO

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(LOG_LEVEL)
logging.getLogger("httpx").setLevel(LOG_LEVEL)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("azure.identity").setLevel(logging.WARNING)

# ============================================================================

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    MCPTool,
    PromptAgentDefinition,
)
from azure.identity import DefaultAzureCredential
from openai.types.responses import ResponseInputParam
from openai.types.responses.response_input_param import McpApprovalResponse

# ============================================================================
# CONFIGURATION
# ============================================================================
PROJECT_ENDPOINT = os.environ.get(
    "PROJECT_ENDPOINT",
    "https://aiservicesaxy3.services.ai.azure.com/api/projects/projectaxy3"
)
MODEL_NAME = os.environ.get("MODEL_NAME", "gpt-4o-mini")

# MCP Server URLs
# Public MCP server (external, accessible from anywhere)
MCP_SERVER_PUBLIC = os.environ.get(
    "MCP_SERVER_PUBLIC",
    "https://multi-auth-mcp.victorioussmoke-7859ae09.uksouth.azurecontainerapps.io/noauth/mcp"
)

# Private MCP server (internal, only accessible from VNet via Data Proxy)
MCP_SERVER_PRIVATE = os.environ.get(
    "MCP_SERVER_PRIVATE",
    "https://mcp-http-server.jollydune-20a0f709.westus2.azurecontainerapps.io/noauth/mcp"
)

# ============================================================================


def log_response_info(response, label="Response"):
    """Extract and log useful debugging info from OpenAI response objects."""
    logger = logging.getLogger(__name__)
    try:
        if hasattr(response, '_request_id'):
            logger.info(f"{label} - Request ID: {response._request_id}")
        if hasattr(response, 'id'):
            logger.info(f"{label} - Response ID: {response.id}")
        if hasattr(response, '_response') and hasattr(response._response, 'headers'):
            headers = response._response.headers
            if 'x-request-id' in headers:
                logger.info(f"{label} - x-request-id: {headers['x-request-id']}")
            if 'x-ms-request-id' in headers:
                logger.info(f"{label} - x-ms-request-id: {headers['x-ms-request-id']}")
    except Exception as e:
        logger.debug(f"Could not extract response info: {e}")


def log_exception_info(exception, label="Exception"):
    """Extract and log request info from OpenAI exceptions."""
    logger = logging.getLogger(__name__)
    try:
        if hasattr(exception, 'response') and exception.response is not None:
            resp = exception.response
            headers = resp.headers if hasattr(resp, 'headers') else {}
            
            request_id = headers.get('x-request-id', 'N/A')
            ms_request_id = headers.get('x-ms-request-id', 'N/A')
            
            logger.error(f"{label} - x-request-id: {request_id}")
            logger.error(f"{label} - x-ms-request-id: {ms_request_id}")
            
            print(f"  📋 Request ID (x-request-id): {request_id}")
            print(f"  📋 MS Request ID (x-ms-request-id): {ms_request_id}")
            
            if hasattr(resp, 'status_code'):
                logger.error(f"{label} - HTTP Status: {resp.status_code}")
                
        if hasattr(exception, 'request_id'):
            logger.error(f"{label} - request_id attribute: {exception.request_id}")
            print(f"  📋 Request ID: {exception.request_id}")
            
    except Exception as e:
        logger.debug(f"Could not extract exception info: {e}")


def test_mcp_connectivity(mcp_url: str, label: str = "MCP Server"):
    """Test MCP server with full session workflow: initialize → list tools → call tool."""
    print("\n" + "=" * 60)
    print(f"TEST: MCP Connectivity - {label}")
    print("=" * 60)

    import urllib.request
    import ssl
    import json

    try:
        ctx = ssl.create_default_context()
        
        print(f"  Target MCP Server: {mcp_url}")
        
        # Step 1: Initialize - Get mcp-session-id
        print("\n--- Step 1: Initialize (get mcp-session-id) ---")
        
        init_data = json.dumps({
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {
                    "sampling": {},
                    "elicitation": {},
                    "roots": {"listChanged": True}
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
            mcp_url,
            data=init_data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            method="POST"
        )
        
        with urllib.request.urlopen(init_req, timeout=15, context=ctx) as response:
            status = response.getcode()
            body = response.read().decode('utf-8')
            mcp_session_id = response.getheader('mcp-session-id')
            
            print(f"  ✓ HTTP Status: {status}")
            print(f"  ✓ Response: {body[:300]}...")
            
            if mcp_session_id:
                print(f"  ✓ MCP Session ID: {mcp_session_id}")
            else:
                print("  ✗ No mcp-session-id header in response!")
                return False
        
        # Step 2: List Tools
        print("\n--- Step 2: List Tools (using session ID) ---")
        
        list_data = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }).encode('utf-8')
        
        list_req = urllib.request.Request(
            mcp_url,
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
        
        # Step 3: Call Tool 'add'
        print("\n--- Step 3: Call Tool 'add' (using session ID) ---")
        
        call_data = json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "add",
                "arguments": {"a": 2, "b": 4}
            }
        }).encode('utf-8')
        
        call_req = urllib.request.Request(
            mcp_url,
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
            
            if "result" in result:
                print(f"  ✓ Tool call successful!")
            else:
                print(f"  ⚠ Unexpected response format")
        
        print("\n" + "=" * 60)
        print(f"✓ TEST PASSED: {label} session flow working correctly")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n✗ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_mcp_tool_via_agent(mcp_url: str, label: str = "MCP Server"):
    """Test that an agent can use MCP tool via the Data Proxy."""
    print("\n" + "=" * 60)
    print(f"TEST: MCP Tool via Agent - {label}")
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

            # Create MCP tool
            mcp_tool = MCPTool(
                server_label="test-mcp",
                server_url=mcp_url,
                require_approval="never",
            )

            # Create agent with MCP tool
            agent = project_client.agents.create_version(
                agent_name="mcp-tool-test",
                definition=PromptAgentDefinition(
                    model=MODEL_NAME,
                    instructions="""You are a helpful agent that can use MCP tools.
                    When asked to calculate, use the 'add' tool from the MCP server.""",
                    tools=[mcp_tool],
                ),
            )
            print(f"✓ Created agent with MCP tool (id: {agent.id})")
            print(f"  MCP Server URL: {mcp_url}")

            # Create conversation
            conversation = openai_client.conversations.create()
            print(f"✓ Created conversation: {conversation.id}")

            # Send request
            print("  Sending request to use MCP add tool...")
            response = openai_client.responses.create(
                conversation=conversation.id,
                input="Please calculate 1 + 2 using the MCP add tool and tell me the result.",
                extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
            )
            log_response_info(response, "MCP Tool Response")

            # Handle MCP approval if needed
            for item in response.output:
                if hasattr(item, 'type') and item.type == "mcp_approval_request":
                    print(f"  MCP approval requested for: {item.server_label}")
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
            
            # Cleanup
            project_client.agents.delete_version(
                agent_name=agent.name,
                agent_version=agent.version
            )
            print(f"  Cleaned up agent: {agent.name}")
            
            print(f"\n✓ TEST PASSED: MCP tool via {label}")
            return True

    except Exception as e:
        error_str = str(e)
        print(f"\n✗ TEST FAILED: {error_str}")
        log_exception_info(e, "MCP Tool Error")
        
        # Provide context for known issues
        if "TaskCanceledException" in error_str:
            print("\n  ⚠ Known Issue: TaskCanceledException")
            print("  This occurs when request hits the wrong Hyena scale unit")
            print("  (Data Proxy is only deployed on one of two scale units)")
            print("  Re-running the test may succeed on the next attempt.")
        elif "424" in error_str or "Failed Dependency" in error_str:
            print("\n  ⚠ Known Issue: DNS Resolution")
            print("  Data Proxy cannot resolve private Container Apps DNS.")
        
        import traceback
        traceback.print_exc()
        
        # Cleanup agent if created
        if agent is not None:
            try:
                with (
                    DefaultAzureCredential() as credential,
                    AIProjectClient(credential=credential, endpoint=PROJECT_ENDPOINT) as project_client,
                ):
                    project_client.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
                    print(f"  Cleaned up agent: {agent.name}")
            except:
                pass
        
        return False


def main():
    parser = argparse.ArgumentParser(description="MCP Tools Test Script")
    parser.add_argument(
        "--test",
        choices=["public", "private", "all"],
        default="all",
        help="Which MCP server to test via agent: public, private, or all (default: all)"
    )
    parser.add_argument(
        "--retry",
        type=int,
        default=1,
        help="Number of retries for agent tests (default: 1)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("MCP TOOLS TEST")
    print("=" * 60)
    print(f"\nConfiguration:")
    print(f"  Project Endpoint: {PROJECT_ENDPOINT}")
    print(f"  Model: {MODEL_NAME}")
    print(f"  Public MCP Server: {MCP_SERVER_PUBLIC}")
    print(f"  Private MCP Server: {MCP_SERVER_PRIVATE}")

    results = {}

    # Always run connectivity test first (opens the session)
    mcp_url = MCP_SERVER_PUBLIC if args.test in ["public", "all"] else MCP_SERVER_PRIVATE
    results['connectivity'] = test_mcp_connectivity(mcp_url, "Public MCP Server" if mcp_url == MCP_SERVER_PUBLIC else "Private MCP Server")

    # Test: MCP Tool via Agent (Public)
    if args.test in ["public", "all"]:
        for attempt in range(args.retry):
            if attempt > 0:
                print(f"\n  Retry attempt {attempt + 1}/{args.retry}...")
            result = test_mcp_tool_via_agent(MCP_SERVER_PUBLIC, "Public MCP Server")
            if result:
                results['agent_public'] = True
                break
        else:
            results['agent_public'] = False

    # Test: MCP Tool via Agent (Private)
    if args.test in ["private", "all"]:
        for attempt in range(args.retry):
            if attempt > 0:
                print(f"\n  Retry attempt {attempt + 1}/{args.retry}...")
            result = test_mcp_tool_via_agent(MCP_SERVER_PRIVATE, "Private MCP Server")
            if result:
                results['agent_private'] = True
                break
        else:
            results['agent_private'] = False

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {test_name}: {status}")

    all_passed = all(results.values())
    print("\n" + "=" * 60)
    if all_passed:
        print("ALL TESTS PASSED!")
    else:
        print("SOME TESTS FAILED")
        print("Note: Agent tests may fail due to Hyena cluster routing (~50% chance)")
        print("      Use --retry N to retry failed tests")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
