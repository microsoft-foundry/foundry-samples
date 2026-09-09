import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";

// Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
const FOUNDRY_PROJECT_ENDPOINT = "your_project_endpoint";

async function main(): Promise<void> {
    // Create project and openai clients to call Foundry API
    const project = new AIProjectClient(FOUNDRY_PROJECT_ENDPOINT, new DefaultAzureCredential());
    const openai = project.getOpenAIClient();

    // Run a responses API call
    const response = await openai.responses.create({
        model: "gpt-5-mini",
        input: "What is the size of France in square miles?",
    });
    console.log(`Response output: ${response.output_text}`);
}

main().catch(console.error);