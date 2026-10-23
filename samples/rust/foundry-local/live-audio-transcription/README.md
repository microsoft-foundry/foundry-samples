# Live Audio Transcription Example (Rust)

Demonstrates real-time microphone-to-text using the Foundry Local Rust SDK:

**Microphone (CPAL) → v2 `AudioSession` input queue → Foundry Local runtime**

Uses [CPAL](https://crates.io/crates/cpal) for cross-platform microphone capture
(the Rust equivalent of `naudiodon2` in JS / `PortAudio` in C++ / `PyAudio` in Python).
If CPAL cannot open a microphone, falls back to synthetic PCM audio.

## Run

```bash
cd samples/rust/foundry-local/live-audio-transcription

# Live microphone (press Ctrl+C to stop)
cargo run

# Synthetic 440Hz sine wave (no microphone needed)
cargo run -- --synth
```
