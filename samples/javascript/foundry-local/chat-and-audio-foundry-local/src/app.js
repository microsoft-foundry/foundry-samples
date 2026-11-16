// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

import {
  AudioSession,
  ChatSession,
  FoundryLocalManager,
  Item,
  Request,
} from "foundry-local-sdk";
import path from "path";

// Model aliases
const CHAT_MODEL = "qwen2.5-0.5b";
const WHISPER_MODEL = "whisper-tiny";

async function main() {
  console.log("Initializing Foundry Local SDK...");
  const manager = FoundryLocalManager.create({
    appName: "foundry_local_samples",
    logLevel: "info",
  });

  // Download and register all execution providers.
  let currentEp = '';
  await manager.downloadAndRegisterEps((epName, percent) => {
    if (epName !== currentEp) {
      if (currentEp !== '') process.stdout.write('\n');
      currentEp = epName;
    }
    process.stdout.write(`\r  ${epName.padEnd(30)}  ${percent.toFixed(1).padStart(5)}%`);
  });
  if (currentEp !== '') process.stdout.write('\n');

  const catalog = manager.catalog;

  // --- Load both models ---
  console.log("\n--- Loading models ---");

  const chatModel = await catalog.getModel(CHAT_MODEL);
  if (!chatModel) {
    throw new Error(
      `Chat model "${CHAT_MODEL}" not found. Run "foundry model list" to see available models.`
    );
  }

  const whisperModel = await catalog.getModel(WHISPER_MODEL);
  if (!whisperModel) {
    throw new Error(
      `Whisper model "${WHISPER_MODEL}" not found. Run "foundry model list" to see available models.`
    );
  }

  // Download models if not cached
  if (!chatModel.isCached) {
    console.log(`Downloading ${CHAT_MODEL}...`);
    await chatModel.download((progress) => {
      process.stdout.write(`\r  ${CHAT_MODEL}: ${progress.toFixed(1)}%`);
    });
    console.log();
  }

  if (!whisperModel.isCached) {
    console.log(`Downloading ${WHISPER_MODEL}...`);
    await whisperModel.download((progress) => {
      process.stdout.write(`\r  ${WHISPER_MODEL}: ${progress.toFixed(1)}%`);
    });
    console.log();
  }

  // Load both models into memory
  console.log(`Loading ${CHAT_MODEL}...`);
  await chatModel.load();
  console.log(`Loading ${WHISPER_MODEL}...`);
  await whisperModel.load();
  console.log("Both models loaded.\n");

  // --- Step 1: Transcribe audio ---
  console.log("=== Step 1: Audio Transcription ===");
  const audioSession = new AudioSession(whisperModel);
  const audioFilePath = path.resolve("recording.mp3");
  const audioRequest = new Request()
    .addItem(Item.audioFromUri(audioFilePath))
    .setOptions({ additionalOptions: { language: "en" } });
  const audioResponse = await audioSession.processRequest(audioRequest);
  const transcription = audioResponse.output.find((item) => item.type === "speechResult");
  if (!transcription) {
    throw new Error("The audio model returned no transcription.");
  }
  console.log("You said:", transcription.text);

  // --- Step 2: Analyze with chat model ---
  console.log("\n=== Step 2: AI Analysis ===");
  const chatSession = new ChatSession(chatModel);

  // Summarize the transcription
  console.log("Generating summary...\n");
  const chatRequest = new Request()
    .addItem(Item.systemMessage(
      "You are a helpful assistant. Summarize the following transcribed audio and extract key themes and action items."
    ))
    .addItem(Item.userMessage(transcription.text))
    .setOptions({ search: { temperature: 0.7, maxOutputTokens: 500 } });
  const stream = chatSession.processStreamingRequest(chatRequest);
  for await (const item of stream) {
    if (item.type === "text" && item.textType === "default") {
      process.stdout.write(item.text);
    }
  }
  await stream.response;
  console.log("\n");

  // --- Clean up ---
  chatSession.dispose();
  audioSession.dispose();
  await chatModel.unload();
  await whisperModel.unload();
  console.log("Done.");
}

main().catch(console.error);
