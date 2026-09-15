// Live-validation-only helper: deletes the agent created by
// quickstart-chat-with-agent.ts so repeated live-validation runs don't accumulate
// agent versions. Not part of the documented quickstart narrative.
import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";

// Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
const FOUNDRY_PROJECT_ENDPOINT = "your_project_endpoint";
const FOUNDRY_AGENT_NAME = "your-agent-name";

async function main(): Promise<void> {
    const project = new AIProjectClient(FOUNDRY_PROJECT_ENDPOINT, new DefaultAzureCredential());
    await project.agents.delete(FOUNDRY_AGENT_NAME);
    console.log(`Agent deleted (name: ${FOUNDRY_AGENT_NAME})`);
}

main().catch(console.error);
