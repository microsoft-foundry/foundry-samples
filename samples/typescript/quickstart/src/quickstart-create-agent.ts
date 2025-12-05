import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";
import "dotenv/config";

const projectEndpoint: string = process.env["AZURE_AI_PROJECT_ENDPOINT"] || "<project endpoint>";
const modelDeploymentName: string = process.env["AZURE_AI_FOUNDRY_MODEL_DEPLOYMENT_NAME"] || "<model deployment name>";
const agentName: string = process.env["AZURE_AI_FOUNDRY_AGENT_NAME"] || "<agent name>";

const credential = new DefaultAzureCredential();
const projectClient = new AIProjectClient(projectEndpoint, credential);
async function main(): Promise<void> {
    // Create agent
    console.log("Creating agent...");
    const agent = await projectClient.agents.createVersion(agentName, {
        kind: "prompt",
        model: modelDeploymentName,
        instructions: "You are a helpful assistant that answers general questions",
    });
    console.log(`Agent created (id: ${agent.id}, name: ${agent.name}, version: ${agent.version})`);
}

main().catch(console.error);