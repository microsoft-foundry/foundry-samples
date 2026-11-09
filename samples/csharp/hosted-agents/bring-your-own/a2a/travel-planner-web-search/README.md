# Native A2A travel planner with web search (.NET)

## What this sample demonstrates

The .NET counterpart to [samples PR #1144](https://github.com/microsoft-foundry/foundry-samples/pull/1144):

- A Copilot SDK planner discovers Flight and Hotel Agent Cards and delegates
  directly through native A2A 1.0 clients, not Toolbox A2A or direct model HTTP.
- Specialists use Copilot's native MCP integration for Foundry Toolbox
  `web_search`, with at most two searches per invocation.
- Successful answers must cite actual search source URLs. Failed and source-less
  searches stay in receipts; no success-shaped fallback is returned.
- Trip requirements, metadata and recommendation history are versioned in
  `FoundryStateStore`, with user isolation, per-user bounded keys, 30-day TTL,
  explicit version checks and ETag protection.
- Saved research is **unverified**, not a guaranteed price, available inventory,
  refundable booking, reservation or payment.

Both public .NET A2A samples pin published AgentServer alpha
**`1.0.0-alpha.20261109.2`**. The sample-local [NuGet.Config](NuGet.Config)
uses the public Azure SDK development feed. No SDK source checkout is required.
The alpha includes SDK fixes through commit `c07c20bf0` and is not a stable release.
The runtime source folder also includes the feed configuration for independent
restoration after template initialization copies the application.

## How it works

```text
User --A2A--> Planner --card-discovered A2A--> Flight specialist
                     \--card-discovered A2A--> Hotel specialist
Specialists --Copilot native MCP--> Toolbox web_search
Planner --FoundryStateStore--> versioned trip research
```

One shared .NET application is deployed as **three distinct agents**.
`AGENT_ROLE` selects `planner`, `flights` or `hotels`. Each instance has its own
identity and model session. This avoids copying common C# runtime and policy
code between three source trees.

The planner collects missing public criteria before creating a plan. Tools
create/read/update that plan, send only its public requirements to specialists,
and save cited research only after both specialists return completed Tasks for
the same plan version. A newer requirement update makes an older research save
fail, rather than clearing the revision's pending refresh.

Actual planner/specialist Task IDs and saved plan/version/status appear in
readable output. `specialist-calls` and `trip-state` artifacts contain receipts.
The native A2A Task store is explicitly in memory; **trip research storage** is
separate. Stored plans do not imply A2A Task persistence across restarts, replay,
durable subscriptions or interrupted-executor recovery.

Hosted plans require a usable caller and Foundry call context and use
server-side user isolation. Local storage uses per-user hashed keys only as a
development partitioning convenience, not an authentication boundary.

The runtime forwards only Foundry call context and W3C trace headers to trusted
project endpoints. It never forwards the inbound user identity header.
Agent Card interface URLs are validated before attaching credentials; redirects,
cross-project endpoints and encoded/traversal paths are rejected.

## Prerequisites

- .NET 10 SDK and access to the Azure SDK development feed.
- azd >= 1.37.2 with `azure.ai.agents` >= 1.0.0-beta.23.
- A Foundry project supporting hosted agents, a Responses-compatible
  `gpt-5.4-mini` deployment, and deployment permissions.
- Foundry Toolbox with web_search enabled, using [toolbox.json](toolbox.json).
- Specialist instance identities must have access to the model and Toolbox.
  Planner identity needs Foundry Agent Consumer access to both specialists and
  access to user-isolated Foundry state storage.

Sign in manually when needed. Never place tokens or credentials in the manifest.
Copilot SDK `1.0.29` downloads and verifies its pinned CLI runtime during
build/publish for the target RID; the runtime is included in deployment output.
Use the package's documented mirror/preinstalled-binary options when GitHub
downloads are restricted.

## Build and offline tests

```powershell
dotnet build .\src\TravelAgents\TravelAgents.csproj
dotnet test .\tests\TravelSample.Tests\TravelSample.Tests.csproj
```

Tests cover URL trust, search admission/citations, plan validation, user
partitioning, history, metadata updates and stale research rejection. They do
not call a model, web search or Azure.

## Deploy with azd

Initialize an independent deployment copy using this manifest and your existing
project. Follow the current [Foundry hosted-agent deployment workflow](https://learn.microsoft.com/azure/ai-foundry/agents/concepts/hosted-agents?view=foundry).
The manifest requests bundled `.NET 10` deployment. Release builds default to
`linux-x64`, even on Windows, so the bundled Copilot CLI matches the hosted OS.
Debug builds use the local OS for development. An explicit runtime identifier
overrides the Release default.

From an independent deployment directory (not inside the template), initialize
the manifest using its absolute path:

```powershell
azd ai agent init -m "<absolute-path-to-this-sample>\azure.yaml" `
  --project-id "<existing-Foundry-project-ARM-resource-ID>" `
  --deploy-mode code --runtime dotnet_10 --entry-point TravelAgents.dll `
  --dep-resolution bundled --environment travel-dotnet-dev --no-prompt
```

Verify that the generated project retains all three services and their
`AGENT_ROLE` values before proceeding; initialization is not a deployment test.

In the deployment directory, create/configure the Toolbox using
`toolbox.json` and set its MCP endpoint:

```powershell
azd env set TOOLBOX_ENDPOINT "https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/<toolbox>/mcp?api-version=v1"
azd deploy flights --no-prompt
azd deploy hotels --no-prompt
```

Read the deployed specialists' endpoints. Set **their native A2A endpoints**,
not their general agent or model URLs:

```powershell
azd env set FLIGHT_AGENT_ENDPOINT "https://<account>.services.ai.azure.com/api/projects/<project>/agents/travel-web-flights-dotnet/endpoint/protocols/a2a?api-version=v1"
azd env set HOTEL_AGENT_ENDPOINT "https://<account>.services.ai.azure.com/api/projects/<project>/agents/travel-web-hotels-dotnet/endpoint/protocols/a2a?api-version=v1"
azd deploy planner --no-prompt
```

Verify role assignments for the actual deployed instance identities and allow
propagation before invoking. A card-discovery 404 can mask authorization failure.
The manifest's endpoint `responses` declaration matches the Python reference's
gateway compatibility setting; the application implements only A2A.

## Run locally

Run the same application in three terminals, setting a different `AGENT_ROLE`
and `PORT` in each. Local specialists still need authenticated Foundry model and
Toolbox access; only their A2A HTTP transport and state-store backend are local.

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT = "https://<account>.services.ai.azure.com/api/projects/<project>"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME = "gpt-5.4-mini"
$env:TOOLBOX_ENDPOINT = "$env:FOUNDRY_PROJECT_ENDPOINT/toolboxes/<toolbox>/mcp?api-version=v1"
$env:AGENT_ROLE = "flights" # use hotels on 8089, planner on 8090
$env:PORT = "8088"
$env:A2A_AGENT_URL = "http://localhost:8088/a2a"
dotnet run --project .\src\TravelAgents --no-launch-profile
```

For the planner terminal also set `FLIGHT_AGENT_ENDPOINT` to
`http://localhost:8088/a2a` and `HOTEL_AGENT_ENDPOINT` to
`http://localhost:8089/a2a`. Keep the advertised `A2A_AGENT_URL` consistent with
each instance's listening port.

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8090/a2a" `
  -ContentType application/json -Headers @{"A2A-Version"="1.0"} `
  -InFile .\trip-request.json -TimeoutSec 600
```

Require a completed native Task, an answer artifact with both specialist Task
IDs and an `unverified` saved plan receipt. HTTP 200 alone is not success: native
JSON-RPC errors and failed/incomplete Tasks must fail validation.
To revise a trip, send its actual returned plan ID and current version with
the changed criteria. Read by ID to inspect stored recommendation history.
Each specialist has a three-minute model/tool timeout. The planner has a
ten-minute overall timeout to cover both specialist calls and synthesis; use a
matching timeout in clients that send blocking requests.

## Web search data handling

Web Search is billed and uses Bing grounding services. Search queries leave
the model/agent processing boundary and may have distinct geographic,
data-residency and compliance terms. Review your organization's approval and the
[grounding/web search documentation](https://learn.microsoft.com/azure/ai-foundry/agents/how-to/tools/bing-grounding).
Send public travel criteria only: never private addresses, company information,
user identity, plan IDs, saved metadata, credentials or secrets.

## Troubleshooting and limits

- No successful cited search: the Task fails explicitly; no invented result.
- More than two searches: the hook denies additional calls.
- Plan version/ETag conflict: reread and research the new requirements, not an
  automatic retry that overwrites another request.
- Future quotes unavailable: return cited research labelled unverified, not a
  claim that no flights or rooms exist.
- Exact arrival, prices, currency, taxes, availability and refundability require
  evidence for the requested dates; do not infer them from generic pages.

The [cloud contract](../../../../../../.azure-pipelines/hosted-agent-tests/csharp/bring-your-own/a2a/travel-planner-web-search/test-spec.yml)
validates/plans as native A2A. Shared cloud execution additionally depends on a
native runner such as the support proposed in PR #1144, model enablement,
specialist endpoint wiring and Toolbox setup. Planning/offline tests are not a
fresh cloud deployment or proof of trace export/cross-user cloud isolation.

## Next steps

- Start with [Echo](../echo/) to verify hosting and native GetTask.
- Inspect actual Task and plan receipts, not merely generated model prose.
- Remove only your own deployment/session resources after testing.
