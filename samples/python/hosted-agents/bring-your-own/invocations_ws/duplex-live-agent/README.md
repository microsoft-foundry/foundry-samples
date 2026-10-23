<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# Duplex Live Agent (`invocations_ws`)

A sample for building real-time voice agents that maintain two parallel tracks simultaneously:

* Foreground router: Low-latency voice conversation (always responsive, never "freezes")
* Background workers: Autonomous task execution (research, analysis, multi-step operations)
  - A sample agent using Microsoft Agent Framework to do handoff between multiple sub-agents.
  - A sample Copilot agent to do long running work.


## Architecture

```
┌─────────────────────────┐  PCM16 24kHz binary + JSON  ┌──────────────────────────────────┐
│ Browser                 │ ◄─────────────────────────► │ This sample (main.py)            │
│ chat_client/index.html  │                             │ azure-ai-agentserver-invocations │
└─────────────────────────┘                             │ @app.ws_handler                  │
                                                        └──────────────┬───────────────────┘
                                                                       │
                                                                       ▼
                                                        ┌──────────────────────────────┐
                                                        │ DuplexLiveAgent              │
                                                        │ two-track orchestration      │
                                                        └──────────────┬───────────────┘
                                                                       │
                                      ┌────────────────────────────────┴────────────────────────────────┐
                                      │                                                                 │
                                      ▼                                                                 ▼
                         ┌──────────────────────────┐                                      ┌──────────────────────────┐
                         │ Router agent             │                                      │ Worker agents            │
                         │ RealtimeRouter           │                                      │ TaskManager queue        │
                         │                          │                                      │                          │
                         │ • Low-latency voice I/O  │  start_task / status injections      │ • CopilotAgent           │
                         │ • Handles interruptions  │ ◄──────────────────────────────────► │ • HandoffAgent           │
                         │ • Routes long tasks      │                                      │ • Future workers         │
                         └────────────┬─────────────┘                                      └──────────────────────────┘
                                      │ azure-ai-voicelive
                                      ▼
                         ┌──────────────────────────┐
                         │ Azure Voice Live service │
                         └──────────────────────────┘
```

## Wire protocol with the browser

| Direction | Frame type | Payload |
|---|---|---|
| Browser → Server | binary | Raw PCM16, **24 kHz mono** mic chunks (matches Voice Live's native rate — no resampling) |
| Browser → Server | text JSON | `{"type":"text","content":"..."}` — sent as a Voice Live user text item + `response.create` |
| Server → Browser | binary | 8-byte LE header `(sample_rate u32, num_channels u32)` + PCM16 audio (assistant speech) |
| Server → Browser | text JSON | `session_started`, `user_speech_started`/`stopped`, `transcription`, `bot_text`, `response_done`, `error` |

## Files

| File | Purpose |
|------|---------|
| [main.py](src/duplex-live-agent/main.py) | The whole agent — `@app.ws_handler` opens a Voice Live session and runs two pumps. |
| [azure.yaml](azure.yaml) | Hosted-agent runtime config (`invocations_ws`, 1 CPU / 1 Gi). |
| [azure.yaml](azure.yaml) | `azd ai agent init` manifest. |
| [Dockerfile](src/duplex-live-agent/Dockerfile) | Builds a frozen uv environment on `python:3.12-slim`. |
| [pyproject.toml](src/duplex-live-agent/pyproject.toml) | Runtime dependencies and the local-only `websockets` development group. |
| [uv.lock](src/duplex-live-agent/uv.lock) | Fully resolved runtime and development dependency graph. |
| [.env.example](src/duplex-live-agent/.env.example) | Required Voice Live env vars. |
| [e2e_local.py](src/duplex-live-agent/e2e_local.py) | Headless E2E that streams a 1 kHz tone in and asserts audio + events come back. |

## Prerequisites

1. Python 3.12 or later.
2. [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.11.7 or later.
3. Azure CLI logged in (`az login`).
4. An Azure AI Services / Voice Live resource and access to a realtime model (e.g. `gpt-realtime`).
5. The `Foundry User` role on that resource for your user (or the hosted agent's managed identity, post-deploy).

## Running locally

```bash
cd samples/python/hosted-agents/bring-your-own/invocations_ws/duplex-live-agent
python -m pip install uv
cd src/duplex-live-agent
uv sync --frozen

cp .env.example .env
# Fill in AZURE_VOICELIVE_ENDPOINT and AZURE_VOICELIVE_MODEL.
export $(grep -v '^#' .env | xargs)

uv run --no-sync python main.py
# → Uvicorn running on http://0.0.0.0:8088
```

### Headless E2E test

In a second terminal:

```bash
cd samples/python/hosted-agents/bring-your-own/invocations_ws/duplex-live-agent/src/duplex-live-agent
uv run --no-sync python e2e_local.py
# [e2e] session_started:   True
# [e2e] audio_bytes recvd: 230400
# [e2e] result:            PASS
```

The test sends a single JSON text message
(`{"type": "text", "content": "Say hello in one short sentence."}`),
which the agent forwards to Voice Live as a user turn + `response.create`,
and asserts that `session_started`, at least one PCM audio frame, and
`response_done` come back. It does not require a microphone or a real
spoken utterance — server-VAD is bypassed entirely.

### Browser test (standalone client)

The sample ships a tiny single-file browser client in [`chat_client/`](src/duplex-live-agent/chat_client/index.html).
With the agent running on `:8088`, just serve the folder:

```bash
cd samples/python/hosted-agents/bring-your-own/invocations_ws/duplex-live-agent/src/duplex-live-agent/chat_client
python -m http.server 8080
```

Open <http://localhost:8080/>, click **▶ Start**, allow mic access, and
speak. The default WebSocket URL is `ws://localhost:8088/invocations_ws`.

## Deploying to Microsoft Foundry

### Init the project

```bash
mkdir ~/azd-deploys/duplex-live-agent && cd ~/azd-deploys/duplex-live-agent

azd ai agent init \
  -m <repo>/samples/python/hosted-agents/bring-your-own/invocations_ws/duplex-live-agent/azure.yaml \
  -p "<foundry-project-resource-id-or-url>" \
  --no-prompt

```

### Set up the environment variables

```bash

# Set the Voice Live endpoint + model for the deployed container.
azd env set AZURE_VOICELIVE_MODEL    "gpt-realtime-1.5"
azd env set AZURE_VOICELIVE_VOICE    "en-US-Ava:DragonHDLatestNeural"

azd env set AZURE_TASK_MODEL  "gpt-5.4-mini"
```

If you want to enable the Copilot agent, also need set the `GITHUB_TOKEN` env var before deploying:

```bash
azd env set GITHUB_TOKEN "<your-github-token>"
```

### Deploy to Foundry

```bash
azd deploy
```

The deployed container's managed identity needs the **Foundry User**
role on your Voice Live resource — assign it once via the Azure
portal or:

```bash
az role assignment create \
  --assignee <agent-managed-identity-principal-id> \
  --role "Foundry User" \
  --scope <voice-live-resource-id>
```

Then test the hosted agent end-to-end with the bundled CLI (which sends
the required `Authorization: Bearer <token>` header — browsers cannot do
this on a WebSocket, so the standalone `chat_client/index.html` is for
local dev only):

```bash
cd src/duplex-live-agent
uv run --no-sync python e2e_local.py \
  --foundry "https://<account>.services.ai.azure.com/api/projects/<project>" \
  --agent duplex-live-agent
```

## Troubleshooting

* **`AZURE_VOICELIVE_ENDPOINT is not set`** — set it to your AI Services
  account URL (no `/api/projects/...` path needed; if you paste a project
  URL the path is stripped automatically).
* **Auth fails locally** — make sure `az login` succeeded for the same
  tenant that owns the Voice Live resource and that you have
  `Foundry User`.
* **No audio comes back** — Voice Live waits for `speech_stopped` from
  its server VAD before generating; make sure you stop sending audio (or
  send silence) for at least the configured `silence_duration_ms`
  (500 ms by default).
* **ARM64 Docker images don't run in Foundry** — build with
  `docker build --platform=linux/amd64 .` or, preferred, use `azd deploy`
  which uses ACR remote build.
