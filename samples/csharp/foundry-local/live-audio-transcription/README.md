# Live Audio Transcription Example

Real-time microphone-to-text transcription using the Foundry Local C# SDK v2 with Nemotron ASR.

## Prerequisites

- .NET 9 SDK
- A microphone (optional — falls back to synthetic audio on non-Windows or with `--synth`)

## Setup

```bash
dotnet restore
```

> **Note:** Microphone capture uses [NAudio](https://github.com/naudio/NAudio) and is Windows-only. On other platforms, the sample falls back to synthetic audio for testing.

## Run

```bash
dotnet run
```

Speak into your microphone. Transcription appears in real-time (cyan text). Press `ENTER` to stop recording.

To force synthetic audio (e.g., for CI or non-Windows):

```bash
dotnet run -- --synth
```

## How it works

1. Initializes the Foundry Local SDK and loads the Nemotron ASR model
2. Creates a native `AudioSession`, `Request`, and `ItemQueue` for 16kHz/16-bit/mono PCM
3. Captures microphone audio via `NAudio.WaveIn` (or generates synthetic audio as fallback)
4. Pushes owned `BytesItem` chunks into the input queue
5. Reads `SpeechSegmentItem` results from `ProcessStreamingRequestAsync`
6. Reads the complete transcript from the final `SpeechResultItem`

## API

```csharp
using var session = new AudioSession(model);
using var queue = new ItemQueue();
using var request = new Request();
session.SetStreaming(true);
request.AddItem(AudioItem.CreateFormatDescriptor("pcm", 16000, 1));
request.AddItem(queue, takeOwnership: false);

await using var stream = session.ProcessStreamingRequestAsync(request);
queue.Push(BytesItem.CreateOwned(pcmBytes));
queue.MarkFinished();

await foreach (var item in stream)
{
    using (item)
    {
        if (item is SpeechSegmentItem segment)
            Console.Write(segment.Text);
    }
}
using var finalResponse = await stream.FinalResponse;
```
