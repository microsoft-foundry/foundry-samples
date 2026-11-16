---
page_type: sample
languages:
- python
products:
- ai-services
- azure
description: Foundry Local Python samples — chat, embeddings, audio, LangChain, tool calling, web server (including Responses & Vision), and tutorials.
---

# 🚀 Foundry Local Python Samples

These samples demonstrate the maintained Foundry Local Python SDK v2. Native
samples use typed sessions, requests, and modality-specific items. Web-service
samples expose the local OpenAI-compatible endpoint for OpenAI and LangChain
clients.

## Prerequisites

- [Python](https://www.python.org/) 3.11 through 3.14
- A supported Windows, Linux, or Apple silicon macOS machine

## Samples

| Sample | Description |
|--------|-------------|
| [native-chat-completions](native-chat-completions/) | Run streaming chat inference with the native typed `ChatSession` API. |
| [embeddings](embeddings/) | Generate single and batch embeddings with `EmbeddingsSession`. |
| [audio-transcription](audio-transcription/) | Transcribe audio files with `AudioSession`. |
| [web-server](web-server/) | Start a local OpenAI-compatible web server and call it with the OpenAI Python SDK. |
| [web-server-responses](web-server-responses/) | Call a running local OpenAI-compatible web server with the Responses API, including streaming and tool calling. |
| [web-server-responses-vision](web-server-responses-vision/) | Vision (image understanding) using the Foundry Local web service and OpenAI Responses API. |
| [tool-calling](tool-calling/) | Native typed tool calling with custom function definitions. |
| [langchain-integration](langchain-integration/) | LangChain integration for building translation and text generation chains. |
| [live-audio-transcription](live-audio-transcription/) | Stream PCM input through `AudioSession` and `ItemQueue`. |
| [verify-winml](verify-winml/) | Verify unified-package Windows ML/current-platform acceleration capabilities. |
| [tutorial-chat-assistant](tutorial-chat-assistant/) | Build an interactive multi-turn chat assistant (tutorial). |
| [tutorial-document-summarizer](tutorial-document-summarizer/) | Summarize documents with AI (tutorial). |
| [tutorial-tool-calling](tutorial-tool-calling/) | Create a tool-calling assistant (tutorial). |
| [tutorial-voice-to-text](tutorial-voice-to-text/) | Transcribe and summarize audio (tutorial). |

## Running a Sample

1. Clone the repository:

   ```bash
   git clone https://github.com/microsoft-foundry/foundry-samples.git
   cd foundry-samples/samples/python/foundry-local
   ```

2. Navigate to a sample and install dependencies:

   ```bash
   cd native-chat-completions
   pip install -r requirements.txt
   ```

3. Run the sample:

   ```bash
   python src/app.py
   ```

> [!TIP]
> Every sample pins the unified `foundry-local-sdk` package. The Windows wheel
> includes Windows ML support; no separate WinML package is required.
