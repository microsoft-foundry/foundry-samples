# What this sample demonstrates

Three **Copilot SDK** agents collaborate over native **A2A 1.0**, using
**Foundry Toolbox** to connect the Travel Planner to Flight and Hotel agents.

| Agent | Responsibility |
|---|---|
| Travel Planner | Uses the Copilot SDK to discover Toolbox tools, ask both specialists, compare their answers and calculate the combined trip budget. |
| Flight Agent | Uses the Copilot SDK to reason over raw dummy flights and calculate fares, taxes and baggage. |
| Hotel Agent | Uses the Copilot SDK to reason over raw dummy hotels and calculate nights, rooms, taxes and stay fees. |

**The LLMs make all travel decisions and calculations. Python does not
recalculate prices, verify eligibility or correct model answers.** Python only
hosts A2A Tasks and calls the SDK. Model output can contain mistakes.
All prices are synthetic; no bookings, reservations or payments are created.

## How it works

```text
User --A2A--> Travel Planner (Copilot SDK)
                  |
                  +-- SDK-managed Toolbox MCP discovery and tool calls
                           |-- A2A --> Flight Agent (Copilot SDK + dummy flights)
                           `-- A2A --> Hotel Agent  (Copilot SDK + dummy hotels)
                  |
User <-- A2A Task artifact containing a readable travel recommendation
```

The Copilot SDK owns the model/tool loop. There is no custom model HTTP client,
manual MCP parser, structured-price validator or Python itinerary algorithm.
The SDK uses a Foundry BYOK `ProviderConfig` and custom tools, matching the Copilot Activity
sample's authentication pattern. Trusted platform context accompanies model
and Toolbox requests. No GitHub token is required for this Foundry model path.

The small planner [tools.py](src/travel-agent/tools.py) adapter uses the standard
MCP client to discover A2A operations and forwards the SDK's text messages to them.
It does not implement a reasoning loop or direct agent HTTP calls.
The planner discovers agents exposed by the configured Toolbox, not arbitrary
agents globally. Only Toolbox-backed custom tools are enabled for the planner; built-in
shell, file and calculator tools are not enabled. Specialists have no tools.
Each request gets an isolated SDK session which is disconnected afterward.
The SDK runtime process is stopped after the request.

## Files

```text
travel-planner/
|-- azure.yaml
|-- toolbox.json
|-- trip-request.json
`-- src/
    |-- travel-agent/
    |   |-- main.py          # A2A executor and planner instructions
    |   |-- client.py        # Copilot SDK session and Toolbox MCP configuration
    |   |-- tools.py         # Thin standard-MCP adapters for discovered A2A tools
    |   |-- pyproject.toml
    |   `-- uv.lock
    |-- flight-agent/
    |   |-- main.py          # A2A executor and flight instructions
    |   |-- client.py        # Independently packaged SDK client
    |   |-- catalog.py       # Raw dummy flights only
    |   |-- pyproject.toml
    |   `-- uv.lock
    `-- hotel-agent/
        |-- main.py          # A2A executor and hotel instructions
        |-- client.py        # Independently packaged SDK client
        |-- catalog.py       # Raw dummy hotels only
        |-- pyproject.toml
        `-- uv.lock
```

One manifest deploys three separate agents with their own endpoints and versions.
There is no role switch, sample tests folder, test client or dedicated test workflow.

## Prerequisites

- Python **3.13** for the configured hosted runtime; packages require **3.11+**
  because of the Copilot SDK.
- azd **1.37.2** and agent extension **1.0.0-beta.23**.
- A Foundry project enabled for native A2A, hosted Task storage and Toolbox A2A 1.0.
  Create a project first if you do not already have one.
- An existing **`gpt-5-nano`** model deployment and permission to use it.
- Permission to deploy agents and create connections/Toolboxes.
- The Copilot SDK's supported runtime must be available. The pinned SDK includes
  its CLI runtime; dependencies and deployment must support executing it.

All three agents use the same model deployment independently. This is not
exactly three API calls: the planner's SDK can make multiple tool-loop calls.
Keep the committed dependency locks. Existing AgentServer alpha-source policy
requirements still apply; do not bypass repository checks.

## Deploy and run

### 1. Sign in and initialize

```powershell
azd extension update azure.ai.agents --version 1.0.0-beta.23 --source azd
azd auth login
$env:AZD_ALPHA_ENABLE_AGENTS_A2A = "true"

azd ai agent init --src . `
    -t "https://github.com/Hameedkunkanoor/foundry-samples/blob/feature/a2a-llm-release-planner/samples/python/hosted-agents/bring-your-own/a2a/travel-planner/azure.yaml" `
    --project-id "<PROJECT-ARM-ID>"
```

Run initialization in an empty folder. In the adopted [azure.yaml](azure.yaml),
change service-level agent `name` values to unique names. Keep the service keys
`flights`, `hotels` and `planner` unchanged.

```powershell
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME gpt-5-nano
azd deploy flights
azd deploy hotels
azd ai agent show flights --output json
azd ai agent show hotels --output json
```

Both specialists must be active. Copy their A2A base URLs, omitting the
`?api-version=v1` query. Do not use a Card or Responses URL.

### 2. Register specialist connections

These register already-deployed agent URLs and authentication settings.
They do not create new agents or invoke them.

```powershell
azd ai connection create travel-flights-conn-youralias-01 --kind remote-a2a `
    --target "<FLIGHT-A2A-BASE-URL>" --auth-type user-entra-token `
    --audience "https://ai.azure.com" --project-endpoint "<PROJECT-ENDPOINT>" --output json

azd ai connection create travel-hotels-conn-youralias-01 --kind remote-a2a `
    --target "<HOTEL-A2A-BASE-URL>" --auth-type user-entra-token `
    --audience "https://ai.azure.com" --project-endpoint "<PROJECT-ENDPOINT>" --output json
```

### 3. Create Toolbox and deploy planner

Edit [toolbox.json](toolbox.json): choose a unique Toolbox name and replace
connection IDs with `<PROJECT-ARM-ID>/connections/<CONNECTION-NAME>`.
Keep explicit `type: "a2a"` and `a2a_version: "1.0"`.

```powershell
azd ai toolbox create travel-tools-youralias-01 --from-file toolbox.json `
    --project-endpoint "<PROJECT-ENDPOINT>" --output json

azd env set TOOLBOX_ENDPOINT "<RETURNED-VERSIONED-MCP-ENDPOINT>"
azd deploy planner
azd ai agent show planner --output json
```

Resolve missing permissions with the project owner. Do not provision over a shared
project or inject tokens into source files.

### 4. Invoke

Use the planner's actual name and deployed version:

```powershell
azd ai agent invoke <PLANNER-AGENT-NAME> -p a2a --a2a-version 1.0 `
    --version 1 --new-session --input-file trip-request.json --output raw
```

Or send a request directly:

```powershell
azd ai agent invoke <PLANNER-AGENT-NAME> -p a2a --a2a-version 1.0 `
    --version 1 --new-session --output raw `
    "Plan a synthetic trip for 1 traveler SFO to SEA, departing 2027-01-10 and returning 2027-01-13. Arrive before 2027-01-11T09:00:00-08:00. Both flight and hotel must be refundable. Hotel within 3000 meters of the office. Total budget USD 1200. Do not book."
```

The completed Task artifact is **readable Markdown**, not a JSON itinerary.
For the supplied dummy data the expected recommendation is FLIGHT-102 ($440)
and HOTEL-202 ($725), total $1,165, remaining $35. These are expected values for
manual inspection, not values enforced or recalculated by Python.

Try a $900 budget, three travelers/$3,000, an earlier arrival deadline or missing
dates. The LLMs should explain no-match, calculate multiple rooms or ask for
clarification as appropriate. Inspect the Task state and artifact; HTTP 200 alone
is not proof of success.

## Local run

Run each agent from its own source folder with its own `PORT`, project endpoint
and model deployment. The planner additionally needs `TOOLBOX_ENDPOINT`.

```powershell
az login
$env:FOUNDRY_PROJECT_ENDPOINT = "<PROJECT-ENDPOINT>"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME = "gpt-5-nano"
$env:TOOLBOX_ENDPOINT = "<TOOLBOX-MCP-ENDPOINT>"
$env:PORT = "8088"
uv run --frozen --python 3.13 python main.py
```

Local planner calls still use the managed Toolbox and hosted specialist targets.
Stop the server with Ctrl+C afterward.

## Cleanup

Delete only your agents, Toolbox and connections through the normal project
cleanup process. Do not run `azd down` on a shared project or delete a shared model.
