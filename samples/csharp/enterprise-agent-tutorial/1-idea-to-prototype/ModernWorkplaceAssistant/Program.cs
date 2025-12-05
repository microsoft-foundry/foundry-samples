#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates

// <imports_and_includes>
using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Azure;
using Azure.AI.Agents;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using OpenAI;
using OpenAI.Responses;
// </imports_and_includes>

/*
 * Azure AI Foundry Agent Sample - Tutorial 1: Modern Workplace Assistant
 * 
 * This sample demonstrates a complete business scenario using Azure AI Agents SDK v2:
 * - Agent creation with the new SDK
 * - Conversation and response management
 * - Robust error handling and graceful degradation
 * 
 * Educational Focus:
 * - Enterprise AI patterns with Agent SDK v2
 * - Real-world business scenarios that enterprises face daily
 * - Production-ready error handling and diagnostics
 * - Foundation for governance, evaluation, and monitoring (Tutorials 2-3)
 * 
 * Business Scenario:
 * An employee needs to implement Azure AD multi-factor authentication. They need:
 * 1. Company security policy requirements
 * 2. Technical implementation steps
 * 3. Combined guidance showing how policy requirements map to technical implementation
 */

class Program
{
    private static AgentsClient? agentsClient;
    private static OpenAIResponseClient? responseClient;
    private static AgentConversation? conversation;

    static async Task Main(string[] args)
    {
        Console.WriteLine("🚀 Azure AI Foundry - Modern Workplace Assistant");
        Console.WriteLine("Tutorial 1: Building Enterprise Agents with Agent SDK v2");
        Console.WriteLine("".PadRight(70, '='));

        try
        {
            // Create the agent with full diagnostic output
            string agentName = await CreateWorkplaceAssistantAsync();

            // Demonstrate business scenarios
            await DemonstrateBusinessScenariosAsync(agentName);

            // Offer interactive testing
            Console.Write("\n🎯 Try interactive mode? (y/n): ");
            var response = Console.ReadLine();
            if (response?.ToLower().StartsWith("y") == true)
            {
                await InteractiveModeAsync(agentName);
            }

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
    /// Create a Modern Workplace Assistant using Agent SDK v2.
    /// 
    /// This demonstrates enterprise AI patterns:
    /// 1. Agent creation with the new SDK
    /// 2. Robust error handling with graceful degradation
    /// 3. Clear diagnostic information for troubleshooting
    /// 
    /// Educational Value:
    /// - Shows real-world complexity of enterprise AI systems
    /// - Demonstrates how to handle partial system failures
    /// - Provides patterns for agent creation with Agent SDK v2
    /// 
    /// Note: Tool integration (SharePoint, MCP) is being explored for SDK v2 beta.
    /// This version demonstrates the core agent functionality.
    /// </summary>
    private static async Task<string> CreateWorkplaceAssistantAsync()
    {
        // Load environment variables
        Env.Load(".env");

        var projectEndpoint = Environment.GetEnvironmentVariable("PROJECT_ENDPOINT");
        var modelDeploymentName = Environment.GetEnvironmentVariable("MODEL_DEPLOYMENT_NAME");
        var tenantId = Environment.GetEnvironmentVariable("AI_FOUNDRY_TENANT_ID");

        if (string.IsNullOrEmpty(projectEndpoint))
            throw new InvalidOperationException("PROJECT_ENDPOINT environment variable not set");
        if (string.IsNullOrEmpty(modelDeploymentName))
            throw new InvalidOperationException("MODEL_DEPLOYMENT_NAME environment variable not set");

        Console.WriteLine("\n🤖 Creating Modern Workplace Assistant...");

        // ============================================================================
        // AUTHENTICATION SETUP
        // ============================================================================
        // <agent_authentication>
        TokenCredential credential;
        if (!string.IsNullOrEmpty(tenantId))
        {
            Console.WriteLine($"🔐 Using AI Foundry tenant: {tenantId}");
            credential = new AzureCliCredential(new AzureCliCredentialOptions { TenantId = tenantId });
        }
        else
        {
            credential = new DefaultAzureCredential();
        }

        agentsClient = new AgentsClient(new Uri(projectEndpoint), credential);
        Console.WriteLine($"✅ Connected to Azure AI Foundry: {projectEndpoint}");
        // </agent_authentication>

        // ========================================================================
        // AGENT CREATION
        // ========================================================================
        string instructions = @"You are a Technical Assistant specializing in Azure and Microsoft 365 guidance.

CAPABILITIES:
- Provide detailed Azure and Microsoft 365 technical guidance
- Explain implementation steps and best practices
- Help with Azure AD, Conditional Access, MFA, and security configurations

RESPONSE STRATEGY:
- Provide comprehensive technical guidance
- Include step-by-step implementation instructions
- Reference best practices and security considerations
- For policy questions, explain common enterprise policies and how to implement them
- For technical questions, provide detailed Azure/M365 implementation steps

EXAMPLE SCENARIOS:
- ""What is a typical enterprise MFA policy?"" → Explain common MFA policies and their implementation
- ""How do I configure Azure AD Conditional Access?"" → Provide detailed technical steps
- ""What are the best practices for remote work security?"" → Combine policy recommendations with implementation guidance";

        // <create_agent>
        Console.WriteLine($"🛠️  Creating agent with model: {modelDeploymentName}");

        AgentDefinition agentDefinition = new PromptAgentDefinition(modelDeploymentName)
        {
            Instructions = instructions
        };

        AgentVersion agent = await agentsClient.CreateAgentVersionAsync(
            "Modern_Workplace_Assistant",
            agentDefinition
        );

        Console.WriteLine("✅ Agent created successfully");
        Console.WriteLine($"   Agent Name: {agent.Name}");
        Console.WriteLine($"   Agent Version: {agent.Version}");

        Console.WriteLine("\n⚠️  Note: SDK v2 beta status:");
        Console.WriteLine("   - Core agent conversation functionality working");
        Console.WriteLine("   - Tool integration patterns being finalized");
        // </create_agent>

        // Initialize OpenAI client for conversations
        OpenAIClient openAIClient = agentsClient.GetOpenAIClient();
        responseClient = openAIClient.GetOpenAIResponseClient(modelDeploymentName);

        // Create a conversation to maintain state
        conversation = await agentsClient.GetConversationsClient().CreateConversationAsync();

        return agent.Name;
    }

    /// <summary>
    /// Demonstrate realistic business scenarios with Agent SDK v2.
    /// 
    /// This function showcases the practical value of the Modern Workplace Assistant
    /// by walking through scenarios that enterprise employees face regularly.
    /// 
    /// Educational Value:
    /// - Shows real business problems that AI agents can solve
    /// - Demonstrates proper conversation and response management
    /// - Illustrates Agent SDK v2 conversation patterns
    /// </summary>
    private static async Task DemonstrateBusinessScenariosAsync(string agentName)
    {
        var scenarios = new[]
        {
            new
            {
                Title = "📋 Enterprise Policy Question",
                Question = "What is a typical enterprise remote work policy for security?",
                Context = "Employee needs to understand common enterprise remote work requirements",
                LearningPoint = "Agent provides general guidance on enterprise policies"
            },
            new
            {
                Title = "📚 Technical Documentation Question",
                Question = "What is the correct way to implement Azure AD Conditional Access policies?",
                Context = "IT administrator needs technical implementation guidance",
                LearningPoint = "Agent provides detailed Azure technical implementation steps"
            },
            new
            {
                Title = "🔄 Combined Implementation Question",
                Question = "How should I configure my Azure environment for secure remote work with MFA?",
                Context = "Need practical implementation combining security best practices",
                LearningPoint = "Agent combines policy guidance with technical implementation"
            }
        };

        Console.WriteLine("\n" + "".PadRight(70, '='));
        Console.WriteLine("🏢 MODERN WORKPLACE ASSISTANT - BUSINESS SCENARIO DEMONSTRATION");
        Console.WriteLine("".PadRight(70, '='));
        Console.WriteLine("This demonstration shows how AI agents solve real business problems");
        Console.WriteLine("using the Azure AI Agents SDK v2.");
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
            var (response, status) = await ChatWithAssistantAsync(agentName, scenario.Question);
            // </agent_conversation>

            // Display response with analysis
            if (status == "completed" && !string.IsNullOrWhiteSpace(response) && response.Length > 10)
            {
                var preview = response.Length > 300 ? response.Substring(0, 300) + "..." : response;
                Console.WriteLine($"✅ SUCCESS: {preview}");
                if (response.Length > 300)
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
        Console.WriteLine("   • Agent SDK v2 usage for enterprise AI");
        Console.WriteLine("   • Proper conversation and response management");
        Console.WriteLine("   • Real business value through AI assistance");
        Console.WriteLine("   • Foundation for governance and monitoring (Tutorials 2-3)");
    }

    /// <summary>
    /// Execute a conversation with the workplace assistant using Agent SDK v2.
    /// 
    /// This function demonstrates the conversation pattern for Azure AI Agents SDK v2.
    /// 
    /// Educational Value:
    /// - Shows proper conversation management with Agent SDK v2
    /// - Demonstrates conversation creation and message handling
    /// - Includes error management patterns
    /// </summary>
    private static async Task<(string response, string status)> ChatWithAssistantAsync(string agentName, string message)
    {
        try
        {
            // <create_response>
            // Set up response creation options with agent and conversation references
            ResponseCreationOptions responseCreationOptions = new();
            responseCreationOptions.SetAgentReference(agentName);
            responseCreationOptions.SetConversationReference(conversation!);

            // Create the user message item
            List<ResponseItem> items = [ResponseItem.CreateUserMessageItem(message)];

            // Create response from the agent
            OpenAIResponse response = await responseClient!.CreateResponseAsync(items, responseCreationOptions);

            // Extract the response text
            string responseText = response.GetOutputText();
            // </create_response>

            return (responseText, "completed");
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

    /// <summary>
    /// Interactive mode for testing the workplace assistant.
    /// 
    /// This provides a simple interface for users to test the agent with their own questions
    /// and see how it provides comprehensive technical guidance.
    /// </summary>
    private static async Task InteractiveModeAsync(string agentName)
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
                var (response, status) = await ChatWithAssistantAsync(agentName, question);
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
