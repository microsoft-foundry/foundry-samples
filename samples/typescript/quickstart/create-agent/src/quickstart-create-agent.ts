import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";

// Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
const PROJECT_ENDPOINT = process.env.AZURE_AI_PROJECT_ENDPOINT || "your_project_endpoint";
const AGENT_NAME = process.env.AZURE_AI_FOUNDRY_AGENT_NAME || "your_agent_name";
const MODEL_DEPLOYMENT = process.env.MODEL_DEPLOYMENT || "gpt-5-mini";

async function main(): Promise<void> {
    // Create project client to call Foundry API
    const project = new AIProjectClient(PROJECT_ENDPOINT, new DefaultAzureCredential());

    // Create an agent with a model and instructions
    const agent = await project.agents.createVersion(AGENT_NAME, {
        kind: "prompt",
        model: MODEL_DEPLOYMENT, //supports all Foundry direct models
        instructions: "You are a helpful assistant that answers general questions",
    });
    console.log(`Agent created (id: ${agent.id}, name: ${agent.name}, version: ${agent.version})`);
}

main().catch(console.error);