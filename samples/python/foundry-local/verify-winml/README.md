# Verify Windows ML and Accelerated Execution Providers

The unified `foundry-local-sdk` wheel includes Windows ML support on Windows.
This sample discovers and registers execution providers, finds an accelerated
model variant, and runs an SDK v2 native streaming chat check. On non-Windows
platforms it validates the accelerated providers available on that machine.

## Prerequisites

- Python 3.11 through 3.14
- A compatible GPU or NPU for accelerated-model validation

## Setup

Use a fresh virtual environment for the cleanest setup.

`requirements.txt` installs the single cross-platform package, including
Windows ML support in the Windows wheel:

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade -r requirements.txt
```

## Run

```bash
python src/app.py
```

## What it tests

1. **EP Discovery** — Lists all available execution providers
2. **EP Download & Registration** — Downloads only providers not already registered
3. **Windows ML Capability** — Requires a registered Windows ML provider on Windows
4. **Model Catalog** — Lists accelerated GPU/NPU model variants
5. **Streaming Chat** — Runs native SDK v2 streaming inference
