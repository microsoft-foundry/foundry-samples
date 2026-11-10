<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# Voice Live Hello World (`invocations_ws`, C#)

A minimal real-time voice agent in C#. The hosted container exposes
`/invocations_ws` using the [`Azure.AI.AgentServer.Invocations`](https://www.nuget.org/packages/Azure.AI.AgentServer.Invocations/)
SDK (`InvocationWebSocketHandler`). Each browser WebSocket connection is
bridged to a fresh **Azure Voice Live** session — Voice Live handles STT,
LLM, and TTS in one managed service, so this sample's only job is to
shuttle audio bytes and control events.

> This sample is intentionally tiny: no audio pipeline framework, no
> resampling, no per-agent voice plumbing — Voice Live owns the
> STT/LLM/TTS pipeline.

## Architecture

```
┌─────────────────────────┐  PCM16 24kHz binary + JSON  ┌──────────────────────────────────┐
│ Browser                 │ ◄─────────────────────────► │ This sample (Program.cs)         │
│ chat_client/index.html  │                             │ Azure.AI.AgentServer.Invocations │
└─────────────────────────┘                             │ InvocationWebSocketHandler       │
                                                        └──────────────┬───────────────────┘
                                                                       │ Azure.AI.VoiceLive
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
| [Program.cs](src/hello-world-dotnet-invocations-ws/Program.cs) | The whole agent — `VoiceLiveHandler` opens a Voice Live session and runs two pumps. |
| [HelloWorld.csproj](src/hello-world-dotnet-invocations-ws/HelloWorld.csproj) | .NET 10 web project; references the Invocations + Voice Live + Identity SDKs. |
| [azure.yaml](azure.yaml) | Hosted-agent runtime config (`invocations_ws`, 1 CPU / 2 Gi). |
| [azure.yaml](azure.yaml) | `azd ai agent init` manifest. |
| [Dockerfile](src/hello-world-dotnet-invocations-ws/Dockerfile) | `mcr.microsoft.com/dotnet/sdk:10.0-alpine` build → `aspnet:10.0-alpine` runtime. |
| [.env.example](src/hello-world-dotnet-invocations-ws/.env.example) | Required Voice Live env vars. |
| [chat_client/index.html](chat_client/index.html) | Standalone browser client (mic + transcript) for local dev. |
| [chat_client/Proxy](chat_client/Proxy/Program.cs) | ASP.NET Core proxy that serves `index.html` and injects an `Authorization: Bearer` header onto the upstream WebSocket — used to talk to a deployed Foundry agent from the browser. |
| [E2ELocal](E2ELocal/Program.cs) | Headless console test that sends a text turn and asserts audio + events come back. |

## Prerequisites

Voice support remains preview in the GA extension. Before running `azd`, set
`AZD_ALPHA_ENABLE_AGENTS_VOICE=true` in that shell (`export AZD_ALPHA_ENABLE_AGENTS_VOICE=true`
in Bash or `$env:AZD_ALPHA_ENABLE_AGENTS_VOICE = "true"` in PowerShell).

1. **.NET 10.0 SDK or later**
   - Verify your version: `dotnet --version`
   - Download from [https://dotnet.microsoft.com/download](https://dotnet.microsoft.com/download)
2. **Azure Developer CLI (`azd`)** (recommended for deploy)
   - [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) and the Foundry extension: `azd ext install microsoft.foundry`
   - Authenticated: `azd auth login`
3. **Azure CLI** — installed and authenticated: `az login`.
4. An **Azure AI Services / Voice Live** resource with access to a realtime model (for example `gpt-realtime-1.5`).
5. The **Foundry User** role on that resource at **account scope** —
   for your user when running locally, and for the hosted agent's
   managed identity post-deploy (see [Deploying to Microsoft Foundry](#deploying-to-microsoft-foundry)).

## Environment variables

See [`.env.example`](src/hello-world-dotnet-invocations-ws/.env.example) for the full list.

| Variable | Required | Description |
|----------|----------|-------------|
| `FOUNDRY_PROJECT_ENDPOINT` | Hosted | Auto-injected in hosted containers — Voice Live endpoint is derived from this. |
| `AZURE_VOICELIVE_ENDPOINT` | Local  | AI Services account URL (no path). Used when `FOUNDRY_PROJECT_ENDPOINT` is unset. |
| `AZURE_VOICELIVE_MODEL`    | Yes    | Realtime model name. Defaults to `gpt-realtime-1.5`. |
| `AZURE_VOICELIVE_VOICE`    | No     | TTS voice. Defaults to `en-US-Ava:DragonHDLatestNeural`. |
| `AZURE_VOICELIVE_INSTRUCTIONS` | No | System prompt override. |
| `AZURE_VOICELIVE_IDLE_ENGAGEMENT_SECONDS` | No | Seconds of silence before the agent proactively re-engages. `0` disables. |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Recommended | Telemetry. Auto-injected in hosted containers. |

## Running locally

```bash
cd samples/csharp/hosted-agents/bring-your-own/invocations_ws/HelloWorld

export AZURE_VOICELIVE_ENDPOINT="https://<account>.cognitiveservices.azure.com/"
export AZURE_VOICELIVE_MODEL="gpt-realtime-1.5"

dotnet run
# → Now listening on: http://0.0.0.0:8088
```

### Headless E2E test

In a second terminal:

```bash
cd samples/csharp/hosted-agents/bring-your-own/invocations_ws/HelloWorld
dotnet run --project E2ELocal
# [e2e] session_started:    True
# [e2e] audio_bytes recvd:  230400
# [e2e] response_done seen: 1
# [e2e] result:             PASS
```

The test sends a single JSON text message
(`{"type": "text", "content": "Say hello in one short sentence."}`),
which the agent forwards to Voice Live as a user turn + `response.create`,
and asserts that `session_started`, at least one PCM audio frame, and
`response_done` come back. It does not require a microphone or a real
spoken utterance — server-VAD is bypassed entirely.

To run the same test against a deployed Foundry agent:

```bash
dotnet run --project E2ELocal -- \
  --foundry "https://<account>.services.ai.azure.com/api/projects/<project>" \
  --agent hello-world-dotnet-invocations-ws
```

### Browser test (standalone client)

The sample ships a tiny single-file browser client in [`chat_client/`](chat_client/index.html).
Because most browsers refuse mic access from `file://` URLs and Foundry
requires an `Authorization` header on the WebSocket, the page is meant
to be served by the bundled proxy, which also bridges the upstream WS:

```bash
dotnet run --project chat_client/Proxy -- \
  --foundry "https://<account>.services.ai.azure.com/api/projects/<project>" \
  --agent hello-world-dotnet-invocations-ws
```

Open <http://localhost:8765/>, click **▶ Start**, allow mic access, and
speak. The page's default WebSocket URL is auto-set to the proxy
(`ws://localhost:8765/invocations_ws`).

For a pure local-only round trip (no Foundry), run `dotnet run` in this
folder and then open the page however you like (e.g. via the proxy or
your favorite static file server) — the default WS URL is
`ws://localhost:8088/invocations_ws`.

## Deploying to Microsoft Foundry

The hosted agent can be developed and deployed to Microsoft Foundry using
the [Azure Developer CLI](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?view=foundry&pivots=azd):

```bash
mkdir hello-world-voicelive && cd hello-world-voicelive

azd ai agent init \
  -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/bring-your-own/invocations_ws/HelloWorld/azure.yaml

# Pin the Voice Live model + voice for the deployed container.
azd env set AZURE_VOICELIVE_MODEL "gpt-realtime-1.5"
azd env set AZURE_VOICELIVE_VOICE "en-US-Ava:DragonHDLatestNeural"

azd provision
azd deploy
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
data-plane** WebSocket URL (the proxy and `E2ELocal` build this for
you from `--foundry` + `--agent`):

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
| `<agent>` | Matches the agent `name` in [`azure.yaml`](azure.yaml) — `hello-world-dotnet-invocations-ws`. |
| `agent_session_id=<unique-session-id>` | A caller-generated string that identifies the conversation. Reuse the same id to resume; use a fresh one (e.g. a GUID) to start a new session. |

Every request must also include `Authorization: Bearer <Entra token>`
for the `https://ai.azure.com` resource. Browsers can't set headers
on a `WebSocket`, which is why the bundled
[`chat_client/Proxy`](chat_client/Proxy) injects the token server-side
and the [`E2ELocal`](E2ELocal) CLI does the same via
`az account get-access-token`.

Then test the hosted agent end-to-end with the bundled CLI (which sends
the required `Authorization: Bearer <token>` header — browsers cannot do
this on a WebSocket, so the standalone `chat_client/index.html` is for
local dev only):

```bash
dotnet run --project E2ELocal -- \
  --foundry "https://<account>.services.ai.azure.com/api/projects/<project>" \
  --agent hello-world-dotnet-invocations-ws
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
* **Images built on Apple Silicon or other ARM64 machines do not work
  on our service** — prefer `azd deploy`, which uses ACR remote build
  and always produces the correct architecture. For local builds run
  `docker build --platform=linux/amd64 -t image .`.
