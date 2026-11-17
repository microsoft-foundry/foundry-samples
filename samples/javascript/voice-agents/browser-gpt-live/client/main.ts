// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

import "./styles.css";
import {
  AIProjectClient,
  type VoiceAgentLiveConnection,
  type VoiceAgentLiveEvent,
} from "@azure/ai-projects";
import { MicrophoneCapture, PcmAudioPlayer } from "./audio.js";

// 50 ms of PCM16 mono 24 kHz silence. GPT-Live is full duplex and advances its clock only while
// input audio arrives, so the page streams silence whenever the microphone is muted.
const silenceFrame = new Uint8Array(2_400);
const silenceIntervalMs = 50;

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const endpointInput = $<HTMLInputElement>("endpoint");
const agentNameInput = $<HTMLInputElement>("agentName");
const createAgentInput = $<HTMLInputElement>("createAgent");
const modelInput = $<HTMLInputElement>("model");
const voiceInput = $<HTMLSelectElement>("voice");
const delegationModelInput = $<HTMLInputElement>("delegationModel");
const instructionsInput = $<HTMLTextAreaElement>("instructions");
const connectButton = $<HTMLButtonElement>("connect");
const disconnectButton = $<HTMLButtonElement>("disconnect");
const micButton = $<HTMLButtonElement>("mic");
const textForm = $<HTMLFormElement>("textForm");
const textInput = $<HTMLInputElement>("textInput");
const statusLabel = $<HTMLSpanElement>("status");
const levelMeter = $<HTMLDivElement>("level");
const transcriptList = $<HTMLOListElement>("transcript");
const eventLog = $<HTMLPreElement>("events");

endpointInput.value = import.meta.env.VITE_FOUNDRY_PROJECT_ENDPOINT ?? "";
modelInput.value = import.meta.env.VITE_FOUNDRY_LIVE_MODEL || "gpt-live-1";
delegationModelInput.value = import.meta.env.VITE_FOUNDRY_DELEGATION_MODEL ?? "";
agentNameInput.value = import.meta.env.VITE_FOUNDRY_VOICE_AGENT_NAME ?? "";

const microphone = new MicrophoneCapture();
const player = new PcmAudioPlayer();
let session: VoiceAgentLiveConnection | undefined;
let project: AIProjectClient | undefined;
let createdAgentName: string | undefined;
let silenceTimer: number | undefined;
let currentUserLine: HTMLLIElement | undefined;
let currentAgentLine: HTMLLIElement | undefined;
let cachedToken: { token: string; expiresOnTimestamp: number } | undefined;
let disconnecting = false;
let microphoneBusy = false;

/** Gets a Foundry access token from the loopback Vite token bridge (Azure CLI credential). */
const credential = {
  async getToken(): Promise<{ token: string; expiresOnTimestamp: number }> {
    if (cachedToken && cachedToken.expiresOnTimestamp - Date.now() > 120_000) {
      return cachedToken;
    }
    const response = await fetch("/api/azure-token", { cache: "no-store" });
    const body = (await response.json()) as { token?: string; expiresOnTimestamp?: number; error?: string };
    if (!response.ok || !body.token || !body.expiresOnTimestamp) {
      throw new Error(body.error ?? "The local Azure token bridge returned no token. Run `npm run dev`.");
    }
    cachedToken = { token: body.token, expiresOnTimestamp: body.expiresOnTimestamp };
    return cachedToken;
  },
};

function setStatus(text: string, state: "offline" | "busy" | "live" | "error"): void {
  statusLabel.textContent = text;
  document.body.dataset.state = state;
}

function setConnected(connected: boolean): void {
  connectButton.disabled = connected;
  disconnectButton.disabled = !connected;
  micButton.disabled = !connected || microphoneBusy;
  textInput.disabled = !connected;
  textForm.querySelector("button")!.disabled = !connected;
  for (const input of [endpointInput, agentNameInput, createAgentInput, modelInput, voiceInput]) {
    input.disabled = connected;
  }
  agentNameInput.disabled = connected || createAgentInput.checked;
  delegationModelInput.disabled = connected;
  instructionsInput.disabled = connected;
}

function logEvent(event: VoiceAgentLiveEvent): void {
  // Audio and delegated text deltas arrive every few milliseconds, so they are not logged.
  if (
    event.type === "session.output_audio.delta" ||
    (event.type === "response.event" && String(event.event.type).endsWith(".delta"))
  ) {
    return;
  }
  const line = `${new Date().toLocaleTimeString()} ${event.type} ${summarize(event)}\n`;
  eventLog.textContent = (line + (eventLog.textContent ?? "")).slice(0, 20_000);
}

function summarize(event: VoiceAgentLiveEvent): string {
  const { type: _type, ...rest } = event;
  const text = JSON.stringify(rest);
  return text.length > 240 ? `${text.slice(0, 240)}…` : text;
}

function appendTranscript(role: "user" | "agent" | "delegation", text: string): HTMLLIElement {
  const item = document.createElement("li");
  item.className = `turn ${role}`;
  item.dataset.role = role === "delegation" ? "Responses delegation" : role;
  item.textContent = text;
  transcriptList.append(item);
  transcriptList.scrollTop = transcriptList.scrollHeight;
  return item;
}

function handleEvent(event: VoiceAgentLiveEvent): void {
  logEvent(event);
  switch (event.type) {
    case "session.started":
      setStatus("Live", "live");
      break;
    case "session.output_audio.delta":
      void player.enqueue(Uint8Array.from(atob(event.delta), (char) => char.charCodeAt(0)))
        .catch((error: unknown) => setStatus(`Audio playback failed: ${error}`, "error"));
      break;
    case "session.input_transcript.delta":
      currentAgentLine = undefined;
      currentUserLine ??= appendTranscript("user", "");
      currentUserLine.textContent += event.delta;
      break;
    case "session.output_transcript.delta":
      currentUserLine = undefined;
      currentAgentLine ??= appendTranscript("agent", "");
      currentAgentLine.textContent += event.delta;
      break;
    case "session.delegation.created": {
      const delegation = event.delegation;
      if (delegation.target === "client") {
        // A client-owned delegation lets the app run its own tool or lookup and hand the
        // result back to the model as commentary. This sample answers with a placeholder.
        void session?.appendCommentary(
          "The browser client has no extra tools. Tell the user you cannot look that up.",
          { delegationId: delegation.id },
        ).catch((error: unknown) => setStatus(`Delegation failed: ${error}`, "error"));
      }
      break;
    }
    case "response.event": {
      const inner = event.event;
      if (inner.type === "response.output_text.delta" && typeof inner.delta === "string") {
        const last = transcriptList.lastElementChild as HTMLLIElement | null;
        const target =
          last?.classList.contains("delegation") ? last : appendTranscript("delegation", "");
        target.textContent += inner.delta;
      }
      break;
    }
    case "error": {
      setStatus(`Error: ${event.error.message}`, "error");
      break;
    }
    case "transport.failed": {
      setStatus(`Connection failed: ${event.error.message}`, "error");
      break;
    }
    case "session.closed":
      setStatus("Session closed", "offline");
      break;
  }
}

async function connect(): Promise<void> {
  const endpoint = endpointInput.value.trim().replace(/\/+$/, "");
  const agentName = createAgentInput.checked
    ? `gpt-live-browser-${crypto.randomUUID()}`
    : agentNameInput.value.trim();
  if (!endpoint || !agentName) {
    setStatus("Enter a project endpoint and agent name", "error");
    return;
  }

  setConnected(true);
  disconnectButton.disabled = true;
  micButton.disabled = true;
  textInput.disabled = true;
  textForm.querySelector("button")!.disabled = true;
  currentUserLine = undefined;
  currentAgentLine = undefined;
  transcriptList.replaceChildren();
  eventLog.textContent = "";
  try {
    project = new AIProjectClient(endpoint, credential);
    if (createAgentInput.checked) {
      setStatus("Creating GPT-Live agent…", "busy");
      const delegationModel = delegationModelInput.value.trim();
      const agent = await project.agents.createVersion(agentName, {
        kind: "voice",
        sub_protocol: "live",
        model_type: "self_deployed",
        model: modelInput.value.trim(),
        instructions: instructionsInput.value.trim(),
        audio: { format: { type: "audio/pcm", rate: 24_000 }, output: { voice: voiceInput.value } },
        ...(delegationModel && {
          delegation: {
            type: "responses" as const,
            responses: { model: delegationModel, instructions: "Answer the user's request accurately and briefly." },
          },
        }),
        store: false,
      }, { foundryFeatures: "VoiceAgents=V1Preview" });
      createdAgentName = agentName;
      appendTranscript("delegation", `Created agent ${agentName} version ${agent.version}.`).className =
        "turn system";
    }

    setStatus("Connecting…", "busy");
    const connected = await project.beta.voiceAgents.live.connect(agentName, {
      store: false,
      onEvent: handleEvent,
    });
    session = connected;
    setConnected(true);
    void connected.closed.then((result) => {
      if (session !== connected) return;
      if (result.error) setStatus(`Connection closed: ${result.error.message}`, "error");
      void teardown();
    });
    startSilence();
  } catch (error) {
    setStatus(error instanceof Error ? error.message : String(error), "error");
    await teardown();
  }
}

function startSilence(): void {
  stopSilence();
  silenceTimer = window.setInterval(() => sendAudio(silenceFrame), silenceIntervalMs);
}

function stopSilence(): void {
  window.clearInterval(silenceTimer);
  silenceTimer = undefined;
}

function sendAudio(audio: Uint8Array): void {
  const active = session;
  if (!active) return;
  void active.sendAudio(audio).catch((error: unknown) => {
    if (session !== active) return;
    setStatus(`Sending audio failed: ${error}`, "error");
    void teardown();
  });
}

async function toggleMicrophone(): Promise<void> {
  if (microphoneBusy || !session) {
    return;
  }
  microphoneBusy = true;
  micButton.disabled = true;
  try {
    if (microphone.active) {
      await microphone.stop();
      levelMeter.style.setProperty("--level", "0");
      micButton.textContent = "Start microphone";
      startSilence();
    } else {
      stopSilence();
      await microphone.start(
        sendAudio,
        (level) => levelMeter.style.setProperty("--level", level.toFixed(3)),
      );
      if (!session) {
        // The session ended while the browser was waiting for microphone permission.
        await microphone.stop();
        return;
      }
      micButton.textContent = "Mute microphone";
    }
  } catch (error) {
    startSilence();
    setStatus(`Microphone unavailable: ${error instanceof Error ? error.message : error}`, "error");
  } finally {
    microphoneBusy = false;
    micButton.disabled = !session;
  }
}

async function teardown(): Promise<void> {
  if (disconnecting) return;
  disconnecting = true;
  stopSilence();
  const closing = session;
  session = undefined;
  if (closing) {
    try {
      await closing.close();
    } catch (error) {
      setStatus(`Could not close the session: ${error}`, "error");
    }
  }
  await microphone.stop();
  player.stop();
  micButton.textContent = "Start microphone";
  levelMeter.style.setProperty("--level", "0");
  if (createdAgentName && project) {
    const name = createdAgentName;
    createdAgentName = undefined;
    try {
      await project.agents.delete(name);
      appendTranscript("delegation", `Deleted agent ${name}.`).className = "turn system";
    } catch (error) {
      setStatus(`Could not delete agent ${name}: ${error}`, "error");
    }
  }
  setConnected(false);
  if (document.body.dataset.state !== "error") {
    setStatus("Offline", "offline");
  }
  disconnecting = false;
}

connectButton.addEventListener("click", () => void connect());
disconnectButton.addEventListener("click", () => void teardown());
micButton.addEventListener("click", () => void toggleMicrophone());
createAgentInput.addEventListener("change", () => {
  agentNameInput.disabled = createAgentInput.checked;
});
textForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = textInput.value.trim();
  if (!text || !session) {
    return;
  }
  currentUserLine = undefined;
  currentAgentLine = undefined;
  appendTranscript("user", text);
  const active = session;
  void (async () => {
    await active.sendResponseItem({
      type: "message",
      role: "user",
      content: [{ type: "input_text", text }],
    });
    await active.requestResponse();
  })().catch((error: unknown) => setStatus(`Sending text failed: ${error}`, "error"));
  textInput.value = "";
});
window.addEventListener("beforeunload", () => {
  void session?.close().catch((error: unknown) => console.warn("Session close failed:", error));
});

setConnected(false);
setStatus("Offline", "offline");
