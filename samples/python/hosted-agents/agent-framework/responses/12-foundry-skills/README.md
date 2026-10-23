# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that loads its behavioral guidelines from [**Foundry Skills**](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/skills?view=foundry&pivots=python) at startup, hosted using the **Responses protocol**. Skills are authored once as `SKILL.md` files, declared as `azure.ai.skill` services in `azure.yaml`, and downloaded by the agent on boot so updates ship without code changes.

## How It Works

### Authoring skills

Each skill is a Markdown file with a YAML front matter block. This sample ships two source skills under [`skills/`](skills/):

| Skill | Purpose |
|---|---|
| [`support-style`](skills/support-style/SKILL.md) | Voice, formatting, and signature rules for Contoso Outdoors support replies. |
| [`escalation-policy`](skills/escalation-policy/SKILL.md) | When and how to escalate a customer ticket. |

Each `SKILL.md` includes a unique `*-CANARY-*` token that the model is asked to echo, so you can prove the skill was loaded from Foundry (not hallucinated) by checking the response.

> The `name` and `description` values in the YAML front matter must be **unquoted** — quoting them causes the Skills REST API to return HTTP 500 on import.

### Provisioning skills with `azure.yaml`

The `azure.yaml` manifest declares each bundled skill as an
`azure.ai.skill` service. The skill service archives the corresponding
directory, including its `SKILL.md`, and creates or updates the skill when you
run `azd deploy` or `azd up`:

```yaml
services:
  support-style:
    host: azure.ai.skill
    uses:
      - ai-project
    archive: src/agent-framework-agent-foundry-skills-responses/skills/support-style
```

The agent lists both skill services in its `uses` collection, so `azd` deploys
the skills before the agent. `azd provision` creates the project and model
deployment, but does not apply the skill service.

### Manual provisioning fallback with `AIProjectClient`

[`provision_skills.py`](src/agent-framework-agent-foundry-skills-responses/provision_skills.py) walks `skills/*/SKILL.md`, packages each file as an in-memory ZIP (with `SKILL.md` at the archive root), and imports it through [`AIProjectClient.beta.skills.create_from_package`](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/skills?view=foundry&pivots=python#option-2-import-from-a-skillmd-zip). The client is constructed with `allow_preview=True` (Skills is a preview feature) and authenticates with `DefaultAzureCredential`. Existing skills are deleted first via `beta.skills.delete` so the script is safe to re-run after editing a `SKILL.md`, and `beta.skills.list` is called at the end to verify each skill round-trips.

### Downloading skills at agent startup

[`main.py`](src/agent-framework-agent-foundry-skills-responses/main.py) reads the comma-separated `SKILL_NAMES` env var, opens an `AIProjectClient` (also with `allow_preview=True`), and for each skill name streams the ZIP archive from `beta.skills.download(name)` and unpacks it into a **separate runtime directory** at `downloaded_skills/<name>/` (kept distinct from the static `skills/` source folder so the two never get confused — `skills/` is the input to `provision_skills.py`, `downloaded_skills/` is the output of `main.py`'s bootstrap step).

A [`SkillsProvider`](../../../../../packages/core/agent_framework/_skills.py) is then built over `downloaded_skills/` and attached to the `Agent` as a context provider. The provider follows the [Agent Skills](https://agentskills.io/) progressive-disclosure pattern:

1. **Advertise** — skill names and descriptions are injected into the system prompt at session start (~100 tokens per skill).
2. **Load** — the model calls the `load_skill` tool when it decides a skill is relevant to the user's turn, and the full `SKILL.md` body is returned.

This means the model only pays the token cost for a skill's full body when it actually needs it, and updating a skill in Foundry + restarting the agent is enough to pick up the change — no code redeploy required.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

## Prerequisites

- An Azure AI Foundry project with a deployed model (e.g., `gpt-5.4-mini`)
- Azure CLI logged in (`az login`)

### Required RBAC

Your identity (or the Managed Identity running the container in production) needs **Azure AI User** on the Foundry project scope. This single role covers both authoring skills with `provision_skills.py` and downloading them from `main.py`.

## Manual skill provisioning (without `azd deploy`)

Use the script when you are running the agent from VS Code or are not using
the declarative `azure.yaml` deployment. From `src/agent-framework-agent-foundry-skills-responses`, with Python 3.13 or later and uv installed:

```bash
uv sync --frozen
export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
uv run --no-sync python provision_skills.py
```

Or in PowerShell:

```powershell
uv sync --frozen
$env:FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
uv run --no-sync python provision_skills.py
```

Expected output:

```text
Provisioning skill 'escalation-policy' from skills/escalation-policy/SKILL.md...
  Imported skill 'escalation-policy' (id=skill_..., has_blob=True).
Provisioning skill 'support-style' from skills/support-style/SKILL.md...
  Imported skill 'support-style' (id=skill_..., has_blob=True).
Done.
```

Re-running the script after editing a `SKILL.md` re-imports the skill, replacing the previous version.

> To remove a skill manually, call `project.beta.skills.delete("<name>")` on an `AIProjectClient` constructed with `allow_preview=True`.

## Running the Agent Host

Follow the instructions in the [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally) section of the README in the parent directory to run the agent host.

When using `azd ai agent run`, run `azd deploy` or `azd up` once first so the
declared skills exist in the Foundry project. Otherwise, use the manual
provisioning script above.

The manifest supplies this default for `azd ai agent run`. For direct
`uv run --no-sync python main.py` runs, set:

```bash
export SKILL_NAMES="support-style,escalation-policy"
```

Or in PowerShell:

```powershell
$env:SKILL_NAMES="support-style,escalation-policy"
```

You can also place these in a `.env` file next to `main.py` — see [`.env.example`](src/agent-framework-agent-foundry-skills-responses/.env.example) or `.env`.

On startup you should see:

```text
Downloading skill 'support-style' from Foundry...
Downloading skill 'escalation-policy' from Foundry...
```

The downloaded `SKILL.md` files land under `downloaded_skills/<name>/SKILL.md` next to `main.py`. This directory is recreated from scratch on every run, so deleting it manually is never necessary.

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the [parent README](../../README.md) for more details. Use this README for sample queries you can send to the agent.

Send a POST request to the server with a JSON body containing an `"input"` field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Hi, I am Alex. I just want to confirm I can return my tent within 30 days."}'
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "I want a $750 refund on Order #A-1042 right now or I am calling my lawyer."}'
```

| Prompt mentions | Skill that should drive the response |
|---|---|
| Routine return / shipping / care question | Model loads `support-style` (canary `STYLE-CANARY-3318`) — no escalation. |
| Injury, legal threat, press, or refund > $500 | Model loads `escalation-policy` (canary `ESC-CANARY-7742`) **and** `support-style`. |

Because skills are loaded on demand, the canary token in a response also proves the model actually invoked `load_skill` for the matching skill (not just saw its name in the advertised list).

### Test in VS Code (Foundry Toolkit)

**Prerequisites**

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.
3. **Python 3.13 or later** and [uv](https://docs.astral.sh/uv/getting-started/installation/) installed outside the project virtual environment.

**Set up the Python virtual environment**

- Create and synchronize the locked environment:

  ```bash
  uv sync --frozen
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select the `.venv` created by uv.

**Run and debug the agent**

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

**Or run manually, then open the Inspector**

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.

The `azure.yaml` manifest defaults `SKILL_NAMES` to
`support-style,escalation-policy`, so no extra environment setting is needed
for the bundled skills. `azd deploy` creates the declared skills before it
deploys the agent.

The deployed agent's Managed Identity needs **Azure AI User** on the Foundry
project to download skills at startup. The manual
`provision_skills.py` step is only required when you do not use the
declarative skill services.

> The `skills/` source folder is **not** deployed to Foundry — only the downloaded skills are used at runtime. The declared skill services upload the skills before the agent can download them.
