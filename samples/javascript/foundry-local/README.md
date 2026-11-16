---
page_type: sample
languages:
- javascript
products:
- ai-services
- azure
description: Foundry Local JavaScript samples — chat, embeddings, audio, Electron app, LangChain, tool calling, web server, and tutorials.
---

# 🚀 Foundry Local JavaScript Samples

These samples demonstrate the Foundry Local JavaScript SDK v2 (`foundry-local-sdk` 2.2.1) with Node.js. Native inference samples use modality-specific `ChatSession`, `AudioSession`, and `EmbeddingsSession` APIs; integration samples use the SDK's embedded OpenAI-compatible web service.

## Prerequisites

- [Node.js](https://nodejs.org/) v20 or later
- [Foundry Local](https://learn.microsoft.com/azure/foundry-local/) installed on your machine

## Samples

| Sample | Description |
|--------|-------------|
| [native-chat-completions](native-chat-completions/) | Initialize the SDK, download a model, and run non-streaming and streaming chat completions. |
| [embeddings](embeddings/) | Generate single and batch text embeddings using the Foundry Local SDK. |
| [audio-transcription-example](audio-transcription-example/) | Transcribe audio files using the Whisper model with streaming output. |
| [chat-and-audio-foundry-local](chat-and-audio-foundry-local/) | Unified sample demonstrating both chat and audio transcription in one application. |
| [electron-chat-application](electron-chat-application/) | Full-featured Electron desktop chat app with voice transcription and model management. |
| [copilot-sdk-foundry-local](copilot-sdk-foundry-local/) | GitHub Copilot SDK integration with Foundry Local for agentic AI workflows. |
| [langchain-integration-example](langchain-integration-example/) | LangChain.js integration for building text generation chains. |
| [tool-calling-foundry-local](tool-calling-foundry-local/) | Tool calling with custom function definitions and streaming responses. |
| [web-server-example](web-server-example/) | Start a local OpenAI-compatible web server and call it with the OpenAI SDK. |
| [live-audio-transcription](live-audio-transcription/) | Real-time microphone-to-text transcription using `naudiodon2`. |
| [verify-winml](verify-winml/) | Verify accelerator execution providers and native streaming chat through the unified SDK package. |
| [tutorial-chat-assistant](tutorial-chat-assistant/) | Build an interactive multi-turn chat assistant (tutorial). |
| [tutorial-document-summarizer](tutorial-document-summarizer/) | Summarize documents with AI (tutorial). |
| [tutorial-tool-calling](tutorial-tool-calling/) | Create a tool-calling assistant (tutorial). |
| [tutorial-voice-to-text](tutorial-voice-to-text/) | Transcribe and summarize audio (tutorial). |

## Running a Sample

1. Clone the repository:

   ```bash
   git clone https://github.com/microsoft-foundry/foundry-samples.git
   cd foundry-samples/samples/javascript/foundry-local
   ```

2. Navigate to a sample and install dependencies:

   ```bash
   cd native-chat-completions
   npm install
   ```

3. Run the sample:

   ```bash
   npm start
   ```

> [!TIP]
> Every sample pins `foundry-local-sdk` 2.2.1. The unified package discovers and installs supported execution providers.
