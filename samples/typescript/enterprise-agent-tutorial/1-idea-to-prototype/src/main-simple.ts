#!/usr/bin/env node
/**
 * Simple Azure AI Foundry Agent Sample - Modern Workplace Assistant
 * Simplified version for demonstration purposes
 */

import { AgentsClient } from "@azure/ai-agents-ii";
import { getBearerTokenProvider, DefaultAzureCredential } from "@azure/identity";
import OpenAI from "openai";
import { config } from "dotenv";

config();

const projectEndpoint = process.env.PROJECT_ENDPOINT || "";
const modelDeploymentName = process.env.MODEL_DEPLOYMENT_NAME || "gpt-4o-mini";

async function main(): Promise<void> {
  console.log("🚀 Azure AI Foundry - Modern Workplace Assistant (Simple Demo)");
  console.log("=".repeat(70));

  try {
    const credential = new DefaultAzureCredential();
    
    // Create Agents client
    const agentsClient = new AgentsClient(projectEndpoint, credential, {
      apiVersion: "2025-05-15-preview",
    });

    console.log("✅ Connected to Azure AI Foundry");
    console.log(`🛠️  Creating agent with model: ${modelDeploymentName}`);

    // Create agent
    const agent = await agentsClient.createVersion("workplace-assistant", {
      kind: "prompt",
      model: modelDeploymentName,
      instructions: "You are a helpful assistant specializing in Azure and Microsoft 365 guidance.",
    });

    console.log(`✅ Agent created: ${agent.name} (version ${agent.version})`);

    // Create OpenAI client for conversations
    const scope = "https://ai.azure.com/.default";
    const azureADTokenProvider = await getBearerTokenProvider(credential, scope);

    const openAIClient = new OpenAI({
      apiKey: azureADTokenProvider,
      baseURL: `${projectEndpoint}/openai`,
      defaultQuery: { "api-version": "2025-05-15-preview" },
    });

    // Create conversation
    console.log("\n📝 Creating conversation...");
    const conversation = await openAIClient.conversations.create({
      items: [
        {
          type: "message",
          role: "user",
          content: "What are the best practices for implementing MFA in Azure AD?",
        },
      ],
    });

    console.log(`✅ Conversation created: ${conversation.id}`);

    // Get response
    console.log("🤖 Getting response from agent...\n");
    const response = await openAIClient.responses.create(
      {
        conversation: conversation.id,
      },
      {
        headers: {
          "accept-encoding": "deflate",
        },
        body: {
          agent: {
            type: "agent_reference",
            name: agent.name,
          },
        },
      }
    );

    console.log("Response:");
    console.log("-".repeat(70));
    console.log(response.output_text);
    console.log("-".repeat(70));

    // Cleanup
    console.log("\n🧹 Cleaning up...");
    await openAIClient.conversations.delete(conversation.id);
    await agentsClient.deleteVersion(agent.name!, agent.version!);
    
    console.log("✅ Demo completed successfully!");
  } catch (error: any) {
    console.error(`\n❌ Error: ${error.message}`);
    console.error("Please check your .env configuration and ensure:");
    console.error("  - PROJECT_ENDPOINT is correct");
    console.error("  - MODEL_DEPLOYMENT_NAME is deployed");
    console.error("  - Azure credentials are configured (az login)");
    process.exit(1);
  }
}

main();
