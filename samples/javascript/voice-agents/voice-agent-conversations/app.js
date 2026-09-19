// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * This sample opens a short realtime voice agent session with conversation storage
 * enabled, then inspects the resulting conversation through the Conversation REST API:
 * fetching the conversation, listing/fetching its items and model responses. See
 * realtime-text-and-tools and realtime-audio for streaming a live session without
 * inspecting it afterward.
 *
 * @summary Inspect a stored voice agent conversation through the Conversation REST API.
 */

import "dotenv/config";
import { AIProjectClient, isRestError } from "@azure/ai-projects";
import { DefaultAzureCredential } from "@azure/identity";

const projectEndpoint = getRequiredEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
const agentName = process.env.FOUNDRY_VOICE_AGENT_NAME?.trim() || `voice-conversations-${Date.now()}`;
const modelName = process.env.FOUNDRY_VOICE_AGENT_MODEL?.trim() || "gpt-realtime";
const preview = "VoiceAgents=V1Preview";
const restOptions = {
  requestOptions: { headers: { "foundry-features": preview } },
  onResponse: (rawResponse) =>
    console.log(`  HTTP ${rawResponse.status} ${rawResponse.request.method} ${rawResponse.request.url}`),
};

async function main() {
  const project = new AIProjectClient(projectEndpoint, new DefaultAzureCredential());
  const { created } = await getOrCreateVoiceAgent(project);

  try {
    const conversationId = await runStoredConversation(project);
    const conversations = project.beta.voiceAgents.conversations;

    console.log(`\nFetching conversation ${conversationId}...`);
    const conversation = await conversations.get(agentName, conversationId, restOptions);
    console.log(
      `Status: ${conversation.status}, created: ${conversation.created_at.toISOString()}` +
        (conversation.completed_at ? `, completed: ${conversation.completed_at.toISOString()}` : ""),
    );

    console.log("\nMost recent conversations for this agent:");
    let recentCount = 0;
    for await (const listed of conversations.list(agentName, { ...restOptions, limit: 5 })) {
      recentCount++;
      console.log(`  - ${listed.id} (${listed.status})${listed.id === conversationId ? "  <- ours" : ""}`);
    }
    console.log(`Listed ${recentCount} conversation(s).`);

    console.log("\nConversation transcript (from listItems):");
    const items = [];
    for await (const item of conversations.listItems(agentName, conversationId, restOptions)) {
      items.push(item);
      console.log(`  ${summarizeItem(item)}`);
    }

    const firstItem = items.find((item) => item.id);
    if (firstItem) {
      console.log(`\nFetching item ${firstItem.id} directly...`);
      const fetchedItem = await conversations.getItem(agentName, conversationId, firstItem.id, restOptions);
      console.log(`  ${summarizeItem(fetchedItem)}`);
    }

    console.log("\nModel responses (from listResponses):");
    const responses = [];
    for await (const response of conversations.listResponses(agentName, conversationId, restOptions)) {
      responses.push(response);
      console.log(`  - ${response.id} (${response.output?.length ?? 0} output item(s))`);
    }

    const firstResponse = responses[0];
    if (firstResponse) {
      console.log(`\nFetching response ${firstResponse.id} directly...`);
      const fetchedResponse = await conversations.getResponse(
        agentName,
        conversationId,
        firstResponse.id,
        restOptions,
      );
      console.log(`  Output item(s): ${fetchedResponse.output?.length ?? 0}`);

      console.log(`\nItems produced by response ${firstResponse.id} (from listResponseItems)...`);
      for await (const item of conversations.listResponseItems(
        agentName,
        conversationId,
        firstResponse.id,
        restOptions,
      )) {
        console.log(`  ${summarizeItem(item)}`);
      }
    }

    // This sample uses a text-only session, so there is no recorded audio to fetch. For
    // voice conversations, the same conversations object also exposes getAudio,
    // downloadAudio, getAudioItem, downloadAudioItem, getGeneratedAudioItem, and
    // downloadGeneratedAudioItem (see realtime-audio for producing spoken responses).

    console.log("\nDeleting the conversation...");
    await conversations.delete(agentName, conversationId, restOptions);
  } finally {
    if (created) {
      await project.agents.delete(agentName, restOptions);
    }
  }
}

async function runStoredConversation(project) {
  console.log("Opening a realtime session with conversation storage enabled...");
  const connection = await project.beta.voiceAgents.realtime.connect(agentName, { store: true });
  let conversationId;

  try {
    await connection.configureSession({ type: "realtime", output_modalities: ["text"] });
    await connection.sendText("In one short sentence, what can you help me with?");

    for await (const event of connection) {
      if (event.type === "session.created") {
        conversationId = event.conversation_id;
      } else if (event.type === "response.output_text.delta") {
        process.stdout.write(event.delta);
      } else if (event.type === "error") {
        throw new Error(`${event.error.code ?? "voice_agent_error"}: ${event.error.message}`);
      } else if (event.type === "response.done") {
        await connection.close();
      }
    }
    console.log();
  } finally {
    await connection.dispose();
  }

  if (!conversationId) {
    throw new Error("The session did not report a conversation_id; was storage enabled?");
  }
  return conversationId;
}

function summarizeItem(item) {
  if (item.type === "message") {
    const text = (item.content ?? [])
      .map((part) => part.text ?? part.transcript ?? "")
      .filter(Boolean)
      .join(" ");
    return `[${item.role}] ${text || "(no text content)"}`;
  }
  return `[${item.type}]`;
}

async function getOrCreateVoiceAgent(project) {
  try {
    await project.agents.get(agentName, restOptions);
    return { created: false };
  } catch (error) {
    if (!isRestError(error) || error.statusCode !== 404) {
      throw error;
    }
  }

  const definition = {
    kind: "voice",
    model_type: "managed",
    model: modelName,
    instructions: "You are a helpful voice assistant. Keep answers to one short sentence.",
    output_modalities: ["text"],
  };
  await project.agents.create(agentName, definition, restOptions);
  return { created: true };
}

function getRequiredEnvironmentVariable(name) {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`Set ${name} before running this sample.`);
  }
  return value;
}

main().catch((err) => {
  console.error("Sample failed:", err);
  process.exitCode = 1;
});
