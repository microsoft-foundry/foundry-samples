import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";
import "dotenv/config";

const projectEndpoint: string = process.env["AZURE_AI_PROJECT_ENDPOINT"] || "<project endpoint>";
const agentName: string = process.env["AZURE_AI_FOUNDRY_AGENT_NAME"] || "<agent name>";

async function main(): Promise<void> {
    const projectClient = new AIProjectClient(projectEndpoint, new DefaultAzureCredential());
    const openAIClient = await  projectClient.getOpenAIClient();

    // Optional step: Create a conversation to use with the agent
    const conversation = await openAIClient.conversations.create();
    console.log(`Created conversation (id: ${conversation.id}).`);

    // Chat with the agent to answer questions
    let response = await openAIClient.responses.create({
        conversation: conversation.id,
        input: 'What is the size of France in square miles?',
    }, {
        body: { agent: { name: agentName, type: "agent_reference"} }
    });
    console.log(`Response output: ${response.output_text}`);

    response = await openAIClient.responses.create({
        conversation: conversation.id,
        input: 'And what is the capital city?',
    }, {
        body: { agent: { name: agentName, type: "agent_reference"} }
    });
    console.log(`Response output: ${response.output_text}`);
}
main().catch(console.error);