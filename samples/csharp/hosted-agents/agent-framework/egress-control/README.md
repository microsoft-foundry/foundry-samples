# Egress Control Test Agent (.NET, Responses Protocol)

An [Agent Framework](https://github.com/microsoft/agent-framework) C# agent for testing **managed egress proxy policies** on Microsoft Foundry hosted agents. It is the .NET counterpart to the [Python egress-control sample](../../../../../python/hosted-agents/agent-framework/responses/18-egress-control/README.md).

## How it works

The agent registers an async C# `EgressTest` function tool with Agent Framework and hosts it through the Responses protocol. The tool uses `HttpClient` to make outbound requests and returns the status, response headers, and up to 4,000 characters of the body. Each request includes `X-Test-Marker` and a distinct `User-Agent`, allowing egress policies to demonstrate Allow, Deny, Transform, and Rewrite behavior.

The layered infrastructure in `azure.yaml` provisions the Foundry project first, then creates an RAI policy that denies all egress except `httpbin.org`. The policy's resource ID is attached to the hosted agent at deployment.

> Each invocation uses the configured model deployment to route the command to the tool. Add delays between repeated invocations if the model deployment returns rate-limit errors.

> TLS verification is enabled by default. When the platform supplies its Full
> inspection CA through `SSL_CERT_FILE`, the agent adds that CA to a custom
> validation chain rather than disabling certificate checks. Set
> `EGRESS_TEST_VERIFY_TLS=false` only as a diagnostic override.

### Supported commands

| Command | Description |
|---------|-------------|
| `test egress to <url>` | GET request; returns status and body |
| `test headers to <url>` | GET request; returns response headers and body |
| `test response headers from <url>` | GET request; returns response headers only |
| `test post to <url> <json>` | POST request with a JSON body |
| `test connectivity` | Probes httpbin.org, example.com, and google.com |
| `help` | Shows the command list |

## Prerequisites

1. An existing Foundry project with a deployed model, or permission to create them during setup.
2. [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0) or later.
3. Permission to create `Microsoft.CognitiveServices/accounts/raiPolicies` resources on the Foundry account.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

1. Install the [Azure Developer CLI](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd).
2. Install the Foundry extension and authenticate:

   ```bash
   azd ext install microsoft.foundry
   azd auth login
   ```

### Initialize and provision

```bash
mkdir my-dotnet-egress-agent && cd my-dotnet-egress-agent
azd ai agent init --deploy-mode container -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/agent-framework/egress-control/azure.yaml
azd provision
```

With `azure.ai.agents` 1.0.0-beta.16, the provisioned `RAI_POLICY_ID` is not interpolated inside
`policies.raiPolicyName`. Before `azd deploy`, run `azd env get-value RAI_POLICY_ID` and replace
`${RAI_POLICY_ID}` in the generated `azure.yaml` with that full ARM resource ID.

### Run and invoke locally

```bash
azd ai agent run
```

In another terminal:

```bash
azd ai agent invoke --local "test connectivity"
```

The local process is not subject to a hosted-agent egress policy, but it lets you verify command routing and response formatting.

### Deploy and invoke

```bash
azd deploy
azd ai agent invoke "test egress to https://httpbin.org/get"
azd ai agent invoke "test egress to https://example.com"
```

The first request should succeed and the second should be denied by the default policy.

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. Install [Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.azure-ai-foundry) and [C# Dev Kit](https://marketplace.visualstudio.com/items?itemName=ms-dotnettools.csdevkit).
2. Sign in to Azure in VS Code.

### Run locally

Copy `.env.example` to `.env`, set the Foundry project endpoint and model deployment, run `az login`, then start the project:

```bash
cd src/agent-framework-egress-control-responses-dotnet
dotnet run
```

Open **Foundry Toolkit: Open Agent Inspector** from the Command Palette and send one of the supported commands.

### Deploy

Run `azd up` from the sample root. This provisions the Foundry and egress layers before deploying the guarded agent. Invoke it from the Agent Playground after deployment.

## Customizing the policy

Edit `infra/egress/main.bicep` to change `defaultAction` or add first-match rules. An RAI policy can combine content filters with one `egressPolicy` containing multiple rules; the agent binds to one RAI policy resource.

For complete Allow, Deny, Transform, Rewrite, Audit, and managed-identity policy examples, see the [Python counterpart's policy catalog](../../../../../python/hosted-agents/agent-framework/responses/18-egress-control/infra/egress/main.bicep) and this sample's [scenario guide](scenarios/README.md). The scenarios deploy policies and agent versions against this .NET agent.

## Troubleshooting

- **`FOUNDRY_PROJECT_ENDPOINT environment variable is not set`**: run through `azd ai agent run`, or set the endpoint in `.env`.
- **A request unexpectedly fails TLS validation**: use `EGRESS_TEST_VERIFY_TLS=false` only for a TLS-intercepting Full inspection policy.
- **Both allowed and denied destinations succeed locally**: egress policies apply to the deployed hosted-agent container, not the local process.
- **Deploy says the RAI policy must be a fully qualified ARM resource ID**: materialize the
  provisioned `RAI_POLICY_ID` in the generated `azure.yaml` as described above.
- **Cleanup when using an existing project**: do not run `azd down`, because it can attempt to delete
  the shared resource group. Delete the test agent with `azd ai agent delete --force`, then delete
  only the provisioned RAI policy with authenticated `az rest`.

## Next steps

- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
