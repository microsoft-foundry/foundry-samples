// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * This sample sends text to a voice agent, streams text/audio output, and handles a local function.
 *
 * @summary Streams text and local function calls with a Foundry voice agent.
 */

import "dotenv/config";
import { AIProjectClient, isRestError } from "@azure/ai-projects";
import { DefaultAzureCredential } from "@azure/identity";
import { once } from "node:events";
import { createWriteStream } from "node:fs";
import type { WriteStream } from "node:fs";
import { finished } from "node:stream/promises";
import type { FullOperationResponse } from "@azure-rest/core-client";

const projectEndpoint = getRequiredEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
const agentName = process.env.FOUNDRY_VOICE_AGENT_NAME?.trim() || `voice-text-${Date.now()}`;
const modelName = process.env.FOUNDRY_VOICE_AGENT_MODEL?.trim() || "gpt-realtime";
const audioOutputPath =
  process.env.FOUNDRY_VOICE_AGENT_AUDIO_OUTPUT_FILE?.trim() || "voice-agent-output.pcm";
const preview = "VoiceAgents=V1Preview";
const restOptions = {
  requestOptions: { headers: { "foundry-features": preview } },
  onResponse: (rawResponse: FullOperationResponse) =>
    console.log(`  HTTP ${rawResponse.status} ${rawResponse.request.method} ${rawResponse.request.url}`),
};
const pcmSampleRate = 24_000;
const pcmBytesPerSample = 2;

type VoiceAgentRealtimeConnection = Awaited<
  ReturnType<AIProjectClient["beta"]["voiceAgents"]["realtime"]["connect"]>
>;
type VoiceAgentRealtimeEvent = VoiceAgentRealtimeConnection extends AsyncIterable<infer TEvent>
  ? TEvent
  : never;

async function main(): Promise<void> {
  const project = new AIProjectClient(projectEndpoint, new DefaultAzureCredential());
  const { created } = await getOrCreateVoiceAgent(project);

  try {
    const connection = await project.beta.voiceAgents.realtime.connect(agentName);
    const audioOutput = createWriteStream(audioOutputPath);
    let pendingToolOutputs = 0;
    let toolCallCount = 0;
    let textCharacterCount = 0;
    let audioByteCount = 0;

    try {
      const pcmFormat = { type: "audio/pcm", rate: pcmSampleRate } as const;
      const weatherTool = {
        type: "function",
        name: "get_weather",
        description: "Get the current weather for a city.",
        parameters: {
          type: "object",
          properties: { city: { type: "string" } },
          required: ["city"],
        },
      } as const;
      await connection.configureSession({
        type: "realtime",
        output_modalities: ["text", "audio"],
        audio: {
          output: { format: pcmFormat },
        },
        tools: [weatherTool],
      });

      await connection.sendText("What is the weather in Seattle? Use the weather tool.");

      for await (const event of connection) {
        console.log(`[event] ${event.type}${describeEvent(event)}`);
        switch (event.type) {
          case "response.output_text.delta":
          case "response.output_audio_transcript.delta":
            textCharacterCount += event.delta.length;
            process.stdout.write(event.delta);
            break;
          case "response.output_audio.delta":
            audioByteCount += event.delta.byteLength;
            await writeAudio(audioOutput, event.delta);
            break;
          case "response.function_call_arguments.done": {
            toolCallCount++;
            pendingToolOutputs++;
            const args = parseWeatherToolArguments(event.arguments);
            await connection.sendToolOutput(
              event.call_id,
              JSON.stringify({ city: args.city, temperature: 62, unit: "F" }),
              { createResponse: false },
            );
            break;
          }
          case "error":
            throw new Error(`${event.error.code ?? "voice_agent_error"}: ${event.error.message}`);
          case "response.done":
            if (pendingToolOutputs > 0) {
              pendingToolOutputs = 0;
              await connection.requestResponse();
            } else {
              await connection.close();
            }
            break;
        }
      }

      console.log(
        `\nCompleted with ${toolCallCount} tool call(s), ${textCharacterCount} text character(s).`,
      );
      console.log(`Audio format: PCM16, ${pcmSampleRate} Hz, mono.`);
      console.log("Input audio:  N/A (this sample sends text input only).");
      console.log(
        `Output audio: ${audioByteCount} bytes (${formatBytes(audioByteCount)}), ` +
          `${formatDuration(audioByteCount)}`,
      );
    } finally {
      audioOutput.end();
      try {
        await finished(audioOutput);
      } finally {
        await connection.dispose();
      }
    }
  } finally {
    if (created) {
      await project.agents.delete(agentName, restOptions);
    }
  }
}

function parseWeatherToolArguments(value: string): { city: string } {
  const argumentsValue = JSON.parse(value);
  if (
    typeof argumentsValue !== "object" ||
    argumentsValue === null ||
    !("city" in argumentsValue) ||
    typeof argumentsValue.city !== "string" ||
    !argumentsValue.city.trim()
  ) {
    throw new Error('The get_weather tool requires a non-empty string "city" argument.');
  }
  return { city: argumentsValue.city.trim() };
}

function describeEvent(event: VoiceAgentRealtimeEvent): string {
  switch (event.type) {
    case "response.output_audio.delta":
      return ` (${event.delta.byteLength} bytes)`;
    case "response.output_text.delta":
    case "response.output_audio_transcript.delta":
      return ` (${event.delta.length} chars)`;
    case "response.function_call_arguments.delta":
      return ` (call_id=${event.call_id}, +${event.delta.length} chars of arguments)`;
    case "response.function_call_arguments.done":
      return ` (call_id=${event.call_id}, name=${event.name}, arguments=${event.arguments})`;
    case "response.output_item.added":
      return ` (item type=${event.item.type})`;
    case "response.done":
      return ` (status=${event.response.status})`;
    case "error":
      return ` (${event.error.code ?? "unknown"}: ${event.error.message})`;
    default:
      return "";
  }
}

const bytesPerKiB = 1024;
const bytesPerMiB = bytesPerKiB * 1024;

function formatBytes(byteCount: number): string {
  if (byteCount >= bytesPerMiB) {
    return `${(byteCount / bytesPerMiB).toFixed(2)} MB`;
  }
  if (byteCount >= bytesPerKiB) {
    return `${(byteCount / bytesPerKiB).toFixed(2)} KB`;
  }
  return `${byteCount} B`;
}

function formatDuration(byteCount: number): string {
  const seconds = byteCount / (pcmSampleRate * pcmBytesPerSample);
  return `${seconds.toFixed(2)}s of audio`;
}

async function writeAudio(output: WriteStream, audio: Uint8Array): Promise<void> {
  if (!output.write(audio)) {
    await once(output, "drain");
  }
}

async function getOrCreateVoiceAgent(project: AIProjectClient) {
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
    instructions: "You are a helpful voice assistant. Use tools when appropriate.",
    output_modalities: ["text", "audio"],
  } as const;
  await project.agents.create(agentName, definition, restOptions);
  return { created: true };
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
