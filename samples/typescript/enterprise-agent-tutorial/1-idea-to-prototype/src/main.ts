#!/usr/bin/env node
/**
 * Azure AI Foundry Agent Sample - Tutorial 1: Modern Workplace Assistant
 *
 * This sample demonstrates a complete business scenario using Azure AI Agents SDK v2:
 * - Agent creation with the new SDK
 * - Thread and message management
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

// <imports_and_includes>
import { AgentsClient } from "@azure/ai-agents-ii";
import { getBearerTokenProvider, DefaultAzureCredential } from "@azure/identity";
import OpenAI from "openai";
import { config } from "dotenv";
import * as readline from "readline";

// Import for connection resolution
let AIProjectClient: any;
let ConnectionType: any;
let HAS_PROJECT_CLIENT = false;

try {
  const projectModule = require("@azure/ai-projects");
  AIProjectClient = projectModule.AIProjectClient;
  ConnectionType = projectModule.ConnectionType;
  HAS_PROJECT_CLIENT = true;
} catch (error) {
  HAS_PROJECT_CLIENT = false;
}
// </imports_and_includes>

config();

// ============================================================================
// AUTHENTICATION SETUP
// ============================================================================
// <agent_authentication>
// Support default Azure credentials
const credential = new DefaultAzureCredential();

const agentsClient = new AgentsClient(
  process.env.PROJECT_ENDPOINT || "",
  credential,
  {
    apiVersion: "2025-05-15-preview",
  }
);

// Create OpenAI client for conversations
let openAIClient: OpenAI;

async function initializeOpenAIClient() {
  const scope = "https://ai.azure.com/.default";
  const azureADTokenProvider = await getBearerTokenProvider(credential, scope);

  openAIClient = new OpenAI({
    apiKey: azureADTokenProvider,
    baseURL: `${process.env.PROJECT_ENDPOINT}/openai`,
    defaultQuery: { "api-version": "2025-05-15-preview" },
  });
}

console.log(`✅ Connected to Azure AI Foundry: ${process.env.PROJECT_ENDPOINT}`);
// </agent_authentication>

interface Agent {
  id: string;
  model: string;
  name: string;
  version?: string;
}

interface ChatResponse {
  response: string;
  status: string;
}

async function createWorkplaceAssistant(): Promise<Agent> {
  /**
   * Create a Modern Workplace Assistant using Agent SDK v2.
   *
   * This demonstrates enterprise AI patterns:
   * 1. Agent creation with the new SDK
   * 2. Robust error handling with graceful degradation
   * 3. Dynamic agent capabilities based on available resources
   * 4. Clear diagnostic information for troubleshooting
   *
   * Educational Value:
   * - Shows real-world complexity of enterprise AI systems
   * - Demonstrates how to handle partial system failures
   * - Provides patterns for agent creation with Agent SDK v2
   */

  console.log("🤖 Creating Modern Workplace Assistant...");

  // ========================================================================
  // SHAREPOINT INTEGRATION SETUP
  // ========================================================================
  // <sharepoint_connection_resolution>
  const sharepointResourceName = process.env.SHAREPOINT_RESOURCE_NAME;
  let sharepointTool: any = null;

  if (sharepointResourceName) {
    console.log("📁 Configuring SharePoint integration...");
    console.log(`   Connection name: ${sharepointResourceName}`);

    try {
      console.log("   🔍 Resolving connection name to ARM resource ID...");

      if (HAS_PROJECT_CLIENT) {
        // Use AIProjectClient to list and find the connection
        const projectClient = new AIProjectClient(
          process.env.PROJECT_ENDPOINT || "",
          credential
        );

        // List all connections and find the one we need
        const connections = await projectClient.connections.list();
        let connectionId: string | null = null;

        for await (const conn of connections) {
          if (conn.name === sharepointResourceName) {
            connectionId = conn.id;
            console.log(`   ✅ Resolved to: ${connectionId}`);
            break;
          }
        }

        if (!connectionId) {
          throw new Error(
            `Connection '${sharepointResourceName}' not found in project`
          );
        }

        // Create SharePoint tool with the full ARM resource ID
        sharepointTool = {
          type: "sharepoint",
          connectionId: connectionId,
        };
        console.log("✅ SharePoint tool configured successfully");
      } else {
        throw new Error("azure-ai-projects not installed");
      }
    } catch (error: any) {
      if (error.message === "azure-ai-projects not installed") {
        console.log("⚠️  Connection resolution requires @azure/ai-projects package");
        console.log("   Install with: npm install @azure/ai-projects");
        console.log("   Agent will operate without SharePoint access");
      } else {
        console.log(`⚠️  SharePoint connection unavailable: ${error.message}`);
        console.log("   Possible causes:");
        console.log(
          `   - Connection '${sharepointResourceName}' doesn't exist in the project`
        );
        console.log("   - Insufficient permissions to access the connection");
        console.log("   - Connection configuration is incomplete");
        console.log("   Agent will operate without SharePoint access");
      }
      sharepointTool = null;
    }
  } else {
    console.log("📁 SharePoint integration skipped (SHAREPOINT_RESOURCE_NAME not set)");
  }
  // </sharepoint_connection_resolution>

  // ========================================================================
  // MICROSOFT LEARN MCP INTEGRATION SETUP
  // ========================================================================
  // <mcp_tool_setup>
  const mcpServerUrl = process.env.MCP_SERVER_URL;
  let mcpTool: any = null;

  if (mcpServerUrl) {
    console.log("📚 Configuring Microsoft Learn MCP integration...");
    console.log(`   Server URL: ${mcpServerUrl}`);

    try {
      // Create MCP tool for Microsoft Learn documentation access
      mcpTool = {
        type: "mcp",
        serverUrl: mcpServerUrl,
        serverLabel: "Microsoft_Learn_Documentation",
      };
      console.log("✅ MCP tool configured successfully");
    } catch (error: any) {
      console.log(`⚠️  MCP tool unavailable: ${error.message}`);
      console.log("   Agent will operate without Microsoft Learn access");
      mcpTool = null;
    }
  } else {
    console.log("📚 MCP integration skipped (MCP_SERVER_URL not set)");
  }
  // </mcp_tool_setup>

  // ========================================================================
  // AGENT CREATION WITH DYNAMIC CAPABILITIES
  // ========================================================================
  let instructions: string;

  if (sharepointTool && mcpTool) {
    instructions = `You are a Modern Workplace Assistant for Contoso Corporation.

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
- "Our policy requires MFA - how do I implement this?" → Combine policy requirements with implementation guidance`;
  } else if (sharepointTool) {
    instructions = `You are a Modern Workplace Assistant with access to Contoso Corporation's SharePoint.

CAPABILITIES:
- Search SharePoint for company policies, procedures, and internal documentation
- Provide detailed technical guidance based on your knowledge
- Combine company policies with general best practices

RESPONSE STRATEGY:
- Search SharePoint for company-specific requirements
- Provide technical guidance based on Azure and M365 best practices
- Explain how to align implementations with company policies`;
  } else if (mcpTool) {
    instructions = `You are a Technical Assistant with access to Microsoft Learn documentation.

CAPABILITIES:
- Access Microsoft Learn for current Azure and Microsoft 365 technical guidance
- Provide detailed implementation steps and best practices
- Explain Azure services, features, and configuration options

RESPONSE STRATEGY:
- Use Microsoft Learn for technical documentation
- Provide comprehensive implementation guidance
- Reference official documentation and best practices`;
  } else {
    instructions = `You are a Technical Assistant specializing in Azure and Microsoft 365 guidance.

CAPABILITIES:
- Provide detailed Azure and Microsoft 365 technical guidance
- Explain implementation steps and best practices
- Help with Azure AD, Conditional Access, MFA, and security configurations

RESPONSE STRATEGY:
- Provide comprehensive technical guidance
- Include step-by-step implementation instructions
- Reference best practices and security considerations`;
  }

  // <create_agent_with_tools>
  console.log(
    `🛠️  Creating agent with model: ${process.env.MODEL_DEPLOYMENT_NAME}`
  );

  const tools: any[] = [];

  if (sharepointTool) {
    tools.push(sharepointTool);
    console.log("   ✓ SharePoint tool added");
  }

  if (mcpTool) {
    tools.push(mcpTool);
    console.log("   ✓ MCP tool added");
  }

  console.log(`   Total tools: ${tools.length}`);

  // Create agent with or without tools
  const agent = await agentsClient.createAgent(
    process.env.MODEL_DEPLOYMENT_NAME || "gpt-4o",
    {
      name: "Modern Workplace Assistant",
      instructions: instructions,
      tools: tools.length > 0 ? tools : undefined,
    }
  );

  console.log(`✅ Agent created successfully: ${agent.id}`);
  return agent as Agent;
  // </create_agent_with_tools>
}

// <mcp_approval_handler>
class MCPApprovalHandler {
  /**
   * Handler to automatically approve MCP tool calls.
   *
   * This demonstrates the MCP approval pattern in Azure AI Agents SDK v2.
   *
   * Educational Value:
   * - Shows proper MCP integration with Agent SDK v2
   * - Demonstrates handler pattern for tool approval
   * - Provides foundation for custom approval logic (RBAC, logging, etc.)
   */

  async submitMcpToolApproval(run: any, toolCall: any): Promise<any> {
    /**
     * Auto-approve MCP tool calls.
     *
     * In production, you might implement custom approval logic here:
     * - RBAC checks (is user authorized for this tool?)
     * - Cost controls (has budget limit been reached?)
     * - Logging and auditing
     * - Interactive approval prompts
     */
    return {
      toolCallId: toolCall.id,
      approve: true,
    };
  }
}
// </mcp_approval_handler>

export async function chatWithAssistant(
  agentId: string,
  message: string
): Promise<ChatResponse> {
  /**
   * Execute a conversation with the workplace assistant using Agent SDK v2.
   *
   * Educational Value:
   * - Shows proper conversation management with Agent SDK v2
   * - Demonstrates thread creation and message handling
   * - Illustrates MCP approval with handler
   * - Includes timeout and error management patterns
   */

  try {
    // Create a thread for the conversation
    const thread = await agentsClient.threads.create();

    // Create a message in the thread
    await agentsClient.messages.create(thread.id, {
      role: "user",
      content: message,
    });

    // <mcp_approval_usage>
    // Use createAndProcess with handler to automatically handle MCP approvals
    const handler = new MCPApprovalHandler();
    const run = await agentsClient.runs.createAndProcess(
      thread.id,
      {
        agentId: agentId,
      },
      {
        runHandler: handler,
      }
    );
    // </mcp_approval_usage>

    // Retrieve messages
    if (run.status === "completed") {
      const messages = await agentsClient.messages.list(thread.id, {
        order: "asc",
      });

      // Get the assistant's response (last message from assistant)
      const messageList = [];
      for await (const msg of messages) {
        messageList.push(msg);
      }

      for (let i = messageList.length - 1; i >= 0; i--) {
        const msg = messageList[i];
        if (msg.role === "assistant" && msg.content && msg.content.length > 0) {
          const textContent = msg.content.find((c: any) => c.type === "text");
          if (textContent && textContent.text) {
            return {
              response: textContent.text.value,
              status: "completed",
            };
          }
        }
      }

      return {
        response: "No response from assistant",
        status: "completed",
      };
    } else {
      return {
        response: `Run ended with status: ${run.status}`,
        status: run.status,
      };
    }
  } catch (error: any) {
    return {
      response: `Error in conversation: ${error.message}`,
      status: "failed",
    };
  }
}

async function demonstrateBusinessScenarios(agent: Agent): Promise<boolean> {
  /**
   * Demonstrate realistic business scenarios with Agent SDK v2.
   *
   * Educational Value:
   * - Shows real business problems that AI agents can solve
   * - Demonstrates proper thread and message management
   * - Illustrates Agent SDK v2 conversation patterns
   */

  const scenarios = [
    {
      title: "📋 Company Policy Question (SharePoint Only)",
      question: "What is Contoso's remote work policy?",
      context: "Employee needs to understand company-specific remote work requirements",
      learningPoint: "SharePoint tool retrieves internal company policies",
    },
    {
      title: "📚 Technical Documentation Question (MCP Only)",
      question:
        "According to Microsoft Learn, what is the correct way to implement Azure AD Conditional Access policies? Please include reference links to the official documentation.",
      context: "IT administrator needs authoritative Microsoft technical guidance",
      learningPoint:
        "MCP tool accesses Microsoft Learn for official documentation with links",
    },
    {
      title: "🔄 Combined Implementation Question (SharePoint + MCP)",
      question:
        "Based on our company's remote work security policy, how should I configure my Azure environment to comply? Please include links to Microsoft documentation showing how to implement each requirement.",
      context:
        "Need to map company policy to technical implementation with official guidance",
      learningPoint:
        "Both tools work together: SharePoint for policy + MCP for implementation docs",
    },
  ];

  console.log("\n" + "=".repeat(70));
  console.log("🏢 MODERN WORKPLACE ASSISTANT - BUSINESS SCENARIO DEMONSTRATION");
  console.log("=".repeat(70));
  console.log("This demonstration shows how AI agents solve real business problems");
  console.log("using the Azure AI Agents SDK v2.");
  console.log("=".repeat(70));

  for (let i = 0; i < scenarios.length; i++) {
    const scenario = scenarios[i];
    console.log(`\n📊 SCENARIO ${i + 1}/${scenarios.length}: ${scenario.title}`);
    console.log("-".repeat(50));
    console.log(`❓ QUESTION: ${scenario.question}`);
    console.log(`🎯 BUSINESS CONTEXT: ${scenario.context}`);
    console.log(`🎓 LEARNING POINT: ${scenario.learningPoint}`);
    console.log("-".repeat(50));

    // <agent_conversation>
    console.log("🤖 ASSISTANT RESPONSE:");
    const { response, status } = await chatWithAssistant(agent.id, scenario.question);
    // </agent_conversation>

    if (status === "completed" && response && response.trim().length > 10) {
      const preview = response.substring(0, 300);
      console.log(`✅ SUCCESS: ${preview}...`);
      if (response.length > 300) {
        console.log(`   📏 Full response: ${response.length} characters`);
      }
    } else {
      console.log(`⚠️  RESPONSE: ${response}`);
    }

    console.log(`📈 STATUS: ${status}`);
    console.log("-".repeat(50));

    // Small delay between scenarios
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  console.log("\n✅ DEMONSTRATION COMPLETED!");
  console.log("🎓 Key Learning Outcomes:");
  console.log("   • Agent SDK v2 usage for enterprise AI");
  console.log("   • Proper thread and message management");
  console.log("   • Real business value through AI assistance");
  console.log(
    "   • Foundation for governance and monitoring (Tutorials 2-3)"
  );

  return true;
}

async function interactiveMode(agent: Agent): Promise<void> {
  /**
   * Interactive mode for testing the workplace assistant.
   */

  console.log("\n" + "=".repeat(60));
  console.log("💬 INTERACTIVE MODE - Test Your Workplace Assistant!");
  console.log("=".repeat(60));
  console.log("Ask questions about Azure, M365, security, and technical implementation:");
  console.log("• 'How do I configure Azure AD conditional access?'");
  console.log("• 'What are MFA best practices for remote workers?'");
  console.log("• 'How do I set up secure SharePoint access?'");
  console.log("Type 'quit' to exit.");
  console.log("-".repeat(60));

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  const askQuestion = (): Promise<string> => {
    return new Promise((resolve) => {
      rl.question("\n❓ Your question: ", (answer) => {
        resolve(answer);
      });
    });
  };

  try {
    while (true) {
      const question = await askQuestion();

      if (
        question.toLowerCase() === "quit" ||
        question.toLowerCase() === "exit" ||
        question.toLowerCase() === "bye"
      ) {
        break;
      }

      if (!question.trim()) {
        console.log(
          "💡 Please ask a question about Azure or M365 technical implementation."
        );
        continue;
      }

      process.stdout.write("\n🤖 Workplace Assistant: ");
      const { response, status } = await chatWithAssistant(agent.id, question);
      console.log(response);

      if (status !== "completed") {
        console.log(`\n⚠️  Response status: ${status}`);
      }

      console.log("-".repeat(60));
    }
  } finally {
    rl.close();
  }

  console.log("\n👋 Thank you for testing the Modern Workplace Assistant!");
}

async function main(): Promise<void> {
  /**
   * Main execution flow demonstrating the complete sample.
   */

  console.log("🚀 Azure AI Foundry - Modern Workplace Assistant");
  console.log("Tutorial 1: Building Enterprise Agents with Agent SDK v2");
  console.log("=".repeat(70));

  try {
    // Create the agent with full diagnostic output
    const agent = await createWorkplaceAssistant();

    // Demonstrate business scenarios
    await demonstrateBusinessScenarios(agent);

    // Offer interactive testing
    process.stdout.write("\n🎯 Try interactive mode? (y/n): ");

    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
    });

    rl.question("", async (answer) => {
      if (answer.toLowerCase().startsWith("y")) {
        await interactiveMode(agent);
      }

      console.log("\n🎉 Sample completed successfully!");
      console.log(
        "📚 This foundation supports Tutorial 2 (Governance) and Tutorial 3 (Production)"
      );
      console.log(
        "🔗 Next: Add evaluation metrics, monitoring, and production deployment"
      );

      rl.close();
      process.exit(0);
    });
  } catch (error: any) {
    console.log(`\n❌ Error: ${error.message}`);
    console.log("Please check your .env configuration and ensure:");
    console.log("  - PROJECT_ENDPOINT is correct");
    console.log("  - MODEL_DEPLOYMENT_NAME is deployed");
    console.log("  - Azure credentials are configured (az login)");
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}
