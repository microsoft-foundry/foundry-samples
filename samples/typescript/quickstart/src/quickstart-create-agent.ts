import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";
import "dotenv/config";

const projectEndpoint = process.env["PROJECT_ENDPOINT"] || "<project endpoint>";
const deploymentName = process.env["MODEL_DEPLOYMENT_NAME"] || "<model deployment name>";

async function main(): Promise<void> {
    const project = new AIProjectClient(projectEndpoint, new DefaultAzureCredential());
    const agent = await project.agents.createVersion("my-agent-basic", {
        kind: "prompt",
        model: deploymentName,
        instructions: "You are a helpful assistant that answers general questions",
  });
  console.log(`Agent created (id: ${agent.id}, name: ${agent.name}, version: ${agent.version})`);
}

main().catch(console.error);