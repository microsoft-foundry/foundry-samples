import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";
import "dotenv/config";

const projectEndpoint = process.env["AZURE_AI_FOUNDRY_PROJECT_ENDPOINT"] || "<endpoint copied from welcome screen>";
const deploymentName = process.env["AZURE_AI_FOUNDRY_MODEL_DEPLOYMENT_NAME"] || "gpt-4.1-mini";

async function main(): Promise<void> {
    const project = new AIProjectClient(projectEndpoint, new DefaultAzureCredential());
    const openAIClient = await project.getOpenAIClient();
    const response = await openAIClient.responses.create({
        model: deploymentName,
        input: "What is the size of France in square miles?",
    });
    const response2 = await openAIClient.responses.create({
        model: deploymentName,
        input: "And what is the capital city?",
        previous_response_id: response.id,
    });
    console.log(`Response output: ${response2.output_text}`);
};

main().catch(console.error);