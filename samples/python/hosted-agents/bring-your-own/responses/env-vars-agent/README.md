**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight.

# Env Vars Agent — Python (Responses Protocol)

A hosted agent built with `azure-ai-agentserver-responses` that demonstrates Foundry's **connection-templated environment-variable injection**. Four example env vars are declared in `azure.yaml` — covering all four corners of the connection grid (ApiKey × CustomKeys × secret × non-secret) — and injected into the container at runtime by the platform's secret resolver.

The agent exposes a single function-calling tool, `get_env_var(name, kind)`, that returns the runtime value with a **kind-aware safety policy**:

| `kind` | Returned to the model | Why |
|---|---|---|
| `metadata` | The **whole value** | Plain, non-secret data (region, account name, feature flags, …) stored in the connection's metadata bag. |
| `target` | The **whole value** | The connection's endpoint URL — also plain, non-secret. |
| `credentials` (default) | A **safe fingerprint** (length + first 4 chars + placeholder-resolved check) | Secrets must never leave the agent. The fingerprint is enough to confirm the placeholder resolved without exposing the value. |

### The four example env vars

| Env var | Connection (kind) | Placeholder | Tool `kind` | Returned |
|---|---|---|---|---|
| `SECRET_API_KEY` | `dummy-api-key` (ApiKey) | `${{connections.dummy-api-key.credentials.key}}` | `credentials` | fingerprint |
| `TARGET` | `dummy-api-key` (ApiKey) | `${{connections.dummy-api-key.target}}` | `target` | whole value |
| `SECRET_KEY` | `dummy-custom-keys` (CustomKeys) | `${{connections.dummy-custom-keys.credentials.secret-key}}` | `credentials` | fingerprint |
| `NON_SECRET_KEY` | `dummy-custom-keys` (CustomKeys) | `${{connections.dummy-custom-keys.metadata.plain-key}}` | `metadata` | whole value |

Built with `azure-ai-agentserver-responses` (BYO — no Agent Framework). The model call uses the **Azure AI Projects + Responses API** (`AIProjectClient.get_openai_client()` → `client.responses.create(...)`).

## How It Works

1. **Connection setup**: `azure.yaml` provisions
   - an **ApiKey** connection named `dummy-api-key`, and
   - a **CustomKeys** connection named `dummy-custom-keys` with a secret
     `secret-key` credential and plain `plain-key` metadata.
   The committed values are non-production demonstration values; replace them
   when adapting the sample to real connections.
2. **Template declaration**: `azure.yaml` declares the four env vars with placeholder values:
   ```yaml
   - name: SECRET_API_KEY
     value: "${{connections.dummy-api-key.credentials.key}}"
   - name: TARGET
     value: "${{connections.dummy-api-key.target}}"
   - name: SECRET_KEY
     value: "${{connections.dummy-custom-keys.credentials.secret-key}}"
   - name: NON_SECRET_KEY
     value: "${{connections.dummy-custom-keys.metadata.plain-key}}"
   ```
3. **Runtime resolution**: when the agent container starts, the Foundry platform reads each named connection, resolves each placeholder, and injects the resulting value into the env var.
4. **Agent execution**: the agent receives natural language messages via `POST /responses`. The Responses-API function-calling loop decides which env var to inspect and which `kind` to pass:
   - `get_env_var("TARGET", "target")` → `{ status: "RESOLVED", value: "https://api.example.com", … }`
   - `get_env_var("SECRET_API_KEY", "credentials")` → `{ status: "RESOLVED", length: 32, head: "ab12", … }` *(no raw value)*
   - `get_env_var("NON_SECRET_KEY", "metadata")` → `{ status: "RESOLVED", value: "westus2", … }`
   - `get_env_var("SECRET_KEY", "credentials")` → `{ status: "RESOLVED", length: 24, head: "p@ss", … }` *(no raw value)*
5. The model's tool result is fed back for a natural-language reply.

## Features

- **Connection-templated env vars** — values injected at container start; never persisted in the agent definition
- **Kind-aware tool** — full value for `metadata`/`target`, fingerprint only for `credentials`
- **Streaming responses** — real-time SSE streaming via the Responses protocol
- **No 3rd-party HTTP deps** — pure standard library for the env-var inspection

## Running Locally

### Prerequisites

- Python 3.12+
- Azure CLI installed and authenticated (`az login`)
- Foundry project with a deployed model (e.g., `gpt-5.4-mini`)
- (For deployment) the project's hosted-agent feature enabled; `azure.yaml`
  creates the two demonstration connections referenced by the agent

### Using `azd`

```bash
azd ai agent run
```

The agent starts on `http://localhost:8088/`.

### Manual setup

```bash
cd src/env-vars-agent-responses-python

pipx install uv==0.11.7
uv sync --frozen --python 3.12
cp .env.example .env  # then edit values — fill in any test values you like (skip if .env already exists)
export FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4-mini"
export SECRET_API_KEY="ab12-fake-test-key"
export TARGET="https://api.example.com"
export SECRET_KEY="p@ssw0rd-test-value"
export NON_SECRET_KEY="westus2"
uv run --no-sync python main.py
```

The agent starts on `http://localhost:8088/`.

### Test

#### 1. Test with azd

##### Read the ApiKey target (whole value)

```bash
azd ai agent invoke --local "what is TARGET? it is the target of an ApiKey connection."
```

##### Read the ApiKey credentials (fingerprint only)

```bash
azd ai agent invoke --local "did SECRET_API_KEY resolve? it is a credentials placeholder."
```

##### Read the CustomKeys metadata (whole value)

```bash
azd ai agent invoke --local "what is NON_SECRET_KEY? it is metadata from a CustomKeys connection."
```

##### Read the CustomKeys credentials (fingerprint only)

```bash
azd ai agent invoke --local "did SECRET_KEY resolve? it is a credentials placeholder."
```

#### 2. Test with curl

```bash
curl -N -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "what is TARGET? it is the target of an ApiKey connection.", "stream": true}'

curl -N -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "did SECRET_KEY resolve? it is a credentials placeholder.", "stream": true}'
```

#### 3. Test in VS Code (Foundry Toolkit)

**Prerequisites**

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

**Set up the Python virtual environment**

- With Python 3.12 or later and [pipx](https://pipx.pypa.io/stable/installation/), install uv outside the project environment, then let uv create and synchronize the locked environment:

  ```bash
  cd src/env-vars-agent-responses-python

  pipx install uv==0.11.7
  uv sync --frozen --python 3.12
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select `src/env-vars-agent-responses-python/.venv`.

**Run and debug the agent**

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

**Or run manually, then open the Inspector**

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. From `src/env-vars-agent-responses-python`, start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

```
what is TARGET? it is the target of an ApiKey connection.
```

```
did SECRET_KEY resolve? it is a credentials placeholder.
```

## Deploying the Agent to Microsoft Foundry

Once you've tested locally, deploy to Microsoft Foundry:

```bash
# Provision Azure resources (skip if already done during local setup)
azd provision

# Build, push, and deploy the agent to Foundry
azd deploy
```

After deploying, invoke the agent running in Foundry:

```bash
azd ai agent invoke "did SECRET_API_KEY resolve? it is a credentials placeholder."
```

To stream logs from the running agent:

```bash
azd ai agent monitor
```

For the full deployment guide, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).

## How the Connection Resolution Works

The resolver supports three placeholder paths today, mapped to the three parts of a connection:

| Path | Template syntax | Source on the connection | Use for |
|------|-----------------|--------------------------|---------|
| `credentials.<field>` | `${{connections.<name>.credentials.key}}` (ApiKey)<br>`${{connections.<name>.credentials.<key-name>}}` (CustomKeys secret) | The connection's secret store | API keys; CustomKeys entries marked **as secret** |
| `target` | `${{connections.<name>.target}}` | The connection's `target` field (endpoint URL) | Endpoints / base URLs |
| `metadata.<key>` | `${{connections.<name>.metadata.<key-name>}}` | The connection's `metadata` bag | Plain (non-secret) CustomKeys entries — region, account name, feature flags, etc. |

> **CustomKeys connections can mix both:** when you add a custom key, you choose whether it's a secret or not. Secret keys land in `credentials` and are reachable via `credentials.<key-name>`; non-secret keys land in `metadata` and are reachable via `metadata.<key-name>`. A single CustomKeys connection can hold any combination — which is exactly what `dummy-custom-keys` shows above.

When the agent container starts, the platform reads the connection by name, resolves each placeholder to the corresponding value, and injects it into the named env var. **Secrets are never persisted into the agent definition** — only the placeholder is stored. `target` and `metadata` values are *not* secrets; they are stored on the connection itself in plain text and surfaced verbatim, but the same placeholder mechanism keeps the manifest portable across environments.

The agent's `get_env_var(name, kind)` tool mirrors this three-way split: pass `kind=metadata` or `kind=target` to get the raw value back; pass `kind=credentials` (or omit it — it's the default) to get a safe fingerprint instead.

## File Layout

| File | Purpose |
|------|---------|
| `main.py` | `ResponsesAgentServerHost` startup + Responses-API function-calling loop with the `get_env_var` tool |
| `pyproject.toml` / `uv.lock` | Python dependencies and reproducible lock — `azure-ai-agentserver-responses` + `azure-ai-projects` + `azure-identity` |
| `azure.yaml` | Container agent spec (`kind: hosted`, protocol, resources) |
| `azure.yaml` | Foundry deployment manifest — model, env vars, connection placeholders |
| `Dockerfile` | python:3.12-slim image, exposes port 8088 |
| `.env.example` or `.env` | Template for local-run env vars |
| `.dockerignore` | Excludes build artifacts and `.env` from the container image |
| `README.md` | The README file |

## Troubleshooting

### An env var shows status `UNRESOLVED_PLACEHOLDER`

The secret resolver did not run or failed for that env var. Check:

- The connection named in `${{connections.<name>.<path>}}` exists in the project (or the parent account) with the **exact** name.
- For `CustomKeys` connections, the custom key name in the connection must match the `<field>` part of the template (case-sensitive).
- The `kind` you used in the placeholder matches where the field actually lives on the connection (a key marked as secret is in `credentials`, not `metadata`).
- The hosted-agent feature flag is enabled for the workspace.
- The agent was redeployed after the env var was added — connection resolution happens at container start.

### Azure OpenAI Permission Denied (401)

If you see an error like:

```
Error code: 401 - The principal <principal-id> lacks the required data action
Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action ...
```

The identity running the agent does not have the required RBAC roles on the Azure AI Foundry project. Assign:

- **Cognitive Services OpenAI User**
- **Azure AI User**

```bash
SUBSCRIPTION_ID="<your-subscription-id>"
RESOURCE_GROUP="<your-resource-group>"
PROJECT_NAME="<your-ai-foundry-project-name>"
PRINCIPAL_ID="<principal-id-from-error-message>"

az role assignment create \
  --assignee "$PRINCIPAL_ID" \
  --role "Cognitive Services OpenAI User" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.MachineLearningServices/workspaces/$PROJECT_NAME"

az role assignment create \
  --assignee "$PRINCIPAL_ID" \
  --role "Azure AI User" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.MachineLearningServices/workspaces/$PROJECT_NAME"
```

> **Note:** It may take a few minutes for role assignments to propagate.
