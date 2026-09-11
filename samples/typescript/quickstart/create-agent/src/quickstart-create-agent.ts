import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";

// Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
const FOUNDRY_PROJECT_ENDPOINT = "your_project_endpoint";
const FOUNDRY_AGENT_NAME = "your_agent_name";

async function main(): Promise<void> {
    // Create project client to call Foundry API
    const project = new AIProjectClient(FOUNDRY_PROJECT_ENDPOINT, new DefaultAzureCredential());

    // Create an agent with a model and instructions
    const agent = await project.agents.createVersion(FOUNDRY_AGENT_NAME, {
        kind: "prompt",
        model: "gpt-5-mini", //supports all Foundry direct models
        instructions: "You are a helpful assistant that answers general questions",
    });
    console.log(`Agent created (id: ${agent.id}, name: ${agent.name}, version: ${agent.version})`);
}

main().catch(console.error);