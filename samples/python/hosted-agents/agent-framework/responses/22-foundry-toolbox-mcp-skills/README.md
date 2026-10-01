# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that discovers **Agent Skills attached to a Foundry Toolbox** over the **MCP protocol** and exposes them to the model using the [Agent Skills](https://agentskills.io/) progressive-disclosure pattern, hosted on Microsoft Foundry using the **Responses protocol**.

This sample is **self-contained**: it ships the `SKILL.md` sources and a `toolbox.yaml`, and walks you through creating the skills and the toolbox from zero with `azd` — you don't need an existing toolbox to run it.

## How it works

[`main.py`](src/agent-framework-agent-foundry-toolbox-mcp-skills-responses/main.py) uses `FoundryChatClient` from the Agent Framework to create an OpenAI-compatible Responses client. It then:

1. Constructs a `FoundryToolbox(credential, load_tools=False)`. The toolbox resolves its MCP endpoint from `TOOLBOX_ENDPOINT`, authenticates every request with the credential, and forwards the platform per-request call-id. `load_tools=False` keeps the toolbox's tools hidden so only its Agent Skills are surfaced.
2. Calls `toolbox.as_skills_provider(disable_load_skill_approval=True)`, which discovers skills from the well-known `skill://index.json` resource on the toolbox's MCP session and exposes them as an agent context provider. `disable_load_skill_approval=True` lets this unattended, session-less agent load skills without an approval round-trip (the Responses host runs the agent without an `AgentSession`, which the default approval flow requires).
3. Passes the toolbox via `tools=` **and** the provider via `context_providers=`. The `tools=` wiring connects the MCP session (the connection the provider reads from); the `context_providers=` wiring runs the advertise/load logic over that session. Both are required.

The agent is hosted with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol on `http://localhost:8088`. See `main.py` for the implementation.

### How progressive disclosure works

When the agent runs, it discovers the toolbox's skills and applies the progressive-disclosure pattern so a skill's full body is only fetched when the agent actually needs it, reducing token usage:

1. **Advertise** — each skill's name and description are injected into the system prompt so the model knows what is available (~100 tokens per skill).
2. **Load** — when the model decides a skill is relevant, it retrieves the full `SKILL.md` body on demand via `resources/read`.

> The Agent Skills spec defines a third stage — **read resources** — where a skill fetches supplementary files (reference documents, assets) on demand. Supporting it means packaging a skill as a multi-file archive (`type: archive`), which `MCPSkillsSource` discovers and serves. This sample keeps both skills as single-file `SKILL.md` (advertise + load only) to stay focused on the toolbox discovery flow; see the [Foundry Skills](../12-foundry-skills/) sample for the same instruction-only pattern via direct download.

### Toolbox MCP skills vs. Foundry Skills

Foundry exposes skills in two ways, and this sample uses the second one.

- **Foundry Skills** are downloaded directly into an agent: the agent pulls each `SKILL.md` from the Skills API at startup and serves the bodies from local files. See the [Foundry Skills](../12-foundry-skills/) sample.
- **Toolbox MCP skills** are accessed through a toolbox over the MCP protocol. A toolbox bundles a curated set of skills (and optionally tools) behind one MCP endpoint, and any MCP client discovers them automatically. Skill bodies are fetched on demand. The same `SKILL.md` files power both modes — the difference is only in delivery.

### The bundled skills

This sample ships two source skills under [`skills/`](src/agent-framework-agent-foundry-toolbox-mcp-skills-responses/skills/), reused from the [Foundry Skills](../12-foundry-skills/) sample so you can compare the two delivery modes side by side:

| Skill | Purpose |
|---|---|
| [`support-style`](src/agent-framework-agent-foundry-toolbox-mcp-skills-responses/skills/support-style/SKILL.md) | Voice, formatting, and signature rules for Contoso Outdoors support replies. |
| [`escalation-policy`](src/agent-framework-agent-foundry-toolbox-mcp-skills-responses/skills/escalation-policy/SKILL.md) | When and how to escalate a customer ticket, including the refund-authority matrix. |

Each file includes a unique `*-CANARY-*` token that the model is asked to echo, so a response proves the model actually **loaded** the skill rather than hallucinating:

| Artifact | Canary | Proves |
|---|---|---|
| `support-style/SKILL.md` | `STYLE-CANARY-3318` | The model loaded the `support-style` body. |
| `escalation-policy/SKILL.md` | `ESC-CANARY-7742` | The model loaded the `escalation-policy` body. |

> The `name` and `description` values in the YAML front matter must be **unquoted** — quoting them causes the Skills API to reject the import.

## Prerequisites

What the **sample itself** needs, independent of how you run it. The tooling for each run path (`azd` or the VS Code Foundry Toolkit) is listed under its option below.

1. An existing Foundry project with a deployed model (or create them during setup in Option 1).
2. **Python 3.12 or later.** The `azd ai agent run` flow in Option 1 uses Python 3.13.
3. **[uv](https://docs.astral.sh/uv/getting-started/installation/)** installed outside the project virtual environment.
4. **Roles (RBAC):** the identity running the sample (and, in production, the Managed Identity running the container) needs the **Foundry User** role (formerly *Azure AI User*) on the Foundry project. This covers creating skills, creating the toolbox, and discovering skills over MCP at runtime.
5. **Additional Azure resources:** a Foundry Toolbox that serves the two bundled skills. You create it from the bundled [`skills/`](src/agent-framework-agent-foundry-toolbox-mcp-skills-responses/skills/) folder and [`toolbox.yaml`](src/agent-framework-agent-foundry-toolbox-mcp-skills-responses/toolbox.yaml) — see [Building the toolbox from zero](#building-the-toolbox-from-zero) below.
6. **Environment variables:** `FOUNDRY_PROJECT_ENDPOINT`, `AZURE_AI_MODEL_DEPLOYMENT_NAME`, and `TOOLBOX_ENDPOINT` (the full versioned MCP endpoint of the toolbox). See [`.env.example`](src/agent-framework-agent-foundry-toolbox-mcp-skills-responses/.env.example).

## Building the toolbox from zero

The agent reads the toolbox's MCP endpoint from `TOOLBOX_ENDPOINT`. Before you can run it, create the skills in your Foundry project and then create a toolbox that references them.

> **Automatic path:** `azd provision` runs the bundled [`postprovision` hook](src/agent-framework-agent-foundry-toolbox-mcp-skills-responses/hooks/) (wired in [`azure.yaml`](azure.yaml)), which creates both skills with `azd ai skill create`, creates the toolbox from [`toolbox.yaml`](src/agent-framework-agent-foundry-toolbox-mcp-skills-responses/toolbox.yaml), and sets `TOOLBOX_ENDPOINT` for you. The manual steps below do the same thing by hand — use them if you are not running `azd provision`, or to understand what the hook does.

Run these commands from the project directory (`src/agent-framework-agent-foundry-toolbox-mcp-skills-responses`), where `toolbox.yaml` and `skills/` live.

Point `azd` at your project once:

```bash
azd ai project set "https://<account>.services.ai.azure.com/api/projects/<project>"
```

### Step 1 — Create the skills in Foundry

Skills referenced by a toolbox must already exist in the same Foundry project. Both skills in this sample are single-file `SKILL.md` skills, so upload each directly:

```bash
azd ai skill create support-style     --file ./skills/support-style/SKILL.md     --no-prompt
azd ai skill create escalation-policy --file ./skills/escalation-policy/SKILL.md --no-prompt
```

> **Why single files?** Both skills ship as single-file `SKILL.md`, which keeps this sample focused on the advertise + load flow. Skills that carry supplementary resource files are packaged as multi-file archives (`type: archive`) instead; `MCPSkillsSource` discovers those too, but they add the read-resources stage that is out of scope here.

> The `name:` in each `SKILL.md` front matter must equal the positional skill name you pass to `azd ai skill create`. To replace a skill after editing it, run `azd ai skill update <name> --file ./skills/<name>/SKILL.md` — this creates a new default version and preserves the skill's version history.

### Step 2 — Create the toolbox

Create the toolbox once from the bundled [`toolbox.yaml`](src/agent-framework-agent-foundry-toolbox-mcp-skills-responses/toolbox.yaml), which references both skills by name plus one connectionless placeholder tool (`code_interpreter`):

```bash
azd ai toolbox create maf-skills-toolbox --from-file ./toolbox.yaml --no-prompt
```

> **Why a placeholder tool?** `azd ai toolbox create` requires at least one `tools` or `connections` entry, so a purely skills-only toolbox cannot be created directly. The bundled `toolbox.yaml` includes a single connectionless `code_interpreter` tool to satisfy this. Because the agent builds the toolbox with `load_tools=False` (see [main.py](src/agent-framework-agent-foundry-toolbox-mcp-skills-responses/main.py)), that tool is never surfaced to the model — only the skills are — so the toolbox stays effectively skills-only from the agent's perspective.

The first version becomes the default automatically. Use `azd ai toolbox list`, `azd ai toolbox show maf-skills-toolbox`, and `azd ai toolbox versions list maf-skills-toolbox` to inspect it, and `azd ai toolbox delete maf-skills-toolbox --force` to remove it.

### Step 3 — Store the toolbox endpoint

`azd ai toolbox create` prints the toolbox's **versioned** MCP endpoint. Copy it and store it so the agent connects to it:

```bash
azd env set TOOLBOX_ENDPOINT "https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/maf-skills-toolbox/versions/1/mcp?api-version=v1"
```

When running the host with plain `python`, put the same value in a `.env` file next to `main.py` instead — see [`.env.example`](src/agent-framework-agent-foundry-toolbox-mcp-skills-responses/.env.example).

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
mkdir my-toolbox-skills-agent && cd my-toolbox-skills-agent
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/22-foundry-toolbox-mcp-skills/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an existing Foundry project, `azd ai agent init` will guide you through creating one.

> `azd ai agent init` prompts for any unset manifest variables. `TOOLBOX_ENDPOINT` is declared as optional (`${TOOLBOX_ENDPOINT:-}` in [`azure.yaml`](azure.yaml)), so you can leave it blank here — the toolbox doesn't exist yet. You set the real endpoint after creating the toolbox in [Building the toolbox from zero](#building-the-toolbox-from-zero).

### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployment:

```bash
azd provision
```

### Create the skills and toolbox

Complete [Building the toolbox from zero](#building-the-toolbox-from-zero) so `TOOLBOX_ENDPOINT` points at a toolbox that serves the two bundled skills.

### Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

### Invoke the local agent

In a separate terminal, from the project directory:

```bash
azd ai agent invoke --local "What skills do you have available?"
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

Make sure the skills and toolbox exist in the **same** Foundry project you deploy to, and that `TOOLBOX_ENDPOINT` is set in your `azd` environment so it is injected into the hosted container. The deployed agent's Managed Identity needs the **Foundry User** role on the Foundry project to discover skills over MCP at startup. For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

> The bundled `skills/` folder and `toolbox.yaml` are authoring inputs only; they are excluded from the deployed code package via [`.agentignore`](src/agent-framework-agent-foundry-toolbox-mcp-skills-responses/.agentignore) (direct code deploy) and from the container image via [`.dockerignore`](src/agent-framework-agent-foundry-toolbox-mcp-skills-responses/.dockerignore) (container deploy). The running agent discovers everything it needs from the toolbox MCP endpoint.

### Invoke the deployed agent

```bash
azd ai agent invoke "What skills do you have available?"
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.
3. **Azure Developer CLI (`azd`)** with the Foundry extension and login — the toolbox setup below uses `azd ai` commands:

   ```bash
   azd ext install microsoft.foundry
   azd auth login
   ```

4. The skills and toolbox must exist in your Foundry project, and `TOOLBOX_ENDPOINT` must be set — see [Building the toolbox from zero](#building-the-toolbox-from-zero). (You can also create the skills and toolbox from the Foundry portal instead of the `azd ai` commands.)

### Set up the Python virtual environment

- Open the Command Palette (`Ctrl+Shift+P`) and run **Python: Create Environment...** to create a virtual environment in the workspace (or **Python: Select Interpreter** to use an existing one).
- Install dependencies in the virtual environment:

  ```bash
   uv sync --frozen
  ```

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `azure.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Interacting with the agent

Send a POST request with a JSON body containing an `"input"` field:

```bash
# Discover what the toolbox advertises (advertise step only)
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "What skills do you have available?"}'

# Routine question -> loads support-style
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Hi, I am Alex. Can I return my tent within 30 days?"}'

# Large refund + legal threat -> loads escalation-policy (which includes the refund matrix)
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "I want a $750 refund on Order #A-1042 right now or I am calling my lawyer."}'
```

| Prompt mentions | Skill that should drive the response | Canary you should see |
|---|---|---|
| Routine return / shipping / care question | `support-style` | `STYLE-CANARY-3318` |
| Injury, legal threat, press, or refund > $500 | `escalation-policy` (+ `support-style`) | `ESC-CANARY-7742` |

Because skills are loaded on demand, a canary token in a response proves the model actually invoked `load_skill` for the matching skill — not that it merely saw the name in the advertised list.

## Troubleshooting

### The agent reports no skills

The toolbox must be **connected** before its skills are discovered, which happens lazily on the first agent run. Make sure the toolbox is passed to the agent via `tools=` (it is in this sample) and that `TOOLBOX_ENDPOINT` points at a toolbox version that has both skills attached. Verify with `azd ai toolbox show maf-skills-toolbox`.

### A skill is missing from the advertised list

Confirm the skill was created in the same Foundry project the toolbox lives in, that its `name:` front matter matches the name in [`toolbox.yaml`](src/agent-framework-agent-foundry-toolbox-mcp-skills-responses/toolbox.yaml), and that it is attached to the toolbox version `TOOLBOX_ENDPOINT` points at. Verify with `azd ai toolbox show maf-skills-toolbox`.

### Skill-loading requests hang

If you removed `disable_load_skill_approval=True`, the `load_skill` tool defaults to requiring approval. The Responses host runs the agent without an `AgentSession`, so the approval flow can't complete and requests stall on an unanswered `mcp_approval_request`. Keep `disable_load_skill_approval=True` for this unattended host.

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent)
- [Foundry Skills](../12-foundry-skills/) — the same `SKILL.md` skills delivered via direct download instead of a toolbox.
- [Foundry Toolbox](../04-foundry-toolbox/) — consume tools (rather than skills) from a Foundry Toolbox.
