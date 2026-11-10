# Live Audio Transcription Example

Real-time microphone-to-text transcription using the Foundry Local JS SDK with Nemotron ASR.

## Prerequisites

- [Foundry Local](https://github.com/microsoft/Foundry-Local) installed
- Node.js 20+
- A microphone (optional — falls back to synthetic audio)

## Setup

```bash
npm install
```

> **Note:** `naudiodon2` is optional — provides cross-platform microphone capture. Without it, the example falls back to synthetic audio for testing.

## Run

```bash
node app.js
```

Speak into your microphone. Transcription appears in real-time. Press `Ctrl+C` to stop.

## How it works

1. Initializes the Foundry Local SDK and loads the Nemotron ASR model
2. Creates an `AudioSession`, `ItemQueue`, and streaming `Request` with 16kHz/16-bit/mono PCM settings
3. Captures microphone audio via `naudiodon2` (or generates synthetic audio as fallback)
4. Pushes PCM chunks to the SDK as `Item.bytes(...)`
5. Reads `speechSegment` items from `session.processStreamingRequest(...)`
6. Reads the final `speechResult` from the stream's terminal response

## API

```javascript
const session = new AudioSession(model);
const queue = new ItemQueue();
const request = new Request()
    .addItem(Item.audioDescriptor('pcm', 16000, 1))
    .addItem(queue)
    .setOptions({ additionalOptions: { language: 'en' } });
const stream = session.processStreamingRequest(request);

// Push audio
queue.push(Item.bytes(pcmBytes));
queue.markFinished();

// Read results
for await (const item of stream) {
    if (item.type === 'speechSegment') {
        console.log(item.text);
    }
}
const response = await stream.response;
```
