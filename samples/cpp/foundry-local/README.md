---
page_type: sample
languages:
- cpp
products:
- ai-services
- azure
description: Foundry Local C++ samples for chat, embeddings, audio, tool calling, and tutorials.
---

# Foundry Local C++ samples

These samples use the header-only C++ v2 API shipped in the
`Microsoft.AI.Foundry.Local.Runtime` NuGet package. The shared package manifest
pins version **2.2.1**; no repository-local SDK checkout is required.

## Prerequisites

- CMake 3.20 or later
- A C++20 compiler
- NuGet CLI
- A supported Foundry Local platform:
  - Windows x64 or Arm64
  - Linux x64 or Arm64
  - macOS on Apple silicon

Model downloads require network access and sufficient disk space. Actual
execution-provider and model availability depends on the operating system and
hardware reported by the local catalog.

## Build and run

Each directory is independently buildable and produces an executable whose
name matches the directory:

```bash
cd native-chat-completions
cmake -S . -B build
cmake --build build --config Release
./build/native-chat-completions
```

On Windows, run `build\native-chat-completions.exe`.

To use a specific NuGet source without storing it in the repository, set
`NUGET_SOURCE` only for the configure command.

## Samples

| Sample | Description |
|---|---|
| [audio-transcription](audio-transcription/) | Transcribe a user-supplied audio file. |
| [embeddings](embeddings/) | Generate single and batch embeddings. |
| [integrate-examples](integrate-examples/) | Integrate manager, EP, catalog, cache, model, and session lifecycle code. |
| [live-audio-transcription](live-audio-transcription/) | Stream raw 16 kHz, 16-bit mono PCM from a file or standard input. |
| [native-chat-completions](native-chat-completions/) | Run native non-streaming and streaming chat completions. |
| [tool-calling](tool-calling/) | Define a function tool and complete a tool-call loop. |
| [tutorial-chat-assistant](tutorial-chat-assistant/) | Build an interactive multi-turn assistant. |
| [tutorial-document-summarizer](tutorial-document-summarizer/) | Summarize `document.txt` or another text file. |
| [tutorial-tool-calling-assistant](tutorial-tool-calling-assistant/) | Build an assistant that invokes local tools. |
| [tutorial-voice-to-text](tutorial-voice-to-text/) | Transcribe audio and summarize the transcript. |

## Audio limitations

`audio-transcription` and `tutorial-voice-to-text` accept encoded audio files
supported by the selected model/runtime. `live-audio-transcription` does not
claim to provide a portable microphone-capture layer: it accepts headerless
little-endian signed 16-bit mono PCM at 16 kHz. Pipe microphone audio from a
platform capture tool, pass a PCM file, or pass `-` to read the stream from
standard input. Audio models and acceleration providers are hardware- and
platform-dependent.
