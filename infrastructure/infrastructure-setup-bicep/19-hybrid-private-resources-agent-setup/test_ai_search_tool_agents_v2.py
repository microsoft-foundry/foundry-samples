#!/usr/bin/env python3
"""
AI Search Tool Test Script

This script focuses on testing Azure AI Search tool integration
with Azure AI Foundry Agents v2.

Tests:
1. AI Search Connectivity - Direct REST API test to AI Search service
2. AI Search Tool via Agent - Test AI Search tool via agent (uses Data Proxy)

The agent test validates that:
- The Data Proxy can resolve private endpoint DNS
- The AI Search connection is properly configured
- The agent can query documents from the private AI Search index
"""

import os
import sys
import logging
import argparse
import json
import urllib.request
import urllib.error
import ssl

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
    AzureAISearchAgentTool,
    AzureAISearchToolResource,
    AISearchIndexResource,
    AzureAISearchQueryType,
    PromptAgentDefinition,
)
from azure.identity import DefaultAzureCredential

# ============================================================================
# CONFIGURATION
# ============================================================================
PROJECT_ENDPOINT = os.environ.get(
    "PROJECT_ENDPOINT",
    "https://aiservicesaxy3.services.ai.azure.com/api/projects/projectaxy3"
)
MODEL_NAME = os.environ.get("MODEL_NAME", "gpt-4o-mini")

# AI Search Configuration
AI_SEARCH_CONNECTION_NAME = os.environ.get(
    "AI_SEARCH_CONNECTION_NAME",
    "aiservicesaxy3search"  # Default connection name from template deployment
)
AI_SEARCH_INDEX_NAME = os.environ.get("AI_SEARCH_INDEX_NAME", "test-index")

# AI Search endpoint for direct connectivity test (optional)
# This is only used for the connectivity test, not the agent test
AI_SEARCH_ENDPOINT = os.environ.get(
    "AI_SEARCH_ENDPOINT",
    ""  # e.g., "https://aiservicesaxy3search.search.windows.net"
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
            logger.error(f"{label} - Status: {resp.status_code if hasattr(resp, 'status_code') else 'N/A'}")
            
            if hasattr(resp, 'text'):
                logger.error(f"{label} - Body: {resp.text[:500]}")
    except Exception as e:
        logger.debug(f"Could not extract exception info: {e}")


def test_ai_search_connectivity():
    """
    Test direct connectivity to AI Search service.
    
    Note: This test requires AI_SEARCH_ENDPOINT to be set and will only work
    from within the VNet (e.g., jump box) for private AI Search endpoints.
    """
    print("\n" + "=" * 60)
    print("TEST: AI Search Connectivity (Direct REST API)")
    print("=" * 60)
    
    if not AI_SEARCH_ENDPOINT:
        print("  ⚠ AI_SEARCH_ENDPOINT not set, skipping connectivity test")
        print("  Set it with: export AI_SEARCH_ENDPOINT=https://<search-service>.search.windows.net")
        print("  Note: This test only works from within the VNet for private endpoints")
        return None
    
    print(f"  Target: {AI_SEARCH_ENDPOINT}")
    print(f"  Index: {AI_SEARCH_INDEX_NAME}")
    
    try:
        # Get Azure AD token for AI Search
        credential = DefaultAzureCredential()
        token = credential.get_token("https://search.azure.com/.default")
        
        # Query the index
        url = f"{AI_SEARCH_ENDPOINT}/indexes/{AI_SEARCH_INDEX_NAME}/docs?api-version=2024-07-01&search=*&$top=1"
        
        ctx = ssl.create_default_context()
        headers = {
            "Authorization": f"Bearer {token.token}",
            "Content-Type": "application/json"
        }
        
        req = urllib.request.Request(url, headers=headers, method="GET")
        
        print("\n--- Querying AI Search Index ---")
        with urllib.request.urlopen(req, timeout=15, context=ctx) as response:
            status = response.status
            body = response.read().decode('utf-8')
            result = json.loads(body)
            
            print(f"  ✓ HTTP Status: {status}")
            doc_count = len(result.get('value', []))
            print(f"  ✓ Documents found: {doc_count}")
            
            if doc_count > 0:
                print(f"  ✓ Sample document keys: {list(result['value'][0].keys())[:5]}")
        
        print("\n" + "=" * 60)
        print("✓ TEST PASSED: AI Search connectivity working")
        print("=" * 60)
        return True
        
    except urllib.error.URLError as e:
        print(f"\n✗ TEST FAILED: {e}")
        if "Name or service not known" in str(e):
            print("  Note: This is expected if running from outside the VNet")
            print("  The AI Search endpoint is only accessible via private endpoint")
        return False
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ai_search_tool_via_agent():
    """
    Test AI Search tool via Azure AI Agent.
    
    This test validates that:
    - The Data Proxy can reach the private AI Search endpoint
    - The AI Search connection is properly configured
    - The agent can query and retrieve documents
    """
    print("\n" + "=" * 60)
    print("TEST: AI Search Tool via Agent")
    print("=" * 60)

    if not AI_SEARCH_CONNECTION_NAME:
        print("  ⚠ AI_SEARCH_CONNECTION_NAME not set, skipping this test")
        print("  Set it with: export AI_SEARCH_CONNECTION_NAME=<connection-name>")
        return None

    print(f"  Connection: {AI_SEARCH_CONNECTION_NAME}")
    print(f"  Index: {AI_SEARCH_INDEX_NAME}")

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

            # Create AI Search tool with SIMPLE query type
            search_tool = AzureAISearchAgentTool(
                azure_ai_search=AzureAISearchToolResource(indexes=[
                    AISearchIndexResource(
                        project_connection_id=AI_SEARCH_CONNECTION_NAME,
                        index_name=AI_SEARCH_INDEX_NAME,
                        query_type=AzureAISearchQueryType.SIMPLE,
                    )
                ])
            )

            # Create an agent with AI Search tool
            agent = project_client.agents.create_version(
                agent_name="search-tool-test",
                definition=PromptAgentDefinition(
                    model=MODEL_NAME,
                    instructions="""You are a helpful assistant that searches for information.
                    When asked a question, use the search tool to find relevant information.
                    Always summarize what you found from the search results.""",
                    tools=[search_tool],
                ),
            )
            print(f"✓ Created agent with AI Search tool (id: {agent.id})")
            print(f"  Connection: {AI_SEARCH_CONNECTION_NAME}")
            print(f"  Index: {AI_SEARCH_INDEX_NAME}")

            # Create a conversation
            conversation = openai_client.conversations.create()
            print(f"✓ Created conversation: {conversation.id}")

            # Send a request that should trigger the search tool
            print("  Sending search request to agent...")
            response = openai_client.responses.create(
                conversation=conversation.id,
                input="Search for any documents in the index and tell me what you find. List any document titles or content you discover.",
                extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
            )
            log_response_info(response, "AI Search Response")

            # Display response (truncate if too long)
            output_text = response.output_text
            if len(output_text) > 500:
                print(f"\n✓ Agent response: {output_text[:500]}...")
            else:
                print(f"\n✓ Agent response: {output_text}")
            
            # Cleanup
            project_client.agents.delete_version(
                agent_name=agent.name,
                agent_version=agent.version
            )
            print(f"  Cleaned up agent: {agent.name}")

            print("\n" + "=" * 60)
            print("✓ TEST PASSED: AI Search tool via agent")
            print("=" * 60)
            return True

    except Exception as e:
        print(f"\n✗ TEST FAILED: {str(e)}")
        log_exception_info(e, "AI Search Error")
        import traceback
        traceback.print_exc()
        
        # Cleanup on failure
        if agent:
            try:
                project_client.agents.delete_version(
                    agent_name=agent.name,
                    agent_version=agent.version
                )
            except:
                pass
        
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Test AI Search tool integration with Azure AI Foundry Agents v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_ai_search_tool_agents_v2.py                    # Run all tests
  python test_ai_search_tool_agents_v2.py --test connectivity # Only connectivity test
  python test_ai_search_tool_agents_v2.py --test agent       # Only agent test
  python test_ai_search_tool_agents_v2.py --retry 3          # Retry failed tests up to 3 times

Environment variables:
  PROJECT_ENDPOINT          - Azure AI project endpoint
  MODEL_NAME                - Model to use (default: gpt-4o-mini)
  AI_SEARCH_CONNECTION_NAME - AI Search connection name in the project
  AI_SEARCH_INDEX_NAME      - AI Search index name (default: test-index)
  AI_SEARCH_ENDPOINT        - AI Search endpoint URL (for connectivity test only)
"""
    )
    parser.add_argument(
        "--test",
        choices=["connectivity", "agent", "all"],
        default="all",
        help="Which test to run (default: all)"
    )
    parser.add_argument(
        "--retry",
        type=int,
        default=0,
        help="Number of times to retry failed tests (default: 0)"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("AI SEARCH TOOL TEST")
    print("=" * 60)
    print()
    print("Configuration:")
    print(f"  Project Endpoint: {PROJECT_ENDPOINT}")
    print(f"  Model: {MODEL_NAME}")
    print(f"  AI Search Connection: {AI_SEARCH_CONNECTION_NAME or '(not set)'}")
    print(f"  AI Search Index: {AI_SEARCH_INDEX_NAME}")
    print(f"  AI Search Endpoint: {AI_SEARCH_ENDPOINT or '(not set - connectivity test skipped)'}")

    results = {}
    
    # Run connectivity test
    if args.test in ["connectivity", "all"]:
        result = test_ai_search_connectivity()
        if result is not None:
            results['connectivity'] = result

    # Run agent test
    if args.test in ["agent", "all"]:
        for attempt in range(args.retry + 1):
            if attempt > 0:
                print(f"\n--- Retry attempt {attempt}/{args.retry} ---")
            
            result = test_ai_search_tool_via_agent()
            if result is not None:
                results['agent'] = result
                if result:
                    break  # Success, no need to retry
            else:
                break  # Skipped, no need to retry

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {test_name}: {status}")

    # Exit with appropriate code
    all_passed = all(results.values()) if results else True
    if all_passed:
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED!")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("SOME TESTS FAILED")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
