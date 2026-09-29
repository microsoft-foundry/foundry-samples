import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";

// Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
const FOUNDRY_PROJECT_ENDPOINT = "your_project_endpoint";
const FOUNDRY_AGENT_NAME = "your-agent-name";

async function main(): Promise<void> {
    const credential = new DefaultAzureCredential();
    const project = new AIProjectClient(FOUNDRY_PROJECT_ENDPOINT, credential);
    const agent = await project.agents.createVersion(FOUNDRY_AGENT_NAME, {
        kind: "prompt",
        model: "gpt-5-mini", // supports all Foundry direct models
        instructions: "You are a helpful assistant that answers general questions",
    });
    if (!agent.name || !agent.version) {
        throw new Error("The created agent did not include a name and version.");
    }
    const agentName = agent.name;
    const agentVersion = agent.version;
    const openai = project.getOpenAIClient();

    try {
        // Create a conversation for multi-turn chat
        const conversation = await openai.conversations.create();

        try {
            // Chat with the agent to answer questions
            const response = await openai.responses.create(
                {
                    conversation: conversation.id,
                    input: "What is the size of France in square miles?",
                },
                {
                    body: { agent_reference: { name: agentName, type: "agent_reference" } },
                },
            );
            console.log(response.output_text);

            // Ask a follow-up question in the same conversation
            const response2 = await openai.responses.create(
                {
                    conversation: conversation.id,
                    input: "And what is the capital city?",
                },
                {
                    body: { agent_reference: { name: agentName, type: "agent_reference" } },
                },
            );
            console.log(response2.output_text);
        } finally {
            await openai.conversations.delete(conversation.id);
        }
    } finally {
        await project.agents.deleteVersion(agentName, agentVersion);
    }
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});