// <imports_and_includes>
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using DotNetEnv;
// </imports_and_includes>

/*
 * Azure AI Foundry Agent Sample - Tutorial 1: Modern Workplace Assistant (C#)
 * 
 * This sample demonstrates a complete business scenario using Azure AI Agents SDK:
 * - Agent creation with SharePoint and MCP tools
 * - Thread and message management
 * - MCP tool approval handling
 * - Robust error handling and graceful degradation
 * 
 * Educational Focus:
 * - Enterprise AI patterns with Azure AI Agents SDK
 * - Real-world business scenarios that enterprises face daily
 * - Production-ready error handling and diagnostics
 * - Foundation for governance, evaluation, and monitoring (Tutorials 2-3)
 * 
 * Business Scenario:
 * An employee needs to implement Azure AD multi-factor authentication. They need:
 * 1. Company security policy requirements (from SharePoint)
 * 2. Technical implementation steps (from Microsoft Learn via MCP)
 * 3. Combined guidance showing how policy requirements map to technical implementation
 */

class Program
{
    private static AIProjectClient? projectClient;
    private static PersistentAgentsClient? agentsClient;
    private static string? mcpServerLabel;

    static async Task Main(string[] args)
    {
        Console.WriteLine("🚀 Azure AI Foundry - Modern Workplace Assistant");
        Console.WriteLine("Tutorial 1: Building Enterprise Agents with SharePoint + MCP Tools");
        Console.WriteLine("".PadRight(70, '='));

        try
        {
            // Create the agent with full diagnostic output
            var agent = await CreateWorkplaceAssistantAsync();

            // Demonstrate business scenarios
            await DemonstrateBusinessScenariosAsync(agent);

            // Offer interactive testing
            Console.Write("\n🎯 Try interactive mode? (y/n): ");
            var response = Console.ReadLine();
            if (response?.ToLower().StartsWith("y") == true)
            {
                await InteractiveModeAsync(agent);
            }

            // Cleanup
            Console.WriteLine("\n🧹 Cleaning up agent...");
            await agentsClient!.Administration.DeleteAgentAsync(agent.Id);
            Console.WriteLine("✅ Agent deleted");

            Console.WriteLine("\n🎉 Sample completed successfully!");
            Console.WriteLine("📚 This foundation supports Tutorial 2 (Governance) and Tutorial 3 (Production)");
            Console.WriteLine("🔗 Next: Add evaluation metrics, monitoring, and production deployment");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"\n❌ Error: {ex.Message}");
            Console.WriteLine("Please check your .env configuration and ensure:");
            Console.WriteLine("  - PROJECT_ENDPOINT is correct");
            Console.WriteLine("  - MODEL_DEPLOYMENT_NAME is deployed");
            Console.WriteLine("  - Azure credentials are configured (az login)");
            throw;
        }
    }

    /// <summary>
    /// Create a Modern Workplace Assistant with SharePoint and MCP tools.
    /// 
    /// This demonstrates enterprise AI patterns:
    /// 1. Agent creation with the SDK
    /// 2. SharePoint integration for company documents
    /// 3. MCP integration for Microsoft Learn documentation
    /// 4. Robust error handling with graceful degradation
    /// 5. Dynamic agent capabilities based on available resources
    /// 
    /// Educational Value:
    /// - Shows real-world complexity of enterprise AI systems
    /// - Demonstrates how to handle partial system failures
    /// - Provides patterns for agent creation with multiple tools
    /// </summary>
    private static async Task<PersistentAgent> CreateWorkplaceAssistantAsync()
    {
        // Load environment variables from shared .env file
        var envPath = Path.Combine(Directory.GetCurrentDirectory(), "..", "shared", ".env");
        if (File.Exists(envPath))
        {
            Env.Load(envPath);
            Console.WriteLine($"📄 Loaded environment from: {envPath}");
        }
        else
        {
            // Fallback to local .env
            Env.Load(".env");
        }

        var projectEndpoint = Environment.GetEnvironmentVariable("PROJECT_ENDPOINT");
        var modelDeploymentName = Environment.GetEnvironmentVariable("MODEL_DEPLOYMENT_NAME");
        var sharePointResourceName = Environment.GetEnvironmentVariable("SHAREPOINT_RESOURCE_NAME");
        var mcpServerUrl = Environment.GetEnvironmentVariable("MCP_SERVER_URL");

        if (string.IsNullOrEmpty(projectEndpoint))
            throw new InvalidOperationException("PROJECT_ENDPOINT environment variable not set");
        if (string.IsNullOrEmpty(modelDeploymentName))
            throw new InvalidOperationException("MODEL_DEPLOYMENT_NAME environment variable not set");

        Console.WriteLine("\n🤖 Creating Modern Workplace Assistant...");

        // ============================================================================
        // AUTHENTICATION SETUP
        // ============================================================================
        // <agent_authentication>
        var credential = new DefaultAzureCredential();

        projectClient = new AIProjectClient(new Uri(projectEndpoint), credential);
        agentsClient = projectClient.GetPersistentAgentsClient();
        Console.WriteLine($"✅ Connected to Azure AI Foundry: {projectEndpoint}");
        // </agent_authentication>

        // ========================================================================
        // SHAREPOINT INTEGRATION SETUP
        // ========================================================================
        // <sharepoint_connection_resolution>
        SharepointToolDefinition? sharepointTool = null;

        // Support either connection name or full ARM ID
        // Full ARM ID format: /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.MachineLearningServices/workspaces/{workspace}/connections/{name}
        var sharePointConnectionId = Environment.GetEnvironmentVariable("SHAREPOINT_CONNECTION_ID");

        if (!string.IsNullOrEmpty(sharePointResourceName) || !string.IsNullOrEmpty(sharePointConnectionId))
        {
            Console.WriteLine($"📁 Configuring SharePoint integration...");

            try
            {
                string? connectionId = sharePointConnectionId;

                // If only a connection name is provided, user needs to provide the full ARM ID
                if (string.IsNullOrEmpty(connectionId))
                {
                    Console.WriteLine($"   Connection name: {sharePointResourceName}");
                    Console.WriteLine($"   ⚠️  Note: SharePoint tool requires the full ARM resource ID");
                    Console.WriteLine($"   💡 Set SHAREPOINT_CONNECTION_ID to the full ARM resource ID");
                    Console.WriteLine($"   📋 Format: /subscriptions/{{sub}}/resourceGroups/{{rg}}/providers/Microsoft.MachineLearningServices/workspaces/{{workspace}}/connections/{{name}}");
                    throw new InvalidOperationException($"Set SHAREPOINT_CONNECTION_ID to the full ARM resource ID for connection '{sharePointResourceName}'");
                }
                
                Console.WriteLine($"   Using connection ID: {connectionId}");

                // <sharepoint_tool_setup>
                // Create SharePoint tool with the full ARM resource ID
                sharepointTool = new SharepointToolDefinition(
                    new SharepointGroundingToolParameters(connectionId)
                );
                Console.WriteLine($"✅ SharePoint tool configured successfully");
                // </sharepoint_tool_setup>
            }
            catch (InvalidOperationException ex)
            {
                Console.WriteLine($"⚠️  {ex.Message}");
                Console.WriteLine($"   Available connections can be viewed in Azure AI Foundry portal");
                Console.WriteLine($"   Agent will operate without SharePoint access");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"⚠️  SharePoint connection unavailable: {ex.Message}");
                Console.WriteLine($"   Possible causes:");
                Console.WriteLine($"   - Connection '{sharePointResourceName}' doesn't exist in the project");
                Console.WriteLine($"   - Insufficient permissions to access the connection");
                Console.WriteLine($"   - Connection configuration is incomplete");
                Console.WriteLine($"   Agent will operate without SharePoint access");
            }
        }
        else
        {
            Console.WriteLine($"📁 SharePoint integration skipped (SHAREPOINT_RESOURCE_NAME not set)");
        }
        // </sharepoint_connection_resolution>

        // ========================================================================
        // MICROSOFT LEARN MCP INTEGRATION SETUP
        // ========================================================================
        // <mcp_tool_setup>
        // MCP (Model Context Protocol) enables agents to access external data sources
        // like Microsoft Learn documentation. The approval flow is handled in ChatWithAssistantAsync.
        MCPToolDefinition? mcpTool = null;
        mcpServerLabel = "Microsoft_Learn_Documentation";

        if (!string.IsNullOrEmpty(mcpServerUrl))
        {
            Console.WriteLine($"📚 Configuring Microsoft Learn MCP integration...");
            Console.WriteLine($"   Server URL: {mcpServerUrl}");

            try
            {
                // Create MCP tool for Microsoft Learn documentation access
                // server_label must match pattern: ^[a-zA-Z0-9_]+$ (alphanumeric and underscores only)
                mcpTool = new MCPToolDefinition(mcpServerLabel, mcpServerUrl);
                Console.WriteLine($"✅ MCP tool configured successfully");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"⚠️  MCP tool unavailable: {ex.Message}");
                Console.WriteLine($"   Agent will operate without Microsoft Learn access");
            }
        }
        else
        {
            Console.WriteLine($"📚 MCP integration skipped (MCP_SERVER_URL not set)");
        }
        // </mcp_tool_setup>

        // ========================================================================
        // AGENT CREATION WITH DYNAMIC CAPABILITIES
        // ========================================================================
        // Create agent instructions based on available data sources
        string instructions = GetAgentInstructions(sharepointTool != null, mcpTool != null);

        // <create_agent_with_tools>
        // Create the agent using the SDK with available tools
        Console.WriteLine($"🛠️  Creating agent with model: {modelDeploymentName}");

        // Build tools list
        var tools = new List<ToolDefinition>();

        if (sharepointTool != null)
        {
            tools.Add(sharepointTool);
            Console.WriteLine($"   ✓ SharePoint tool added");
        }

        if (mcpTool != null)
        {
            tools.Add(mcpTool);
            Console.WriteLine($"   ✓ MCP tool added");
        }

        Console.WriteLine($"   Total tools: {tools.Count}");

        // Create agent with or without tools
        PersistentAgent agent = await agentsClient.Administration.CreateAgentAsync(
            model: modelDeploymentName,
            name: "Modern_Workplace_Assistant",
            instructions: instructions,
            tools: tools.Count > 0 ? tools : null
        );

        Console.WriteLine($"✅ Agent created successfully: {agent.Id}");
        return agent;
        // </create_agent_with_tools>
    }

    /// <summary>
    /// Generate agent instructions based on available tools.
    /// </summary>
    private static string GetAgentInstructions(bool hasSharePoint, bool hasMcp)
    {
        if (hasSharePoint && hasMcp)
        {
            return @"You are a Modern Workplace Assistant for Contoso Corporation.

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
- ""What is our MFA policy?"" → Search SharePoint for security policies
- ""How do I configure Azure AD Conditional Access?"" → Use Microsoft Learn for technical steps
- ""Our policy requires MFA - how do I implement this?"" → Combine policy requirements with implementation guidance";
        }
        else if (hasSharePoint)
        {
            return @"You are a Modern Workplace Assistant with access to Contoso Corporation's SharePoint.

CAPABILITIES:
- Search SharePoint for company policies, procedures, and internal documentation
- Provide detailed technical guidance based on your knowledge
- Combine company policies with general best practices

RESPONSE STRATEGY:
- Search SharePoint for company-specific requirements
- Provide technical guidance based on Azure and M365 best practices
- Explain how to align implementations with company policies";
        }
        else if (hasMcp)
        {
            return @"You are a Technical Assistant with access to Microsoft Learn documentation.

CAPABILITIES:
- Access Microsoft Learn for current Azure and Microsoft 365 technical guidance
- Provide detailed implementation steps and best practices
- Explain Azure services, features, and configuration options

RESPONSE STRATEGY:
- Use Microsoft Learn for technical documentation
- Provide comprehensive implementation guidance
- Reference official documentation and best practices";
        }
        else
        {
            return @"You are a Technical Assistant specializing in Azure and Microsoft 365 guidance.

CAPABILITIES:
- Provide detailed Azure and Microsoft 365 technical guidance
- Explain implementation steps and best practices
- Help with Azure AD, Conditional Access, MFA, and security configurations

RESPONSE STRATEGY:
- Provide comprehensive technical guidance
- Include step-by-step implementation instructions
- Reference best practices and security considerations";
        }
    }

    /// <summary>
    /// Demonstrate realistic business scenarios.
    /// 
    /// This function showcases the practical value of the Modern Workplace Assistant
    /// by walking through scenarios that enterprise employees face regularly.
    /// 
    /// Educational Value:
    /// - Shows real business problems that AI agents can solve
    /// - Demonstrates proper thread and message management
    /// - Illustrates conversation patterns with tool usage
    /// </summary>
    private static async Task DemonstrateBusinessScenariosAsync(PersistentAgent agent)
    {
        var scenarios = new[]
        {
            new
            {
                Title = "📋 Company Policy Question (SharePoint Only)",
                Question = "What is Contoso's remote work policy?",
                Context = "Employee needs to understand company-specific remote work requirements",
                LearningPoint = "SharePoint tool retrieves internal company policies"
            },
            new
            {
                Title = "📚 Technical Documentation Question (MCP Only)",
                Question = "According to Microsoft Learn, what is the correct way to implement Azure AD Conditional Access policies? Please include reference links to the official documentation.",
                Context = "IT administrator needs authoritative Microsoft technical guidance",
                LearningPoint = "MCP tool accesses Microsoft Learn for official documentation with links"
            },
            new
            {
                Title = "🔄 Combined Implementation Question (SharePoint + MCP)",
                Question = "Based on our company's remote work security policy, how should I configure my Azure environment to comply? Please include links to Microsoft documentation showing how to implement each requirement.",
                Context = "Need to map company policy to technical implementation with official guidance",
                LearningPoint = "Both tools work together: SharePoint for policy + MCP for implementation docs"
            }
        };

        Console.WriteLine("\n" + "".PadRight(70, '='));
        Console.WriteLine("🏢 MODERN WORKPLACE ASSISTANT - BUSINESS SCENARIO DEMONSTRATION");
        Console.WriteLine("".PadRight(70, '='));
        Console.WriteLine("This demonstration shows how AI agents solve real business problems");
        Console.WriteLine("using the Azure AI Agents SDK with SharePoint and MCP tools.");
        Console.WriteLine("".PadRight(70, '='));

        for (int i = 0; i < scenarios.Length; i++)
        {
            var scenario = scenarios[i];
            Console.WriteLine($"\n📊 SCENARIO {i + 1}/{scenarios.Length}: {scenario.Title}");
            Console.WriteLine("".PadRight(50, '-'));
            Console.WriteLine($"❓ QUESTION: {scenario.Question}");
            Console.WriteLine($"🎯 BUSINESS CONTEXT: {scenario.Context}");
            Console.WriteLine($"🎓 LEARNING POINT: {scenario.LearningPoint}");
            Console.WriteLine("".PadRight(50, '-'));

            // <agent_conversation>
            Console.WriteLine("🤖 ASSISTANT RESPONSE:");
            var (response, status) = await ChatWithAssistantAsync(agent, scenario.Question);
            // </agent_conversation>

            // Display response with analysis
            if (status == "completed" && !string.IsNullOrWhiteSpace(response) && response.Length > 10)
            {
                var preview = response.Length > 500 ? response.Substring(0, 500) + "..." : response;
                Console.WriteLine($"✅ SUCCESS: {preview}");
                if (response.Length > 500)
                {
                    Console.WriteLine($"   📏 Full response: {response.Length} characters");
                }
            }
            else
            {
                Console.WriteLine($"⚠️  RESPONSE: {response}");
            }

            Console.WriteLine($"📈 STATUS: {status}");
            Console.WriteLine("".PadRight(50, '-'));

            // Small delay between scenarios
            await Task.Delay(1000);
        }

        Console.WriteLine("\n✅ DEMONSTRATION COMPLETED!");
        Console.WriteLine("🎓 Key Learning Outcomes:");
        Console.WriteLine("   • Azure AI Agents SDK usage for enterprise AI");
        Console.WriteLine("   • Proper thread and message management");
        Console.WriteLine("   • SharePoint + MCP tool integration");
        Console.WriteLine("   • MCP tool approval handling");
        Console.WriteLine("   • Real business value through AI assistance");
        Console.WriteLine("   • Foundation for governance and monitoring (Tutorials 2-3)");
    }

    /// <summary>
    /// Execute a conversation with the workplace assistant.
    /// 
    /// This function demonstrates the conversation pattern including:
    /// - Thread creation and message handling
    /// - MCP tool approval handling (auto-approve pattern)
    /// - Proper run status monitoring
    /// 
    /// Educational Value:
    /// - Shows proper conversation management
    /// - Demonstrates MCP approval with SubmitToolApprovalAction
    /// - Includes timeout and error management patterns
    /// </summary>
    // <mcp_approval_handler>
    private static async Task<(string response, string status)> ChatWithAssistantAsync(PersistentAgent agent, string message)
    {
        try
        {
            // Create a thread for the conversation
            PersistentAgentThread thread = await agentsClient!.Threads.CreateThreadAsync();

            // Create a message in the thread
            await agentsClient.Messages.CreateMessageAsync(
                thread.Id,
                MessageRole.User,
                message
            );

            // Setup MCP tool resources if MCP is configured
            ToolResources? toolResources = null;
            if (!string.IsNullOrEmpty(mcpServerLabel))
            {
                MCPToolResource mcpToolResource = new(mcpServerLabel);
                toolResources = mcpToolResource.ToToolResources();
            }

            // Create and run the agent
            ThreadRun run = await agentsClient.Runs.CreateRunAsync(
                thread,
                agent,
                toolResources
            );

            // <mcp_approval_usage>
            // Handle run execution and MCP tool approvals
            // This loop polls the run status and automatically approves MCP tool calls
            int maxIterations = 60; // 30 second timeout
            int iteration = 0;

            while ((run.Status == RunStatus.Queued || 
                    run.Status == RunStatus.InProgress || 
                    run.Status == RunStatus.RequiresAction) && 
                   iteration < maxIterations)
            {
                await Task.Delay(500);
                run = await agentsClient.Runs.GetRunAsync(thread.Id, run.Id);
                iteration++;

                // Handle MCP tool approval requests
                if (run.Status == RunStatus.RequiresAction && 
                    run.RequiredAction is SubmitToolApprovalAction toolApprovalAction)
                {
                    var toolApprovals = new List<ToolApproval>();

                    foreach (var toolCall in toolApprovalAction.SubmitToolApproval.ToolCalls)
                    {
                        if (toolCall is RequiredMcpToolCall mcpToolCall)
                        {
                            Console.WriteLine($"   🔧 Approving MCP tool: {mcpToolCall.Name}");
                            
                            // Auto-approve MCP tool calls
                            // In production, you might implement custom approval logic here:
                            // - RBAC checks (is user authorized for this tool?)
                            // - Cost controls (has budget limit been reached?)
                            // - Logging and auditing
                            // - Interactive approval prompts
                            toolApprovals.Add(new ToolApproval(mcpToolCall.Id, approve: true));
                        }
                    }

                    if (toolApprovals.Count > 0)
                    {
                        run = await agentsClient.Runs.SubmitToolOutputsToRunAsync(
                            thread.Id,
                            run.Id,
                            toolApprovals: toolApprovals
                        );
                    }
                }
            }
            // </mcp_approval_usage>

            // Retrieve messages if completed
            if (run.Status == RunStatus.Completed)
            {
                var messages = agentsClient.Messages.GetMessages(
                    thread.Id,
                    order: ListSortOrder.Descending
                );

                // Get the assistant's response (most recent agent message)
                foreach (PersistentThreadMessage threadMessage in messages)
                {
                    if (threadMessage.Role == MessageRole.Agent)
                    {
                        foreach (MessageContent contentItem in threadMessage.ContentItems)
                        {
                            if (contentItem is MessageTextContent textItem)
                            {
                                // Cleanup thread
                                await agentsClient.Threads.DeleteThreadAsync(thread.Id);
                                return (textItem.Text, "completed");
                            }
                        }
                    }
                }

                await agentsClient.Threads.DeleteThreadAsync(thread.Id);
                return ("No response from assistant", "completed");
            }
            else if (run.Status == RunStatus.Failed)
            {
                await agentsClient.Threads.DeleteThreadAsync(thread.Id);
                return ($"Run failed: {run.LastError?.Message ?? "Unknown error"}", "failed");
            }
            else
            {
                await agentsClient.Threads.DeleteThreadAsync(thread.Id);
                return ($"Run ended with status: {run.Status}", run.Status.ToString().ToLower());
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"\n❌ Exception details: {ex.GetType().Name}: {ex.Message}");
            if (ex.InnerException != null)
            {
                Console.WriteLine($"   Inner: {ex.InnerException.Message}");
            }
            return ($"Error in conversation: {ex.Message}", "failed");
        }
    }
    // </mcp_approval_handler>

    /// <summary>
    /// Interactive mode for testing the workplace assistant.
    /// 
    /// This provides a simple interface for users to test the agent with their own questions
    /// and see how it provides comprehensive technical guidance.
    /// </summary>
    private static async Task InteractiveModeAsync(PersistentAgent agent)
    {
        Console.WriteLine("\n" + "".PadRight(60, '='));
        Console.WriteLine("💬 INTERACTIVE MODE - Test Your Workplace Assistant!");
        Console.WriteLine("".PadRight(60, '='));
        Console.WriteLine("Ask questions about Azure, M365, security, and technical implementation:");
        Console.WriteLine("• 'How do I configure Azure AD conditional access?'");
        Console.WriteLine("• 'What are MFA best practices for remote workers?'");
        Console.WriteLine("• 'How do I set up secure SharePoint access?'");
        Console.WriteLine("Type 'quit' to exit.");
        Console.WriteLine("".PadRight(60, '-'));

        while (true)
        {
            try
            {
                Console.Write("\n❓ Your question: ");
                string? question = Console.ReadLine()?.Trim();

                if (string.IsNullOrEmpty(question))
                {
                    Console.WriteLine("💡 Please ask a question about Azure or M365 technical implementation.");
                    continue;
                }

                if (question.ToLower() is "quit" or "exit" or "bye")
                {
                    break;
                }

                Console.Write("\n🤖 Workplace Assistant: ");
                var (response, status) = await ChatWithAssistantAsync(agent, question);
                Console.WriteLine(response);

                if (status != "completed")
                {
                    Console.WriteLine($"\n⚠️  Response status: {status}");
                }

                Console.WriteLine("".PadRight(60, '-'));
            }
            catch (Exception ex)
            {
                Console.WriteLine($"\n❌ Error: {ex.Message}");
                Console.WriteLine("".PadRight(60, '-'));
            }
        }

        Console.WriteLine("\n👋 Thank you for testing the Modern Workplace Assistant!");
    }
}
