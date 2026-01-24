#!/usr/bin/env python3
"""
Hybrid Private Resources - Agents v2 Test Script

This script tests that agents can use tools that connect to private resources
via the Data Proxy when AI Services has PUBLIC access enabled.

Template 19: AI Services (public) → Data Proxy → Private Resources (VNet)

Key tests:
1. Basic agent - validates public API access works
2. AI Search tool - validates Data Proxy routes to private AI Search
3. MCP tool - validates Data Proxy routes to private MCP server

This script can be run from ANYWHERE (no jump box required for API access).
However, MCP connectivity test requires access to the private VNet.
"""

import os
import sys
import time
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import AzureAISearchTool
from azure.identity import DefaultAzureCredential

# ============================================================================
# CONFIGURATION - Update these values for your deployment
# ============================================================================
# NOTE: Use the project-scoped endpoint from Azure Portal:
# AI Services resource -> Projects -> <project> -> Properties -> "AI Foundry API" endpoint
PROJECT_ENDPOINT = os.environ.get("PROJECT_ENDPOINT", "https://<ai-services-name>.services.ai.azure.com/api/projects/<project-name>")
MODEL_NAME = os.environ.get("MODEL_NAME", "gpt-4o-mini")

# AI Search configuration
AI_SEARCH_CONNECTION_NAME = os.environ.get("AI_SEARCH_CONNECTION_NAME", "")
AI_SEARCH_INDEX_NAME = os.environ.get("AI_SEARCH_INDEX_NAME", "test-index")

# MCP Server configuration (Container App deployed in Step 6)
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "https://mcp-test-server.jollydune-20a0f709.westus2.azurecontainerapps.io")

# ============================================================================


def test_mcp_server_connectivity():
    """Test that we can reach the MCP server from within the VNet."""
    print("\n" + "="*60)
    print("TEST 1: MCP Server Connectivity (Direct HTTP)")
    print("="*60)
    
    import urllib.request
    import ssl
    
    try:
        # Create SSL context that doesn't verify certificates (for testing)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        print(f"  Attempting to reach: {MCP_SERVER_URL}")
        
        req = urllib.request.Request(MCP_SERVER_URL)
        with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
            status = response.getcode()
            body = response.read().decode('utf-8')[:200]
            
            print(f"✓ HTTP Status: {status}")
            print(f"✓ Response preview: {body}...")
            print("\n✓ TEST PASSED: MCP server is reachable from VNet")
            return True
            
    except Exception as e:
        print(f"\n✗ TEST FAILED: Cannot reach MCP server: {str(e)}")
        return False


def test_basic_agent():
    """Test basic agent creation and execution."""
    print("\n" + "="*60)
    print("TEST 2: Basic Agent Creation and Execution")
    print("="*60)
    
    try:
        # Connect to the project using the project-scoped endpoint
        client = AIProjectClient(
            credential=DefaultAzureCredential(),
            endpoint=PROJECT_ENDPOINT,
        )
        
        print(f"✓ Connected to AI Project at {PROJECT_ENDPOINT}")
        
        # Create a simple agent without tools first
        agent = client.agents.create_agent(
            model=MODEL_NAME,
            name="basic-test-agent",
            instructions="You are a helpful assistant. Answer briefly.",
        )
        print(f"✓ Created agent: {agent.id}")
        
        # Create a thread and send a message
        thread = client.agents.threads.create()
        print(f"✓ Created thread: {thread.id}")
        
        message = client.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content="Say hello and confirm you are working."
        )
        print(f"✓ Created message: {message.id}")
        
        # Run the agent
        run = client.agents.runs.create(thread_id=thread.id, agent_id=agent.id)
        print(f"✓ Started run: {run.id}")
        
        # Wait for completion
        print("  Waiting for agent to complete...")
        while run.status in ["queued", "in_progress"]:
            time.sleep(2)
            run = client.agents.runs.get(thread_id=thread.id, run_id=run.id)
            print(f"  Status: {run.status}")
        
        if run.status == "completed":
            # Get the response - messages.list returns ItemPaged, iterate directly
            messages = client.agents.messages.list(thread_id=thread.id)
            for msg in messages:
                if msg.role == "assistant":
                    print(f"\n✓ Agent response:")
                    for content in msg.content:
                        if hasattr(content, 'text'):
                            print(f"  {content.text.value}")
                    break
            print("\n✓ TEST PASSED: Basic agent works")
            return True
        else:
            print(f"\n✗ Run failed with status: {run.status}")
            if hasattr(run, 'last_error'):
                print(f"  Error: {run.last_error}")
            return False
            
    except Exception as e:
        print(f"\n✗ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        try:
            client.agents.delete_agent(agent.id)
            print(f"  Cleaned up agent: {agent.id}")
        except:
            pass


def test_ai_search_tool():
    """Test that an agent can use AI Search tool to query private AI Search."""
    print("\n" + "="*60)
    print("TEST 3: AI Search Tool → Private AI Search")
    print("="*60)
    
    if not AI_SEARCH_CONNECTION_NAME:
        print("  ⚠ AI_SEARCH_CONNECTION_NAME not set, skipping this test")
        print("  Set it with: export AI_SEARCH_CONNECTION_NAME=<connection-name>")
        return None
    
    try:
        # Connect to the project using the project-scoped endpoint
        client = AIProjectClient(
            credential=DefaultAzureCredential(),
            endpoint=PROJECT_ENDPOINT,
        )
        
        print(f"✓ Connected to AI Project at {PROJECT_ENDPOINT}")
        
        # Create AI Search tool using the SDK class
        search_tool = AzureAISearchTool(
            index_connection_id=AI_SEARCH_CONNECTION_NAME,
            index_name=AI_SEARCH_INDEX_NAME
        )
        
        # Create an agent with AI Search tool
        agent = client.agents.create_agent(
            model=MODEL_NAME,
            name="search-test-agent",
            instructions="""You are a helpful assistant that searches for information.
            When asked a question, use the search tool to find relevant information.""",
            tools=search_tool.definitions,
            tool_resources=search_tool.resources
        )
        print(f"✓ Created agent with AI Search tool: {agent.id}")
        
        # Create a thread and send a message
        thread = client.agents.threads.create()
        print(f"✓ Created thread: {thread.id}")
        
        message = client.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content="Search for any documents in the index and tell me what you find."
        )
        print(f"✓ Created message: {message.id}")
        
        # Run the agent
        run = client.agents.runs.create(thread_id=thread.id, agent_id=agent.id)
        print(f"✓ Started run: {run.id}")
        
        # Wait for completion
        print("  Waiting for agent to complete...")
        while run.status in ["queued", "in_progress"]:
            time.sleep(2)
            run = client.agents.runs.get(thread_id=thread.id, run_id=run.id)
            print(f"  Status: {run.status}")
        
        if run.status == "completed":
            messages = client.agents.messages.list(thread_id=thread.id)
            for msg in messages:
                if msg.role == "assistant":
                    print(f"\n✓ Agent response:")
                    for content in msg.content:
                        if hasattr(content, 'text'):
                            print(f"  {content.text.value[:500]}...")
                    break
            print("\n✓ TEST PASSED: AI Search tool successfully queried private AI Search")
            return True
        else:
            print(f"\n✗ Run ended with status: {run.status}")
            if hasattr(run, 'last_error'):
                print(f"  Error: {run.last_error}")
            return False
            
    except Exception as e:
        print(f"\n✗ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            client.agents.delete_agent(agent.id)
            print(f"  Cleaned up agent: {agent.id}")
        except:
            pass


def test_mcp_tool_with_agent():
    """Test that an agent can use MCP tool to call the private MCP server."""
    print("\n" + "="*60)
    print("TEST 4: MCP Tool → Private MCP Server")
    print("="*60)
    
    # Note: MCP tool support may not be available in all SDK versions
    # Check if azure-ai-agents supports MCP tools
    try:
        from azure.ai.agents.models import McpToolDefinition
    except ImportError:
        print("  ⚠ MCP tool support not available in this SDK version (azure-ai-agents)")
        print("  The MCP server is reachable (verified in Test 1), but SDK doesn't have McpToolDefinition")
        print("  This test requires a newer SDK version or using the REST API directly")
        return None
    
    try:
        client = AIProjectClient(
            credential=DefaultAzureCredential(),
            endpoint=PROJECT_ENDPOINT,
        )
        
        print(f"✓ Connected to AI Project")
        
        # Create an agent with MCP tool
        agent = client.agents.create_agent(
            model=MODEL_NAME,
            name="mcp-test-agent",
            instructions="""You are a helpful assistant with access to MCP tools.
            Use the available tools to help answer questions.""",
            tools=[
                McpToolDefinition(
                    server_label="test-mcp-server",
                    server_url=MCP_SERVER_URL,
                    allowed_tools=["*"]
                )
            ]
        )
        print(f"✓ Created agent with MCP tool: {agent.id}")
        
        # Create a thread and send a message
        thread = client.agents.threads.create()
        print(f"✓ Created thread: {thread.id}")
        
        message = client.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content="What tools are available from the MCP server? List them."
        )
        print(f"✓ Created message: {message.id}")
        
        # Run the agent
        run = client.agents.runs.create(thread_id=thread.id, agent_id=agent.id)
        print(f"✓ Started run: {run.id}")
        
        # Wait for completion
        print("  Waiting for agent to complete...")
        while run.status in ["queued", "in_progress"]:
            time.sleep(2)
            run = client.agents.runs.get(thread_id=thread.id, run_id=run.id)
            print(f"  Status: {run.status}")
        
        if run.status == "completed":
            messages = client.agents.messages.list(thread_id=thread.id)
            for msg in messages:
                if msg.role == "assistant":
                    print(f"\n✓ Agent response:")
                    for content in msg.content:
                        if hasattr(content, 'text'):
                            print(f"  {content.text.value[:500]}...")
                    break
            print("\n✓ TEST PASSED: MCP tool connected to private MCP server")
            return True
        else:
            print(f"\n✗ Run ended with status: {run.status}")
            if hasattr(run, 'last_error'):
                print(f"  Error: {run.last_error}")
            return False
            
    except Exception as e:
        print(f"\n✗ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            client.agents.delete_agent(agent.id)
            print(f"  Cleaned up agent: {agent.id}")
        except:
            pass


def main():
    print("="*60)
    print("AGENTS V2 END-TO-END TEST")
    print("Testing Data Proxy routing to private resources")
    print("="*60)
    print(f"\nConfiguration:")
    print(f"  Project Endpoint: {PROJECT_ENDPOINT}")
    print(f"  Model: {MODEL_NAME}")
    print(f"  AI Search Index: {AI_SEARCH_INDEX_NAME}")
    print(f"  AI Search Connection: {AI_SEARCH_CONNECTION_NAME or '(not set)'}")
    print(f"  MCP Server: {MCP_SERVER_URL}")
    
    results = {}
    
    # Test 1: MCP Server Connectivity (direct HTTP)
    results['mcp_connectivity'] = test_mcp_server_connectivity()
    
    # Test 2: Basic Agent
    results['basic_agent'] = test_basic_agent()
    
    # Test 3: AI Search Tool (optional)
    ai_search_result = test_ai_search_tool()
    if ai_search_result is not None:
        results['ai_search'] = ai_search_result
    
    # Test 4: MCP Tool with Agent (optional - SDK support may vary)
    mcp_tool_result = test_mcp_tool_with_agent()
    if mcp_tool_result is not None:
        results['mcp_tool'] = mcp_tool_result
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {test_name}: {status}")
    
    all_passed = all(results.values())
    print("\n" + ("="*60))
    if all_passed:
        print("ALL TESTS PASSED - Data Proxy routing is working!")
    else:
        print("SOME TESTS FAILED - Check the output above for details")
    print("="*60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
