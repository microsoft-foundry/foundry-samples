// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

package com.microsoft.azure.samples;

// <imports_and_includes>
import com.azure.ai.agents.AgentsClient;
import com.azure.ai.agents.AgentsClientBuilder;
import com.azure.ai.agents.ConversationsClient;
import com.azure.ai.agents.ResponsesClient;
import com.azure.ai.agents.models.AgentReference;
import com.azure.ai.agents.models.AgentVersionObject;
import com.azure.ai.agents.models.PromptAgentDefinition;
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.openai.models.conversations.Conversation;
import com.openai.models.conversations.items.ItemCreateParams;
import com.openai.models.responses.EasyInputMessage;
import com.openai.models.responses.Response;
import io.github.cdimascio.dotenv.Dotenv;

import java.util.ArrayList;
import java.util.List;
import java.util.Scanner;
// </imports_and_includes>

/**
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
 * 
 * Note: This Java implementation uses the Agent SDK v2 beta which has a different
 * API structure than the Python SDK. Tool integration (SharePoint, MCP) is not yet
 * available in the Java SDK v2 beta.
 */
public class ModernWorkplaceAssistant {

    private static Dotenv dotenv;
    private static AgentsClient agentsClient;
    private static ResponsesClient responsesClient;
    private static ConversationsClient conversationsClient;

    public static void main(String[] args) {
        System.out.println("🚀 Azure AI Foundry - Modern Workplace Assistant");
        System.out.println("Tutorial 1: Building Enterprise Agents with Agent SDK v2 (Java)");
        System.out.println("=".repeat(70));

        try {
            // Load environment variables from current directory
            dotenv = Dotenv.configure()
                    .directory("./")
                    .ignoreIfMissing()
                    .load();

            // Create the agent with full diagnostic output
            AgentVersionObject agent = createWorkplaceAssistant();

            // Demonstrate business scenarios
            demonstrateBusinessScenarios(agent);

            // Offer interactive testing
            System.out.print("\n🎯 Try interactive mode? (y/n): ");
            Scanner scanner = new Scanner(System.in);
            String input = scanner.nextLine().trim();
            if (input.toLowerCase().startsWith("y")) {
                interactiveMode(agent);
            }

            System.out.println("\n🎉 Sample completed successfully!");
            System.out.println("📚 This foundation supports Tutorial 2 (Governance) and Tutorial 3 (Production)");
            System.out.println("🔗 Next: Add evaluation metrics, monitoring, and production deployment");
            
            scanner.close();

        } catch (Exception e) {
            System.out.println("\n❌ Error: " + e.getMessage());
            System.out.println("Please check your .env configuration and ensure:");
            System.out.println("  - PROJECT_ENDPOINT is correct");
            System.out.println("  - MODEL_DEPLOYMENT_NAME is deployed");
            System.out.println("  - Azure credentials are configured (az login)");
            e.printStackTrace();
        }
    }

    /**
     * Create a Modern Workplace Assistant using Agent SDK v2.
     * 
     * This demonstrates enterprise AI patterns:
     * 1. Agent creation with the new SDK
     * 2. Robust error handling with graceful degradation
     * 3. Clear diagnostic information for troubleshooting
     * 
     * Educational Value:
     * - Shows real-world complexity of enterprise AI systems
     * - Demonstrates how to handle partial system failures
     * - Provides patterns for agent creation with Agent SDK v2
     * 
     * Note: Tool integration (SharePoint, MCP) is not available in Java SDK v2 beta.
     * This version demonstrates the core agent functionality.
     * 
     * @return AgentVersionObject for further interaction
     */
    private static AgentVersionObject createWorkplaceAssistant() {
        System.out.println("\n🤖 Creating Modern Workplace Assistant...");

        // ========================================================================
        // AUTHENTICATION SETUP
        // ========================================================================
        // <agent_authentication>
        String endpoint = dotenv.get("PROJECT_ENDPOINT");
        String modelDeploymentName = dotenv.get("MODEL_DEPLOYMENT_NAME");
        
        // Support default Azure credentials
        TokenCredential credential = new DefaultAzureCredentialBuilder().build();

        AgentsClientBuilder builder = new AgentsClientBuilder()
                .endpoint(endpoint)
                .credential(credential);
        
        agentsClient = builder.buildClient();
        responsesClient = builder.buildResponsesClient();
        conversationsClient = builder.buildConversationsClient();
        
        System.out.println("✅ Connected to Azure AI Foundry: " + endpoint);
        // </agent_authentication>

        // ========================================================================
        // AGENT CREATION
        // ========================================================================
        String instructions = """
You are a Technical Assistant specializing in Azure and Microsoft 365 guidance.

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
- "What is a typical enterprise MFA policy?" → Explain common MFA policies and their implementation
- "How do I configure Azure AD Conditional Access?" → Provide detailed technical steps
- "What are the best practices for remote work security?" → Combine policy recommendations with implementation guidance
""";

        // <create_agent>
        System.out.println("🛠️  Creating agent with model: " + modelDeploymentName);
        
        // Create agent definition
        PromptAgentDefinition definition = new PromptAgentDefinition(modelDeploymentName)
                .setInstructions(instructions);

        // Create agent version
        AgentVersionObject agent = agentsClient.createAgentVersion(
                "Modern_Workplace_Assistant",
                definition
        );

        System.out.println("✅ Agent created successfully");
        System.out.println("   Agent ID: " + agent.getId());
        System.out.println("   Agent Name: " + agent.getName());
        System.out.println("   Agent Version: " + agent.getVersion());
        
        System.out.println("\n⚠️  Note: Java SDK v2 beta limitations:");
        System.out.println("   - Tool integration (SharePoint, MCP) not yet available");
        System.out.println("   - This demonstrates core agent conversation functionality");
        System.out.println("   - Full tool support will be added in future releases");
        
        return agent;
        // </create_agent>
    }

    /**
     * Demonstrate realistic business scenarios with Agent SDK v2.
     * 
     * This function showcases the practical value of the Modern Workplace Assistant
     * by walking through scenarios that enterprise employees face regularly.
     * 
     * Educational Value:
     * - Shows real business problems that AI agents can solve
     * - Demonstrates proper conversation management
     * - Illustrates Agent SDK v2 conversation patterns
     */
    private static void demonstrateBusinessScenarios(AgentVersionObject agent) {
        List<BusinessScenario> scenarios = List.of(
                new BusinessScenario(
                        "📋 Enterprise Policy Question",
                        "What is a typical enterprise remote work policy for security?",
                        "Employee needs to understand common enterprise remote work requirements",
                        "Agent provides general guidance on enterprise policies"
                ),
                new BusinessScenario(
                        "📚 Technical Documentation Question",
                        "What is the correct way to implement Azure AD Conditional Access policies?",
                        "IT administrator needs technical implementation guidance",
                        "Agent provides detailed Azure technical implementation steps"
                ),
                new BusinessScenario(
                        "🔄 Combined Implementation Question",
                        "How should I configure my Azure environment for secure remote work with MFA?",
                        "Need practical implementation combining security best practices",
                        "Agent combines policy guidance with technical implementation"
                )
        );

        System.out.println("\n" + "=".repeat(70));
        System.out.println("🏢 MODERN WORKPLACE ASSISTANT - BUSINESS SCENARIO DEMONSTRATION");
        System.out.println("=".repeat(70));
        System.out.println("This demonstration shows how AI agents solve real business problems");
        System.out.println("using the Azure AI Agents SDK v2.");
        System.out.println("=".repeat(70));

        for (int i = 0; i < scenarios.size(); i++) {
            BusinessScenario scenario = scenarios.get(i);
            System.out.println(String.format("\n📊 SCENARIO %d/%d: %s", i + 1, scenarios.size(), scenario.title));
            System.out.println("-".repeat(50));
            System.out.println("❓ QUESTION: " + scenario.question);
            System.out.println("🎯 BUSINESS CONTEXT: " + scenario.context);
            System.out.println("🎓 LEARNING POINT: " + scenario.learningPoint);
            System.out.println("-".repeat(50));

            // <agent_conversation>
            System.out.println("🤖 ASSISTANT RESPONSE:");
            ChatResult result = chatWithAssistant(agent, scenario.question);
            // </agent_conversation>

            // Display response with analysis
            if ("completed".equals(result.status) && result.response != null && result.response.length() > 10) {
                String preview = result.response.length() > 300 
                        ? result.response.substring(0, 300) + "..." 
                        : result.response;
                System.out.println("✅ SUCCESS: " + preview);
                if (result.response.length() > 300) {
                    System.out.println("   📏 Full response: " + result.response.length() + " characters");
                }
            } else {
                System.out.println("⚠️  RESPONSE: " + result.response);
            }

            System.out.println("📈 STATUS: " + result.status);
            System.out.println("-".repeat(50));

            // Small delay between scenarios
            try {
                Thread.sleep(1000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }

        System.out.println("\n✅ DEMONSTRATION COMPLETED!");
        System.out.println("🎓 Key Learning Outcomes:");
        System.out.println("   • Agent SDK v2 usage for enterprise AI");
        System.out.println("   • Proper conversation and response management");
        System.out.println("   • Real business value through AI assistance");
        System.out.println("   • Foundation for governance and monitoring (Tutorials 2-3)");
    }

    /**
     * Execute a conversation with the workplace assistant using Agent SDK v2.
     * 
     * This function demonstrates the conversation pattern for Azure AI Agents SDK v2.
     * 
     * Educational Value:
     * - Shows proper conversation management with Agent SDK v2
     * - Demonstrates conversation creation and message handling
     * - Includes error management patterns
     * 
     * @param agent The agent to chat with
     * @param message The user's message
     * @return ChatResult containing response text and status
     */
    private static ChatResult chatWithAssistant(AgentVersionObject agent, String message) {
        try {
            // <create_conversation>
            // Create a conversation
            Conversation conversation = conversationsClient.getOpenAIClient().create();

            // Add system and user messages to the conversation
            conversationsClient.getOpenAIClient().items().create(
                    ItemCreateParams.builder()
                            .conversationId(conversation.id())
                            .addItem(EasyInputMessage.builder()
                                    .role(EasyInputMessage.Role.USER)
                                    .content(message)
                                    .build())
                            .build()
            );
            // </create_conversation>

            // <create_response>
            // Create agent reference and get response
            AgentReference agentReference = new AgentReference(agent.getName())
                    .setVersion(agent.getVersion());
            
            Response response = responsesClient.createWithAgentConversation(
                    agentReference,
                    conversation.id()
            );
            // </create_response>

            // Extract the response text
            if (response != null && response.output() != null) {
                // Get the first output item's content
                if (!response.output().isEmpty()) {
                    Object firstOutput = response.output().get(0);
                    if (firstOutput != null) {
                        String responseText = firstOutput.toString();
                        return new ChatResult(responseText, "completed");
                    }
                }
            }

            return new ChatResult("No response from assistant", "completed");

        } catch (Exception e) {
            return new ChatResult("Error in conversation: " + e.getMessage(), "failed");
        }
    }

    /**
     * Interactive mode for testing the workplace assistant.
     * 
     * This provides a simple interface for users to test the agent with their own questions
     * and see how it provides comprehensive technical guidance.
     */
    private static void interactiveMode(AgentVersionObject agent) {
        System.out.println("\n" + "=".repeat(60));
        System.out.println("💬 INTERACTIVE MODE - Test Your Workplace Assistant!");
        System.out.println("=".repeat(60));
        System.out.println("Ask questions about Azure, M365, security, and technical implementation:");
        System.out.println("• 'How do I configure Azure AD conditional access?'");
        System.out.println("• 'What are MFA best practices for remote workers?'");
        System.out.println("• 'How do I set up secure SharePoint access?'");
        System.out.println("Type 'quit' to exit.");
        System.out.println("-".repeat(60));

        Scanner scanner = new Scanner(System.in);

        while (true) {
            try {
                System.out.print("\n❓ Your question: ");
                String question = scanner.nextLine().trim();

                if (question.toLowerCase().matches("quit|exit|bye")) {
                    break;
                }

                if (question.isEmpty()) {
                    System.out.println("💡 Please ask a question about Azure or M365 technical implementation.");
                    continue;
                }

                System.out.print("\n🤖 Workplace Assistant: ");
                ChatResult result = chatWithAssistant(agent, question);
                System.out.println(result.response);

                if (!"completed".equals(result.status)) {
                    System.out.println("\n⚠️  Response status: " + result.status);
                }

                System.out.println("-".repeat(60));

            } catch (Exception e) {
                System.out.println("\n❌ Error: " + e.getMessage());
                System.out.println("-".repeat(60));
            }
        }

        System.out.println("\n👋 Thank you for testing the Modern Workplace Assistant!");
    }

    // Helper classes
    private static class BusinessScenario {
        String title;
        String question;
        String context;
        String learningPoint;

        BusinessScenario(String title, String question, String context, String learningPoint) {
            this.title = title;
            this.question = question;
            this.context = context;
            this.learningPoint = learningPoint;
        }
    }

    private static class ChatResult {
        String response;
        String status;

        ChatResult(String response, String status) {
            this.response = response;
            this.status = status;
        }
    }
}
