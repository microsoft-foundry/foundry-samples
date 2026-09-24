---
page_type: sample
languages:
- java
products:
- ai-services
- azure
description: Java samples for creating, configuring, and using Microsoft Foundry voice agents.
---

# Voice Agents Java samples

These samples demonstrate how to create, configure, and use Microsoft Foundry voice agents with the
[Azure AI Agents client library for Java](https://github.com/Azure/azure-sdk-for-java/tree/main/sdk/ai/azure-ai-agents).
Voice agent APIs are currently in preview.

## Prerequisites

- Java Development Kit (JDK) 8 or later
- [Apache Maven](https://maven.apache.org/install.html)
- An Azure subscription and Microsoft Foundry project
- Permission to create and use agents in the project
- Azure CLI authentication (`az login`) or another credential supported by `DefaultAzureCredential`

## Configure the samples

Set the project endpoint before running a sample. You can copy it from the Microsoft Foundry portal. The endpoint
resembles `https://<resource>.services.ai.azure.com/api/projects/<project>`.

PowerShell:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT = "<your-project-endpoint>"
```

Bash:

```bash
export FOUNDRY_PROJECT_ENDPOINT="<your-project-endpoint>"
```

Most samples also accept these optional variables:

| Variable | Description | Default |
| --- | --- | --- |
| `FOUNDRY_VOICE_AGENT_NAME` | Name of the voice agent | Varies by sample |
| `FOUNDRY_VOICE_MODEL` | Voice model or deployment name | `gpt-realtime` |
| `FOUNDRY_VOICE_MODEL_TYPE` | Voice model type | `managed` |
| `FOUNDRY_KEEP_VOICE_AGENT` | Keep an agent created by a live async sample | `false` |

The conversation-reading samples additionally require `FOUNDRY_VOICE_CONVERSATION_ID`.

## Run a sample

Run a sample by supplying its fully qualified class name:

```bash
mvn compile exec:java -Dexec.mainClass=com.azure.ai.agents.voice.VoiceAgentBasicSample
```

Replace `VoiceAgentBasicSample` with any runnable class below.

## Examples

| Sample | Demonstrates |
| --- | --- |
| `VoiceAgentBasicSample` | Synchronous voice-agent lifecycle |
| `VoiceAgentBasicAsyncSample` | Asynchronous voice-agent lifecycle |
| `VoiceAgentGenerateSample` | Guided voice-agent generation |
| `VoiceAgentVersionsSample` | Released and draft agent versions |
| `VoiceAgentWithToolsSample` | Audio processing, transcription, and tool configuration |
| `VoiceAgentLiveTextConversationSample` | Synchronous multi-turn realtime text conversation with audio replies |
| `VoiceAgentLiveTextConversationAsyncSample` | Asynchronous multi-turn realtime text conversation with audio replies |
| `VoiceAgentLiveAudioConversationAsyncSample` | Live microphone and speaker conversation |
| `VoiceAgentLiveFunctionToolSample` | Client-side function calls in a live conversation |
| `VoiceAgentReadConversationSample` | Persisted conversation responses and transcripts |
| `VoiceAgentReadConversationAudioSample` | Persisted whole-call and item-level audio |

The live audio examples use the system microphone and speakers. End an interactive text conversation with a blank line,
`exit`, or `quit`.

These examples are adapted from the
[Azure SDK for Java voice samples](https://github.com/Azure/azure-sdk-for-java/tree/main/sdk/ai/azure-ai-agents/src/samples/java/com/azure/ai/agents/voice).
