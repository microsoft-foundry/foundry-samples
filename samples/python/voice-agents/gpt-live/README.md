<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# GPT Live Voice Agent with Responses delegation

## What this sample demonstrates

This sample deploys a declarative Foundry Voice Agent that uses the native GPT Live
protocol and delegates grammar questions to a Responses model. It uses the same
agent CRUD and azd deployment lifecycle as other Voice Agents, but clients connect
through `/protocols/voice/live/sessions` and exchange native Live events.

The Python client is based on the Microsoft `voice-agent` GPT Live sample. It only
connects to the agent deployed by azd; it does not create, update, or delete agents.

## How it works

```text
microphone or PCM WAV
  ↕ native Live audio/transcript events
Foundry kind: voice / subProtocol: live agent
  ↕ native Responses delegation lifecycle
Responses model deployment
```

The service owns `session.start`; the client waits for `session.started`. Spoken
output, backend guidance, and delegation lifecycle are separate event streams.
`SessionEvidence` correlates the same delegation ID with a completed, nonempty
backend response for deterministic WAV smoke checks.

## Prerequisites

1. Python 3.11 or later with PortAudio for microphone/speaker use. WAV smoke with
   `--no-playback` does not require audio hardware.
2. azd 1.37.0 or later. The manifest requires `azure.ai.agents`
   `>=1.0.0-beta.24`, the first expected release containing GPT Live manifest
   support. Released beta.23 does not contain this feature.
3. A Foundry project whose subscription has the Voice Agent and GPT Live preview
   gates enabled.
4. Existing compatible deployments named `gpt-live-1` and `gpt-5.6-terra`, or
   update both IDs in `azure.yaml` before the first deployment.
5. Permission to deploy/invoke Voice Agents and use both model deployments.

Set the process-only Voice preview flag in every shell that runs azd:

```powershell
$env:AZD_ALPHA_ENABLE_AGENTS_VOICE = "true"
```

Until beta.24 is published, reviewers can install a trusted development bundle
built from Azure/azure-dev#10685. Normal sample users should wait for the
released extension.

## Initialize and deploy with azd

Create an empty folder and initialize from this manifest:

```powershell
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/voice-agents/gpt-live/azure.yaml
```

Select an existing GPT Live-enabled Foundry project. This sample intentionally
does not change the existing interactive Prompt Voice init flow and does not
provision GPT Live models.

Deploy the agent:

```powershell
azd deploy
azd ai agent show gpt-live-response-delegation
```

The displayed callable endpoint ends with:

```text
/endpoint/protocols/voice/live/sessions?api-version=v1
```

`azd ai agent invoke` is not a native Live audio client. Use `client.py` or a
GPT Live-compatible Dashboard.

## Install and configure the client

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill in the deployed project endpoint, subscription ID, and agent name in `.env`.
Do not add API keys; authentication uses the signed-in Azure CLI identity.

Interactive microphone mode:

```powershell
.\.venv\Scripts\python.exe .\client.py
```

Press Ctrl+C to close cleanly. For repeatable smoke testing, provide an
uncompressed mono PCM16/24-kHz WAV:

```powershell
.\.venv\Scripts\python.exe .\client.py `
  --input-wav .\input.wav `
  --no-playback `
  --save-audio .\response.wav `
  --result-json .\result.json `
  --expect-backend goes
```

The WAV mode requires input/output transcripts, output audio, a correlated
completed delegation, and clean `session.closed`. It never retries silently.

## Test the sample

Run the same cumulative checks used by `sample.yaml`:

```powershell
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m compileall -q .
python -c "import openai.resources.live.live"
python -m ruff check .
python -m pytest -q
```

These are local build/protocol-unit checks. A live regression additionally needs
an approved gated project and the two model deployments.

## Limitations

- This is a preview, WebSocket-only native Live path. It does not support Avatar,
  WebRTC, telephony, Hosted Voice `conversationEngine`, or Voice Live STT/VAD and
  Azure voice-tuning fields.
- `store: false` keeps the sample focused on the live protocol. It does not claim
  Foundry conversation recording/readback.
- Model/region/SKU availability and feature gates vary.
- The client displays test transcripts and delegation guidance; do not log real
  sensitive conversations in production.

## Source alignment

The client flow is based on `microsoft/voice-agent` `samples/gpt_live` at commit
`a23df94e0400fc2f8d61f771c3757f455952e787`. Keep protocol changes aligned with
that sample and the GPT Live service contract.
