# LangGraph A2A Executor — Math Expert (Responses)

A [LangGraph](https://langchain-ai.github.io/langgraph/) math-expert agent
hosted on Foundry over the **Responses protocol** using
[`langchain_azure_ai.agents.hosting`](https://github.com/langchain-ai/langchain-azure/tree/main/libs/azure-ai/langchain_azure_ai/agents/hosting),
that **also exposes an incoming A2A endpoint** so other Foundry agents can call
it agent-to-agent.

This is the **executor** half of the A2A pair. The
[`a2a-caller`](../a2a-caller/README.md) concierge delegates math questions to
this agent through Foundry's A2A gateway.

## How it works

### LangGraph agent

The agent is built with `langchain.agents.create_agent(model, tools=[...])`,
which returns a compiled LangGraph runnable implementing the standard ReAct loop.
It registers one local tool, `calculator`, and a math-expert system prompt. See
[main.py](src/math-expert/main.py).

### Agent hosting

The compiled graph is hosted with `ResponsesHostServer`, which exposes the
OpenAI-compatible Responses endpoint at `/responses` and handles conversation
history, streaming lifecycle events, and tool-call surfacing automatically.
Conversation state is managed server-side by the platform via
`previous_response_id`.

### Incoming A2A (the key part)

The agent **code** is a plain Responses agent. A2A is added **declaratively** in
[azure.yaml](azure.yaml) / [azure.yaml](azure.yaml):

```yaml
agent_endpoint:
  protocols:
    - responses
    - a2a
agent_card:
  description: A math expert that performs arithmetic operations and explains the steps
  version: 1.0.0
  skills:
    - id: arithmetic-and-math-expert
      name: Arithmetic and math expert
      description: Performs arithmetic operations ...
      tags: [math]
      examples:
        - What is 15 multiplied by 23?
```

`azd deploy` applies both at agent **create** time (requires azd `azure.ai.agents`
extension >= 0.1.30) — no out-of-band PATCH or setup script is needed. After
deploy, the agent card is served at:

```
<projectEndpoint>/agents/math-expert/endpoint/protocols/a2a/agentCard/v1.0
```

> **A2A protocol versions.** You author `agent_card` once; Foundry serves both
> A2A **v1.0** (recommended for new integrations) and **v0.3** on the same base
> path, projecting your card into each shape. The card *version* selects the
> protocol version — fetch `agentCard/v1.0` or `agentCard/v0.3` accordingly. This
> sample's caller targets v1.0. Note: A2A v1.0 uses the **JSONRPC** transport.

## Scaffolding into an azd project

From an empty directory:

```bash
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/a2a/a2a-executor/azure.yaml
```

> [!NOTE]
> If you've already cloned this repository, pass a local path to the manifest instead:
> `azd ai agent init -t <path-to-repo>/samples/python/hosted-agents/langgraph/a2a/a2a-executor/azure.yaml`

This copies the agent source into `src/math-expert/` and
wires it into `azure.yaml`. Add the caller next (see the
[parent README](../README.md)), then `azd up`.

## Try it

After `azd up` (see the [parent README](../README.md)):

```bash
azd ai agent invoke math-expert '{"input":"What is 15 multiplied by 23?"}'
```
