# LangGraph A2A Caller — Concierge (Responses)

A [LangGraph](https://langchain-ai.github.io/langgraph/) concierge agent hosted
on Foundry over the **Responses protocol** using
[`langchain_azure_ai.agents.hosting`](https://github.com/langchain-ai/langchain-azure/tree/main/libs/azure-ai/langchain_azure_ai/agents/hosting),
that **delegates specialist questions to a remote A2A agent** — the sibling
[`a2a-executor`](../a2a-executor/README.md) math expert.

This is the **caller** half of the A2A pair.

## How it works

### LangGraph agent

The agent is built with `langchain.agents.create_agent(model, tools=[...])` and
a concierge system prompt. The LLM decides when to call the delegation tool. See
[main.py](src/concierge/main.py).

### Delegation over A2A (the key part)

Delegation tools are loaded at startup from a Foundry **Toolbox** over MCP using
[`langchain-mcp-adapters`](https://github.com/langchain-ai/langchain-mcp-adapters):

```python
client = MultiServerMCPClient({
    "a2a-delegation": {
        "transport": "streamable_http",
        "url": f"{project_endpoint}/toolboxes/{toolbox_name}/mcp?api-version=v1",
        "auth": _ToolboxAuth(token_provider),  # fresh Entra token per request
    }
})
tools = await client.get_tools()
```

The toolbox itself is declared **declaratively** in
[azure.yaml](azure.yaml), not in code:

```yaml
resources:
  - kind: connection
    name: math-expert-a2a
    category: RemoteA2A
    authType: UserEntraToken
    audience: https://ai.azure.com
    target: "{{ a2a_executor_endpoint }}"   # the executor's A2A endpoint
    metadata:
      AgentCardPath: /agentCard/v1.0
  - kind: toolbox
    name: a2a-delegation-tools
    tools:
      - type: a2a_preview
        name: math_expert
        project_connection_id: math-expert-a2a
        agent_card_path: agentCard/v1.0
```

`azd` provisions the `RemoteA2A` connection + toolbox; the running container
loads the toolbox's `math_expert` tool over MCP and hands it to LangGraph.

### Agent hosting

The compiled graph is hosted with `ResponsesHostServer`, which exposes the
OpenAI-compatible Responses endpoint at `/responses`. Conversation state is
managed server-side by the platform via `previous_response_id`.

## Scaffolding into an azd project

The caller depends on the executor's *live* A2A endpoint, so the executor is
provisioned **first**, then the caller is pointed at the real endpoint. This
keeps everything within documented azd behavior — no placeholder, no two-phase
re-provision, no hook. Full steps are in the [parent README](../README.md);
in short:

```bash
# 1. Scaffold + deploy the executor
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/a2a/a2a-executor/azure.yaml
cd math-expert
azd up

# 2. Capture its real A2A endpoint
endpoint=$(azd env get-value FOUNDRY_PROJECT_ENDPOINT)
echo "$endpoint/agents/math-expert/endpoint/protocols/a2a/"

# 3. Add the caller; paste the value above at the a2a_executor_endpoint prompt
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/a2a/a2a-caller/azure.yaml
azd up
```

Or in PowerShell:

```powershell
# 1. Scaffold + deploy the executor
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/a2a/a2a-executor/azure.yaml
cd math-expert
azd up

# 2. Capture its real A2A endpoint
$endpoint = azd env get-value FOUNDRY_PROJECT_ENDPOINT
"$endpoint/agents/math-expert/endpoint/protocols/a2a/"

# 3. Add the caller; paste the value above at the a2a_executor_endpoint prompt
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/a2a/a2a-caller/azure.yaml
azd up
```

The caller manifest declares an `a2a_executor_endpoint` parameter. At init,
`azd ai agent init` writes whatever you type into the connection `target` in
`azure.yaml` **verbatim** — so paste the executor's *already-provisioned*
endpoint (Step 2). Because it already exists, it is a real, working URL.

> **Why provision-first?** The executor's A2A endpoint contains the Foundry
> account name, a non-deterministic resource token that does not exist until the
> project is provisioned. azd also does **not** expand `${...}` inside
> `config.connections.target`. Standing the executor up first means the value
> you paste is real, so no placeholder or two-phase patch is needed.

## Try it

After both `azd up` runs complete:

```bash
azd ai agent invoke concierge '{"input":"What is 15 multiplied by 23?"}'
# -> "15 multiplied by 23 is 345." (computed by the remote math expert)
```
