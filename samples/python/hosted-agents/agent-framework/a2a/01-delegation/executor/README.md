# Executor agent — math expert exposed over A2A

A minimal Foundry-hosted [Agent Framework](https://github.com/microsoft/agent-framework) agent (Responses protocol) that answers arithmetic / math questions. Once deployed, you turn on **incoming A2A** so the [caller](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents/agent-framework/a2a/01-delegation/caller) (or any other A2A client) can reach it through Foundry's A2A endpoint.

For the full two-agent walkthrough, see the **[parent README](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/a2a/01-delegation/README.md)**.

## How it works

The agent uses `FoundryChatClient` for the model (Responses API on the project endpoint) and is hosted with `ResponsesHostServer` from the [Agent Framework Foundry hosting package](https://pypi.org/project/agent-framework-foundry-hosting/) on port `8088`.

By default a Responses-protocol agent is reachable only through Responses. **Enabling incoming A2A** is a per-agent PATCH (REST API or Python SDK only — no portal UI yet) that publishes an `agent_card` for client discovery and adds `a2a` to `agent_endpoint.protocols`. After that, the agent answers both Responses **and** A2A requests at the same endpoint.

The PATCH is performed by [`scripts/setup-a2a`](src/agent-framework-a2a-executor-responses/scripts/). This is the **only** step that has to happen out-of-band — `agent_card` and multi-protocol endpoints aren't AgentSchema concepts, so the manifest can't express them yet. The caller-side `RemoteA2A` connection and `a2a_preview` toolbox live in the [caller's manifest](../caller/azure.yaml) and are created by `azd provision` on the caller.

The script's hard-coded `agent_card` (skills, description, version) describes this math-expert specifically; edit it if you adapt the executor for a different task, since the caller's tool routing depends on the advertised skill descriptions.

A2A endpoints require Microsoft Entra ID auth (Foundry User role on the project). See [Enable incoming A2A](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint) for the underlying REST contract.

## Running locally

Follow [Running the Agent Host Locally](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/README.md#running-the-agent-host-locally). A2A is a Foundry-side feature, so a local run only exercises the Responses interface.

```bash
azd ai agent invoke --local "What is 15 multiplied by 23?"
```

## Deploying

See the [parent README](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/a2a/01-delegation/README.md) — `azd provision` + `azd deploy` to deploy the agent, then run [`scripts/setup-a2a`](src/agent-framework-a2a-executor-responses/scripts/) to enable incoming A2A. Copy the A2A endpoint URL it prints; you'll paste it into the caller's `azd ai agent init` prompt.
