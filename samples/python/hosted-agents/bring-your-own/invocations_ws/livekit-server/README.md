# LiveKit voice agent (Azure STT + Azure OpenAI LLM + Azure TTS)

A [LiveKit Agents](https://docs.livekit.io/agents/) sample that runs a
voice agent powered by Azure Speech and Azure OpenAI. The
`invocations_ws` WebSocket is **signaling-only**, while audio media flows
browser ↔ LiveKit server ↔ agent over LiveKit's WebRTC stack.

```
    ┌────────────────────────────────────────────────────────────────┐
    │                                                                │
    │  browser ── /invocations_ws (signaling) ──►  server.py         │
    │     │                       ◄── {livekit_url, token, room} ──  │
    │     │                                                          │
    │     │ join(livekit_url, token)                                 │
    │     ▼                                                          │
    │  LiveKit server  ◄────────────  agent.py (Azure STT/LLM/TTS)   │
    │                                                                │
    └────────────────────────────────────────────────────────────────┘
```

## ⚠️ Security Warning

This sample is for demonstration purposes only and is not production-ready.

Key risks to address before production:

- **LiveKit API secret handling**: The LiveKit API key/secret must stay
  server-side — never embed it in client code or check it into source
  control. Use a secret store (Key Vault, environment variables injected
  by the platform) and rotate on compromise.
- **JWT scoping and lifetime**: Mint short-lived JWTs with the narrowest
  `VideoGrants` / `RoomAgentDispatch` grants the connecting client needs.
  Long-lived or over-scoped tokens can be replayed by unauthorized
  callers.
- **Endpoint and worker-name validation**: Validate the LiveKit endpoint
  URL and `LIVEKIT_AGENT_WORKER_NAME` per deployment to avoid worker
  collisions or impersonation across environments.
- **`/invocations_ws` is unauthenticated in this sample**: Production
  deployments should add auth (e.g., Foundry-issued bearer token,
  Entra-backed gateway) and rate limiting in front of the signaling
  WebSocket.
- **Customer responsibility**: You are responsible for securing your
  LiveKit infrastructure, token issuance, and authentication flows.

Failure to properly secure these components may result in credential
theft, service abuse, or data exposure.

## Files

| File | Purpose |
| --- | --- |
| `agent.py` | LiveKit Agents worker. Defines a small multi-agent workflow (`GreeterAgent` ⇄ `CheckOrderAgent`) using the [LiveKit handoff pattern](https://docs.livekit.io/agents/logic/agents-handoffs/) — each specialist has its own Azure TTS voice. Uses `livekit-plugins-azure` for STT and `livekit-plugins-openai` (Azure OpenAI variant) for the LLM. For TTS it uses the in-repo [`azure_tts_text_streaming.py`](src/livekit-server/azure_tts_text_streaming.py) plugin (Azure Speech `TextStream` over websocket v2) for token-level streaming, instead of the chunked SSML path in `livekit-plugins-azure`. Registers with `agent_name=foundry-azure-voice` for explicit dispatch so it never competes with other agents on the same LiveKit project. |
| `azure_tts_text_streaming.py` | LiveKit `tts.TTS` subclass that wraps the Azure Speech SDK's `SpeechSynthesisRequest(TextStream)` API. LLM tokens are written into a persistent `input_stream` as they arrive on the LiveKit `SynthesizeStream._input_ch`, and audio chunks stream back over a single websocket — noticeably lower TTFA than the stock SSML-per-utterance plugin. |
| `server.py` | FastAPI `/invocations_ws` signaling endpoint. Mints a JWT (with a `RoomAgentDispatch` targeting this worker) and hands the browser `{type: "config", livekit_url, token, room, identity}`. Also spawns `agent.py start` as a child process so one command boots everything. |
| `Dockerfile` | Container image for hosted deployment. Runs `server.py` from the frozen uv environment. |
| `azure.yaml` / `azure.yaml` | Foundry hosted-agent manifests. |
| `pyproject.toml` | Direct backend dependencies and Python requirement. |
| `uv.lock` | Fully resolved backend dependency graph. |
| `.env.example` | Copy to `.env` and fill in Azure + LiveKit credentials. |
| [`chat_client/`](src/livekit-server/chat_client/) | Browser portal — LiveKit signaling proxy. |

## Prerequisites

- A **LiveKit Cloud** project (https://cloud.livekit.io) — copy the
  WebSocket URL, API key, and secret. LiveKit is the media broker
  between browser and agent and is the only piece that has to run
  outside this sample.
- Azure Speech and Azure OpenAI resources.
- Python 3.12 or later.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.11.7 or later.

> Self-hosting LiveKit is also supported but requires TLS + TURN and a
> reachable UDP port; LiveKit Cloud is significantly simpler.

## Run locally

```bash
cd samples/python/hosted-agents/bring-your-own/invocations_ws/livekit-server
python -m pip install uv
cd src/livekit-server
uv sync --frozen

# 2) Configure
cp .env.example .env
# edit .env -> AZURE_*, LIVEKIT_URL/KEY/SECRET

# 3) Start the backend (signaling endpoint + agent worker in one process)
uv run --no-sync python server.py
```

Then start the chat-client portal:

```bash
cd samples/python/hosted-agents/bring-your-own/invocations_ws/livekit-server/src/livekit-server/chat_client
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# To use this LOCAL livekit-server instead of the hosted Foundry agent,
# uncomment in chat_client/.env:
#   LIVEKIT_LOCAL_URL=ws://localhost:8088/invocations_ws
python web_portal.py
```

Open <http://localhost:9529> in Chrome / Edge.

> `server.py` automatically launches `agent.py start` as a child
> process. To run the worker yourself (e.g. with `uv run --no-sync python agent.py dev`
> for live reload), set `RUN_AGENT_WORKER=0` before starting `server.py`.

## Default ports

| Process | Port |
| --- | --- |
| FastAPI signaling + agent worker (`server.py`) | 8088 |
| chat-client portal | 9529 |

## Configuration

`.env` keys:

| Key | Notes |
| --- | --- |
| `AZURE_SPEECH_API_KEY`, `AZURE_SPEECH_REGION` | Azure Speech resource for STT + TTS. |
| `AZURE_FOUNDRY_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_VERSION`, `AZURE_LLM_MODEL` | Azure OpenAI resource for the LLM. |
| `AZURE_TTS_VOICE_GREETER` | Optional. TTS voice for `GreeterAgent`. Defaults to `en-US-Ava:DragonHDLatestNeural`. |
| `AZURE_TTS_VOICE_CHECK_ORDER` | Optional. TTS voice for `CheckOrderAgent`. Defaults to `en-US-Andrew:DragonHDLatestNeural`. |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | LiveKit server the agent registers with and the browser joins. |
| `LIVEKIT_PUBLIC_URL` | Optional override of the URL handed to the *browser*. Falls back to `LIVEKIT_URL`. |
| `LIVEKIT_AGENT_WORKER_NAME` | Optional. Worker name used for explicit dispatch (must match between `agent.py` and `server.py`). Defaults to `foundry-azure-voice`. |
| `RUN_AGENT_WORKER` | Set to `0` to skip launching `agent.py` from `server.py` (e.g. when running it yourself with `uv run --no-sync python agent.py dev`). |

## Hosted deployment (Azure Foundry)

Same pattern as the sibling samples — `azd ai agent init` scaffolds a
project, `azd deploy` does an ACR remote build and registers the new
agent version with Foundry. The container runs `server.py` from the uv environment,
which boots both the signaling endpoint and the LiveKit agent worker.

### 1. Initialise an azd workspace

```bash
# Fresh folder for the azd project (anywhere outside this repo)
mkdir ~/azd-deploys/livekit-server && cd ~/azd-deploys/livekit-server

az account set --subscription <subscription-id>

azd ai agent init \
  -m <path-to-repo>/samples/python/hosted-agents/bring-your-own/invocations_ws/livekit-server/azure.yaml \
  -p "/subscriptions/<subscription-id>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/projects/<foundry-project>" \
  --no-prompt
```

`azd` downloads the sample into `src/livekit-server-azd/`, adopts its
`azure.yaml`, and seeds an env file under `.azure/<env-name>/.env`.

### 2. (Optional) reuse an existing ACR attached to your project

```bash
azd env set AZURE_CONTAINER_REGISTRY_NAME     <acr-name>
azd env set AZURE_CONTAINER_REGISTRY_ENDPOINT <acr-name>.azurecr.io
azd env set USE_EXISTING_CONTAINER_REGISTRY   true
azd env set CONTAINER_REGISTRY_RESOURCE_GROUP <acr-rg>
```

### 3. Set the runtime environment variables

`azure.yaml` resolves these from your azd environment so secrets stay out
of the image:

```bash
azd env set AZURE_SPEECH_API_KEY     <speech-key>
azd env set AZURE_SPEECH_REGION      eastus
azd env set AZURE_FOUNDRY_API_KEY    <aoai-key>
azd env set AZURE_OPENAI_ENDPOINT    https://<your-aoai>.openai.azure.com
azd env set AZURE_OPENAI_API_VERSION 2024-10-01-preview
azd env set AZURE_LLM_MODEL          gpt-4o-mini
azd env set LIVEKIT_URL              wss://<your-project>.livekit.cloud
azd env set LIVEKIT_API_KEY          <livekit-key>
azd env set LIVEKIT_API_SECRET       <livekit-secret>
```

### 4. Deploy

```bash
azd deploy livekit-server-azd
```

Stream logs while testing:

```bash
azd ai agent monitor livekit-server-azd --follow
```

> The local `.env` file is excluded from the Docker image via `.dockerignore`
> and is **only** used for local runs. For redeploys after code changes just
> re-run `azd deploy livekit-server-azd`; `azd ai agent init` is one-time
> per workspace.

### Concrete example

```bash
az account set --subscription <subscription-id>

mkdir -p ~/azd-deploys/livekit-server && cd ~/azd-deploys/livekit-server

azd ai agent init \
  -m <path-to-repo>/samples/python/hosted-agents/bring-your-own/invocations_ws/livekit-server/azure.yaml \
  -p "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/projects/<foundry-project>" \
  --no-prompt

azd env set AZURE_CONTAINER_REGISTRY_NAME     <acr-name>
azd env set AZURE_CONTAINER_REGISTRY_ENDPOINT <acr-name>.azurecr.io
azd env set USE_EXISTING_CONTAINER_REGISTRY   true
azd env set CONTAINER_REGISTRY_RESOURCE_GROUP <acr-resource-group>

# ...azd env set the AZURE_/LIVEKIT_ variables above...

azd deploy livekit-server-azd
```

## Resources

- [LiveKit Agents docs](https://docs.livekit.io/agents/)
- [LiveKit Azure STT plugin](https://docs.livekit.io/agents/models/stt/azure/)
- [LiveKit Azure TTS plugin](https://docs.livekit.io/agents/models/tts/azure/)
- [LiveKit Azure OpenAI LLM plugin](https://docs.livekit.io/agents/models/llm/azure-openai/)
- Inspiration: [`livekit-examples/agent-deployment#21`](https://github.com/livekit-examples/agent-deployment/pull/21) (Bedrock AgentCore deployment)
