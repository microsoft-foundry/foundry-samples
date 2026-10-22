---
page_type: sample
languages:
- rust
products:
- ai-services
- azure
description: Foundry Local Rust samples — chat, embeddings, audio, tool calling, web server, and tutorials.
---

# 🚀 Foundry Local Rust Samples

These samples demonstrate the maintained v2 Rust API for [Foundry Local](https://learn.microsoft.com/azure/foundry-local/) using `foundry-local-sdk` 2.2.1.

The samples form a single Cargo workspace defined in [`Cargo.toml`](Cargo.toml).

## Prerequisites

- [Rust](https://www.rust-lang.org/) 1.70.0 or later
- [Foundry Local](https://learn.microsoft.com/azure/foundry-local/) installed on your machine

## Samples

| Sample | Description |
|--------|-------------|
| [native-chat-completions](native-chat-completions/) | Non-streaming and streaming chat completions using `ChatSession`. |
| [embeddings](embeddings/) | Generate single and batch text embeddings using `EmbeddingsSession`. |
| [audio-transcription-example](audio-transcription-example/) | Audio transcription (non-streaming and streaming) using the Whisper model. |
| [foundry-local-webserver](foundry-local-webserver/) | Start a local OpenAI-compatible web server and call it with a standard HTTP client. |
| [tool-calling-foundry-local](tool-calling-foundry-local/) | Tool calling with streaming responses, multi-turn conversation, and local tool execution. |
| [live-audio-transcription](live-audio-transcription/) | Real-time microphone transcription using a v2 input queue and `cpal`. |
| [verify-winml](verify-winml/) | Verify accelerated WinML execution providers through the unified SDK (Windows only). |
| [tutorial-chat-assistant](tutorial-chat-assistant/) | Build an interactive multi-turn chat assistant (tutorial). |
| [tutorial-document-summarizer](tutorial-document-summarizer/) | Summarize documents with AI (tutorial). |
| [tutorial-tool-calling](tutorial-tool-calling/) | Create a tool-calling assistant (tutorial). |
| [tutorial-voice-to-text](tutorial-voice-to-text/) | Transcribe and summarize audio (tutorial). |

## Running a Sample

1. Clone the repository:

   ```bash
   git clone https://github.com/microsoft-foundry/foundry-samples.git
   cd foundry-samples/samples/rust/foundry-local
   ```

2. Run a sample from the workspace root:

   ```bash
   cargo run -p native-chat-completions
   ```

   Or navigate to a sample directory and run directly:

   ```bash
   cd native-chat-completions
   cargo run
   ```

> [!TIP]
> The unified v2 SDK discovers and registers supported execution providers at runtime. No separate Windows package or `winml` Cargo feature is required.
