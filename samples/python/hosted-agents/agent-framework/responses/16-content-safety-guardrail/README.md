# Content safety guardrail (Responses protocol)

An [Agent Framework](https://github.com/microsoft/agent-framework) agent hosted on Microsoft Foundry using the **Responses protocol**, with a Responsible AI (RAI) **content safety guardrail** attached. The guardrail screens the prompts the agent receives and the responses it returns against an RAI policy, so harmful content is filtered according to your safety configuration.

## How it works

The agent itself is the basic `FoundryChatClient` agent served via `ResponsesHostServer` — see [main.py](src/agent-framework-content-safety-guardrail/main.py). The guardrail is **not** code; it's a definition-level setting. The agent declares a `policies` list with a `rai_policy` entry that points to an RAI policy by its full Azure Resource Manager (ARM) resource ID:

```yaml
policies:
  - type: rai_policy
    raiPolicyName: /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<account>/raiPolicies/<policy-name>
```

The platform applies that policy to the agent at runtime. Omit the `policies` block entirely to deploy the agent without a content safety guardrail.

`raiPolicyName` is **required** on every `rai_policy` entry. If you declare the entry and leave the name off, `azd` rejects the deployment during packaging:

```text
policies[0] of type 'rai_policy' requires a policy name
```

To use the built-in default policy, give its full ARM resource ID with `Microsoft.DefaultV2` as the policy name, scoped to the account that hosts your agent.

For a conceptual overview, see [Add a content safety guardrail to a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/add-hosted-agent-guardrails).

> [!WARNING]
> Don't rely on deploy-time validation to catch a bad policy ID. On many subscriptions an agent that
> points at a policy that doesn't exist — including the `<subscription-id>`/`<policy-name>` placeholder
> that ships in [azure.yaml](azure.yaml) — deploys successfully and reports `active`, but **no content
> filtering is applied**: the guardrail fails open and harmful prompts reach the agent. Always replace
> the placeholder with a real policy ID and run [Verify the guardrail](#verify-the-guardrail) before you
> rely on this agent's content safety.

## Prerequisites

1. An RAI policy created on your Foundry resource, and its full ARM resource ID. To create one, see [Configure guardrails and controls](https://learn.microsoft.com/en-us/azure/foundry/guardrails/how-to-create-guardrails). The ARM resource ID has this form:

   ```text
   /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<account>/raiPolicies/<policy-name>
   ```

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd), then install the AI agent extension and authenticate:

   ```bash
   azd ext install azure.ai.agents
   azd auth login
   ```

## Configure the guardrail

Set `raiPolicyName` to your RAI policy's full ARM resource ID in [azure.yaml](azure.yaml). Use the full ARM resource ID, not the bare policy name.

## Option 1: Azure Developer CLI (`azd`)

### Initialize the agent project

No cloning required. Create a new folder and initialize from the manifest:

```bash
mkdir my-guardrail-agent && cd my-guardrail-agent

azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/16-content-safety-guardrail/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an existing Foundry project, `azd ai agent init` guides you through creating one.

> [!NOTE]
> After init, confirm that `raiPolicyName` in the generated `azure.yaml` holds your policy's full ARM resource ID.

### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployment:

```bash
azd provision
```

> [!IMPORTANT]
> If you provisioned a new Foundry project, it doesn't have your RAI policy yet. Before you deploy, [create an RAI policy](https://learn.microsoft.com/en-us/azure/foundry/guardrails/how-to-create-guardrails) on the provisioned account, then set `raiPolicyName` in the generated `azure.yaml` to that policy's full ARM resource ID. Deploying with the placeholder or a nonexistent policy ID **may not fail** — on many subscriptions the agent deploys with no effective guardrail.

### Deploy to Foundry

```bash
azd deploy
```

The platform applies the guardrail when it creates the agent version. For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke "Write a short friendly hello message."
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

### Set up the Python virtual environment

- With Python 3.13 or later and [pipx](https://pipx.pypa.io/stable/installation/), install uv outside the project environment, then let uv create and synchronize the locked environment:

  ```bash
  pipx install uv==0.11.7
  uv sync --frozen --python 3.13
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select the `.venv` created by uv.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Set `raiPolicyName` in `azure.yaml` to your policy's full ARM resource ID.
2. Run **Foundry Toolkit: Deploy Hosted Agent** and follow the wizard to deploy.

## Verify the guardrail

After deployment, confirm the guardrail filters content by sending a benign prompt and a prompt that violates your policy to the agent's Responses endpoint. The platform screens prompts at the input stage and rejects a violating prompt before the agent runs.

A prompt that passes the policy returns `HTTP 200` with the agent's response. A blocked prompt returns `HTTP 400` with a `content_filter` error:

```json
{
  "error": {
    "code": "content_filter",
    "message": "The request was blocked due to content safety policy violation at input stage.",
    "type": "content_safety_error"
  }
}
```

If a violating prompt isn't blocked, check in this order:

1. `raiPolicyName` names a policy that **actually exists** on your account. A nonexistent policy (including the shipped placeholder) fails open with no error. List the policies on your account and confirm the final segment of `raiPolicyName` matches one of them:

   ```bash
   az rest --method get \
     --url "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<account>/raiPolicies?api-version=2024-10-01" \
     --query "value[].name" -o tsv
   ```

1. The policy is configured to filter the relevant content category and severity, with `source: Prompt` for input-stage filtering.

The guardrail applies to streaming requests too. With `"stream": true`, a violating prompt is rejected with the same `HTTP 400` before any SSE event is emitted.

## Next steps

- [Add a content safety guardrail to a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/add-hosted-agent-guardrails) — set a guardrail with `azd`, the Python SDK, or REST
- [Guardrails and controls overview](https://learn.microsoft.com/en-us/azure/foundry/guardrails/guardrails-overview) — what guardrails are and the risks they detect
- [Basic hosted agent](../01-basic/) — the agent this sample builds on
- [Manage hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent) — monitor and manage deployed agents
