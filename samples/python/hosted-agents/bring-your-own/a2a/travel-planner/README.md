# What this sample demonstrates

A business traveler needs a refundable flight, a hotel near the office and a
trip that fits a budget. Three separate native A2A agents collaborate:

| Agent | Responsibility |
|---|---|
| **Travel Planner** | Uses `gpt-5-nano` to interpret the request, discover and select Toolbox tools, and explain the itinerary. |
| **Flight Agent** | Searches a synthetic round-trip inventory, including arrival time, taxes, baggage, refundability and seats. |
| **Hotel Agent** | Searches a synthetic hotel inventory, including distance, refundability, rooms, nights, taxes and stay fees. |

The planner uses **managed Foundry Toolbox A2A 1.0 tools only** for remote
discovery and calls. It does not fetch specialist Cards or call their URLs itself.
No real flights, live prices, reservations or payments are involved.

## How it works

```text
User --native A2A--> Travel Planner --Responses API--> gpt-5-nano
                         |
                         +-- Toolbox MCP tools/list --> discovered Flight/Hotel tools
                         |
                         +-- LLM tool choice --> Toolbox tools/call --A2A--> Flight Agent
                         +-- LLM tool choice --> Toolbox tools/call --A2A--> Hotel Agent
                         |
                         +-- verify both completed Tasks and catalog results
                         +-- LLM selection + explanation; code computes exact cost
User <-- completed A2A Task + itinerary + both specialist Task IDs
```

The three services share [one runtime](src/travel-a2a/main.py). `AGENT_ROLE`
selects their behavior. The native SDK owns Tasks and artifacts; the hosting
adapter selects caller-isolated Foundry Task storage when deployed.

[The planner](src/travel-a2a/planner.py) discovers actual operation names,
descriptions and message schemas through MCP. Toolbox configurations are named
`flight_options` and `hotel_options`; operation names are discovered, not hardcoded.
The model chooses those tools through bound-query adapters: normalized criteria
are encoded into the discovered A2A message shape by code, rather than rewritten
by the model. The planner verifies both real Task IDs, execution IDs, queries and
fixture results before accepting the cheapest eligible returned combination.
There is no direct A2A or model-only fallback.

Eligibility and budget arithmetic are code-authoritative. The final structured
model schema permits only valid cheapest returned IDs, or `no_match` with null
IDs when no eligible pair exists.
See the [Foundry A2A tool](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/agent-to-agent?pivots=python)
and [Toolbox](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/toolbox) documentation.

**Discovery means the tools in your configured Toolbox**, not a global search
for arbitrary agents. Foundry discovers the connected agents' Cards.
The planner only sends model/MCP requests inside the configured HTTPS project.
Authentication uses fresh managed credentials and trusted platform call context.
The tested connections use `UserEntraToken` for delegated user access; incoming
Authorization is never copied. App-only/other authentication modes require their
own access setup and are not covered by this walkthrough.

Each request is self-contained. If required details are missing, the planner asks
for clarification without calling specialists. Send the complete updated request;
this sample does not merge conversation history or perform bookings.

Follow the shared [Python startup configuration](../../../README.md#python-startup-configuration).

## Prerequisites

1. Python **3.13**, uv **0.11.7 or later**, azd **1.37.2** and agent extension
   **1.0.0-beta.23** are the tested toolchain.
2. A Foundry project enabled for native A2A, managed Task storage and A2A 1.0 tools.
   For a first-time setup, create a project before running the commands below.
3. An existing **`gpt-5-nano`** model deployment and permission to use it.
4. Permission to deploy/invoke agents and create project connections/Toolboxes.
   Ask the project owner to handle any required access; do not alter shared roles.

Three agents, sessions and model calls incur charges. Use synthetic data and do
not load test. Keep the committed project/lock: AgentServer A2A
`1.0.0a20261029006`, Core `2.3.1a20261029006`, native A2A `1.2.3`.
The existing repository alpha-feed policy gate still applies; no bypass is added.

## Option 1: Azure Developer CLI (`azd`)

### Install and sign in

Update the extension, or replace `update` with `install`:

```powershell
azd extension update azure.ai.agents --version 1.0.0-beta.23 --source azd
azd auth login
$env:AZD_ALPHA_ENABLE_AGENTS_A2A = "true"
```

### Initialize the agent project

From a fresh directory, adopt the local manifest from your checkout:

```powershell
azd ai agent init --src . -t "C:\path\to\travel-planner\azure.yaml" `
    --project-id "<PROJECT-ARM-ID>"
```

Open the adopted `azure.yaml` and change these three **`name` fields** to unique
names. Keep service keys, role values and source paths unchanged.

| Service key | Example unique `name` |
|---|---|
| `flights` | `travel-flights-youralias-01` |
| `hotels` | `travel-hotels-youralias-01` |
| `planner` | `travel-planner-youralias-01` |

```powershell
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME gpt-5-nano
azd deploy flights
azd deploy hotels
azd ai agent show flights --output json
azd ai agent show hotels --output json
```

Confirm both specialists are active. This uses existing infrastructure; do not
run `azd up` or `azd provision` against a shared project.

### Connect the specialists to a Toolbox

Use each specialist's native A2A base URL, **not its Card or Responses URL**.
The examples below omit the endpoint's `?api-version=v1` query.
Replace endpoint/project placeholders and choose unique connection names.

```powershell
azd ai connection create travel-flights-conn-youralias-01 --kind remote-a2a `
    --target "<FLIGHT-A2A-BASE-URL>" --auth-type user-entra-token `
    --audience "https://ai.azure.com" --project-endpoint "<PROJECT-ENDPOINT>" --output json

azd ai connection create travel-hotels-conn-youralias-01 --kind remote-a2a `
    --target "<HOTEL-A2A-BASE-URL>" --auth-type user-entra-token `
    --audience "https://ai.azure.com" --project-endpoint "<PROJECT-ENDPOINT>" --output json
```

Copy [toolbox.json](toolbox.json) into your adopted project. Set its Toolbox
`name` to a unique name and replace the two connection IDs. A connection ID is:

```text
<PROJECT-ARM-ID>/connections/<CONNECTION-NAME>
```

Keep configuration names `flight_options` and `hotel_options`.
**Keep `type: "a2a"` and `a2a_version: "1.0"`**. Beta.23's automatic
connection-to-tool mapping creates legacy `a2a_preview` entries, which failed
Card discovery for these native 1.0 agents during testing. Use the explicit tools.

On a shared project, skip automatic role grants; arrange access with its owner:

```powershell
$env:AZD_AGENT_SKIP_ROLE_ASSIGNMENTS = "true"
azd ai toolbox create travel-tools-youralias-01 --from-file toolbox.json `
    --project-endpoint "<PROJECT-ENDPOINT>" --output json
```

Copy the returned **versioned MCP endpoint** into the planner configuration:

```powershell
azd env set TOOLBOX_ENDPOINT "<TOOLBOX-MCP-ENDPOINT>"
azd deploy planner
azd ai agent show planner --output json
```

Toolbox endpoints look like
`<PROJECT-ENDPOINT>/toolboxes/<NAME>/versions/1/mcp?api-version=v1`.
There are no Flight/Hotel URLs in planner environment settings.

### Try a complete trip

Replace the name/version with your deployed planner:

```powershell
azd ai agent invoke travel-planner-youralias-01 -p a2a --a2a-version 1.0 `
    --version 1 --new-session --output raw `
    "Plan a synthetic business trip for 1 traveler from SFO to SEA. Depart 2027-01-10 and return 2027-01-13. Arrive before 2027-01-11T09:00:00-08:00. Both flight and hotel must be refundable. Hotel must be within 3000 meters of the office. Total flight and hotel budget is USD 1200. Do not book anything."
```

For file input, copy [trip-request.json](trip-request.json) into your project:

```powershell
azd ai agent invoke travel-planner-youralias-01 -p a2a --a2a-version 1.0 `
    --version 1 --new-session --input-file trip-request.json --output raw
```

Expected completed Task artifact:

| Check | Expected |
|---|---|
| Status | `proposed` |
| Flight | `FLIGHT-102`, refundable, arrives before the deadline |
| Hotel | `HOTEL-202` / Office Flex, refundable, 1,200 meters from office |
| Flight total | 44,000 cents = **$440** |
| Hotel total | 72,500 cents = **$725**, including 3 nights, taxes and stay fee |
| Combined total | `total_cents: 116500`, `total_usd: "1165.00"` |
| Remaining budget | 3,500 cents = **$35** |
| Delegation | `toolbox_verified: true`, Flight and Hotel entries with distinct remote Task IDs |
| Safety | `synthetic: true`, `booking_created: false` |

### More bug-bash scenarios

Repeat the full request with one change at a time:

| Change | Expected behavior |
|---|---|
| Budget **USD 900** | `no_match`; both specialists still ran; no invented cheaper option. |
| Budget **USD 1165** / **USD 1164.99** | Exact boundary: proposed / no-match. |
| Hotel within **500 meters**, budget USD 1200 | Only Premium Center meets distance/refundability; combined cost exceeds budget, so no-match. |
| Arrive before **2027-01-10T17:00:00-08:00** | No eligible flight; no-match after both tools. |
| **3 travelers**, budget USD 3000 | 2 hotel rooms, flight $1320 + hotel $1450 = **$2770**. |
| Remove dates or budget | `needs_clarification`, a question, no successful-delegation claim. |
| Ask to book/pay | Still a synthetic proposal only; no booking/payment created. |
| Configure a Toolbox missing either specialist | Explicit failure, not a model-only itinerary. |

Inspect the JSON-RPC body even for HTTP 200. `error`, failed Tasks, MCP
`isError`, incomplete model output or missing evidence are failures, not success.
Model prose and tool ordering can vary; check structured results, not exact prose.

## Option 2: Local planner with the managed Toolbox

Deploy/connect the two specialists as above. Only the planner runs locally;
outbound specialist calls still use the managed Toolbox.

From [src/travel-a2a](src/travel-a2a), sign in with Azure CLI and configure:

```powershell
az login
$env:AGENT_ROLE = "planner"
$env:PORT = "8088"
$env:FOUNDRY_PROJECT_ENDPOINT = "<PROJECT-ENDPOINT>"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME = "gpt-5-nano"
$env:TOOLBOX_ENDPOINT = "<TOOLBOX-MCP-ENDPOINT>"
uv run --frozen --python 3.13 python main.py
```

In a second terminal, from the same runtime folder:

```powershell
uv run --frozen --python 3.13 python test_client.py
```

The native client discovers the local planner, verifies its completed Task,
both specialist Task IDs and persisted `GetTask` result, then prints the JSON.

## Validation and troubleshooting

The following were tested: real model + managed Toolbox + hosted specialists;
fully hosted planner + Toolbox + both specialists; exact $1,165 golden itinerary;
USD 900 no-match; missing-input clarification; local native worker Tasks/GetTask.
Unit/contract tests separately cover failures, tampered results, budgets, capacity,
discovered names, JSON/SSE MCP responses and endpoint trust.

If discovery fails, verify explicit A2A 1.0 Toolbox entries and connection targets.
For authentication failures, verify delegated-user access and trusted platform
context; do not inject a static user token or add a direct-call fallback.
Use complete fixed-date requests: this catalog is not a live travel search.

## Clean up

Delete only your uniquely named planner, specialists, Toolbox and connections
using your project's normal cleanup process. Do not delete a shared project,
model deployment or another participant's resources.
