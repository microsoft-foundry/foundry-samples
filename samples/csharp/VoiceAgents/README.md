---
page_type: sample
languages:
- csharp
products:
- ai-services
- azure
description: Microsoft Foundry Voice Agents samples in C#, covering voice agent configuration, generation, realtime audio/text streaming, and telephony inspection.
---

# 🎙️ Voice Agents C# Samples

Samples for Microsoft Foundry **Voice Agents**, a preview feature of the [`Azure.AI.Projects`](https://www.nuget.org/packages/Azure.AI.Projects)/[`Azure.AI.Projects.Agents`](https://www.nuget.org/packages/Azure.AI.Projects.Agents) SDKs that lets an agent hold a spoken, real-time conversation over a WebSocket connection.

`ProjectsRealtimeSessionClient` (the realtime session type used by the streaming samples below) extends the [`OpenAI`](https://www.nuget.org/packages/OpenAI) package's own `OpenAI.Realtime.RealtimeSessionClient`, so it reuses OpenAI's realtime command/event model (`AddItemAsync`, `SendInputAudioAsync`, `StartResponseAsync`, `ReceiveUpdatesAsync`, ...); only the WebSocket handshake targets the Foundry voice-agent endpoint instead of OpenAI's own `/realtime` endpoint. Voice Agents types are marked `[Experimental("AAIP001")]`/`[Experimental("AAIP002")]` while in preview; each sample's `.csproj` suppresses those warnings with `<NoWarn>`.

## Samples

| Sample | Description |
| --- | --- |
| [`configure-voice-agent`](./configure-voice-agent) | Create a self-deployed voice agent definition with a greeting and disabled conversation storage, then retrieve and delete it. |
| [`generate-voice-agent`](./generate-voice-agent) | Generate a managed voice agent from a natural-language goal and inspect its generated definition. |
| [`manage-voice-agent`](./manage-voice-agent) | Full agent management lifecycle: create, read, update via new versions, list, version history, enable/disable, and delete. |
| [`realtime-audio`](./realtime-audio) | Stream raw PCM16 audio to a voice agent over a realtime connection and save the streamed audio response. |
| [`realtime-text-and-tools`](./realtime-text-and-tools) | Send text to a voice agent, stream its text/audio response, and handle a local function tool call. |
| [`voice-agent-conversations`](./voice-agent-conversations) | Inspect a stored voice agent conversation - its items and model responses - through the Conversation REST API. |
| [`telephony-inspection`](./telephony-inspection) | Read-only inspection of a voice agent's telephony bindings, transfer targets, and call history. |

## Prerequisites

- [.NET 8 SDK](https://dotnet.microsoft.com/download) or later
- An Azure subscription with a [Microsoft Foundry](https://ai.azure.com) project that has Voice Agents enabled, and a realtime/cascaded voice model deployment (for example `gpt-realtime`)
- Sign in with the Azure CLI so [`DefaultAzureCredential`](https://www.nuget.org/packages/Azure.Identity) can authenticate: `az login`
- Your identity needs the **Azure AI User** role (or equivalent) on the Foundry project

## Running a sample

Each sample is self-contained. From a sample's folder:

```bash
cp .env-template .env   # then fill in your values, and set them as environment variables
dotnet run
```

Every sample reads its configuration from environment variables (see each sample's `.env-template`); `dotnet run` does not load a `.env` file automatically, so export the values from it into your shell first (for example `Get-Content .env | ForEach-Object { if ($_ -match '^([^=]+)="?([^"]*)"?$') { Set-Item "Env:$($Matches[1])" $Matches[2] } }` in PowerShell, or `set -a; source .env; set +a` in bash).

## Learn more

- [`Azure.AI.Projects` on NuGet](https://www.nuget.org/packages/Azure.AI.Projects)
- [`Azure.AI.Projects.Agents` on NuGet](https://www.nuget.org/packages/Azure.AI.Projects.Agents)
- [Azure SDK for JS - ai-projects voice agent samples](../../javascript/voice-agents) (the JavaScript/TypeScript equivalents of these samples, including a browser-based console)
