<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# Voice Live Hello World (`invocations_ws`)

A minimal, single-file real-time voice agent. The container exposes
`/invocations_ws` using the
new [`azure-ai-agentserver-invocations`](https://pypi.org/project/azure-ai-agentserver-invocations/)
**1.0.0b4** SDK (`@app.ws_handler`). Each browser WebSocket connection is
bridged to a fresh **Azure Voice Live** session — Voice Live handles STT,
LLM, and TTS in one managed service, so this sample's only job is to
shuttle audio bytes and control events.

> This sample is intentionally tiny: ~250 lines of Python, no audio
> pipeline framework, no resampling, no per-agent voice plumbing —
> Voice Live owns the STT/LLM/TTS pipeline.

## Architecture

```
┌─────────────────────────┐  PCM16 24kHz binary + JSON  ┌──────────────────────────────────┐
│ Browser                 │ ◄─────────────────────────► │ This sample (main.py)            │
│ chat_client/index.html  │                             │ azure-ai-agentserver-invocations │
└─────────────────────────┘                             │ @app.ws_handler                  │
                                                        └──────────────┬───────────────────┘
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
| [main.py](src/hello-world/main.py) | The whole agent — `@app.ws_handler` opens a Voice Live session and runs two pumps. |
| [azure.yaml](azure.yaml) | Hosted-agent runtime config (`invocations_ws`, 1 CPU / 2 Gi). |
| [azure.yaml](azure.yaml) | `azd ai agent init` manifest. |
| [Dockerfile](src/hello-world/Dockerfile) | Builds a frozen uv environment on `python:3.12-slim`. |
| [pyproject.toml](src/hello-world/pyproject.toml) | Runtime dependencies and the local-only `websockets` development group. |
| [uv.lock](src/hello-world/uv.lock) | Fully resolved runtime and development dependency graph. |
| [.env.example](src/hello-world/.env.example) | Required Voice Live env vars. |
| [e2e_local.py](src/hello-world/e2e_local.py) | Headless E2E that streams a 1 kHz tone in and asserts audio + events come back. Supports `--foundry`/`--agent` to run against a deployed hosted agent. |
| [chat_client/index.html](src/hello-world/chat_client/index.html) | Standalone browser client (mic + transcript). |
| [chat_client/proxy.py](src/hello-world/chat_client/proxy.py) | Local proxy that serves `index.html` and injects an `Authorization: Bearer` header onto the upstream WebSocket — used to talk to a deployed Foundry agent from the browser. |

## Prerequisites

1. Python 3.12 or later.
2. [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.11.7 or later.
3. Azure CLI logged in (`az login`).
4. An Azure AI Services / Voice Live resource and access to a realtime model (e.g. `gpt-realtime`).
5. The `Foundry User` role on that resource at **account scope** —
   for your user when running locally, and for the hosted agent's
   managed identity post-deploy (see [Deploying to Microsoft Foundry](#deploying-to-microsoft-foundry)).

## Running locally

```bash
cd samples/python/hosted-agents/bring-your-own/invocations_ws/hello-world
python -m pip install uv
cd src/hello-world
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
cd samples/python/hosted-agents/bring-your-own/invocations_ws/hello-world/src/hello-world
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

The sample ships a tiny single-file browser client in [`chat_client/index.html`](src/hello-world/chat_client/index.html)
plus a small Python proxy in [`chat_client/proxy.py`](src/hello-world/chat_client/proxy.py).

**Against the locally-running agent** (no auth needed) — just serve the folder:

```bash
cd samples/python/hosted-agents/bring-your-own/invocations_ws/hello-world/src/hello-world/chat_client
python -m http.server 8080
```

Open <http://localhost:8080/>, click **▶ Start**, allow mic access, and
speak. The default WebSocket URL is `ws://localhost:8088/invocations_ws`.

**Against a deployed Foundry agent** — browsers can't set the
`Authorization: Bearer` header that the Foundry data-plane WebSocket
requires, so use the bundled proxy, which serves `index.html` *and*
bridges the upstream WS with the token injected:

```bash
cd samples/python/hosted-agents/bring-your-own/invocations_ws/hello-world/src/hello-world
uv run --no-sync python chat_client/proxy.py \
  --foundry "https://<account>.services.ai.azure.com/api/projects/<project>" \
  --agent hello-world
```

Open <http://localhost:8765/>, click **▶ Start**, and speak. The page's
default WS URL is auto-set to the proxy (`ws://localhost:8765/invocations_ws`),
and the proxy upgrades each connection to the Foundry endpoint with a
fresh `az account get-access-token` token.

## Deploying to Microsoft Foundry

```bash
mkdir ~/azd-deploys/hello-world && cd ~/azd-deploys/hello-world

azd ai agent init \
  -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/invocations_ws/hello-world/azure.yaml \
  -p "<foundry-project-resource-id-or-url>" \
  --no-prompt

# Set the Voice Live endpoint + model for the deployed container.
azd env set AZURE_VOICELIVE_MODEL    "gpt-realtime-1.5"
azd env set AZURE_VOICELIVE_VOICE    "en-US-Ava:DragonHDLatestNeural"

azd provision
azd deploy hello-world
```

The deployed container's managed identity needs the **Foundry User**
role on the **AI Services account** (account scope, not project
scope) — Voice Live's realtime API is exposed at the account host
(`https://<account>.services.ai.azure.com/`), so an assignment scoped
only to the project will return 403 and the upstream WebSocket will
close immediately after the client connects.

Grab the principal id from the deployed agent (the GET returns an
`instance_identity.principal_id`) and assign the role at the account
scope:

```bash
# Get the agent's managed-identity principal id (set <project-endpoint>
# and <agent-name> for your deployment).
TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
PID=$(curl -sS -H "Authorization: Bearer $TOKEN" \
  "<project-endpoint>/agents/<agent-name>?api-version=2025-11-15-preview" \
  | python -c "import json,sys; print(json.load(sys.stdin)['instance_identity']['principal_id'])")

# Assign Foundry User at the AI Services *account* scope (not the project scope).
az role assignment create \
  --assignee-object-id "$PID" \
  --assignee-principal-type ServicePrincipal \
  --role "Foundry User" \
  --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>"
```

RBAC propagation can take a few minutes (typically up to ~5); the
first connections after the assignment may still 403 until it lands.

### Hosted WebSocket URL

Once deployed, browsers and the bundled CLI connect to the **Foundry
data-plane** WebSocket URL (`e2e_local.py` builds this for you from
`--foundry` + `--agent`):

```
wss://<account>.services.ai.azure.com/api/projects/<project>/agents/<agent>/endpoint/protocols/invocations_ws
    ?api-version=v1
    &agent_session_id=<unique-session-id>
```

Where the segments come from:

| Part | Value |
|------|-------|
| `<account>` | AI Services account host — the same host as your Foundry project endpoint (`https://<account>.services.ai.azure.com/api/projects/<project>`). |
| `/api/projects/<project>/agents/<agent>/endpoint/protocols/invocations_ws` | Data-plane route; project and agent are URL-encoded path segments. |
| `api-version=v1` | Foundry data-plane API version. |
| `<project>` | The last segment of your project endpoint path. |
| `<agent>` | Matches the agent `name` in [`azure.yaml`](azure.yaml) — `hello-world`. |
| `agent_session_id=<unique-session-id>` | A caller-generated string that identifies the conversation. Reuse the same id to resume; use a fresh one (e.g. a UUID) to start a new session. |

Every request must also include `Authorization: Bearer <Entra token>`
for the `https://ai.azure.com` resource. Browsers can't set headers on
a `WebSocket`, which is why the [`e2e_local.py`](src/hello-world/e2e_local.py) CLI
fetches a token with `az account get-access-token` and sends it in the
upgrade handshake.

Then test the hosted agent end-to-end with the bundled CLI (which sends
the required `Authorization: Bearer <token>` header — browsers cannot do
this on a WebSocket, so the standalone `chat_client/index.html` is for
local dev only):

```bash
cd src/hello-world
uv run --no-sync python e2e_local.py \
  --foundry "https://<account>.services.ai.azure.com/api/projects/<project>" \
  --agent hello-world
```

## Troubleshooting

* **`AZURE_VOICELIVE_ENDPOINT is not set`** — set it to your AI Services
  account URL (no `/api/projects/...` path needed; if you paste a project
  URL the path is stripped automatically).
* **Auth fails locally** — make sure `az login` succeeded for the same
  tenant that owns the Voice Live resource and that you have
  `Foundry User` at **account scope** on the AI Services account.
* **Deployed agent's WebSocket closes immediately after the client
  connects** — the agent's managed identity is missing `Foundry User`
  at the AI Services account scope (a project-scope assignment is not
  enough). See [Deploying to Microsoft Foundry](#deploying-to-microsoft-foundry)
  for the exact `az role assignment create` command.
* **No audio comes back** — Voice Live waits for `speech_stopped` from
  its server VAD before generating; make sure you stop sending audio (or
  send silence) for at least the configured `silence_duration_ms`
  (500 ms by default).
* **ARM64 Docker images don't run in Foundry** — build with
  `docker build --platform=linux/amd64 .` or, preferred, use `azd deploy`
  which uses ACR remote build.
