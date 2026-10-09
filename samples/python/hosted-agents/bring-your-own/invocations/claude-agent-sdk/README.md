# Claude Agent SDK — Invocations Protocol (Streaming)

**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight.

A minimal getting-started agent using the [Claude Agent SDK](https://pypi.org/project/claude-agent-sdk/) with [azure-ai-agentserver-invocations](https://pypi.org/project/azure-ai-agentserver-invocations/) protocol support.

This sample is configured for **Microsoft Foundry** mode by default

## How It Works

1. Receives plain text via `POST /invocations`
2. Uses Claude Agent SDK `query()` to process the input
3. Streams assistant text chunks directly without buffering
4. Emits response and handles errors gracefully

## Environment Variables

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `FOUNDRY_PROJECT_ENDPOINT` | Auto-injected | Automatically provided by Foundry when agent is invoked |
| `CLAUDE_CODE_USE_FOUNDRY` | Yes (default `1`) | Enables Foundry integration path in Claude Agent SDK |
| `ANTHROPIC_MODEL` | Built-in default | Explicit startup model set to `claude-opus-4-7`  |
| `ANTHROPIC_FOUNDRY_BASE_URL` | Auto-generated | Automatically constructed from `FOUNDRY_PROJECT_ENDPOINT` as `https://<resource>.services.ai.azure.com/anthropic` |
| `TOOLBOX_ENDPOINT` | Optional | Full Foundry toolbox MCP endpoint URL. When set (together with `TOOLBOX_ALLOWED_TOOLS`), the agent validates and exposes the allowlisted toolbox tools to Claude. |
| `TOOLBOX_NAME` | Optional | Toolbox name. If `TOOLBOX_ENDPOINT` isn't set, the agent builds the latest-version endpoint from this and `FOUNDRY_PROJECT_ENDPOINT`. |
| `TOOLBOX_ALLOWED_TOOLS` | Required if either toolbox variable above is set | Comma-separated, explicit allowlist of toolbox tool names to expose (e.g. `web_search`). |

## Optional: Consuming an Existing Foundry Toolbox

This sample can optionally connect to an **already-provisioned Foundry Toolbox** so Claude can call toolbox tools (for example `web_search`) during the conversation. This sample only *consumes* a toolbox — it does not create or configure one. Provision the toolbox separately (e.g. with `azd ai toolbox create`) before setting any of the variables below.

If neither `TOOLBOX_ENDPOINT` nor `TOOLBOX_NAME` is set, this sample behaves exactly as it did before — no toolbox integration is attempted, and the module-level `TOOLBOX_ALLOWED_TOOLS` check is skipped entirely.

### Fail-loud contract

Once `TOOLBOX_ENDPOINT` or `TOOLBOX_NAME` is set, toolbox integration becomes **required** for that invocation to succeed:

- `TOOLBOX_ALLOWED_TOOLS` must also be set, or the process fails to start (`EnvironmentError` at import time).
- Each invocation runs a fresh MCP `tools/list` discovery call against the toolbox. If the toolbox is unreachable, returns an error, or returns no tools, the invocation fails immediately with an explicit `{"error": ...}` SSE event (and a server-side log entry) — it never silently falls back to running without toolbox tools.
- Every name in `TOOLBOX_ALLOWED_TOOLS` must be present in that invocation's discovery result, or the invocation fails with the unknown/missing name(s) listed. Discovery can only confirm a configured name exists; it never expands access to tools you didn't list. A write/mutating tool the toolbox happens to expose, but that you didn't add to `TOOLBOX_ALLOWED_TOOLS`, is never passed to `allowed_tools` and so is never callable by the model.
- `permission_mode="dontAsk"` is used (fail-closed: only pre-approved `allowed_tools` can run); the blanket `bypassPermissions` mode is never used.

### Authentication and request-scoping

Each invocation builds its own headers dict (never a shared/mutated global): a Microsoft Entra ID bearer token (`DefaultAzureCredential`, scope `https://ai.azure.com/.default`) plus `Foundry-Features: Toolboxes=V1Preview` and the inbound request's `x-agent-foundry-call-id` (propagated via `get_request_context().platform_headers()`). Discovery receives the real bearer token. The Claude Agent SDK's native `mcp_servers` config uses an environment-variable placeholder for Authorization, and `ClaudeAgentOptions.env` passes the per-invocation token to the child process, keeping the credential out of the serialized MCP-config command-line argument. The token is minted once per invocation; the SDK's MCP HTTP transport has no mid-stream refresh hook, so if a single invocation genuinely outlives the token's lifetime, the subsequent MCP call fails with `401` and surfaces as an invocation error rather than being silently retried.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

- Python 3.12+
- `az login` 
- A Foundry resource with Claude model deployments

### Run the agent locally

```bash
azd ai agent run
```

This sample sets `ANTHROPIC_MODEL=claude-opus-4-7` in YAML, you can change the model here.

### Invoke the local agent

```bash
azd ai agent invoke --local "Hey hi"
```

Or invoke directly with curl:

```bash
curl -sS -N -X POST http://localhost:8088/invocations \
  -H "Content-Type: text/plain" \
  -d "List the main Python files in this folder."
```

### Deploy to Foundry

```bash
azd provision
azd deploy
```

> After deployment, configure RBAC — see [⚠️ CRITICAL: RBAC Configuration After Deployment](#-critical-rbac-configuration-after-deployment) below.

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

### Set up the Python virtual environment

- With Python 3.12 or later and [pipx](https://pipx.pypa.io/stable/installation/), install uv outside the project environment, then let uv create and synchronize the locked environment:

  ```bash
  cd src/claude-agent-sdk-invocations

  pipx install uv==0.11.7
  uv sync --frozen --python 3.12
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select `src/claude-agent-sdk-invocations/.venv`.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. From `src/claude-agent-sdk-invocations`, start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## ⚠️ CRITICAL: RBAC Configuration After Deployment

**IMPORTANT!** After running `azd deploy`, you **MUST** assign the `Foundry User` role at the **account scope** to your agent's runtime identity. Without this, your agent will fail with a `401 Unauthorized` error when attempting to invoke the Claude model.

### Why This Is Required

Azure AI Foundry enforces authorization at two levels:

1. **Project Scope**: Controls agent orchestration and project operations
2. **Account Scope**: Controls model inference API calls (required for Claude SDK calls)

Without the account-level `Foundry User` role, your agent will initialize but fail when trying to call the model API.

### Step-by-Step RBAC Setup

#### Step 1: Get Your Agent's Runtime Principal ID

After deployment, retrieve your agent's runtime principal ID:

```bash
azd ai agent show
```

Look for the `instance_identity.principal_id` in the output:

```json
"instance_identity": {
  "principal_id": "11111111-2222-3333-4444-555555555555",
  "client_id": "11111111-2222-3333-4444-555555555555"
}
```

Save this `principal_id` — you'll need it for the next step.

#### Step 2: Collect Required Information

Get your Azure subscription ID, resource group, and account name:

```bash
# Get subscription ID
az account show --query id -o tsv

# Get resource group (if not known)
az group list --query "[0].name" -o tsv

# Get account name from environment (look for AZURE_AI_ACCOUNT_NAME in the output)
azd env get-values
```

From the `azd env get-values` output, find the line with `AZURE_AI_ACCOUNT_NAME` and copy that value. Do not leave `myFoundryAccount` in the command examples below; replace it with your actual Azure AI account name.

#### Step 3: Assign Foundry User Role at Account Scope

Run this command, replacing the placeholders with your values:

**For Bash/Linux/macOS:**

```bash
az role assignment create \
  --assignee-object-id <PRINCIPAL_ID> \
  --assignee-principal-type ServicePrincipal \
  --role "Foundry User" \
  --scope /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>/providers/Microsoft.CognitiveServices/accounts/<ACCOUNT_NAME>
```

**For PowerShell (Windows):**

```powershell
az role assignment create --assignee-object-id <PRINCIPAL_ID> --assignee-principal-type ServicePrincipal --role "Foundry User" --scope "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>/providers/Microsoft.CognitiveServices/accounts/<ACCOUNT_NAME>"
```

#### Step 4: Verify the Role Assignment

Confirm the role is assigned at account scope:

```bash
az role assignment list \
  --assignee-object-id <PRINCIPAL_ID> \
  --all -o table
```

For PowerShell, a single-line version is safest:

```powershell
az role assignment list --assignee-object-id <PRINCIPAL_ID> --all -o table
```

You should see both:

- `Foundry User` at the project scope
- `Foundry User` at the account scope (this is the critical one)

#### Step 5: Wait for RBAC Propagation

Azure RBAC changes can take **2-5 minutes** to propagate. Wait before testing.

#### Step 6: Test Your Agent

After waiting, test with a new session:

```bash
azd ai agent invoke --new-session "Hey hi"
```

If successful, you'll see the Claude model's response streaming through. If it still fails with a 401 error:

- Verify the principal ID matches exactly by running `azd ai agent show` and checking `instance_identity.principal_id`
- Check the account scope path is correct
- Ensure you've waited 5+ minutes for role propagation
- Verify the role assignment: `az role assignment list --assignee-object-id <PRINCIPAL_ID> --all -o table`
