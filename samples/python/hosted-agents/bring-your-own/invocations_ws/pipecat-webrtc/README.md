<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# What this sample demonstrates

A real-time voice agent hosted as a **Bring Your Own** WebSocket container that uses **WebRTC for audio media**. It runs the same Zava multi-agent pipeline as the sibling [`pipecat-ws-server`](../pipecat-ws-server/) sample (one main transport-owning agent plus a `greeter` and a `check_order` LLM sub-agent built with [pipecat-ai-subagents](https://pypi.org/project/pipecat-ai-subagents/)), but swaps the WebSocket audio transport for pipecat's [`SmallWebRTCTransport`](https://docs.pipecat.ai/api-reference/server/services/transport/small-webrtc):

- **Azure Fast Transcription** for streaming STT
- **Azure OpenAI** (LLM) for the two specialised sub-agents
- **Azure TTS** with text streaming for low-latency speech output
- **WebRTC** (via [`aiortc`](https://github.com/aiortc/aiortc)) for browser ⇄ bot media, with **STUN bundled and TURN credentials supplied via env vars**

Why a single `/invocations_ws` endpoint? This sample lives under the `bring-your-own/invocations_ws/` tree, where the Foundry contract is "one duplex WebSocket called `invocations_ws`". We keep that surface here but use the WebSocket purely for **WebRTC signaling** (offer / answer / ICE candidates / ICE config). Audio still flows over the WebRTC peer connection and never touches the signaling WebSocket.

The browser client lives in [`chat_client/`](src/pipecat-ws-webrtc/chat_client/) — a small FastAPI portal that terminates the browser's WebSocket, attaches the Entra token as the `Authorization` header in hosted mode, and forwards signaling JSON to the upstream `/invocations_ws`. The same proxy works against either a local server or the Foundry-hosted agent.

## ⚠️ Security Warning

This sample is for demonstration purposes only and is not production-ready.

Key risks to address before production:

- **Credential leakage**: Do not embed TURN or signaling credentials in client-side code.
  Use short-lived (ephemeral) credentials with proper rotation and scoping.
- **TURN server abuse**: Exposed or long-lived credentials may be reused by unauthorized users, leading to unexpected cost and traffic.
- **Customer responsibility**: You are responsible for securing your TURN/STUN infrastructure, key exchange, and authentication flows.

Failure to properly secure these components may result in credential theft, service abuse, or data exposure.

## Architecture

```
                ┌─────────────────────────────────────────────┐
                │  Browser (chat_client/static/...)        │
                │  - RTCPeerConnection                        │
                │  - <audio> playback                         │
                └─────────┬─────────────────────────┬─────────┘
                          │                         │
       /ws/connect        │                         │  WebRTC media
       (signaling JSON)   │                         │  (RTP audio +
                          ▼                         │   data channel)
                ┌──────────────────────┐            │
                │ chat_client/      │            │
                │   web_portal.py      │            │
                │  - JSON pass-through │            │
                │  - Entra token in    │            │
                │    hosted mode       │            │
                └─────────┬────────────┘            │
                          │                         │
        /invocations_ws   │                         │
        (signaling JSON)  ▼                         ▼
                ┌─────────────────────────────────────────────┐
                │  server.py + bot_webrtc_server.py           │
                │  - SmallWebRTCConnection (signaling)        │
                │  - SmallWebRTCTransport (RTP)               │
                │  - pipecat: STT → SubAgents(LLM+TTS)        │
                │  - STUN bundled; TURN via WEBRTC_TURN_*     │
                └─────────────────────────────────────────────┘
```

## Layout

| Path                          | What it does                                                   |
| ----------------------------- | -------------------------------------------------------------- |
| `server.py`                   | FastAPI app — exposes `/invocations_ws` for WebRTC signaling   |
| `bot_webrtc_server.py`        | The pipecat bot — `SmallWebRTCTransport` + sub-agents          |
| `bot_websocket_server.py`     | Bundled copy of the sibling sample's agent classes             |
| `azure_*.py`                  | Bundled copies of the Azure STT / TTS helper services          |
| `Dockerfile`                  | Container image for Foundry deployment (`linux/amd64`, port 8088) |
| `azure.yaml`         | Foundry hosted-agent manifest                                  |
| `azure.yaml`                  | Foundry hosted-agent definition (kind / protocols / resources) |
| `pyproject.toml`              | Direct bot dependencies and Python requirement                 |
| `uv.lock`                     | Fully resolved bot dependency graph                            |
| `.env.example`                | Required Azure Speech / Foundry env vars for the bot           |
| [`chat_client/`](src/pipecat-ws-webrtc/chat_client/) | Browser portal — pipecat WebRTC signaling proxy |

The agent classes (`GreeterAgent`, `CheckOrderAgent`) and helper services (`AzureFastTranscriptionSTTService`, `AzureTTSTextStreamingService`) are bundled here as copies of the files under [`../pipecat-ws-server/`](../pipecat-ws-server/), so the container build context is self-contained.

## Signaling protocol

Each frame is a single JSON object on the WebSocket. Replies arrive in FIFO order — exactly one reply per request.

| client → server                                                                  | server → client                                                  |
| -------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `{ "action": "ice_config" }`                                                     | `{ "iceServers": [...] }`                                        |
| `{ "action": "offer", "data": {"sdp": "...", "type": "offer"} }`                 | `{ "answer": {"sdp": "...", "type": "answer", "pc_id": "..."} }` |
| `{ "action": "ice_candidate", "data": { candidate, sdp_mid, sdp_mline_index } }` | `{ "status": "ok" }`                                             |
| `{ "action": "disconnect" }`                                                     | (server tears down peer connection and closes the WebSocket)     |

The server may also push `{ "type": "closed" }` if the peer connection is torn down on its side. The shared `web_portal.py` is a transparent JSON pass-through — the contract above is the same on both sides of the proxy.

## Prerequisites

1. **Python 3.12 or later** — `python --version`
2. **uv 0.11.7 or later** — [Install uv](https://docs.astral.sh/uv/getting-started/installation/)
3. **Azure CLI** — installed and authenticated: `az login`
4. **Azure Developer CLI (`azd`)** (only needed for the deploy step) — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) (1.34.2 or later) and the unified Foundry CLI extension: `azd ext install microsoft.foundry`
5. **Azure resources**:
   - Azure Speech (any region) — for STT and TTS
   - Azure OpenAI deployment (e.g. `gpt-4o-mini`) — for the LLM agents
   - A STUN/TURN provider for production deployments (e.g. Azure Communication Services relay token, Twilio NTS, Cloudflare TURN, or self-hosted coturn)

## Environment Variables

### Server ([`pipecat-webrtc/.env`](src/pipecat-ws-webrtc/.env.example))

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_SPEECH_API_KEY` | Yes | Key for Azure Speech (STT + TTS). |
| `AZURE_SPEECH_REGION` | Yes | Region (e.g. `eastus`). The fast-transcription endpoint is built as `https://{region}.api.cognitive.microsoft.com/`. |
| `AZURE_FOUNDRY_API_KEY` | Yes | Key for the Azure OpenAI / Foundry endpoint used by the LLM. |
| `AZURE_OPENAI_ENDPOINT` | Yes | Azure OpenAI endpoint (e.g. `https://your-aoai.openai.azure.com`). |
| `AZURE_LLM_MODEL` | Yes | Model deployment name (e.g. `gpt-4o-mini`). |
| `WEBRTC_TURN_URL` | Recommended | TURN server URL (e.g. `turn:relay.communication.microsoft.com:3478`). **Required for containerized deployments** (ACA, etc.) — without it the server uses STUN-only, which won't traverse symmetric NAT or work where inbound UDP isn't available. A public STUN server (`stun:stun.l.google.com:19302`) is always added automatically. |
| `WEBRTC_TURN_STUN_URL` | Optional | The TURN provider's own STUN endpoint (e.g. `stun:relay.communication.microsoft.com:3478`), advertised alongside the relay so the browser can discover srflx candidates through the same host. |
| `WEBRTC_TURN_USERNAME` | Required if `WEBRTC_TURN_URL` is set | TURN username. |
| `WEBRTC_TURN_CREDENTIAL` | Required if `WEBRTC_TURN_URL` is set | TURN credential (password). |
| `SERVER_HOST` | No | Bind address (default `0.0.0.0`). |
| `SERVER_PORT` | No | Bind port (default `8089` locally; the container `Dockerfile` overrides this to `8088` for Foundry). |

```bash
cp .env.example .env
# Edit .env with your values
```

### Client ([`chat_client/.env`](src/pipecat-ws-webrtc/chat_client/.env.example))

The shared portal under [`chat_client/`](src/pipecat-ws-webrtc/chat_client/) handles the
browser. Configure it to point at either a local `server.py` or the
Foundry-hosted agent.

| Variable | Mode | Description |
|----------|------|-------------|
| `PIPECAT_WEBRTC_LOCAL_URL` | Local | Set to `ws://localhost:8089/invocations_ws` to talk to a server you started locally. When set, the agent name is ignored. |
| `PROJECT_ENDPOINT` | Foundry | Public Foundry project endpoint, `https://{account}.services.ai.azure.com/api/projects/{project}`. |
| `PIPECAT_WEBRTC_AGENT_NAME` | Foundry | Hosted agent name (e.g. `pipecat-ws-webrtc`). |
| `API_VERSION` | Foundry, optional | Service API version. Defaults to `v1`. |
| `PORTAL_PORT` | Both, optional | Override for the portal's listening port (default `9528`). |

The portal builds the upstream URL as:

```
wss://{account}.services.ai.azure.com
   /api/projects/{project}/agents/{PIPECAT_WEBRTC_AGENT_NAME}/endpoint/protocols/invocations_ws
   ?api-version={API_VERSION}
   &agent_session_id={generated-per-connection}
```

and injects an `Authorization: Bearer <token>` header from
`az account get-access-token --resource https://ai.azure.com`.

Example for the reference deployment:

```bash
PROJECT_ENDPOINT=https://{account}.services.ai.azure.com/api/projects/{project}
PIPECAT_WEBRTC_AGENT_NAME=pipecat-ws-webrtc
# PIPECAT_WEBRTC_LOCAL_URL=ws://localhost:8089/invocations_ws
```

```bash
cd samples/python/hosted-agents/bring-your-own/invocations_ws/pipecat-webrtc/src/pipecat-ws-webrtc/chat_client
cp .env.example .env
# Edit .env with your values
```

---

## Running Locally

You can run the server and client in two terminals.

### 1. Start the server

```bash
cd samples/python/hosted-agents/bring-your-own/invocations_ws/pipecat-webrtc
python -m pip install uv
cd src/pipecat-ws-webrtc
uv sync --frozen

# Make sure .env is filled in (see "Server" table above)
uv run --no-sync python server.py
```

The server logs `Uvicorn running on http://0.0.0.0:8089` and exposes:

- `GET /health`, `/readiness`, `/liveness` — health probes
- `WS  /invocations_ws` — the WebRTC signaling endpoint

> [!NOTE]
> First-launch is slow (~10 s) because pipecat initialises Silero VAD and the smart-turn analyzer.

### 2. Start the shared web portal

In a second terminal:

```bash
cd samples/python/hosted-agents/bring-your-own/invocations_ws/pipecat-webrtc/src/pipecat-ws-webrtc/chat_client
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Local mode — point at the server you just started
echo 'PIPECAT_WEBRTC_LOCAL_URL=ws://localhost:8089/invocations_ws' >> .env

python web_portal.py             # listens on :9528 (open http://localhost:9528)
```

Open <http://localhost:9528> in Chrome (Edge / Firefox also work). Click **▶ Start**, allow microphone
access, and start speaking. The bot greeter opens the conversation; the log
panel shows live transcripts, bot responses, turn boundaries, and TTFA
latency.

You can also type into the text bar — the proxy forwards `send-text` RTVI frames over the WebRTC data channel so the bot replies without needing a voice turn.

> [!TIP]
> WebRTC requires a secure context for microphone access. `http://localhost` counts as a secure context, so local testing works as-is. For LAN testing, terminate TLS in front of the portal (e.g. with `caddy`, `mkcert`, or `ngrok`).

---

## Deploying the Agent to Microsoft Foundry

The recommended path is `azd`, which uses ACR remote build (so Apple Silicon machines work) and registers the hosted agent in Foundry in one step.

### 1. Initialise an azd workspace

```bash
# Create a fresh folder for the azd project
mkdir ~/azd-deploys/pipecat-ws-webrtc && cd ~/azd-deploys/pipecat-ws-webrtc

# Point azd at the azure.yaml that ships with the sample
azd ai agent init \
  -m <path-to-repo>/samples/python/hosted-agents/bring-your-own/invocations_ws/pipecat-webrtc/azure.yaml \
  -p "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/projects/<foundry-project>" \
  --no-prompt
```

`azd` downloads the sample into `src/pipecat-ws-webrtc/`, adopts its `azure.yaml`, and seeds an env file under `.azure/<env-name>/.env`.

> [!NOTE]
> Omit `-p` to let `azd provision` create a new Foundry project for you.

### 2. (Optional) reuse an existing Azure Container Registry

If your Foundry project already has an ACR attached, point `azd` at it instead of provisioning a new one:

```bash
azd env set AZURE_CONTAINER_REGISTRY_NAME     <acr-name>
azd env set AZURE_CONTAINER_REGISTRY_ENDPOINT <acr-name>.azurecr.io
azd env set USE_EXISTING_CONTAINER_REGISTRY   true
azd env set CONTAINER_REGISTRY_RESOURCE_GROUP <acr-rg>
```

### 3. Bump the container resources (optional)

The default scaffold uses `0.25` CPU / `0.5Gi`, which is too small for pipecat. Edit `azure.yaml` to:

```yaml
resources:
  cpu: "2"
  memory: 4Gi
```

### 4. Set the runtime environment variables

`azure.yaml` declares the env vars the hosted container needs and resolves them from your azd environment at deploy time, so secrets stay out of the image. Set them once with `azd env set`:

```bash
azd env set AZURE_SPEECH_API_KEY      <speech-key>
azd env set AZURE_SPEECH_REGION       eastus
azd env set AZURE_FOUNDRY_API_KEY     <aoai-key>
azd env set AZURE_OPENAI_ENDPOINT     https://<your-aoai>.openai.azure.com
azd env set AZURE_LLM_MODEL           gpt-4o-mini
azd env set WEBRTC_TURN_URL           turn:your-turn.example.com:3478
azd env set WEBRTC_TURN_STUN_URL      stun:your-turn.example.com:3478
azd env set WEBRTC_TURN_USERNAME      <username>
azd env set WEBRTC_TURN_CREDENTIAL    <credential>
```

> The local `.env` file is excluded from the Docker image via `.dockerignore` and is **only** used for local runs. For the hosted agent, values must come from the azd environment (or be edited directly into `azure.yaml` under `environment_variables`).

### 5. Deploy

```bash
azd deploy pipecat-ws-webrtc
```

`azd` performs an ACR remote build, pushes the image, and registers the new agent version in Foundry. On success it prints an Agent playground URL.

To stream logs from the running container:

```bash
azd ai agent monitor pipecat-ws-webrtc --follow
```

---

## Connecting the Client to the Hosted Agent

Once the agent is `Running` in Foundry, point the shared web portal at it.

1. Find your **project endpoint** in the Foundry portal under **Project → Overview → Endpoint** (or copy it from your project URL). It must be in the form:

   ```
   https://{account}.services.ai.azure.com/api/projects/{project}
   ```

2. Update `src/pipecat-ws-webrtc/chat_client/.env`:

   ```bash
   # Comment out the local-mode override
   # PIPECAT_WEBRTC_LOCAL_URL=ws://localhost:8089/invocations_ws

   PROJECT_ENDPOINT=https://{account}.services.ai.azure.com/api/projects/{project}
   PIPECAT_WEBRTC_AGENT_NAME=pipecat-ws-webrtc
   # API_VERSION=v1   # optional, defaults to v1
   ```

3. Make sure your shell is logged in with `az login` — the proxy fetches an access token via `az account get-access-token --resource https://ai.azure.com` on each new browser session.

4. Restart the portal and reload <http://localhost:9528>:

   ```bash
   cd samples/python/hosted-agents/bring-your-own/invocations_ws/pipecat-webrtc/src/pipecat-ws-webrtc/chat_client
   python web_portal.py
   ```

The portal log shows the upstream `agent_session_id` it generated; that ID is also useful when fetching server logs:

```bash
azd ai agent monitor pipecat-ws-webrtc --session-id <session-id> --follow
```
