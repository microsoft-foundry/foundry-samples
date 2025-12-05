import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";
import "dotenv/config";

const projectEndpoint: string = process.env["AZURE_AI_PROJECT_ENDPOINT"] || "<project endpoint>";
const modelDeploymentName: string = process.env["AZURE_AI_FOUNDRY_MODEL_DEPLOYMENT_NAME"] || "<model deployment name>";
const agentName: string = process.env["AZURE_AI_FOUNDRY_AGENT_NAME"] || "<agent name>";

const credential = new DefaultAzureCredential();
const project = new AIProjectClient(projectEndpoint, credential);

async function main(): Promise<void> {
  // Create agent
  console.log("Creating agent...");
  const agent = await project.agents.createVersion(agentName, {
    kind: "prompt",
    model: modelDeploymentName,
    instructions: "You are a helpful assistant that answers general questions",
  });
  console.log(`Agent created (id: ${agent.id}, name: ${agent.name}, version: ${agent.version})`);

  // Create conversation with initial user message
  console.log("\nCreating conversation with initial user message...");
  const conversation = await project.conversations.create({
    items: [
      { type: "message", role: "user", content: "What is the size of France in square miles?" },
    ],
  });
  console.log(`Created conversation with initial user message (id: ${conversation.id})`);

  // Generate response using the agent
  console.log("\nGenerating response...");
  const response = await project.responses.create(
    {
      conversation: conversation.id,
      input: "", // TODO: Remove 'input' once service is fixed
    },
    {
      body: { agent: { name: agent.name, type: "agent_reference" } },
    },
  );
  console.log(`Response output: ${response.output_text}`);
}

main().catch(console.error);