import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";
import "dotenv/config";

const projectEndpoint = process.env["AZURE_AI_FOUNDRY_PROJECT_ENDPOINT"] || "<endpoint copied from welcome screen>";
const deploymentName = process.env["AZURE_AI_FOUNDRY_MODEL_DEPLOYMENT_NAME"] || "gpt-4.1-mini";
const agentName = process.env["AZURE_AI_FOUNDRY_AGENT_NAME"] || "MyAgent";

async function main(): Promise<void> {
    const project = new AIProjectClient(projectEndpoint, new DefaultAzureCredential());
    const agent = await project.agents.createVersion(agentName, {
        kind: "prompt",
        model: deploymentName,
        instructions: "You are a helpful assistant that answers general questions",
  });
  console.log(`Agent created (id: ${agent.id}, name: ${agent.name}, version: ${agent.version})`);
}

main().catch(console.error);