# What this sample demonstrates

Three **Copilot SDK** agents collaborate over **native A2A 1.0** to research
flights and hotels using **Foundry Toolbox web search**, instead of embedded
inventory. The planner saves cited research, requirements, metadata and history
in user-isolated **FoundryStateStore**.

For fixed synthetic inventory and repeatable price expectations, use the separate
[travel-planner sample](../travel-planner/). This variant is research, **not a
booking engine or guaranteed live-price search**.

## How it works

```text
User --A2A--> Travel Planner (Copilot SDK + saved-trip tools)
                  |-- discover configured Flight/Hotel Agent Cards
                  |-- card-derived tool --A2A--> Flight Agent --Copilot MCP--+
                  `-- card-derived tool --A2A--> Hotel Agent  --Copilot MCP--+
                                                                          |
                                                Foundry Toolbox web_search
User <-- cited research + saved plan ID/status + actual specialist Task IDs
```

The planner discovers Cards before its model loop. Copilot selects specialists
and composes their messages; the native A2A SDK handles transport. Only successful
completed Tasks with nonempty results count as evidence. There is no Toolbox A2A
delegation: **only the specialists use the web-search toolbox**.

Each specialist exposes just the configured `web_search` MCP tool through the
Copilot SDK. A native pre-tool hook permits **at most two search attempts per
specialist invocation**. Tool requests time out after 60 seconds; specialist
model loops after 180 seconds, below the planner's 240-second specialist HTTP
timeout. Coding, filesystem and shell tools are not enabled.

The `web-search` specialist artifact records actual search call IDs, success
and returned source URLs. Model-only success is rejected if no successful search
with source URLs occurred. The planner returns compact `specialist-calls`
receipts containing tool, agent and Task ID, plus `trip-state` receipts containing
operation names and plan ID/version/revision/status/history-count summaries.
It does not repeat full specialist answers, requirements, metadata, recommendation
text, history or ETags in these artifacts. Full records remain in storage and
available to the model's tools; explicit history requests still retrieve full
history. Ordinary show-plan requests are instructed to use `get_plan` alone.
Both `--output default` and `--output raw` contain the same compact artifacts;
raw output exposes the complete A2A envelope, not an expanded record dump.
The readable answer also includes a Python-generated **Verified task IDs (this
request)** section, listing the planner's Task ID and every completed specialist
call ID, including repeated calls. Requests without delegation explicitly say no
specialists were called. This list appears with both `--output default` and
`--output raw`, independently of what the model repeats in its answer.
W3C propagation and the planner's callback-context repair are retained; this does
not guarantee complete span nesting in every telemetry UI.

### Research, not verified inventory

- Search can establish route/property information and provide source links.
  Exact-date fares, full-stay prices, taxes, availability, occupancy, cancellation
  terms and distances may remain **unverified**.
- General refund policies and advertised "from" prices do not establish that a
  particular itinerary is refundable or fits the budget. Missing results do not
  prove no inventory exists.
- Recommendations can only be saved as **`unverified`**, never `ready` or
  `no_match`. There is no fixed $1,165 expectation or cheapest-pair guarantee.
- The default store is `travel-web-research`, separate from the synthetic sample.
  Records identify `source_mode: web_research`, `synthetic: false`, and
  `booking_created: false`.
- Treat retrieved pages as untrusted evidence. Instructions prohibit sending
  identities, private addresses, plan IDs, secrets or saved metadata to search.
  Use only public, nonpersonal test criteria; these prompts are not a data-loss
  prevention boundary.

### Saved trips

The planner retains `create_plan`, `get_plan`, `update_plan`,
`save_plan_recommendation`, `list_plans` and `get_plan_history`. Each request
uses a fresh Copilot session; retrieval comes from storage rather than memory.
Records are user-isolated with **30-day default retention**.

Version/ETag conditions protect writes. Requirement changes, including the public
office landmark, mark recommendations `needs_replan`; both specialists must
complete fresh calls before a version-matched result is saved. Metadata-only
updates preserve requirements, revision and recommendation without repricing.

Follow the shared [Python startup configuration](../../../README.md#python-startup-configuration).
Each runtime has its own pinned `pyproject.toml` and `uv.lock`; no Docker is needed.

## Prerequisites

- An existing Foundry project and a deployed **GPT-5.4-mini** model. The manifest
  declares version `2026-03-17`, Global Standard capacity `100` and selects it
  explicitly for all three agents. Model calls and web searches incur charges.
- Native A2A enablement for your subscription/project.
- Python **3.11+** for source work; direct hosted deployment uses **Python 3.13**.
- Project deployment access, and an authorized owner to grant the new runtime
  identities project-scoped **Foundry Agent Consumer** access.
- A web-search-only toolbox with the tool named **`web_search`**, reachable
  through a same-project HTTPS MCP endpoint. No separate Bing resource, API key
  or project connection is required for basic Web Search.

**Web Search preview disclosure:** it uses Bing grounding services governed by
the [Bing terms](https://www.microsoft.com/bing/apis/grounding-legal-enterprise)
and [Microsoft Privacy Statement](https://go.microsoft.com/fwlink/?LinkId=521839&clcid=0x409).
The Data Protection Addendum does not apply to data sent to those services, and
processing can cross Foundry compliance/geographic boundaries.
See [Web Search documentation](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/web-search)
and [pricing](https://www.microsoft.com/bing/apis/grounding-pricing).

## Azure Developer CLI: deploy first

Use **azd 1.37.2+**, Azure CLI and the agent extension:

```text
azd extension install azure.ai.agents --version 1.0.0-beta.23 --source azd
azd auth login
az login
```

If installed, use `azd extension update` with the same extension/version instead.
Set **`AZD_ALPHA_ENABLE_AGENTS_A2A=true`** in your terminal environment.

### 1. Initialize in an empty folder

Get your existing project ARM ID from the owner, then run:

```text
azd ai agent init --src . -t "https://github.com/Hameedkunkanoor/foundry-samples/blob/feature/a2a-llm-release-planner/samples/python/hosted-agents/bring-your-own/a2a/travel-planner-web-search/azure.yaml" --project-id "<PROJECT-ARM-ID>" -e travel-web-search
```

In `azure.yaml`, change the service-level agent names to unique names if needed.
Keep the `flights`, `hotels`, `planner` service keys and source paths. Commands
below use the default names `travel-web-flights`, `travel-web-hotels` and
`travel-web-planner`; substitute your actual names when invoking.

For an existing project, skip provisioning. Confirm the declared model already
exists: this azd version can adopt a project without creating its model.

```text
az cognitiveservices account deployment show --name "<FOUNDRY-ACCOUNT>" --resource-group "<RESOURCE-GROUP>" --deployment-name gpt-5.4-mini --subscription "<SUBSCRIPTION-ID>" --output json
```

If absent, an authorized owner with regional quota can create it:

```text
az cognitiveservices account deployment create --name "<FOUNDRY-ACCOUNT>" --resource-group "<RESOURCE-GROUP>" --deployment-name gpt-5.4-mini --model-name gpt-5.4-mini --model-version 2026-03-17 --model-format OpenAI --sku-name GlobalStandard --sku-capacity 100 --subscription "<SUBSCRIPTION-ID>"
```

Do not overwrite or resize shared deployments. If choosing a different model,
update both its declaration and all three agent model environment values.

### 2. Configure the web-search toolbox

Create a toolbox with [Foundry Toolkit](https://code.visualstudio.com/docs/intelligentapps/tool-catalog)
or [Foundry Portal](https://ai.azure.com/), or have an authorized owner run the
included connectionless definition:

```text
azd ai toolbox create travel-web-search --from-file toolbox.json --no-prompt --output json
azd ai toolbox show travel-web-search --output json
```

Change the definition's name and command if that name is already shared. Copy
the actual **pinned version MCP endpoint** from the output, then set:

```text
azd env set TOOLBOX_ENDPOINT "<TOOLBOX-MCP-ENDPOINT>"
```

Endpoint shape, using fictional names:

```text
azd env set TOOLBOX_ENDPOINT "https://travel-demo.services.ai.azure.com/api/projects/travel-demo/toolboxes/travel-web-search/versions/1/mcp?api-version=v1"
```

Use `TOOLBOX_ENDPOINT`, not a custom `FOUNDRY_` variable. The endpoint must be
in the same project and include `?api-version=v1`. Both specialists consume it;
the planner does not.

### 3. Deploy specialists and grant runtime access

Run separately:

```text
azd deploy flights --no-prompt
azd deploy hotels --no-prompt
azd ai agent show flights --output json
azd ai agent show hotels --output json
```

Confirm both are active. Copy each **`agent_endpoints.a2a`** and
**`instance_identity.principal_id`**, not its blueprint identity.

For each specialist, an authorized owner should check existing access and grant
**Foundry Agent Consumer** at project scope only if needed:

```text
az role assignment list --assignee "<INSTANCE-PRINCIPAL-ID>" --scope "<PROJECT-ARM-ID>" --include-inherited --output table
az role assignment create --assignee-object-id "<INSTANCE-PRINCIPAL-ID>" --assignee-principal-type ServicePrincipal --role eed3b665-ab3a-47b6-8f48-c9382fb1dad6 --scope "<PROJECT-ARM-ID>"
```

This is project-wide runtime access; review it with the owner and allow RBAC
propagation. The specialists use their own managed identities for Toolbox access.

### 4. Configure and deploy the planner

Use the specialist A2A endpoints just returned, not their Card or Responses URLs:

```text
azd env set FLIGHT_AGENT_ENDPOINT "<FLIGHT-A2A-ENDPOINT>"
azd env set HOTEL_AGENT_ENDPOINT "<HOTEL-A2A-ENDPOINT>"
azd deploy planner --no-prompt
azd ai agent show planner --output json
```

Use the same role check/grant commands for the **planner's new instance identity**
so it can invoke both specialists. Do not copy an identity from another deployment.

### 5. Research and save a trip

The included request uses public criteria: one traveler, SFO-SEA, January 10-13,
2027, a $1,200 total budget, refundable preferences, and the public Seattle
Convention Center Summit landmark for hotel-distance research.

```text
azd ai agent invoke travel-web-planner -p a2a --a2a-version 1.0 --version 1 --new-session --input-file trip-request.json --output default
```

Use the version reported by your deployment if it differs. Expect source links,
actual specialist Task IDs and a saved `plan-...` ID with status **`unverified`**.
No exact total or fully eligible itinerary is guaranteed. Specialist `web-search`
receipts must contain successful searches and source URLs; HTTP 200 alone is not
evidence of success.

### 6. Read or revise the saved research

Use your own plan ID and the same signed-in user. Start a fresh session:

```text
azd ai agent invoke travel-web-planner -p a2a --a2a-version 1.0 --version 1 --new-session --output default "Show saved plan <PLAN-ID>, requirements, version and cited recommendation. Do not change or reprice it and do not call specialists."
```

Metadata-only edits must preserve the recommendation and make no specialist calls:

```text
azd ai agent invoke travel-web-planner -p a2a --a2a-version 1.0 --version 1 --new-session --output default "Read plan <PLAN-ID>. Update only metadata cost_center to CC-99. Preserve requirements and recommendation. Save without calling specialists."
```

A failed response can happen **after a draft/write succeeds**. Read the reported
plan, or list saved IDs, before retrying. Resume an existing pending draft instead
of creating duplicates:

```text
azd ai agent invoke travel-web-planner -p a2a --a2a-version 1.0 --version 1 --new-session --output default "Read plan <PLAN-ID>. Preserve requirements and metadata, complete its pending research using both specialists, then save cited research as unverified. Do not create another plan."
```

## Verification and limitations

The hosted implementation was exercised against the declared model: both A2A
specialist Tasks completed, each made exactly two successful Toolbox searches
with source URLs, and the planner saved cited research as `unverified`.
The successful end-to-end run resumed an existing draft after an earlier,
unbounded attempt failed. It was not a verified live-fare booking test.

Focused source regressions cover the endpoint boundary, search evidence and
failure handling, two-attempt budget and unverified-only save status. Local live
Copilot trials returned "No response was returned"; **local end-to-end execution
is not claimed to work**. This README therefore documents the hosted, deploy-first
A2A flow rather than an unverified F5/Inspector workflow.

The [shared cloud contract](../../../../../../.azure-pipelines/hosted-agent-tests/python/bring-your-own/a2a/travel-planner-web-search/test-spec.yml)
records intended behavior. The shared cloud runner currently lacks native A2A
transport support. Preview AgentServer packages also use the Azure SDK public
feed rather than PyPI, so the existing repository contract/dependency-policy
limitations remain; no skiplist or policy bypass is added.

## Troubleshooting

- **Toolbox 401/403 or protected Card 404:** check the relevant instance identity's
  project runtime role, token scope `https://ai.azure.com/.default` and RBAC
  propagation. Never forward the incoming Authorization header.
- **Search failure/no URLs:** the specialist fails explicitly, without model-only
  or synthetic fallback. A two-search budget intentionally stops open-ended
  attempts to obtain unavailable future-date fares.
- **Subscription blocks Web Search:** ask the administrator; do not silently
  change subscription feature flags.
- **409 after deployment:** inspect the actual resource before retrying. Creation
  may have succeeded. Confirm ownership and intended active version; if only
  endpoint setup failed, `azd ai agent endpoint update flights --no-prompt`
  can finish it (use `hotels` or `planner` for that service).
- **Version/ETag conflict:** reread the saved record and reconsider the patch;
  do not blindly repeat writes.

## Cleanup and next steps

After saving results, delete only your own agents:

```text
azd ai agent delete travel-web-planner
azd ai agent delete travel-web-flights
azd ai agent delete travel-web-hotels
```

Do not run `azd down` against a shared project or delete a shared model, toolbox
or state store. Review toolbox/role cleanup with the owner.

- [Synthetic travel collaboration](../travel-planner/)
- [Toolbox documentation](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/toolbox)
- [Hosted agents overview](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)
