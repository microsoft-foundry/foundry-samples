**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight.

# Env Vars Agent — Responses Protocol

This sample demonstrates Foundry's **connection-templated environment-variable injection** in a hosted agent. Four example env vars are declared in `azure.yaml` — covering all four corners of the connection grid (ApiKey × CustomKeys × secret × non-secret) — and injected into the container at runtime by the platform's secret resolver.

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

Built with [Azure.AI.AgentServer.Responses](https://www.nuget.org/packages/Azure.AI.AgentServer.Responses) (BYO — no Agent Framework). The model call uses **Azure AI Projects + the Responses API** (`Azure.AI.Projects` + `Azure.AI.Extensions.OpenAI`).

## How It Works

1. **Connection setup (one-time)**: in your Foundry project, create
   - an **ApiKey** connection named `dummy-api-key` (give it a `target` URL and a `key`), and
   - a **CustomKeys** connection named `dummy-custom-keys` with two custom keys — `secret-key` (marked **as secret**) and `plain-key` (plain).
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

## Prerequisites

1. An existing Foundry project with a deployed model (e.g., `gpt-5.4-mini`), or create them during setup in Option 1.
2. **[.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)** or later.
3. **Foundry connections** (for deployment): an **ApiKey** connection `dummy-api-key` and a **CustomKeys** connection `dummy-custom-keys` (with a secret `secret-key` and a plain `plain-key`), as described in [How It Works](#how-it-works). The placeholders in `azure.yaml` resolve against these at container startup.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
2. Install the Foundry extension:

   ```bash
   azd ext install microsoft.foundry
   ```

3. Authenticate:

   ```bash
   azd auth login
   ```

### Initialize the agent project

No cloning required. Create a new folder and initialize from the manifest:

```bash
mkdir env-vars-agent && cd env-vars-agent
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/bring-your-own/responses/env-vars-agent/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an existing Foundry project, `azd ai agent init` will guide you through creating one.

### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployment:

```bash
azd provision
```

### Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

### Invoke the local agent

Ask the agent about each env var. The tool returns whole values for `target`/`metadata` and a safe fingerprint for `credentials`:

```bash
# ApiKey target (whole value)
azd ai agent invoke --local "what is TARGET? it is the target of an ApiKey connection."

# ApiKey credentials (fingerprint only)
azd ai agent invoke --local "did SECRET_API_KEY resolve? it is a credentials placeholder."

# CustomKeys metadata (whole value)
azd ai agent invoke --local "what is NON_SECRET_KEY? it is metadata from a CustomKeys connection."

# CustomKeys credentials (fingerprint only)
azd ai agent invoke --local "did SECRET_KEY resolve? it is a credentials placeholder."
```

Or use curl directly:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "what is TARGET? it is the target of an ApiKey connection."}' \
  --no-buffer

curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "did SECRET_KEY resolve? it is a credentials placeholder."}' \
  --no-buffer
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke "did SECRET_API_KEY resolve? it is a credentials placeholder."
```

Stream logs from the running agent with `azd ai agent monitor`.

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. [C# Dev Kit](https://marketplace.visualstudio.com/items?itemName=ms-dotnettools.csdevkit) extension.
3. Command Palette (`Ctrl+Shift+P`) → **C#: Check Workspace Requirements** to confirm the toolchain is ready.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Try a message such as:

```
what is TARGET? it is the target of an ApiKey connection.
```

### Or run manually, then open the Inspector

1. Sign in to Azure with the Azure CLI (`az login`) and build:

   ```bash
   dotnet build
   ```

   Copy `.env.example` to `.env` and fill in any test values you like (the agent loads `.env` automatically on startup).

2. Start the agent: `dotnet run` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

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
| `Program.cs` | `ResponsesServer.Run<EnvVarsHandler>` startup + Responses-API function-calling loop with the `get_env_var` tool |
| `EnvVarsAgent.csproj` | net10.0 project — `Azure.AI.AgentServer.Responses` + `Azure.AI.Projects` + `Azure.AI.Extensions.OpenAI` |
| `azure.yaml` | Container agent spec (`kind: hosted`, protocol, resources) |
| `azure.yaml` | Foundry deployment manifest — model, env vars, connection placeholders |
| `Dockerfile` | Multi-stage net10.0-alpine build, exposes port 8088 |
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
