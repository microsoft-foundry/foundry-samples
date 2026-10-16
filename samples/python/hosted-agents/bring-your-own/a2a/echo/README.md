<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# What this sample demonstrates

A minimal native **A2A v1 echo agent** using the Bring Your Own approach in
Python. The native `a2a-sdk` owns the Agent Card, JSON-RPC, Task, artifact, and
executor behavior. `azure-ai-agentserver-a2a` adds Foundry's canonical routes,
request context, readiness, telemetry, and lifecycle.

## How it works

The executor creates an A2A Task, adds an artifact containing
`Echo: <message>`, and completes the Task. The host exposes:

```text
POST /invocations/a2a
GET  /invocations/a2a/.well-known/agent-card.json
GET  /readiness
```

[`test_client.py`](src/echo-a2a/test_client.py) uses the native A2A client for
Agent Card discovery and JSON-RPC validation against either the local server or
the public Foundry A2A endpoint.

> [!NOTE]
> `InMemoryTaskStore` is used only for this deterministic echo sample. Use a
> durable native A2A `TaskStore` for production workloads that must survive
> container restarts, suspension, or replica movement.

## Prerequisites

1. Python 3.13.
2. Azure Developer CLI 1.27.1 or later with the `azure.ai.agents` extension.
3. Azure CLI authentication for hosted E2E validation.

## Run and test locally

```powershell
cd src\echo-a2a
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python main.py
```

In another terminal:

```powershell
cd src\echo-a2a
.\.venv\Scripts\python test_client.py --message "hello"
```

Successful output includes:

```text
Echo: hello
```

## Deploy to Microsoft Foundry

From this sample directory:

```powershell
azd env new echo-a2a-dev
azd env set AZURE_SUBSCRIPTION_ID <subscription-id>
azd env set AZURE_LOCATION <supported-region>
azd provision
azd deploy
```

After deployment, get the project endpoint:

```powershell
$projectEndpoint = azd env get-value FOUNDRY_PROJECT_ENDPOINT
$endpoint = "$projectEndpoint/agents/echo-a2a/endpoint/protocols/a2a"
```

Run the dedicated hosted E2E client:

```powershell
cd src\echo-a2a
.\.venv\Scripts\python test_client.py `
  --endpoint $endpoint `
  --card-path agentCard/v1.0 `
  --azure-auth `
  --message "hosted hello"
```

The generic `azd ai agent invoke` and hosted-agent cloud test runner do not yet
implement A2A Agent Card discovery and JSON-RPC Task handling, so this sample
uses its dedicated native client.

## Troubleshooting

- **`JSON-RPC Error -32099: The requested A2A operation is not supported for
  this hosted-agent target`** — the project or subscription has not been
  enabled for native hosted-agent A2A passthrough. Agent Card discovery may
  still work through the A2A Head, but `SendMessage` will not reach the native
  container. The Vienna code references
  `AgentsPlatform.A2A.EnablePassthrough`, but its reviewed threat model requires
  passthrough to remain disabled pending a separate security/privacy review.
  This is a service-side ECS rollout controlled by the Foundry Agents team, not
  a flag customers can enable on their Azure subscription.
- **Agent Card says both `a2a` and `responses` are required** — keep both
  entries under `agentEndpoint.protocols` in `azure.yaml`. The container itself
  remains native A2A.
- **Agent Card is not defined** — keep the deployment-time `agentCard` metadata
  in `azure.yaml`; the native container card remains available at the canonical
  container route for passthrough.

## Next steps

- Replace `InMemoryTaskStore` with a durable native A2A `TaskStore`.
- Add skills and artifacts using native `a2a-sdk` types.
- Add another Agent Server protocol host to run multiple protocol paths in the
  same process.
