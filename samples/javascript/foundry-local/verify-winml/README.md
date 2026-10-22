# Verify Accelerator Execution Providers (JavaScript)

This sample verifies that accelerator execution providers are correctly discovered,
downloaded, and registered by the unified Foundry Local JavaScript SDK package. It finds
GPU- or NPU-backed model variants and finishes with a native v2 streaming chat check.

## Prerequisites

- A supported machine with a compatible GPU or NPU
- Node.js 20+

## Setup

`package.json` installs `foundry-local-sdk` 2.2.1. Execution-provider discovery and
registration are built into the unified package:

```bash
npm install
```

## Run

```bash
npm start
```
