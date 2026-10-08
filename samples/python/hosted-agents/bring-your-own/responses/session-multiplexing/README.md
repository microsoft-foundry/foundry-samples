<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# What this sample demonstrates

A Bring Your Own hosted agent using the **Responses protocol 2.0.0**. It starts from the [hello-world Responses sample](../hello-world) and uses platform-managed conversation state through `previous_response_id` and `context.get_history()`.

The session multiplexing behavior is the key difference: multiple acted-for users can share the same `agent_session_id`, but a response chain created by one platform user cannot be continued by another user through `previous_response_id`.

## How it works

### Model integration

The agent uses the Foundry SDK to create an OpenAI-compatible Responses client from the project endpoint. When a request arrives, the handler extracts input text, loads platform conversation history with `context.get_history()`, calls the model, and returns the final response as a `TextResponse`.

See [main.py](src/hello-world-session-multiplexing-python-responses/main.py) for the full implementation.

### Conversation state

This sample does **not** use in-memory conversation state or a container-side note store. Conversation context is automatically managed by the platform:

- The caller creates a response and receives a response `id`.
- The caller can continue that chain by sending the response `id` as `previous_response_id`.
- The container calls `context.get_history()` to receive the platform-authorized history for the current request.

### Session multiplexing

The hosted platform resolves the acted-for user for each request and the AgentServer SDK exposes that request context through `get_request_context()`:

- `get_request_context().user_id` identifies the platform-resolved user for the current request.
- `get_request_context().call_id` is the opaque per-request call ID for the current hosted request.

The caller owns the session-pool policy:

```text
user -> sticky agent_session_id
```

If a user has no sticky mapping yet, the caller reuses an existing session with available capacity. If none exists, it generates the next session ID. In the Responses protocol, sending a new `agent_session_id` on `create response` creates/opens that hosted session on first use.

> [!WARNING]
> Do not treat `agent_session_id` as the only user isolation boundary. A shared session can contain requests from multiple users; platform identity and `previous_response_id` visibility determine which response history is accessible.

### Agent hosting

The agent is hosted using the [Azure AI AgentServer Responses SDK](https://pypi.org/project/azure-ai-agentserver-responses/), which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

Before running this sample, ensure you have:

1. **Azure Developer CLI (`azd`)**
   - [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) (1.25 or later) and the unified Foundry CLI extension: `azd ext install microsoft.foundry`
   - Authenticated: `azd auth login`

1. **Azure CLI**
   - Installed and authenticated: `az login`

1. **Python 3.12 or higher**
   - Verify your version: `python --version`

1. **A deployed hosted agent for the multiplexing test**
   - Protocol `2.0.0` platform context is populated in hosted Foundry. Local calls are useful for startup checks, but they do not demonstrate session multiplexing.

### Environment variables

See [`.env.example`](src/hello-world-session-multiplexing-python-responses/.env.example) or `.env` for the full list of environment variables this sample uses.

| Variable | Required | Description |
|----------|----------|-------------|
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | Foundry project endpoint. Auto-injected in hosted containers; set automatically by `azd ai agent run` locally. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Yes | Model deployment name; declared in `azure.yaml`. |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Recommended | Enables telemetry. Auto-injected in hosted containers; set manually for local dev. |

**Local development (without `azd`):**

```bash
cp .env.example .env  # skip if .env already exists
# Edit .env with your values
source .env
```

> [!NOTE]
> When using `azd ai agent run`, environment variables are handled automatically.

### Installing dependencies

> [!NOTE]
> If using `azd ai agent run`, dependencies are installed automatically.

```bash
cd src/hello-world-session-multiplexing-python-responses

pipx install uv==0.11.7
uv sync --frozen --python 3.12
```

### Run the agent locally

```bash
mkdir session-multiplexing-agent && cd session-multiplexing-agent
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/responses/session-multiplexing/azure.yaml
azd provision
azd ai agent run
```

> [!NOTE]
> If you've already cloned this repository, pass a local path to the manifest instead:
> `azd ai agent init -m <path-to-repo>/samples/python/hosted-agents/bring-your-own/responses/session-multiplexing/azure.yaml`

The agent starts on `http://localhost:8088/`. Local requests do not include hosted protocol 2.0.0 platform context, so the handler fails closed until `get_request_context().user_id` and `get_request_context().call_id` are present.

To run without `azd`, set the required environment variables manually, then, from `src/hello-world-session-multiplexing-python-responses`, start the agent with `uv run --no-sync python main.py`.

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd provision
azd deploy
```

For the full deployment guide, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).

### Invoke the deployed agent

```bash
azd ai agent invoke "Remember that my code word is BLUE-LANTERN"
```

To stream logs from the running agent:

```bash
azd ai agent monitor
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

### Set up the Python virtual environment

- With Python 3.12 or later and [pipx](https://pipx.pypa.io/stable/installation/), install uv outside the project environment, then let uv create and synchronize the locked environment:

  ```bash
  cd src/hello-world-session-multiplexing-python-responses

  pipx install uv==0.11.7
  uv sync --frozen --python 3.12
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select `src/hello-world-session-multiplexing-python-responses/.venv`.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. From `src/hello-world-session-multiplexing-python-responses`, start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Testing session multiplexing after deployment

This sample has two caller scripts.

### 1. Minimal A-A-B previous_response_id isolation test

Use [scripts/invoke_previous_response_isolation.py](scripts/invoke_previous_response_isolation.py) when you only want to verify the core platform behavior. The script generates a fresh `agent_session_id` when `--session-id` is not provided and uses `alice` and `bob` as the acted-for users. In the Responses protocol, the first `create response` call with that session ID creates/opens the session.

```bash
cd src/hello-world-session-multiplexing-python-responses

export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
export AGENT_NAME="<agent-name>"
uv run --no-sync python scripts/invoke_previous_response_isolation.py
```

Flow:

1. Alice creates response 1 in session A.
1. Alice creates response 2 in session A with `previous_response_id=<response 1 id>`.
1. Bob uses the same session A and tries `previous_response_id=<response 2 id>`.
1. The script passes only if Bob's call fails.

If you want to force a specific session, pass `--session-id <session-id>`.

### 2. Lazy sticky session-pool demo

Use [scripts/invoke_session_pool.py](scripts/invoke_session_pool.py) to demonstrate caller-owned load balancing with `alice` and `bob` as the acted-for users. The default `sticky-fill` strategy is lazy: if a user has no sticky mapping yet, it reuses the first session with available capacity; if none exists, it generates the next `agent_session_id`. The script also includes `round-robin` for demonstrating alternate assignment. It calls the A-A-B helper only when `alice` and `bob` are assigned to the same session.

```bash
cd src/hello-world-session-multiplexing-python-responses

export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
export AGENT_NAME="<agent-name>"
uv run --no-sync python scripts/invoke_session_pool.py --max-users-per-session 100

# Optional: show round-robin assignment. With --pool-size 2, alice and
# bob land in different sessions and the same-session check is skipped.
uv run --no-sync python scripts/invoke_session_pool.py --strategy round-robin --pool-size 2
```

The assigned session is passed explicitly from the pool script into the A-A-B helper:

```python
user_a_session = pool.get_session_for_user("alice")
user_b_session = pool.get_session_for_user("bob")

result = run_previous_response_isolation(
    agent=agent,
    session_id=user_a_session,
    user_b_session_id=user_b_session,
    user_a="alice",
    user_b="bob",
)
```

The pool script owns session assignment. The A-A-B helper only proves isolation for the `session_id` and `user_b_session_id` it receives.

> [!NOTE]
> The caller principal must have `Microsoft.CognitiveServices/accounts/AIServices/agents/endpoints/UserIdentityImpersonation/action` to use `x-ms-user-identity`.

## File structure

| File | Description |
|---|---|
| `main.py` | Responses handler using platform-managed history from `context.get_history()` |
| `scripts/invoke_previous_response_isolation.py` | Standalone A-A-B previous_response_id isolation test |
| `scripts/invoke_session_pool.py` | Lazy sticky session-pool demo that calls the A-A-B helper with the assigned session |
| `pyproject.toml` / `uv.lock` | Python dependencies and reproducible lock |
| `Dockerfile` | Container image definition |
| `azure.yaml` | Agent hosting configuration |
| `azure.yaml` | Agent metadata and template |
| `.dockerignore` | Docker build exclusions |

## Troubleshooting

### Local calls return `A user context is required`

This is expected. Local requests do not include hosted protocol 2.0.0 platform context. Deploy the agent and use `scripts/invoke_previous_response_isolation.py` or `scripts/invoke_session_pool.py` to verify session multiplexing.

### Hosted calls return `403` when using `x-ms-user-identity`

The calling identity does not have permission to impersonate users. Grant `Microsoft.CognitiveServices/accounts/AIServices/agents/endpoints/UserIdentityImpersonation/action` to the middle-tier service identity.

### Bob can continue Alice's previous response

That means the test did not exercise two distinct platform users. Use two different Entra users or object IDs. Passing two labels that resolve to the same identity is not a valid cross-user isolation test.

### Images built on Apple Silicon or other ARM64 machines do not work on the service

Deploy with `azd deploy`, which uses ACR remote build and produces images with the correct architecture. If you build locally, force the platform:

```bash
docker build --platform=linux/amd64 -t image .
```
