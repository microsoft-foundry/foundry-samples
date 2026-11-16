---
page_type: sample
languages:
- javascript
products:
- ai-services
- azure
description: JavaScript samples for Microsoft Foundry Voice Agents, including agent setup, realtime audio, telephony sounds, tracing, and GPT-Live in the browser.
---

# 🎙️ Voice Agents JavaScript Samples

Samples for Microsoft Foundry **Voice Agents**, a preview feature of the [`@azure/ai-projects`](https://www.npmjs.com/package/@azure/ai-projects) SDK that lets an agent hold a spoken, real-time conversation over a WebSocket connection.

GPT-Live and some other Voice Agents features require the `VoiceAgents=V1Preview` opt-in. The samples use the `foundry-features` request header or `{ foundryFeatures: "VoiceAgents=V1Preview" }` where needed.

## Samples

| Sample | Description |
| --- | --- |
| [`configure-voice-agent`](./configure-voice-agent) | Create a self-deployed voice agent definition with a greeting and disabled conversation storage, then retrieve and delete it. |
| [`generate-voice-agent`](./generate-voice-agent) | Generate a managed voice agent from a natural-language goal and inspect its generated definition. |
| [`manage-voice-agent`](./manage-voice-agent) | Full agent management lifecycle: create, read, update, list, version history, enable/disable, and delete. |
| [`realtime-audio`](./realtime-audio) | Stream raw PCM16 audio to a voice agent over a realtime connection and save the streamed audio response. |
| [`realtime-image-input`](./realtime-image-input) | Send one text-and-image turn to an existing voice agent and validate the response lifecycle. |
| [`realtime-text-and-tools`](./realtime-text-and-tools) | Send text to a voice agent, stream its text/audio response, and handle a local function tool call. |
| [`voice-agent-conversations`](./voice-agent-conversations) | Inspect a stored voice agent conversation - its items and model responses - through the Conversation REST API. |
| [`telephony-inspection`](./telephony-inspection) | Read-only inspection of a voice agent's telephony bindings, transfer targets, and call history. |
| [`configure-soundscape-and-audio`](./configure-soundscape-and-audio) | Set up telephony background and event sounds, noise suppression, and speech transcription. Soundscape audio is for telephony calls; the realtime check only verifies the agent responds. |
| [`realtime-tracing`](./realtime-tracing) | View OpenTelemetry traces for agent setup, a realtime response, and a local function call. |
| [`browser-voice-console`](./browser-voice-console) | Browser-based console for chatting or talking with a voice agent and managing its definitions, using a local Azure CLI token bridge. |
| [`browser-gpt-live`](./browser-gpt-live) | Talk or type to a GPT-Live agent in your browser using the SDK's Live API. |

These samples target `@azure/ai-projects` 2.11.0.

## Prerequisites

- Node.js >= 22
- An Azure subscription with a [Microsoft Foundry](https://ai.azure.com) project that has Voice Agents enabled, and a realtime/cascaded voice model deployment (for example `gpt-realtime`)
- Sign in with the Azure CLI so [`DefaultAzureCredential`](https://www.npmjs.com/package/@azure/identity) can authenticate: `az login`
- Your identity needs the **Azure AI User** role (or equivalent) on the Foundry project

## Running a sample

Each sample is self-contained. From a sample's folder:

```bash
npm install
cp .env-template .env   # then fill in your values
npm start
```

`browser-voice-console` and `browser-gpt-live` are Vite apps instead of Node.js scripts: run `npm install`, copy `.env-template` to `.env`, then `npm run dev` and open the printed local URL (`browser-gpt-live` uses port 5174). In `browser-gpt-live/.env`, set `VITE_FOUNDRY_LIVE_MODEL` to your GPT-Live deployment name (the default is `gpt-live-1`). To send typed messages, also set `VITE_FOUNDRY_DELEGATION_MODEL` to a Responses model deployment, such as `gpt-4.1`; allow microphone access to talk.

The browser samples use a local development server that passes Azure CLI access tokens to the browser. Disconnect before closing the GPT-Live page so its temporary agent is deleted.

## Learn more

- [`@azure/ai-projects` on npm](https://www.npmjs.com/package/@azure/ai-projects)
- [Azure SDK for JS – ai-projects voice agent samples](https://github.com/Azure/azure-sdk-for-js/tree/main/sdk/ai/ai-projects/samples-dev/agents)
