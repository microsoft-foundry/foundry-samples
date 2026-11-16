# Verify WinML 2.0 Execution Providers (Rust)

This sample verifies that accelerated WinML execution providers are correctly discovered,
downloaded, and registered using the unified Foundry Local Rust SDK. It uses registered
accelerated model variants and finishes with one v2 streaming chat-session check.

## Prerequisites

- Windows with a compatible GPU
- Rust toolchain

## Build & Run

The unified v2 SDK provides execution-provider discovery and registration directly;
there is no separate `winml` Cargo feature or package split.

```bash
cargo run
```
