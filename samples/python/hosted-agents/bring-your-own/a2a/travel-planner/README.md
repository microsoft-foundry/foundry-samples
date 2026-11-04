# What this sample demonstrates

Three Copilot SDK agents collaborate over **direct native A2A 1.0**:

- **Flight Agent** reasons over raw dummy flights and calculates prices.
- **Hotel Agent** reasons over raw dummy hotels and calculates nights, rooms and fees.
- **Travel Planner** fetches the configured specialists' Agent Cards and exposes
  their descriptions and skills as Copilot custom tools. Its Copilot session
  selects which agent to call and composes the request. The native A2A client
  invokes the advertised interface and returns the actual answer to Copilot.
- The planner's LLM also saves and retrieves trips by **plan ID**, revises their
  requirements and metadata, and saves refreshed recommendations through
  user-isolated **FoundryStateStore** tools.

```text
User --A2A--> Travel Planner
                  |-- fetch configured Flight/Hotel Agent Cards
                  `-- Copilot SDK model/tool loop
                        |-- card-derived tool --A2A--> Flight Agent
                        |-- card-derived tool --A2A--> Hotel Agent
                        `-- combine actual answers and plan budget
User <-- readable recommendation in a completed A2A Task
```

**No Toolbox, MCP or project connections.** Only the two custom delegation tools
are enabled; no built-in coding tools. Card discovery runs before the planner
model, but specialist messages are sent only when the model selects a tool.
The two configured
endpoint URLs are discovery starting points; the native client invokes the
JSONRPC/A2A 1.0 URL advertised by each Card. URLs must stay in the configured
Foundry project (loopback is also allowed locally). Unsafe Card URLs fail rather
than receiving credentials. This is discovery of two configured agents, not a
global search.

All travel filtering, calculations, budget decisions and recommendations belong
to the LLMs. Python handles A2A transport, completed-Task checks and SDK sessions,
not price correctness. Dummy data only; no web search, real reservations or payments.
Hotel distances are already measured from the synthetic office in the inventory;
provide a distance limit in meters, not a real office address or coordinates.

## Files

```text
travel-planner/
|-- azure.yaml
|-- trip-request.json
`-- src/
    |-- travel-agent/   main.py, client.py, tools.py, agents.py, plan_store.py, pyproject.toml, uv.lock
    |-- flight-agent/   main.py, client.py, catalog.py, pyproject.toml, uv.lock
    `-- hotel-agent/    main.py, client.py, catalog.py, pyproject.toml, uv.lock
```

[agents.py](src/travel-agent/agents.py) owns authenticated Card discovery and native
A2A client construction. [tools.py](src/travel-agent/tools.py) turns each Card's
description and skills into a `consult_agent_N` tool, sends selected requests
through its A2A client and validates completed Tasks and nonempty answers.
Each agent's `client.py` uses Copilot SDK with a Foundry BYOK provider. Only the
planner registers custom delegation tools; specialists have no tools.
The planner returns a separate `specialist-calls` artifact with actual successful
tool results and Task IDs (empty for clarification without delegation).
The `trip-state` artifact contains acknowledged state-store operations and saved
records. A verified footer reports plan IDs, versions and statuses from actual
tool receipts rather than relying only on model prose.
Each request is self-contained; no conversation-history merge is implemented.
No sample tests or test client are included.

### Saved trips and revisions

The planner gets a fresh Copilot session for every request, but its state-store
tools retain trip data across sessions:

| Tool | Purpose |
|---|---|
| `create_plan` | Save complete requirements and optional JSON metadata; generate a `plan-...` ID |
| `get_plan` | Retrieve requirements, metadata, version, current recommendation/stale marker and history count |
| `update_plan` | Patch requested requirements or top-level metadata using the read version |
| `save_plan_recommendation` | Save ready/no-match model output with actual fresh specialist Task IDs |
| `list_plans` | List the caller's saved plan IDs, 20 per page |
| `get_plan_history` | Retrieve creation, changes and previous recommendations |

For a new complete trip, Copilot creates a draft, consults both specialists and
saves its recommendation. For existing trips, it reads the saved record instead
of pretending to remember earlier conversations. All writes must succeed before
the planner reports success.

Changing dates, route, budget, traveler count, refundability or distance increments
the **requirements revision** and marks the recommendation `needs_replan`.
The previous recommendation stays in history and is not current. The LLM then
queries both specialists with the revised requirements and saves a new `ready` or
`no_match` recommendation. A failed refresh leaves the saved requirements pending,
not falsely current; the failure includes acknowledged saved plan IDs.
Normal read/write tool results omit full history to avoid repeatedly sending old
recommendations to the model. Full records remain in storage and acknowledged
`trip-state` artifacts; `get_plan_history` retrieves the complete history.
If the model fails after a write (for example, on a rate limit), the failed Task
reports the last acknowledged plan ID/version/status. A failed final response does
not roll back an already acknowledged write.

Metadata-only changes increment the record **version** but preserve its
requirements revision and current recommendation. Metadata patches add or replace
top-level keys; `remove_metadata_keys` explicitly deletes keys. Nested values are
supported, but the model must preserve unmentioned nested fields when replacing
an object. Metadata is data, not instructions or hidden travel constraints.

Each update uses both the model's `expected_version` and the storage ETag.
Concurrent edits or a stale recommendation save fail with a precondition error,
so the LLM must reread and reconsider changes. A recommendation save also requires
both actual specialist calls after reading/changing that plan version.
Python validates storage shape, dates and write evidence, not model price arithmetic
or the semantic correctness of specialist queries.

The store defaults to `travel-plans`, user isolation enabled and 30-day item
retention. Change `TRAVEL_PLAN_STORE_NAME` in the planner's `azure.yaml` env map to
choose a different store. Existing stores must have isolation enabled; the sample
does not silently accept a shared store. Caller context is captured outside the
model and passed to storage calls. Locally the SDK uses its file-backed storage;
hosted requests use Foundry storage. No new Cosmos DB or external database is
required. Business plan IDs and native A2A Task IDs are separate.
Conditional writes use a specific `if_match` ETag. The SDK's `require_exists`
alternative is mutually exclusive with `if_match` and is not combined with it.

Metadata is limited to 16,000 serialized bytes and the whole record to 128,000
bytes. History is retained, never silently truncated; oversized writes fail
explicitly. Store only synthetic data, not credentials or real bookings.

### Tracing across Python, Copilot and the specialists

All three `client.py` files inject the active W3C trace context into the Copilot
BYOK provider's HTTP headers. Passing only the platform call ID is insufficient:
model calls can appear as separate two-span traces instead of joining the A2A
request. Outgoing native A2A requests also inject W3C headers.

The planner binds trusted platform headers and the incoming trace context before
Copilot dispatches callbacks. Each selected tool keeps the callback's parent when
it belongs to the same trace. If that parent is missing or belongs to another
trace, the tool restores the captured request context and logs the correction.
The selected context is attached around the A2A call and detached in `finally`,
including on failure. Context is captured per request so concurrent requests stay
isolated. The sample does not create custom discovery or delegation spans; native
SDK/platform instrumentation records the available invocation/model spans.
The application still repairs callback context and explicitly injects outgoing
headers: this is not a demonstration of fully automatic SDK-only tracing.

To check a run, use the **Trace ID printed by the A2A invocation**, not an older
model-only trace. In the project's linked App Insights, that operation should
contain planner activity and any invoked specialists under the same trace ID.
The exact set of tool, HTTP and model spans depends on runtime instrumentation,
sampling and export configuration. A clarification request may correctly contain
no tool or specialist invocations. Allow telemetry ingestion time.
Trace-context changes apply only to new requests; they cannot repair old traces.
App Insights correlation and the Foundry UI's rendered hierarchy are distinct:
gateway/internal spans and UI filtering may affect the displayed tree.

### Diagnostic logs

The planner uses Python `logging` to explain its lifecycle without adding spans:

| Event | Useful fields |
|---|---|
| `A2A_TRAVEL_STARTED` / `A2A_TRAVEL_COMPLETED` | Planner Task ID, trace ID, total duration, successful delegation count |
| `A2A_CARD_DISCOVERED` | Agent, protocol/version, discovery duration, trace ID |
| `A2A_CALLBACK_CONTEXT_RESTORED` | Agent/tool, tool-call ID, restoration reason, request/callback trace IDs |
| `A2A_REQUEST_STARTED` | Selected agent, A2A method, tool-call ID, trace/parent span IDs |
| `A2A_HTTP_REQUEST` | HTTP method, destination path, trace/parent span IDs, trace-header presence |
| `A2A_DELEGATION_COMPLETED` | Agent, actual remote Task ID/state, tool-call ID, duration, trace ID |
| `A2A_PLAN_COMPLETED` | Successful delegation count, planning duration, trace ID |
| `A2A_HTTP_FAILED` | HTTP status, destination path, response request ID, duration, trace ID |
| `A2A_CARD_DISCOVERY_FAILED`, `A2A_DELEGATION_FAILED`, `A2A_TRAVEL_FAILED` | Identifiers, exception type, duration, trace ID |

Durations use a monotonic clock. Sample-owned logs omit bearer tokens, raw headers,
URL query strings, user messages, specialist answers, HTTP response bodies and
arbitrary exception text. The `specialist-calls` result artifact intentionally
contains specialist answers; do not confuse that user-visible artifact with logs.
Third-party SDK/platform logging and telemetry have their own configuration.

Missing context does not mean no call happened: separate traces, completion logs
and actual Task IDs can still prove execution. Propagation connects those
operations to the originating planner trace. It does not create spans, grant
access or guarantee every internal operation is exported.

## Prerequisites

- azd 1.37.2, agent extension 1.0.0-beta.23, Python 3.13 hosted runtime.
- Existing Foundry project enabled for native A2A and Task storage.
- A `gpt-5.4-mini` deployment usable by all three agents, or permission/quota
  for an owner to create it as described below. Usage is billed at that model's rate.
- **Direct-call access:** the planner's agent-instance managed identity needs
  permission to read/invoke the specialists, such as Foundry Agent Consumer on the
  target project. Ask the owner to grant only required access. Earlier delegated
  Toolbox access does not establish this permission.

Hosted direct A2A selects `FOUNDRY_AGENT_INSTANCE_CLIENT_ID` explicitly and
forwards trusted platform context; local calls use DefaultAzureCredential.
Do not inject static user tokens or add a Toolbox fallback.
Package minimum is Python 3.11 for Copilot SDK. Keep committed locks; AgentServer
alpha-source and repository contract policy gates remain applicable.

### Model configuration

[azure.yaml](azure.yaml) declares `gpt-5.4-mini`, version `2026-03-17`,
`GlobalStandard`, capacity `100` (100,000 TPM and 100 RPM), and explicitly selects
that deployment in all three agents' environment maps. It is not selected through
an implicit model-name environment placeholder.

The same unchanged golden trip passed with this model: hotel Jan 10-13,
three nights at $725, flight $440, total $1,165, remaining $35, with an actual
saved plan and specialist Task receipts. The earlier nano run shifted hotel
check-in to Jan 11 and returned the wrong total. This is one successful comparison,
not a guarantee of every model response or a full larger-model regression.

For a new project managed by azd, the declaration describes the model required
by provisioning. **When referencing an existing project, the installed
1.0.0-beta.23 provider can report "nothing to provision" and skip model creation.**
The YAML declaration alone is not proof that the deployment exists.

For the existing-project flow below, have the owner verify that the model
deployment exists before deploying agents. If absent, an authorized owner with
available regional quota can create it in the project's parent Foundry account:

```text
az cognitiveservices account deployment create --name "<FOUNDRY-ACCOUNT>" --resource-group "<RESOURCE-GROUP>" --deployment-name gpt-5.4-mini --model-name gpt-5.4-mini --model-version 2026-03-17 --model-format OpenAI --sku-name GlobalStandard --sku-capacity 100 --subscription "<SUBSCRIPTION-ID>"
```

Do not overwrite an existing deployment or alter shared quota without approval.
To choose a different deployment, update the declaration and all three agents'
`AZURE_AI_MODEL_DEPLOYMENT_NAME` values together, then redeploy. Changing only
an azd environment value does not override the explicit values in this manifest.

## Deploy

From an empty directory:

```powershell
azd extension update azure.ai.agents --version 1.0.0-beta.23 --source azd
azd auth login
$env:AZD_ALPHA_ENABLE_AGENTS_A2A = "true"
azd ai agent init --src . `
    -t "https://github.com/Hameedkunkanoor/foundry-samples/blob/feature/a2a-llm-release-planner/samples/python/hosted-agents/bring-your-own/a2a/travel-planner/azure.yaml" `
    --project-id "<PROJECT-ARM-ID>"
```

Change the three service-level `name` values to unique agent names. Keep service
keys `flights`, `hotels`, `planner`, source paths and `codeConfiguration` unchanged.
No Dockerfile/local Docker is required.

```powershell
azd deploy flights
azd deploy hotels
azd ai agent show flights --output json
azd ai agent show hotels --output json
```

Copy each `agent_endpoints.a2a` URL:

```powershell
azd env set FLIGHT_AGENT_ENDPOINT "<FLIGHT-A2A-ENDPOINT>"
azd env set HOTEL_AGENT_ENDPOINT "<HOTEL-A2A-ENDPOINT>"
azd deploy planner
azd ai agent show planner --output json
```

### Grant the planner access to the specialists

**Required for hosted direct A2A:** the planner authenticates outbound calls as
its own agent-instance managed identity, not as the signed-in user. Deploying
the agents or granting your user access does not automatically grant this identity
access. Earlier Toolbox delegated-user access does not carry over.

After deploying the planner, an authorized project owner/RBAC administrator should
run the following from the deployment directory. Use `instance_identity.principal_id`,
not the blueprint identity or the developer's user ID:

```powershell
az login
$planner = azd ai agent show planner --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Cannot read the deployed planner" }
$project = azd env get-values --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Cannot read the azd environment" }
if (-not $planner.instance_identity.principal_id -or -not $project.AZURE_AI_PROJECT_ID) {
    throw "Planner instance identity or project ARM ID is missing"
}
az role assignment create `
    --assignee-object-id $planner.instance_identity.principal_id `
    --assignee-principal-type ServicePrincipal `
    --role "eed3b665-ab3a-47b6-8f48-c9382fb1dad6" `
    --scope $project.AZURE_AI_PROJECT_ID
if ($LASTEXITCODE -ne 0) { throw "Granting Foundry Agent Consumer failed" }
```

This is the built-in **Foundry Agent Consumer** role: endpoint interaction, not
project administration. The grant is project-scoped, not limited to these two
specialists. Review it with the owner before running on a shared project.
If the identity already has sufficient direct/inherited access, no new grant is
needed. Allow RBAC propagation before retrying a failed invocation; redeployment
is not required for a permission-only change. An inaccessible protected Card can
return **404**, even when the agent exists and your own local calls work.
Do not bypass this by embedding a user token or silently granting a broader role.

### Invoke

Use the actual deployed name/version:

```powershell
azd ai agent invoke <PLANNER-AGENT-NAME> -p a2a --a2a-version 1.0 `
    --version 1 --new-session --input-file trip-request.json --output raw
```

Expected model recommendation: FLIGHT-102 $440 + Office Flex $725 = $1,165,
remaining budget $35. Inspect the Task state and artifact, not HTTP200 alone.
A missing/inaccessible Card, incompatible interface or failed specialist must
fail the planner Task rather than producing a model-only success.

Try a $900 budget, three travelers/$3,000, earlier arrival or missing details.
The model decides when to delegate, no-match, room requirements or clarification;
arithmetic is not recomputed by Python. It composes specialist requests preserving
the user's dates and constraints, and must consult both before recommending a
complete itinerary. Failed calls fail the planner Task rather than allowing a
model-only success, even if the model subsequently offers a recommendation.

## Local planner with hosted specialists

From `src/travel-agent`:

```powershell
az login
$env:FOUNDRY_PROJECT_ENDPOINT = "<PROJECT-ENDPOINT>"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME = "gpt-5.4-mini"
$env:FLIGHT_AGENT_ENDPOINT = "<FLIGHT-A2A-ENDPOINT>"
$env:HOTEL_AGENT_ENDPOINT = "<HOTEL-A2A-ENDPOINT>"
$env:PORT = "8088"
uv run --frozen --python 3.13 python main.py
```

Local success uses your signed-in identity; it does not prove hosted managed
identity permissions. A 404 on a protected Card may mean missing access as well
as an incorrect URL. Resolve the cause rather than bypassing authentication.

## Revise a saved plan in fresh sessions

The initial complete-trip invocation now returns a generated plan ID. Use that
**plan ID**, not the A2A Task UUID, in later natural-language requests:

```powershell
azd ai agent invoke <PLANNER-AGENT-NAME> -p a2a --a2a-version 1.0 `
    --new-session --output raw `
    "Show saved plan <PLAN-ID>, including requirements, metadata and whether its recommendation is current."

azd ai agent invoke <PLANNER-AGENT-NAME> -p a2a --a2a-version 1.0 `
    --new-session --output raw `
    "For plan <PLAN-ID>, change departure to 2027-01-11, return to 2027-01-14 and arrival deadline to 2027-01-12T09:00:00-08:00. Keep other requirements, refresh both specialists and save the revised recommendation."

azd ai agent invoke <PLANNER-AGENT-NAME> -p a2a --a2a-version 1.0 `
    --new-session --output raw `
    'For plan <PLAN-ID>, add metadata cost_center "CC-42" and purpose "business". Do not change trip requirements or rerun specialists.'

azd ai agent invoke <PLANNER-AGENT-NAME> -p a2a --a2a-version 1.0 `
    --new-session --output raw "Show the saved change history for plan <PLAN-ID>."
```

The fixed synthetic catalogs do not guarantee options for changed dates. A saved
`no_match` result after a fresh search is valid; do not invent inventory to make
every revision succeed. Inspect `trip-state` receipts and the stored version,
requirements revision, metadata and specialist Task IDs independently of prose.

## Cleanup

Delete only your agents through the project's normal process. Existing Toolboxes
or connections from older versions are not used; do not delete shared resources.
Do not run `azd down` on a shared project or remove a shared model.
