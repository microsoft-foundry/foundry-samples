// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

/**
 * This sample configures the voice-agent audio features added in @azure/ai-projects 2.10.0:
 * a telephony soundscape, Azure headset noise suppression, and Azure Speech transcription with
 * a profanity filter. It then opens a short realtime session to confirm the agent works.
 *
 * @summary Configure soundscape, noise suppression, and transcription profanity filtering.
 */

import "dotenv/config";
import { AIProjectClient } from "@azure/ai-projects";
import { DefaultAzureCredential } from "@azure/identity";

const projectEndpoint = getRequiredEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT");
const modelName = process.env.FOUNDRY_VOICE_AGENT_MODEL?.trim() || "gpt-realtime";
const agentName = `voice-soundscape-${Date.now()}`;
const restOptions = {
  requestOptions: { headers: { "foundry-features": "VoiceAgents=V1Preview" } },
  onResponse: (rawResponse) =>
    console.log(`  HTTP ${rawResponse.status} ${rawResponse.request.method} ${rawResponse.request.url}`),
};

async function main() {
  const project = new AIProjectClient(projectEndpoint, new DefaultAzureCredential());

  console.log("Creating a voice agent with soundscape and audio settings...");
  const agent = await project.agents.createVersion(
    agentName,
    {
      kind: "voice",
      model_type: "managed",
      model: modelName,
      instructions: "You are a contact-center assistant for Contoso. Keep answers to one sentence.",
      audio: {
        input: {
          // Headset noise suppression is tuned for low-sample-rate audio such as 8 kHz telephony.
          noise_reduction: { type: "azure_deep_noise_suppression_headset" },
          // Azure Speech transcription requires Azure semantic turn detection.
          turn_detection: { type: "azure_semantic_vad" },
          transcription: {
            // Use "azure-speech-streaming" instead for cascaded (text-model) voice agents.
            model: "azure-speech",
            language: "en-US",
            phrase_list: ["Contoso"],
            profanity_filter: "masked",
          },
        },
      },
      // The soundscape is rendered only on telephony calls, not WebSocket or WebRTC sessions.
      soundscape: {
        background: { source: { type: "built_in", name: "office" }, gain: 0.2 },
        working: { source: { type: "built_in", name: "call_center" }, gain: 0.4, delay_ms: 1500 },
        opening: { source: { type: "built_in", name: "ding1" } },
        transfer: { source: { type: "built_in", name: "ding2" }, gain: 0.6 },
        closing: { source: { type: "built_in", name: "ding2" } },
      },
      output_modalities: ["text", "audio"],
      store: false,
    },
    restOptions,
  );

  try {
    console.log(`Created voice agent: ${agent.name}, version: ${agent.version}`);
    const version = await project.agents.getVersion(agent.name, agent.version, restOptions);
    if (version.definition.kind === "voice") {
      const { soundscape, audio } = version.definition;
      for (const [track, config] of Object.entries(soundscape ?? {})) {
        const delay = config.delay_ms === undefined ? "" : `, delay ${config.delay_ms} ms`;
        console.log(`  Soundscape ${track}: ${config.source.name} (gain ${config.gain ?? 1}${delay})`);
      }
      console.log(`  Noise reduction: ${audio?.input?.noise_reduction?.type}`);
      console.log(`  Turn detection: ${audio?.input?.turn_detection?.type}`);
      const transcription = audio?.input?.transcription;
      console.log(
        `  Transcription: ${transcription?.model} (${transcription?.language}), ` +
          `profanity filter: ${transcription?.profanity_filter}`,
      );
    }

    console.log("\nOpening a realtime session to confirm the configuration...");
    const connection = await project.voiceAgents.realtime.connect(agent.name);
    try {
      await connection.configureSession({ type: "realtime", output_modalities: ["text"] });
      await connection.sendText("Greet the caller in one short sentence.");
      for await (const event of connection) {
        if (event.type === "response.output_text.delta") {
          process.stdout.write(event.delta);
        } else if (event.type === "error") {
          throw new Error(`${event.error.code ?? "voice_agent_error"}: ${event.error.message}`);
        } else if (event.type === "response.done") {
          console.log(`\nResponse status: ${event.response.status}`);
          break;
        }
      }
    } finally {
      await connection.close();
    }
  } finally {
    console.log("Deleting the sample agent...");
    await project.agents.delete(agent.name, restOptions);
  }
}

function getRequiredEnvironmentVariable(name) {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`Set ${name} before running this sample.`);
  }
  return value;
}

main().catch((error) => {
  console.error("The sample encountered an error:", error);
  process.exitCode = 1;
});
