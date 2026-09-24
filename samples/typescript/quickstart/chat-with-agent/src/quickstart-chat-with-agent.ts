import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";

// Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
const FOUNDRY_PROJECT_ENDPOINT = "your_project_endpoint";
const FOUNDRY_AGENT_NAME = "your-agent-name";

async function createAgentVersion(projectEndpoint: string, agentName: string): Promise<void> {
    const credential = new DefaultAzureCredential();
    const token = await credential.getToken("https://ai.azure.com/.default");
    if (!token) {
        throw new Error("Failed to acquire a Foundry access token");
    }

    const response = await fetch(
        `${projectEndpoint.replace(/\/$/, "")}/agents/${encodeURIComponent(agentName)}/versions?api-version=v1`,
        {
            method: "POST",
            headers: {
                "Authorization": ["Bearer", token.token].join(" "),
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                definition: {
                    kind: "prompt",
                    model: "gpt-5-mini", //supports all Foundry direct models
                    instructions: "You are a helpful assistant that answers general questions",
                },
            }),
        },
    );
    if (!response.ok) {
        throw new Error(`Failed to create agent version: ${response.status} ${await response.text()}`);
    }
}

async function main(): Promise<void> {
    // Create project and openai clients to call Foundry API
    const project = new AIProjectClient(FOUNDRY_PROJECT_ENDPOINT, new DefaultAzureCredential());

    // Create the agent (or a new version, if it already exists)
    await createAgentVersion(FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_AGENT_NAME);

    const openai = project.getOpenAIClient({
        azureConfig: { allowPreview: true, agentName: FOUNDRY_AGENT_NAME },
    });

    // Create a conversation for multi-turn chat
    const conversation = await openai.conversations.create();

    // Chat with the agent to answer questions
    const response = await openai.responses.create({
        conversation: conversation.id,
        input: "What is the size of France in square miles?",
    });
    console.log(response.output_text);

    // Ask a follow-up question in the same conversation
    const response2 = await openai.responses.create({
        conversation: conversation.id,
        input: "And what is the capital city?",
    });
    console.log(response2.output_text);
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});