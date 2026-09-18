<!--
README template for a PYTHON hosted-agent sample.

How to use:
  1. Copy this file into your sample folder as README.md.
  2. Replace every {{placeholder}}.
  3. Delete any section that does not apply, but keep the section order.
  4. Delete this comment block.
-->

# What this sample demonstrates

{{One or two sentences: what the agent does and which framework it uses.}}

## How it works

{{Short description of how the agent is wired.}} See `main.py` for the implementation.

<!--
Sample-specific *background* subsections (e.g. "Environment variables", "Architecture",
"Features") belong here, right after "How it works" and before "Prerequisites" — they give
context a reader needs before running. Keep run/deploy steps out of them; those live in the
Options below. Deep-dive/customization/reference sections go *after* the two options.
-->

## Prerequisites

What the **sample itself** needs, independent of how you run it. The tooling for each run
path (`azd` or the VS Code Foundry Toolkit) is listed under its option below.

1. An existing Foundry project with a deployed model (or create them during setup in Option 1).
2. **Python 3.10 or later.**
3. **Roles (RBAC):** {{Azure roles the identity running the sample needs on the Foundry project or other resources, e.g. `Azure AI User`. Delete if project access is sufficient.}}
4. **Additional Azure resources:** {{Extra resources the sample depends on — a toolbox, connection, storage account, etc. If declared in the sample's `azure.yaml`, `azd provision` (Option 1) creates them; otherwise create them before running (Foundry portal, SDK, or `azd ai`). Delete if none.}}
5. **Environment variables / secrets:** {{Required env vars or secrets, e.g. `GITHUB_PAT`, and how to obtain them. Delete if none.}}

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

1. **Azure Developer CLI (`azd`) 1.27.1 or later** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
2. Install the Foundry extension:

   ```bash
   azd ext install microsoft.foundry
   ```

   If the manifest defines service environment variables, use the `env:` map
   rather than the legacy `environmentVariables` list. This requires `azd`
   1.27.1+ and `azure.ai.agents` 1.0.0-beta.9+; declare both in
   `requiredVersions`.

3. Authenticate:

   ```bash
   azd auth login
   ```

### Initialize the agent project

No cloning required. Create a new folder and initialize from the manifest:

```bash
mkdir my-agent && cd my-agent
azd ai agent init -m {{URL to your sample's azure.yaml on GitHub}}
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an existing Foundry project, `azd ai agent init` will guide you through creating one.

### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployment:

```bash
azd provision
```

### Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

### Invoke the local agent

In a separate terminal, from the project directory:

```bash
azd ai agent invoke --local "{{prompt}}"
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke "{{prompt}}"
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.
3. **Azure CLI** — [Install Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), then run `az login` in the VS Code integrated terminal.

### Set up the Python virtual environment

- Open the Command Palette (`Ctrl+Shift+P`) and run **Python: Create Environment...** to create a virtual environment in the workspace (or **Python: Select Interpreter** to use an existing one).
- Install the complete, resolved dependency graph from the sample's committed dependency artifact. New samples use `pyproject.toml` with `uv.lock` by default; `requirements.txt` remains the backward-compatible fallback. When authoring or updating a sample, see the [Python Hosted Agent dependency policy](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/DEPENDENCY_POLICY.md).

  ```bash
  # Default uv-native sample (use the exact uv version documented by the sample)
  uv sync --frozen

  # Backward-compatible requirements.txt sample
  pip install -r requirements.txt
  ```

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `azure.yaml` to identify the service source folder and auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

<!--
Sample-specific deep-dive sections go here, AFTER the two options, so the run/deploy
lifecycle stays consistent across samples. Give each its own `##` heading. Common kinds:
  - Customization  — swapping a dependency/endpoint (e.g. "Targeting a different MCP server",
                     "Using your own Foundry model", "Adding skills").
  - Advanced demos — behavior worth showing after deploy (e.g. "Uploading files to a hosted
                     session", "Testing session multiplexing after deployment").
  - Reference      — protocol/wire format, event shapes, or project structure.
Delete this comment and add the real sections your sample needs.
-->

## Troubleshooting

> Delete if not needed. List errors specific to this sample and their fixes.

{{Symptom → cause → fix.}}

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent)
- {{Links to related samples.}}
