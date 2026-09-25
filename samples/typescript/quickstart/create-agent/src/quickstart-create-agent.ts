import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";

// Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
const FOUNDRY_PROJECT_ENDPOINT = "your_project_endpoint";
const FOUNDRY_AGENT_NAME = "your-agent-name";

async function main(): Promise<void> {
    const project = new AIProjectClient(FOUNDRY_PROJECT_ENDPOINT, new DefaultAzureCredential());
    const agent = await project.agents.createVersion(FOUNDRY_AGENT_NAME, {
        kind: "prompt",
        model: "gpt-5-mini", // supports all Foundry direct models
        instructions: "You are a helpful assistant that answers general questions",
    });
    console.log(`Agent created: ${agent.name}, version: ${agent.version}`);
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
