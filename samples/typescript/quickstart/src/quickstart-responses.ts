import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";
import "dotenv/config";

const projectEndpoint: string = process.env["AZURE_AI_PROJECT_ENDPOINT"] || "<project endpoint>";
const modelDeploymentName: string = process.env["AZURE_AI_FOUNDRY_MODEL_DEPLOYMENT_NAME"] || "<model deployment name>";

async function main(): Promise<void> {
    const projectClient = new AIProjectClient(projectEndpoint, new DefaultAzureCredential());
    const openAIClient = await  projectClient.getOpenAIClient();

    const response = await openAIClient.responses.create({
        model: modelDeploymentName,
        input: 'What is the size of France in square miles?',
    });
    console.log(`Response output: ${response.output_text}`);

}
main().catch(console.error);