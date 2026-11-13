// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * This sample traces a realtime voice-agent session with OpenTelemetry. The project client is
 * created with experimental tracing enabled, so the SDK emits spans for the agent REST calls and
 * the realtime session, which this sample prints with the console span exporter.
 *
 * @summary Trace a realtime voice-agent session and a local tool call with OpenTelemetry.
 */

// Tracing must be configured before the Azure SDK modules load.
import { context, provider, trace } from "./tracing.js";
import "dotenv/config";
import { AIProjectClient } from "@azure/ai-projects";
import { DefaultAzureCredential } from "@azure/identity";

const projectEndpoint = getRequiredEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
const modelName = process.env.FOUNDRY_VOICE_AGENT_MODEL?.trim() || "gpt-realtime";
const agentName = `voice-tracing-${Date.now()}`;
const restOptions = { requestOptions: { headers: { "foundry-features": "VoiceAgents=V1Preview" } } };

async function main(): Promise<void> {
  const project = new AIProjectClient(projectEndpoint, new DefaultAzureCredential(), {
    // contentRecording: false keeps prompts, transcripts, and tool arguments out of the spans.
    tracingOptions: { experimental: true, contentRecording: false },
  });

  const parentSpan = trace.getTracer("voice-agents-realtime-tracing").startSpan("voice conversation");
  try {
    await context.with(trace.setSpan(context.active(), parentSpan), async () => {
      await project.agents.createVersion(
        agentName,
        {
          kind: "voice",
          model_type: "managed",
          model: modelName,
          instructions: "Answer briefly. Use the get_current_time function when asked for the time.",
          output_modalities: ["text", "audio"],
          store: false,
        },
        restOptions,
      );
      try {
        await runConversation(project);
      } finally {
        await project.agents.delete(agentName, restOptions);
      }
    });
  } finally {
    parentSpan.end();
    await provider.shutdown();
  }
}

async function runConversation(project: AIProjectClient): Promise<void> {
  const connection = await project.voiceAgents.realtime.connect(agentName);
  try {
    await connection.configureSession({
      type: "realtime",
      output_modalities: ["text", "audio"],
      tools: [
        {
          type: "function",
          name: "get_current_time",
          description: "Get the current UTC time.",
          parameters: { type: "object", properties: {} },
        },
      ],
    });
    await connection.sendText("What time is it? Please call get_current_time.");

    let toolOutputSent = false;
    let audioByteCount = 0;
    for await (const event of connection) {
      switch (event.type) {
        case "response.output_audio.delta":
          audioByteCount += event.delta.byteLength;
          break;
        case "response.output_audio_transcript.delta":
        case "response.output_text.delta":
          process.stdout.write(event.delta);
          break;
        case "response.function_call_arguments.done":
          if (event.name !== "get_current_time") {
            throw new Error(`Unexpected tool request: ${event.name}`);
          }
          // Application tool execution is not a span owned by the Voice Agents SDK.
          await connection.sendToolOutput(
            event.call_id,
            JSON.stringify({ time: new Date().toISOString() }),
            { createResponse: false },
          );
          toolOutputSent = true;
          break;
        case "error":
          throw new Error(`${event.error.code ?? "voice_agent_error"}: ${event.error.message}`);
        case "response.done":
          if (event.response.status === "failed") {
            throw new Error("The voice agent response failed.");
          }
          if (toolOutputSent) {
            toolOutputSent = false;
            await connection.requestResponse();
          } else {
            console.log(`\nResponse finished; received ${audioByteCount} audio bytes.`);
            return;
          }
          break;
      }
    }
  } finally {
    await connection.close();
  }
}

function getRequiredEnvironmentVariable(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`Set ${name} before running this sample.`);
  }
  return value;
}

main().catch((error: unknown) => {
  console.error("The sample encountered an error:", error);
  process.exitCode = 1;
});
