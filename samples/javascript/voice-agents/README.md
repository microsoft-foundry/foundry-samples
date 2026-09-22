---
page_type: sample
languages:
- javascript
products:
- ai-services
- azure
description: Microsoft Foundry Voice Agents samples in JavaScript, covering voice agent configuration, generation, realtime audio/text streaming, and telephony inspection.
---

# 🎙️ Voice Agents JavaScript Samples

Samples for Microsoft Foundry **Voice Agents**, a preview feature of the [`@azure/ai-projects`](https://www.npmjs.com/package/@azure/ai-projects) SDK that lets an agent hold a spoken, real-time conversation over a WebSocket connection.

Voice Agents are gated behind an opt-in preview header, sent automatically by these samples via the `foundry-features: VoiceAgents=V1Preview` request option (or the equivalent `{ foundryFeatures: "VoiceAgents=V1Preview" }` shorthand).

## Samples

| Sample | Description |
| --- | --- |
| [`configure-voice-agent`](./configure-voice-agent) | Create a self-deployed voice agent definition with a greeting and disabled conversation storage, then retrieve and delete it. |
| [`generate-voice-agent`](./generate-voice-agent) | Generate a managed voice agent from a natural-language goal and inspect its generated definition. |
| [`manage-voice-agent`](./manage-voice-agent) | Full agent management lifecycle: create, read, update, list, version history, enable/disable, and delete. |
| [`realtime-audio`](./realtime-audio) | Stream raw PCM16 audio to a voice agent over a realtime connection and save the streamed audio response. |
| [`realtime-text-and-tools`](./realtime-text-and-tools) | Send text to a voice agent, stream its text/audio response, and handle a local function tool call. |
| [`voice-agent-conversations`](./voice-agent-conversations) | Inspect a stored voice agent conversation - its items and model responses - through the Conversation REST API. |
| [`telephony-inspection`](./telephony-inspection) | Read-only inspection of a voice agent's telephony bindings, transfer targets, and call history. |
| [`browser-voice-console`](./browser-voice-console) | Browser-based console for chatting or talking with a voice agent and managing its definitions, authenticated through a loopback Azure CLI bridge so no credential is ever supplied to the browser. |

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

`browser-voice-console` is a Vite app instead of a Node.js script: run `npm install`, copy `.env-template` to `.env`, then `npm run dev` and open the printed local URL.

## Learn more

- [`@azure/ai-projects` on npm](https://www.npmjs.com/package/@azure/ai-projects)
- [Azure SDK for JS – ai-projects voice agent samples](https://github.com/Azure/azure-sdk-for-js/tree/main/sdk/ai/ai-projects/samples-dev/agents)
