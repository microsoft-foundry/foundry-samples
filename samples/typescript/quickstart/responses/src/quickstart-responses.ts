import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";

// Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
const PROJECT_ENDPOINT = process.env.AZURE_AI_PROJECT_ENDPOINT || "your_project_endpoint";
const MODEL_DEPLOYMENT = process.env.MODEL_DEPLOYMENT || "gpt-5-mini";

async function main(): Promise<void> {
    // Create project and openai clients to call Foundry API
    const project = new AIProjectClient(PROJECT_ENDPOINT, new DefaultAzureCredential());
    const openai = project.getOpenAIClient();

    // Run a responses API call
    const response = await openai.responses.create({
        model: MODEL_DEPLOYMENT,
        input: "What is the size of France in square miles?",
    });
    console.log(`Response output: ${response.output_text}`);
}

main().catch(console.error);