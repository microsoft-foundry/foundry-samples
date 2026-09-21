# What this sample demonstrates

This sample hosts the Agent Framework **"scaling its capabilities"** personal-finance harness agent
(Post 3 of *Build your own claw and agent harness*) through the Foundry **Responses** protocol v2. It
preserves the original agent instructions, tools, file skills, background research agent, confined
shell, CodeAct provider, and token limits while replacing the interactive console host with the native
Foundry `ResponsesHostServer`. File writes, shell commands, and simulated trades require approval.

**Source:** ported from [`claw_step03_scaling_capabilities.py`](https://github.com/microsoft/agent-framework/blob/main/python/samples/02-agents/harness/build_your_own_claw/claw_step03_scaling_capabilities.py)
in the Microsoft Agent Framework. The original runs the agent in an interactive console; this project
keeps the same instructions, agent configuration, seed data, and skills while replacing the console
host with the native Foundry Responses host.

## How it works

The agent is a personal-finance assistant built with `create_harness_agent`, hosted by
`ResponsesHostServer`. See `src/harness-scaling-capabilities-responses/main.py` for the
implementation. On top of file access and approvals it adds Post 3's four "scaling" capabilities:

- **Skills** — file-based finance skills (`valuation`, `risk-scoring`) under
  `src/harness-scaling-capabilities-responses/skills/`, loaded on demand and able to run their
  Python scripts via `subprocess_script_runner.py`. Optionally folds in centrally-managed
  **Foundry skills** from a Foundry Toolbox MCP endpoint (opt-in via
  `FOUNDRY_TOOLBOX_MCP_SERVER_URL`).
- **Shell** — a `LocalShellTool` confined to the trade-confirmation vault (`working/confirmations/`),
  used to reorganize the accumulated confirmation files. Guarded by a deny-list policy and a confined
  working directory, and exposed as the `run_shell` tool.
- **CodeAct** — a `MontyCodeActProvider` gives the agent a sandboxed, pure-Python interpreter to
  crunch portfolio numbers by writing and running code (no hardware virtualization required).
- **Background agents** — a lean, web-search-only `TickerResearchAgent` is registered via
  `background_agents`, exposing the `background_agents_*` tools so the main agent can fan out
  per-ticker research concurrently and aggregate the findings.

At startup, the bundled `src/harness-scaling-capabilities-responses/working/` seed data is copied
once to `$HOME/working`. File access and the confined shell both use that writable copy, while the
harness's session-scoped file memory uses `$HOME/agent-file-memory`. This keeps runtime writes out
of the read-only packaged source tree. Foundry injects `$HOME` for the hosted session, and that
filesystem persists across turns and idle periods; deleting the session removes it. Local runs fall
back to the current working directory when `$HOME` is unavailable.

The Responses host owns conversation history. Continue a conversation with `previous_response_id` (or
a conversation ID). File reads run without approval; file writes, shell commands, and the simulated
`place_trade` tool pause for approval.

### Approval policy

Read-only file operations have approval disabled so reading `portfolio.csv` is frictionless. The
source requires approval for file writes, `place_trade`, and every `run_shell` command, and this port
preserves that policy. The trade tool is simulated and places no real order. File writes are confined
to the session's writable working directory. The shell's deny-list and confined working directory are
additional guardrails, not a security boundary.

## Prerequisites

What the **sample itself** needs, independent of how you run it. The tooling for each run path (`azd`
or the VS Code Foundry Toolkit) is listed under its option below.

1. An existing Foundry project with a deployed model (or create them during setup in Option 1). The
   default deployment name is `gpt-5.4-mini`.
2. **Python 3.13 or later.**
3. **Environment variables:** `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME` (see
   `src/harness-scaling-capabilities-responses/.env.example`).
   `FOUNDRY_TOOLBOX_MCP_SERVER_URL` is optional — set it to enable centrally-managed Foundry skills;
   when unset, the agent runs with the local file skills only.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
2. Install the Foundry extension:

   ```bash
   azd ext install microsoft.foundry
   ```

3. Authenticate:

   ```bash
   azd auth login
   ```

### Initialize the agent project

No cloning required. Create a new folder and initialize from the manifest:

```bash
mkdir my-agent && cd my-agent
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/21-harness-scaling-capabilities/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an
existing Foundry project, `azd ai agent init` will guide you through creating one.

### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployment:

```bash
azd provision
```

### Run the agent locally

```bash
azd ai agent run
```

The agent host starts on `http://localhost:8088`.

### Invoke the local agent

This is a **harness agent**, so you work with it over several turns. The trajectory below walks every
capability the sample exposes, in the order the [original Agent Framework sample](https://github.com/microsoft/agent-framework/tree/main/python/samples/02-agents/harness/build_your_own_claw)
suggests. `azd ai agent invoke` reuses the session across consecutive local invokes, so the
frictionless turns chain naturally.

**Frictionless turns** — skills, file reads, mode, CodeAct, and background research all run without
approval:

```bash
# Skills — loads the valuation skill and runs its script
azd ai agent invoke --local "Value MSFT for me."

# File access + Skills — reads portfolio.csv, loads the risk-scoring skill, runs its script
azd ai agent invoke --local "Score the risk of my portfolio."

# Mode — switch to plan mode (the agent proposes before acting; sets up the shell turn)
azd ai agent invoke --local "Switch to plan mode."

# CodeAct — writes and runs Python to sum the portfolio
azd ai agent invoke --local "Write and run a Python script to work out the total value of my portfolio."

# Background agents — fans the three tickers out to concurrent research sub-agents
azd ai agent invoke --local "Research MSFT, NVDA and SPY and summarize the latest news."
```

**Approval-gated turns** — use the Agent Inspector opened by `azd ai agent run`:

1. Send `Buy 10 shares of MSFT.` The Responses host returns an `mcp_approval_request`; the simulated
   trade has not run yet and no `TRADE-…` confirmation is present.
2. Select **Approve**. The Inspector sends an `mcp_approval_response` in the same conversation. The
   host resumes the turn, runs `place_trade` once, and returns its `TRADE-…` confirmation.

Shell commands follow the same contract and may require one approval per proposed command. The
Responses host owns translating and persisting pending approval items; the client or Inspector owns
the user's explicit approve/reject decision.

> **One more capability — Foundry skills.** With `FOUNDRY_TOOLBOX_MCP_SERVER_URL` set and a
> `financial-agent-rules` skill published to your toolbox, asking an off-topic question
> (`"What's the capital of France?"`) makes the agent load that skill, recognize the question is
> off-topic, and politely decline. See [Customization](#customization-centrally-managed-foundry-skills)
> for how to provision the toolbox.

### Deploy to Foundry

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke "Value MSFT for me."
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.
3. **Azure CLI** — [Install Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), then run `az login` in the VS Code integrated terminal.

### Set up the Python virtual environment

- Install the locked dependencies, then select the generated `.venv` in VS Code:

  ```bash
  uv sync --frozen
  ```

### Run and debug the agent

The Foundry Toolkit generates `.vscode/launch.json` and `.vscode/tasks.json` for the local workspace;
these files are intentionally not checked in. Press **F5** to start the agent. The agent starts and
the **Agent Inspector** opens automatically. Chat with the agent in the Inspector — file reads run
automatically; file writes, shell commands, and simulated trades pause for approval.

### Or run manually, then open the Inspector

1. Change to `src/harness-scaling-capabilities-responses`.
2. Copy `.env.example` to `.env`, set the required environment variables, and sign in with `az login`.
3. Start the agent with `uv run --no-sync python main.py`; it listens on `http://localhost:8088`.
4. Open the Command Palette (`Ctrl+Shift+P`), run **Foundry Toolkit: Open Agent Inspector**, and send
   a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The
   extension opens a **Deploy Hosted Agent** wizard and reads `azure.yaml` to identify the service
   source folder and auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose **Code** deployment and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Customization: centrally-managed Foundry skills

Set `FOUNDRY_TOOLBOX_MCP_SERVER_URL` to a Foundry Toolbox MCP endpoint to fold centrally-managed
Foundry skills into the agent alongside the local file skills. Skills published to the toolbox are
discovered at runtime, so they can be managed and updated without changing or redeploying this agent.
When the variable is unset, the sample runs with the local `valuation` and `risk-scoring` skills only
and prints a note.

**The toolbox is not provisioned for you.** This sample's `azure.yaml` provisions only the project,
model, and agent — it has no toolbox hook or provisioning script, and this sample bundles no
`toolbox.yaml`. To use Foundry skills you bring your own toolbox and provision it manually:

1. Create any project connections the toolbox's tools require (see
   [`azd ai connection create`](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox)).
2. Create the toolbox from your own `toolbox.yaml` and copy the versioned MCP endpoint it prints:

   ```bash
   azd ai toolbox create <toolbox-name> --from-file ./toolbox.yaml \
     --project-endpoint https://<account>.services.ai.azure.com/api/projects/<project>
   ```

3. Set that endpoint as `FOUNDRY_TOOLBOX_MCP_SERVER_URL` (in `.env` or your `azd env`) and re-run the
   agent.

For a full toolbox example with connections and a sample `toolbox.yaml`, see the
[Foundry Toolbox sample](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents/agent-framework/responses/04-foundry-toolbox).

## Troubleshooting

- **`FOUNDRY_PROJECT_ENDPOINT`/`AZURE_AI_MODEL_DEPLOYMENT_NAME` not set** — copy
  `src/harness-scaling-capabilities-responses/.env.example` to `.env` in the same directory and fill
  both in, or let `azd ai agent run` inject them from your `azd env`.
- **Authentication errors locally** — run `az login` so `DefaultAzureCredential` can resolve your
  Azure CLI login.

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent)
- [Part 3 blog post — Scaling the claw's capabilities](https://devblogs.microsoft.com/agent-framework/agent-harness-scaling-the-claw-or-harness-capabilities/)
