---
page_type: sample
languages:
- csharp
products:
- ai-services
- azure
description: Foundry Local C# samples — chat, embeddings, audio, tool calling, model management, web server, and tutorials.
---

# 🚀 Foundry Local C# Samples

These samples demonstrate how to use the [Foundry Local](https://learn.microsoft.com/azure/foundry-local/) C# SDK v2. All projects reference the unified `Microsoft.AI.Foundry.Local` package:

- **Windows**: WinML 2.x acceleration and execution-provider management are included in the unified package.
- **macOS / Linux**: The same package provides the cross-platform runtime and APIs.

## Prerequisites

- [.NET 9 SDK](https://dotnet.microsoft.com/download/dotnet/9.0)

The SDK package includes the Foundry Local runtime; a separate CLI/runtime installation is not required.

## Samples

| Sample | Description |
|---|---|
| [native-chat-completions](native-chat-completions/) | Initialize the SDK, download a model, and run chat completions. |
| [embeddings](embeddings/) | Generate single and batch text embeddings using the Foundry Local SDK. |
| [audio-transcription-example](audio-transcription-example/) | Transcribe audio files using the Foundry Local SDK. |
| [foundry-local-web-server](foundry-local-web-server/) | Start a local OpenAI-compatible web server. |
| [tool-calling-foundry-local-sdk](tool-calling-foundry-local-sdk/) | Use tool calling with native chat completions. |
| [tool-calling-foundry-local-web-server](tool-calling-foundry-local-web-server/) | Use tool calling with the local web server. |
| [model-management-example](model-management-example/) | Manage models, variant selection, and updates. |
| [live-audio-transcription](live-audio-transcription/) | Stream PCM audio through the native v2 audio session (NAudio microphone capture on Windows). |
| [verify-winml](verify-winml/) | Verify the unified package's WinML capability and accelerated execution providers. |
| [tutorial-chat-assistant](tutorial-chat-assistant/) | Build an interactive chat assistant (tutorial). |
| [tutorial-document-summarizer](tutorial-document-summarizer/) | Summarize documents with AI (tutorial). |
| [tutorial-tool-calling](tutorial-tool-calling/) | Create a tool-calling assistant (tutorial). |
| [tutorial-voice-to-text](tutorial-voice-to-text/) | Transcribe and summarize audio (tutorial). |

## Running a sample

1. Clone the repository:

   ```bash
   git clone https://github.com/microsoft-foundry/foundry-samples.git
   cd foundry-samples/samples/csharp/foundry-local
   ```

2. Run a sample:

   ```bash
   cd native-chat-completions
   dotnet run
   ```

> [!TIP]
> Shared helpers used by multiple samples live under [`Shared/`](Shared/), and central package versions are managed by [`Directory.Packages.props`](Directory.Packages.props).
