# LangGraph Agent-to-Agent (A2A) on Foundry hosted agents

A two-agent [LangGraph](https://langchain-ai.github.io/langgraph/) sample that
demonstrates the **agent-to-agent (A2A)** delegation pattern on Microsoft
Foundry hosted agents, over the **Responses protocol**.

It shows how one hosted agent can call another.

## The two agents

| Folder | Agent | Role |
| --- | --- | --- |
| [`a2a-executor/`](a2a-executor/README.md) | `math-expert` | **Math expert.** A Responses agent that *also* publishes an **incoming A2A** endpoint + agent card (declared in `azure.yaml`). |
| [`a2a-caller/`](a2a-caller/README.md) | `concierge` | **Concierge.** A Responses agent that **delegates** math questions to the executor through a Foundry **Toolbox** `a2a_preview` tool loaded over MCP. |

### How A2A is wired

- **Executor (incoming A2A)** — the agent *code* is a plain LangGraph Responses
  agent. A2A is added **declaratively** in
  [`a2a-executor/azure.yaml`](a2a-executor/azure.yaml) via `agent_endpoint`
  (adds the `a2a` protocol) + `agent_card` (the discovery document). `azd deploy`
  applies both at agent create time — no setup script.
- **Caller (outgoing A2A)** — declares a `RemoteA2A` **connection** pointing at
  the executor's A2A endpoint plus a **toolbox** with an `a2a_preview` tool, both
  in [`a2a-caller/azure.yaml`](a2a-caller/azure.yaml). At
  runtime the container loads the toolbox over MCP
  (`langchain-mcp-adapters` → `MultiServerMCPClient`) and hands the
  `math_expert` tool to LangGraph.

## Scaffolding into an azd project

Each agent is self-contained (its `azure.yaml` sits next to its code),
so you scaffold a fresh azd project from these manifests with
`azd ai agent init -t <manifest>`. Because the caller's A2A connection must point
at the executor's *live* endpoint, the executor is **provisioned and deployed
first** — then the caller is added and pointed at the real endpoint.

### Step 1 — Scaffold, provision, and deploy the executor

From an **empty directory**:

```bash
# Adopts the sample's azure.yaml + src/math-expert
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/a2a/a2a-executor/azure.yaml

# Provision the Foundry project and deploy the executor
cd math-expert   # init roots the project in this subfolder
azd up
```

> [!NOTE]
> If you've already cloned this repository, pass a local path to the manifest instead:
> `azd ai agent init -t <path-to-repo>/samples/python/hosted-agents/langgraph/a2a/a2a-executor/azure.yaml`

### Step 2 — Capture the executor's A2A endpoint

```bash
endpoint=$(azd env get-value FOUNDRY_PROJECT_ENDPOINT)
executorA2A="$endpoint/agents/math-expert/endpoint/protocols/a2a/"
echo "$executorA2A"   # copy this value
```

Or in PowerShell:

```powershell
$endpoint = azd env get-value FOUNDRY_PROJECT_ENDPOINT
$executorA2A = "$endpoint/agents/math-expert/endpoint/protocols/a2a/"
$executorA2A   # copy this value
```

### Step 3 — Add the caller and point it at the real endpoint

```bash
# Run from inside the same project root (where azure.yaml is located) created in Step 1
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/a2a/a2a-caller/azure.yaml
```

At the `a2a_executor_endpoint` prompt, paste the `$executorA2A` value from
Step 2. Because the executor already exists, this is a real, working URL.

```bash
# Deploy the caller (its connection target is already correct)
azd up
```

`azd ai agent init` copies each agent's source into `src/<agent-name>/` and adds
a service to `azure.yaml`, translating the manifest `resources` (model,
connection, toolbox) into `azure.yaml` config.

## Try it

```bash
azd ai agent invoke concierge '{"input":"What is 15 multiplied by 23?"}'
# -> "15 multiplied by 23 is 345." (computed by the remote math expert)
```

Verify the executor's published A2A card:

```bash
tok=$(az account get-access-token --resource "https://ai.azure.com" --query accessToken -o tsv)
ep=$(azd env get-value FOUNDRY_PROJECT_ENDPOINT)
curl -s -H "Authorization: Bearer $tok" \
    "$ep/agents/math-expert/endpoint/protocols/a2a/agentCard/v1.0" | jq
```

Or in PowerShell:

```powershell
$tok = az account get-access-token --resource "https://ai.azure.com" --query accessToken -o tsv
$ep  = azd env get-value FOUNDRY_PROJECT_ENDPOINT
Invoke-RestMethod -Uri "$ep/agents/math-expert/endpoint/protocols/a2a/agentCard/v1.0" `
    -Headers @{ Authorization = "Bearer $tok" } | ConvertTo-Json -Depth 8
```

## Requirements

- azd `azure.ai.agents` extension **>= 0.1.30** (declarative `agent_endpoint` /
  `agent_card`). Validated with **0.1.37-preview**.
- A region with Foundry hosted agents + Responses (e.g. `northcentralus`).

## A2A protocol version

Foundry serves both A2A **v1.0** (recommended) and **v0.3** on the same base
path (`…/endpoint/protocols/a2a`); the agent card you fetch selects the version.
The executor authors its `agent_card` once and Foundry projects it into both the
v1.0 and v0.3 card shapes. This sample's caller targets **v1.0** — its connection
`AgentCardPath` and toolbox `agent_card_path` point at `agentCard/v1.0`, so the
delegation tool negotiates v1.0 end to end. To target v0.3 instead, change both
to `agentCard/v0.3`. Note that A2A v1.0 uses the **JSONRPC** transport. See
[Enable incoming A2A on a Foundry agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint).
