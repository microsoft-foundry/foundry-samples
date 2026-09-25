import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";

// Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
const FOUNDRY_PROJECT_ENDPOINT = "your_project_endpoint";
const FOUNDRY_AGENT_NAME = "your-agent-name";

async function main(): Promise<void> {
  // Create AI Project client
  const project = new AIProjectClient(FOUNDRY_PROJECT_ENDPOINT, new DefaultAzureCredential());
  const openai = project.getOpenAIClient();

  // Create agent
  const agent = await project.agents.createVersion(FOUNDRY_AGENT_NAME, {
    kind: "prompt",
    model: "gpt-5-mini", // supports all Foundry direct models
    instructions: "You are a helpful assistant that answers general questions",
  });

  try {
    // Create conversation with initial user message
    const conversation = await openai.conversations.create({
      items: [
        { type: "message", role: "user", content: "What is the size of France in square miles?" },
      ],
    });

    try {
      // Generate response using the agent
      const response = await openai.responses.create(
        {
          conversation: conversation.id,
        },
        {
          body: { agent_reference: { name: agent.name, type: "agent_reference" } },
        },
      );
      console.log(`Response output: ${response.output_text}`);
    } finally {
      await openai.conversations.delete(conversation.id);
    }
  } finally {
    await project.agents.deleteVersion(agent.name, agent.version);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});