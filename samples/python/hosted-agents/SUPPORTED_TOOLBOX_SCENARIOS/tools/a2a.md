# A2A (Agent-to-Agent)

Configure a Foundry-hosted caller agent to delegate requests to a remote A2A-compatible agent
through a Foundry Toolbox.

> This page covers the caller-side `azure.yaml`. The configuration comes from the validated
> [A2A delegation sample](../../agent-framework/a2a/01-delegation/). Use the sample's
> [caller `azure.yaml`](../../agent-framework/a2a/01-delegation/caller/azure.yaml) as the source of
> truth.

## Prerequisites

- A remote agent with an incoming A2A endpoint and agent card. The
  [sample executor](../../agent-framework/a2a/01-delegation/executor/) demonstrates how to enable
  incoming A2A on a Foundry-hosted Responses agent.
- The remote agent's A2A endpoint URL.
- A caller implementation that reads `TOOLBOX_NAME` and connects to the named Foundry Toolbox.

## Configure the caller in `azure.yaml`

The caller's `azure.yaml` declares the project, remote A2A connection, toolbox, and hosted caller
agent together:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/Azure/azure-dev/main/schemas/v1.0/azure.yaml.json

requiredVersions:
  azd: '>=1.27.1'
  extensions:
    azure.ai.agents: '>=1.0.0-beta.9'
name: agent-framework-a2a-caller-responses
services:
  ai-project:
    host: azure.ai.project
    deployments:
      - name: gpt-5.4-mini
        model:
          format: OpenAI
          name: gpt-5.4-mini
          version: '2026-03-17'
        sku:
          name: GlobalStandard
          capacity: 10
  math-expert-a2a:
    host: azure.ai.connection
    uses:
      - ai-project
    category: RemoteA2A
    target: '${a2a_executor_endpoint}'
    authType: UserEntraToken
    audience: https://ai.azure.com
    metadata:
      AgentCardPath: /agentCard/v0.3
  a2a-delegation-tools:
    host: azure.ai.toolbox
    uses:
      - ai-project
      - math-expert-a2a
    description: Toolbox exposing the math-expert A2A executor agent.
    tools:
      - type: a2a_preview
        name: math_expert
        description: Delegates arithmetic and math questions to the math-expert A2A agent.
        connection: math-expert-a2a
        agent_card_path: agentCard/v0.3
  agent-framework-a2a-caller-responses:
    host: azure.ai.agent
    metadata:
      tags:
        - Agent Framework
        - AI Agent Hosting
        - Azure AI AgentServer
        - Responses Protocol
        - A2A
    project: src/agent-framework-a2a-caller-responses
    language: python
    codeConfiguration:
      runtime: python_3_13
      entryPoint: main.py
    uses:
      - ai-project
      - math-expert-a2a
      - a2a-delegation-tools
    kind: hosted
    name: agent-framework-a2a-caller-responses
    description: An Agent Framework hosted agent (Responses protocol) that delegates tasks to a Foundry-hosted A2A executor agent through a Foundry Toolbox A2A connection.
    protocols:
      - protocol: responses
        version: 2.0.0
    env:
      PYTHONNOUSERSITE: "1"
      AZURE_AI_MODEL_DEPLOYMENT_NAME: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}
      TOOLBOX_NAME: ${TOOLBOX_NAME}
    container:
      resources:
        cpu: '0.5'
        memory: 1Gi
infra:
  provider: microsoft.foundry
```

### Remote A2A connection

The `math-expert-a2a` service defines how Foundry reaches the remote agent:

| Field | Purpose |
|-------|---------|
| `host: azure.ai.connection` | Declares a Foundry project connection. |
| `uses: [ai-project]` | Creates the connection in the same Foundry project as the caller. |
| `category: RemoteA2A` | Identifies the target as an A2A agent. |
| `target: '${a2a_executor_endpoint}'` | Prompts for and stores the remote A2A endpoint during project initialization. |
| `authType: UserEntraToken` | Forwards the calling user's Microsoft Entra token to the remote agent. |
| `audience: https://ai.azure.com` | Requests a token accepted by the Foundry-hosted A2A endpoint. |
| `metadata.AgentCardPath` | Locates the remote agent card used for A2A capability discovery. |

### A2A toolbox

The `a2a-delegation-tools` service exposes the remote connection as a toolbox tool:

| Field | Purpose |
|-------|---------|
| `host: azure.ai.toolbox` | Declares a Foundry Toolbox. |
| `uses` | Ensures the toolbox is created in `ai-project` after `math-expert-a2a`. |
| `type: a2a_preview` | Adds the A2A tool type. |
| `name` and `description` | Tell the model when to delegate to the remote agent. |
| `connection: math-expert-a2a` | References the `azure.ai.connection` service by name. |
| `agent_card_path: agentCard/v0.3` | Identifies the agent card path exposed by the remote endpoint. |

Use `connection`, not the legacy `project_connection_id`, when the connection is another service in
the same `azure.yaml`.

### Hosted caller agent

The caller agent lists the project, connection, and toolbox under `uses`, so `azd` provisions the
dependencies before the agent. Its environment variables use the current `env` map schema:

```yaml
uses:
  - ai-project
  - math-expert-a2a
  - a2a-delegation-tools
env:
  PYTHONNOUSERSITE: "1"
  AZURE_AI_MODEL_DEPLOYMENT_NAME: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}
  TOOLBOX_NAME: ${TOOLBOX_NAME}
```

The caller code uses `TOOLBOX_NAME` to find the toolbox. Foundry then discovers the
`a2a_preview` tool and executes A2A calls through the server-side connection.

## References

- [A2A delegation sample](../../agent-framework/a2a/01-delegation/)
- [Enable incoming A2A on a Foundry agent](https://learn.microsoft.com/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint)
- [Connect to an A2A agent endpoint](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/agent-to-agent)
