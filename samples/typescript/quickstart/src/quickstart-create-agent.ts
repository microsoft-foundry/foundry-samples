import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";
import "dotenv/config";

const projectEndpoint = process.env["PROJECT_ENDPOINT"] || "<project endpoint>";
const deploymentName = process.env["MODEL_DEPLOYMENT_NAME"] || "<model deployment name>";

async function main(): Promise<void> {
    const project = new AIProjectClient(projectEndpoint, new DefaultAzureCredential());
    const openAIClient = await project.getOpenAIClient();
    
    // Create agent
    console.log("Creating agent...");
    const agent = await project.agents.createVersion("my-agent-basic", {
        kind: "prompt",
        model: deploymentName,
        instructions: "You are a helpful assistant that answers general questions",
    });
    console.log(`Agent created (id: ${agent.id}, name: ${agent.name}, version: ${agent.version})`);
    
    // Create conversation with initial user message
    // You can save the conversation ID to database to retrieve later
    console.log("\nCreating conversation with initial user message...");
    const conversation = await openAIClient.conversations.create({
        items: [
            { type: "message", role: "user", content: "What is the size of France in square miles?" },
        ],
    });
    console.log(`Created conversation with initial user message (id: ${conversation.id})`);

    // Generate response using the agent
    console.log("\nGenerating response...");
    const response = await openAIClient.responses.create(
        {
            conversation: conversation.id,
        },
        {
            body: { agent: { name: agent.name, type: "agent_reference" } },
        },
    );
    console.log(`Response output: ${response.output_text}`);

     // Clean up
    console.log("\nCleaning up resources...");
    await openAIClient.conversations.delete(conversation.id);
    console.log("Conversation deleted");

    await project.agents.deleteVersion(agent.name, agent.version);
    console.log("Agent deleted");
}

main().catch(console.error);