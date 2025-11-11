#!/usr/bin/env python3
"""
Azure AI Foundry Agent Sample - Tutorial 1: Modern Workplace Assistant

This sample demonstrates a complete business scenario using Azure AI Agents SDK v2:
- Agent creation with the new SDK
- Thread and message management
- Robust error handling and graceful degradation

Educational Focus:
- Enterprise AI patterns with Agent SDK v2
- Real-world business scenarios that enterprises face daily
- Production-ready error handling and diagnostics
- Foundation for governance, evaluation, and monitoring (Tutorials 2-3)

Business Scenario:
An employee needs to implement Azure AD multi-factor authentication. They need:
1. Company security policy requirements
2. Technical implementation steps
3. Combined guidance showing how policy requirements map to technical implementation
"""

# <imports_and_includes>
import os
import time
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    SharepointTool,
    SharepointGroundingToolParameters,
    McpTool,
    RunHandler,
    ToolApproval
)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Import for connection resolution
try:
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import ConnectionType
    HAS_PROJECT_CLIENT = True
except ImportError:
    HAS_PROJECT_CLIENT = False
# </imports_and_includes>

load_dotenv()

# ============================================================================
# AUTHENTICATION SETUP
# ============================================================================
# <agent_authentication>
# Support default Azure credentials
credential = DefaultAzureCredential()

agents_client = AgentsClient(
    endpoint=os.environ["PROJECT_ENDPOINT"],
    credential=credential,
)
print(f"✅ Connected to Azure AI Foundry: {os.environ['PROJECT_ENDPOINT']}")
# </agent_authentication>

def create_workplace_assistant():
    """
    Create a Modern Workplace Assistant using Agent SDK v2.
    
    This demonstrates enterprise AI patterns:
    1. Agent creation with the new SDK
    2. Robust error handling with graceful degradation
    3. Dynamic agent capabilities based on available resources
    4. Clear diagnostic information for troubleshooting
    
    Educational Value:
    - Shows real-world complexity of enterprise AI systems
    - Demonstrates how to handle partial system failures
    - Provides patterns for agent creation with Agent SDK v2
    
    Returns:
        agent: The created agent object
    """
    
    print("🤖 Creating Modern Workplace Assistant...")
    
    # ========================================================================
    # SHAREPOINT INTEGRATION SETUP
    # ========================================================================
    # <sharepoint_connection_resolution>
    # This demonstrates how to resolve a user-friendly connection name to the
    # full ARM resource ID required by SharepointTool. This pattern allows
    # users to specify simple names in .env while the code handles the complexity.
    sharepoint_resource_name = os.environ.get("SHAREPOINT_RESOURCE_NAME")
    sharepoint_tool = None
    
    if sharepoint_resource_name:
        print(f"📁 Configuring SharePoint integration...")
        print(f"   Connection name: {sharepoint_resource_name}")
        
        try:
            # Resolve the connection name to its full ARM resource ID
            # This is critical: SharepointTool requires the full ARM ID, not just the name
            print(f"   🔍 Resolving connection name to ARM resource ID...")
            
            if HAS_PROJECT_CLIENT:
                # Use AIProjectClient to list and find the connection
                project_client = AIProjectClient(
                    endpoint=os.environ["PROJECT_ENDPOINT"],
                    credential=credential
                )
                
                # List all connections and find the one we need
                connections = project_client.connections.list()
                connection_id = None
                
                for conn in connections:
                    if conn.name == sharepoint_resource_name:
                        connection_id = conn.id
                        print(f"   ✅ Resolved to: {connection_id}")
                        break
                
                if not connection_id:
                    raise ValueError(f"Connection '{sharepoint_resource_name}' not found in project")
            else:
                # Fallback: construct the connection ID from environment variables
                # This requires additional environment variables to be set
                print(f"   ⚠️  AIProjectClient not available, attempting fallback...")
                raise ImportError("azure-ai-projects not installed")

            # <sharepoint_tool_setup>
            # Create SharePoint tool with the full ARM resource ID
            sharepoint_tool = SharepointTool(connection_id=connection_id)
            print(f"✅ SharePoint tool configured successfully")
            # </sharepoint_tool_setup>
            
        except ImportError:
            print(f"⚠️  Connection resolution requires azure-ai-projects package")
            print(f"   Install with: pip install azure-ai-projects")
            print(f"   Agent will operate without SharePoint access")
            sharepoint_tool = None
        except ValueError as e:
            print(f"⚠️  {e}")
            print(f"   Available connections can be viewed in Azure AI Foundry portal")
            print(f"   Agent will operate without SharePoint access")
            sharepoint_tool = None
        except Exception as e:
            print(f"⚠️  SharePoint connection unavailable: {e}")
            print(f"   Possible causes:")
            print(f"   - Connection '{sharepoint_resource_name}' doesn't exist in the project")
            print(f"   - Insufficient permissions to access the connection")
            print(f"   - Connection configuration is incomplete")
            print(f"   Agent will operate without SharePoint access")
            sharepoint_tool = None
    else:
        print(f"📁 SharePoint integration skipped (SHAREPOINT_RESOURCE_NAME not set)")
    # </sharepoint_connection_resolution>
    
    # ========================================================================
    # MICROSOFT LEARN MCP INTEGRATION SETUP  
    # ========================================================================
    # <mcp_tool_setup>
    # MCP (Model Context Protocol) enables agents to access external data sources
    # like Microsoft Learn documentation. The approval flow is handled automatically
    # in the chat_with_assistant function.
    from azure.ai.agents.models import McpTool
    
    mcp_server_url = os.environ.get("MCP_SERVER_URL")
    mcp_tool = None
    
    if mcp_server_url:
        print(f"📚 Configuring Microsoft Learn MCP integration...")
        print(f"   Server URL: {mcp_server_url}")
        
        try:
            # Create MCP tool for Microsoft Learn documentation access
            # server_label must match pattern: ^[a-zA-Z0-9_]+$ (alphanumeric and underscores only)
            mcp_tool = McpTool(
                server_url=mcp_server_url,
                server_label="Microsoft_Learn_Documentation"
            )
            print(f"✅ MCP tool configured successfully")
        except Exception as e:
            print(f"⚠️  MCP tool unavailable: {e}")
            print(f"   Agent will operate without Microsoft Learn access")
            mcp_tool = None
    else:
        print(f"📚 MCP integration skipped (MCP_SERVER_URL not set)")
    # </mcp_tool_setup>
    
    # ========================================================================
    # AGENT CREATION WITH DYNAMIC CAPABILITIES
    # ========================================================================
    # Create agent instructions based on available data sources
    if sharepoint_tool and mcp_tool:
        instructions = """You are a Modern Workplace Assistant for Contoso Corporation.

CAPABILITIES:
- Search SharePoint for company policies, procedures, and internal documentation
- Access Microsoft Learn for current Azure and Microsoft 365 technical guidance
- Provide comprehensive solutions combining internal requirements with external implementation

RESPONSE STRATEGY:
- For policy questions: Search SharePoint for company-specific requirements and guidelines
- For technical questions: Use Microsoft Learn for current Azure/M365 documentation and best practices
- For implementation questions: Combine both sources to show how company policies map to technical implementation
- Always cite your sources and provide step-by-step guidance
- Explain how internal requirements connect to external implementation steps

EXAMPLE SCENARIOS:
- "What is our MFA policy?" → Search SharePoint for security policies
- "How do I configure Azure AD Conditional Access?" → Use Microsoft Learn for technical steps
- "Our policy requires MFA - how do I implement this?" → Combine policy requirements with implementation guidance"""
    elif sharepoint_tool:
        instructions = """You are a Modern Workplace Assistant with access to Contoso Corporation's SharePoint.

CAPABILITIES:
- Search SharePoint for company policies, procedures, and internal documentation
- Provide detailed technical guidance based on your knowledge
- Combine company policies with general best practices

RESPONSE STRATEGY:
- Search SharePoint for company-specific requirements
- Provide technical guidance based on Azure and M365 best practices
- Explain how to align implementations with company policies"""
    elif mcp_tool:
        instructions = """You are a Technical Assistant with access to Microsoft Learn documentation.

CAPABILITIES:
- Access Microsoft Learn for current Azure and Microsoft 365 technical guidance
- Provide detailed implementation steps and best practices
- Explain Azure services, features, and configuration options

RESPONSE STRATEGY:
- Use Microsoft Learn for technical documentation
- Provide comprehensive implementation guidance
- Reference official documentation and best practices"""
    else:
        instructions = """You are a Technical Assistant specializing in Azure and Microsoft 365 guidance.

CAPABILITIES:
- Provide detailed Azure and Microsoft 365 technical guidance
- Explain implementation steps and best practices
- Help with Azure AD, Conditional Access, MFA, and security configurations

RESPONSE STRATEGY:  
- Provide comprehensive technical guidance
- Include step-by-step implementation instructions
- Reference best practices and security considerations"""

    # <create_agent_with_tools>
    # Create the agent using Agent SDK v2 with available tools
    print(f"🛠️  Creating agent with model: {os.environ['MODEL_DEPLOYMENT_NAME']}")
    
    # Build tools list with proper serialization
    tools = []
    
    # Add SharePoint tool using .definitions property
    if sharepoint_tool:
        tools.extend(sharepoint_tool.definitions)
        print(f"   ✓ SharePoint tool added")
    
    # Add MCP tool using .definitions property
    if mcp_tool:
        tools.extend(mcp_tool.definitions)
        print(f"   ✓ MCP tool added")
    
    print(f"   Total tools: {len(tools)}")
    
    # Create agent with or without tools
    if tools:
        agent = agents_client.create_agent(
            model=os.environ["MODEL_DEPLOYMENT_NAME"],
            name="Modern Workplace Assistant",
            instructions=instructions,
            tools=tools
        )
    else:
        agent = agents_client.create_agent(
            model=os.environ["MODEL_DEPLOYMENT_NAME"],
            name="Modern Workplace Assistant",
            instructions=instructions,
        )
    
    print(f"✅ Agent created successfully: {agent.id}")
    return agent
    # </create_agent_with_tools>

def demonstrate_business_scenarios(agent):
    """
    Demonstrate realistic business scenarios with Agent SDK v2.
    
    This function showcases the practical value of the Modern Workplace Assistant
    by walking through scenarios that enterprise employees face regularly.
    
    Educational Value:
    - Shows real business problems that AI agents can solve
    - Demonstrates proper thread and message management
    - Illustrates Agent SDK v2 conversation patterns
    """
    
    scenarios = [
        {
            "title": "📋 Company Policy Question (SharePoint Only)", 
            "question": "What is Contoso's remote work policy?",
            "context": "Employee needs to understand company-specific remote work requirements",
            "learning_point": "SharePoint tool retrieves internal company policies"
        },
        {
            "title": "📚 Technical Documentation Question (MCP Only)",
            "question": "According to Microsoft Learn, what is the correct way to implement Azure AD Conditional Access policies? Please include reference links to the official documentation.",
            "context": "IT administrator needs authoritative Microsoft technical guidance",
            "learning_point": "MCP tool accesses Microsoft Learn for official documentation with links"
        },
        {
            "title": "🔄 Combined Implementation Question (SharePoint + MCP)",
            "question": "Based on our company's remote work security policy, how should I configure my Azure environment to comply? Please include links to Microsoft documentation showing how to implement each requirement.",
            "context": "Need to map company policy to technical implementation with official guidance",
            "learning_point": "Both tools work together: SharePoint for policy + MCP for implementation docs"
        }
    ]
    
    print("\n" + "="*70)
    print("🏢 MODERN WORKPLACE ASSISTANT - BUSINESS SCENARIO DEMONSTRATION")  
    print("="*70)
    print("This demonstration shows how AI agents solve real business problems")
    print("using the Azure AI Agents SDK v2.")
    print("="*70)
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n📊 SCENARIO {i}/3: {scenario['title']}")
        print("-" * 50)
        print(f"❓ QUESTION: {scenario['question']}")
        print(f"🎯 BUSINESS CONTEXT: {scenario['context']}")
        print(f"🎓 LEARNING POINT: {scenario['learning_point']}")
        print("-" * 50)
        
        # <agent_conversation>
        # Get response from the agent
        print("🤖 ASSISTANT RESPONSE:")
        response, status = chat_with_assistant(agent.id, scenario['question'])
        # </agent_conversation>
        
        # Display response with analysis
        if status == 'completed' and response and len(response.strip()) > 10:
            print(f"✅ SUCCESS: {response[:300]}...")
            if len(response) > 300:
                print(f"   📏 Full response: {len(response)} characters")
        else:
            print(f"⚠️  RESPONSE: {response}")
        
        print(f"📈 STATUS: {status}")
        print("-" * 50)
        
        # Small delay between scenarios
        time.sleep(1)
    
    print(f"\n✅ DEMONSTRATION COMPLETED!")
    print("🎓 Key Learning Outcomes:")
    print("   • Agent SDK v2 usage for enterprise AI")
    print("   • Proper thread and message management")  
    print("   • Real business value through AI assistance")
    print("   • Foundation for governance and monitoring (Tutorials 2-3)")
    
    return True

# <mcp_approval_handler>
class MCPApprovalHandler(RunHandler):
    """
    Handler to automatically approve MCP tool calls.
    
    This demonstrates the MCP approval pattern in Azure AI Agents SDK v2.
    The handler implements the submit_mcp_tool_approval method which is called
    automatically when an MCP tool needs approval.
    
    Educational Value:
    - Shows proper MCP integration with Agent SDK v2
    - Demonstrates RunHandler pattern for tool approval
    - Provides foundation for custom approval logic (RBAC, logging, etc.)
    """
    
    def submit_mcp_tool_approval(self, *, run, tool_call, **kwargs):
        """
        Auto-approve MCP tool calls.
        
        In production, you might implement custom approval logic here:
        - RBAC checks (is user authorized for this tool?)
        - Cost controls (has budget limit been reached?)
        - Logging and auditing
        - Interactive approval prompts
        
        Args:
            run: The current run requiring approval
            tool_call: The specific MCP tool call to approve
            
        Returns:
            ToolApproval: Approval object indicating approval/rejection
        """
        # Auto-approve by returning ToolApproval with approve=True
        return ToolApproval(
            tool_call_id=tool_call.id,
            approve=True
        )
# </mcp_approval_handler>

def chat_with_assistant(agent_id, message):
    """
    Execute a conversation with the workplace assistant using Agent SDK v2.
    
    This function demonstrates the conversation pattern for Azure AI Agents SDK v2
    including MCP tool approval handling.
    
    Educational Value:
    - Shows proper conversation management with Agent SDK v2
    - Demonstrates thread creation and message handling
    - Illustrates MCP approval with RunHandler
    - Includes timeout and error management patterns
    
    Args:
        agent_id: The ID of the agent to chat with
        message: The user's message
        
    Returns:
        tuple: (response_text, status)
    """
    
    try:
        # Create a thread for the conversation
        thread = agents_client.threads.create()
        
        # Create a message in the thread
        message_obj = agents_client.messages.create(
            thread_id=thread.id,
            role="user",
            content=message
        )
        
        # <mcp_approval_usage>
        # Use create_and_process with RunHandler to automatically handle MCP approvals
        # This is the recommended pattern for MCP tools in Agent SDK v2
        handler = MCPApprovalHandler()
        run = agents_client.runs.create_and_process(
            thread_id=thread.id,
            agent_id=agent_id,
            run_handler=handler
        )
        # </mcp_approval_usage>
        
        # Retrieve messages
        if run.status == "completed":
            from azure.ai.agents.models import ListSortOrder
            messages = agents_client.messages.list(
                thread_id=thread.id,
                order=ListSortOrder.ASCENDING
            )
            
            # Get the assistant's response (last message from assistant)
            for msg in reversed(list(messages)):
                if msg.role == "assistant" and msg.text_messages:
                    response_text = msg.text_messages[-1].text.value
                    return response_text, 'completed'
            
            return "No response from assistant", 'completed'
        else:
            return f"Run ended with status: {run.status}", run.status
        
    except Exception as e:
        return f"Error in conversation: {str(e)}", 'failed'

def interactive_mode(agent):
    """
    Interactive mode for testing the workplace assistant.
    
    This provides a simple interface for users to test the agent with their own questions
    and see how it provides comprehensive technical guidance.
    """
    
    print("\n" + "="*60)
    print("💬 INTERACTIVE MODE - Test Your Workplace Assistant!")
    print("="*60)
    print("Ask questions about Azure, M365, security, and technical implementation:")
    print("• 'How do I configure Azure AD conditional access?'")
    print("• 'What are MFA best practices for remote workers?'") 
    print("• 'How do I set up secure SharePoint access?'")
    print("Type 'quit' to exit.")
    print("-" * 60)
    
    while True:
        try:
            question = input("\n❓ Your question: ").strip()
            
            if question.lower() in ['quit', 'exit', 'bye']:
                break
                
            if not question:
                print("💡 Please ask a question about Azure or M365 technical implementation.")
                continue
            
            print(f"\n🤖 Workplace Assistant: ", end="", flush=True)
            response, status = chat_with_assistant(agent.id, question)
            print(response)
            
            if status != 'completed':
                print(f"\n⚠️  Response status: {status}")
            
            print("-" * 60)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("-" * 60)
    
    print("\n👋 Thank you for testing the Modern Workplace Assistant!")

def main():
    """
    Main execution flow demonstrating the complete sample.
    
    This orchestrates the full demonstration:
    1. Agent creation with diagnostic information
    2. Business scenario demonstration  
    3. Interactive testing mode
    4. Clean completion with next steps
    """
    
    print("🚀 Azure AI Foundry - Modern Workplace Assistant")
    print("Tutorial 1: Building Enterprise Agents with Agent SDK v2")
    print("="*70)
    
    try:
        # Create the agent with full diagnostic output
        agent = create_workplace_assistant()
        
        # Demonstrate business scenarios  
        demonstrate_business_scenarios(agent)
        
        # Offer interactive testing
        print(f"\n🎯 Try interactive mode? (y/n): ", end="")
        try:
            if input().lower().startswith('y'):
                interactive_mode(agent)
        except EOFError:
            print("n")
        
        print(f"\n🎉 Sample completed successfully!")
        print("📚 This foundation supports Tutorial 2 (Governance) and Tutorial 3 (Production)")
        print("🔗 Next: Add evaluation metrics, monitoring, and production deployment")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("Please check your .env configuration and ensure:")
        print("  - PROJECT_ENDPOINT is correct")
        print("  - MODEL_DEPLOYMENT_NAME is deployed")
        print("  - Azure credentials are configured (az login)")

if __name__ == "__main__":
    main()
