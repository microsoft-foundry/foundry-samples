# What this sample demonstrates

This sample hosts the Agent Framework **"scaling its capabilities"** personal-finance harness agent
(Post 3 of *Build your own claw and agent harness*) through the Foundry **Responses** protocol v2 in
C#. It preserves the original agent instructions, tools, file skills, background research agent,
confined shell, CodeAct provider, and approval policy — replacing only the interactive console host
with the native Foundry Responses host.

**Source:** ported from [`Claw_Step03_ScalingCapabilities`](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/Harness/BuildYourOwnClaw/Claw_Step03_ScalingCapabilities)
in the Microsoft Agent Framework, with the interactive console host replaced by the Foundry Responses host.

## How it works

Ask the personal-finance assistant about your portfolio. On top of file access and approvals it adds Post 3's four "scaling" capabilities:

- **Skills** — file-based finance skills (`valuation`, `risk-scoring`) the agent loads on demand and whose scripts it can run. Can optionally fold in centrally-managed **Foundry skills** from a Foundry Toolbox MCP endpoint (opt-in via `FOUNDRY_TOOLBOX_MCP_SERVER_URL`).
- **Shell** — an approval-gated `run_shell` tool confined to the trade-confirmation vault (`working/confirmations/`), used to reorganize confirmation files; a deny-list blocks destructive commands.
- **CodeAct** — a sandboxed Python interpreter the agent uses to crunch portfolio numbers. **See "CodeAct and hosting" below.**
- **Background agents** — the agent fans out per-ticker research to a web-search sub-agent concurrently, then aggregates the findings.

The Responses host owns conversation history. Continue a conversation with `previous_response_id`;
file and skill reads run without approval, while writes, skill scripts, `place_trade`, and shell
commands surface a structured approval request you resolve on the next turn.

### CodeAct and hosting

CodeAct runs on **Hyperlight**, which requires **hardware virtualization** on the host. It works on a
local machine with virtualization enabled, but a hosted Foundry container without nested
virtualization cannot start the Hyperlight micro-VM. If you deploy where virtualization is
unavailable, the other three capabilities (skills, shell, background research) still work; only the
CodeAct tool is affected. This matches the source sample, which carries the same requirement.

### Files and session

When hosted, the working data (portfolio.csv and the confirmations vault the shell reorganizes) and
file memory live under `$HOME`. In Foundry, `$HOME` belongs to the hosted session and persists across
turns and idle periods, so files the agent writes are durable for the life of the session and are
visible through the Session Files API; deleting the session removes that filesystem. The seed data is
copied only when a file is missing, so the user's reports and reorganized confirmations are never
overwritten. Local runs read and write the sample's `working/` folder directly.

## Prerequisites

What the **sample itself** needs, independent of how you run it. The tooling for each run path (`azd`
or the VS Code Foundry Toolkit) is listed under its option below.

1. An existing Foundry project with a deployed model (or create them during setup in Option 1). The
   default deployment name is `gpt-5.4-mini`.
2. The **.NET 10 SDK**.
3. *(For CodeAct)* a host with hardware virtualization enabled (Hyperlight runs the Python
   interpreter in a micro-VM).
4. **Environment variables:** `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME` (see
   `src/harness-scaling-capabilities/.env.example`). `FOUNDRY_TOOLBOX_MCP_SERVER_URL` is optional —
   set it to enable centrally-managed Foundry skills; when unset, the agent runs with the local file
   skills only.

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
azd ai agent init --deploy-mode container -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/agent-framework/harness-scaling-capabilities/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an
existing Foundry project, `azd ai agent init` will guide you through creating one.

### Provision Azure resources (if needed)

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
capability the sample exposes, in the order the [original Agent Framework sample](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/Harness/BuildYourOwnClaw/Claw_Step03_ScalingCapabilities)
suggests. `azd ai agent invoke` reuses the session across consecutive local invokes, so the
frictionless turns chain naturally. The gated turns use `azd` for the initial request and a direct
structured Responses request for the approval.

**Frictionless turns** — skill discovery and reading, file reads, mode, CodeAct, and background
research run without prompting:

```bash
# Skills — discover and read the available skill instructions
azd ai agent invoke --local "What finance skills are available?"

# Mode — switch to plan mode (the agent proposes before acting; sets up the shell turn)
azd ai agent invoke --local "Switch to plan mode."

# CodeAct — writes and runs Python to sum the portfolio (Hyperlight; requires host virtualization,
# see "CodeAct and hosting" above)
azd ai agent invoke --local "Work out the total value of my portfolio."

# Background agents — fans the three tickers out to concurrent research sub-agents
azd ai agent invoke --local "Research MSFT, NVDA and SPY and summarize the latest news."
```

**Gated turns** — `run_skill_script`, `run_shell`, and `place_trade` require approval. The agent
returns an `mcp_approval_request` output item before executing the action. Send a structured
approval response with the same `conversation.id` to continue. Set `"approve": false` to reject.
Reading a skill does not require approval; executing its Python script does.

The model may first ask for a natural-language confirmation before it calls the gated tool. If that
happens, reply `Confirm`; the next response contains the structured `mcp_approval_request`.

> [!IMPORTANT]
> `azd ai agent invoke -f` currently sends the file contents as text inside the Responses `input`
> field. It cannot send the structured `mcp_approval_response` shown below. Use `az rest`.

Save this template as `approval-response.json`, then replace the conversation and approval IDs for
each pending action:

```json
{
  "conversation": { "id": "<conversation-id>" },
  "input": [
    {
      "type": "mcp_approval_response",
      "approval_request_id": "<id>",
      "approve": true
    }
  ]
}
```

```bash
# Valuation — loads the skill and reads its reference before requesting approval to run its script.
azd ai agent invoke --local --conversation-id demo-valuation-1 \
  "Value MSFT using the valuation skill and its script."

# Risk scoring — reads portfolio.csv and the skill before requesting script approval.
azd ai agent invoke --local --conversation-id demo-risk-1 \
  "Score the risk of my portfolio using the risk-scoring skill and its script."

# Shell (confined to the confirmations vault). The original sample tidies the vault with the natural
# prompt "Tidy up my trade confirmations." after switching to plan mode; the agent then reorganizes
# and renames the files, using the shell. Because the model may instead just inspect the folder or use
# the file-write tools, this command names run_shell explicitly to reliably exercise the shell path.
# It returns an mcp_approval_request per command; note the "id".
azd ai agent invoke --local --conversation-id demo-shell-1 \
  "Use the run_shell tool to reorganize the confirmations vault into year/month folders and rename each file to YYYY-MM-DD_TICKER_BUY|SELL.txt. Inspect with shell commands first."

# To approve a pending skill script, shell command, or trade, replace the conversation and approval
# IDs in approval-response.json. For shell commands, repeat for each command the agent proposes
# (the exact command differs by OS — bash on Linux/macOS, PowerShell on Windows).
az rest --method POST \
  --url http://localhost:8088/responses \
  --headers "Content-Type=application/json" \
  --body @approval-response.json

# Trade (a real action). Returns an mcp_approval_request; nothing is traded yet.
azd ai agent invoke --local --conversation-id demo-trade-1 "Buy 10 shares of MSFT."

# Approve it, chaining the same conversation id. Only now is the (simulated) trade placed, exactly once.
# Set <conversation-id> to demo-trade-1 and replace <id>, then use the same az rest command above.
```

Confirm the gate: a pending `mcp_approval_request` has **no protected-action result** (no script
metrics, `TRADE-…` confirmation, or files moved). Only after the matching
`mcp_approval_response` does that action run. The browser Agent Inspector (Option 2) surfaces the
same pending actions with **Approve** / **Deny** buttons.

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
azd ai agent invoke --new-session --new-conversation \
  "Value MSFT using the valuation skill and its script."
```

The script waits for approval. Copy the emitted service session ID, conversation ID, and approval
request ID, put the last two values in `approval-response.json`, then send it to the deployed
Responses endpoint:

```bash
az rest --method POST \
  --url "<responses-endpoint>" \
  --resource https://ai.azure.com \
  --headers "Content-Type=application/json" "x-agent-session-id=<agent-session-id>" \
  --body @approval-response.json
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. The **.NET 10 SDK** and the **[C# Dev Kit](https://marketplace.visualstudio.com/items?itemName=ms-dotnettools.csdevkit)** extension for debugging.
3. **Azure CLI** — [Install Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), then run `az login` in the VS Code integrated terminal.

### Run and debug the agent

Copy `src/harness-scaling-capabilities/.env.example` to
`src/harness-scaling-capabilities/.env`, set `FOUNDRY_PROJECT_ENDPOINT` and
`AZURE_AI_MODEL_DEPLOYMENT_NAME`, then press **F5** to start the agent. The agent starts and the
**Agent Inspector** opens automatically.
Chat with the agent in the Inspector — reads run automatically, while skill scripts, trades, and
shell commands surface **Approve** / **Deny** buttons on the pending action.

### Or run manually, then open the Inspector

1. Restore dependencies:

   ```bash
   cd src/harness-scaling-capabilities
   dotnet restore
   ```

2. Copy `.env.example` to `.env` and fill in `FOUNDRY_PROJECT_ENDPOINT` and
   `AZURE_AI_MODEL_DEPLOYMENT_NAME`. Set `FOUNDRY_TOOLBOX_MCP_SERVER_URL` only when using
   centrally-managed Foundry skills.
3. Sign in to Azure so `DefaultAzureCredential` can authenticate the terminal process:

   ```bash
   az login
   ```

4. Start the agent (listens on `http://localhost:8088`):

   ```bash
   dotnet run
   ```

5. Open the Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send
   a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The
   extension reads `azure.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
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

- **`FOUNDRY_PROJECT_ENDPOINT`/`AZURE_AI_MODEL_DEPLOYMENT_NAME` not set** — copy `.env.example` to
  `.env` in `src/harness-scaling-capabilities/` and fill both in, or let `azd ai agent run` inject
  them from your `azd env`.
- **CodeAct fails to start / virtualization error** — the host lacks hardware virtualization required
  by Hyperlight. See "CodeAct and hosting" above; the other capabilities are unaffected.
- **Skill script, trade, or shell command "did nothing"** — that's the approval gate. The first turn returns an
  `mcp_approval_request`, possibly after a natural-language `Confirm` turn; the action runs only
  after you send the matching `mcp_approval_response`.
- **Approval fails after `azd ... -f approval-response.json`** — `azd` sent the JSON as user text.
  Use the local or deployed REST command above so the host receives a structured approval item.
- **HTTP 403 / "Identity … does not have permissions"** — the local `DefaultAzureCredential` resolved
  a different identity than the one you signed into with `az login` (common when the machine also has
  a Visual Studio, `azd`, or shared-token-cache login for another account). Confirm the intended
  account has an `Azure AI User` (or equivalent data-plane) role on the project, then pin the Azure
  CLI identity for the run: `azd env set AZURE_TOKEN_CREDENTIALS AzureCliCredential` (or set that
  environment variable in the process) so `DefaultAzureCredential` uses your `az login`. When hosted
  in Foundry, managed identity is used automatically and this does not apply.

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent)
- [Part 3 blog post — Scaling the claw's capabilities](https://devblogs.microsoft.com/agent-framework/agent-harness-scaling-the-claw-or-harness-capabilities/)
