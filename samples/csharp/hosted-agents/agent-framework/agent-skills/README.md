# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that loads its behavioral guidelines from [**Foundry Skills**](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/skills) at startup, hosted using the **Responses protocol**. Skills are authored once as `SKILL.md` files, uploaded to your Foundry project through the Skills REST API, and downloaded by the agent on boot so updates ship without code changes.

## How It Works

### Authoring skills

Each skill is a Markdown file with a YAML front matter block. This sample ships two source skills under [`skills/`](skills/):

| Skill | Purpose |
|---|---|
| [`support-style`](skills/support-style/SKILL.md) | Voice, formatting, and signature rules for Contoso Outdoors support replies. |
| [`escalation-policy`](skills/escalation-policy/SKILL.md) | When and how to escalate a customer ticket. |

Each `SKILL.md` includes a unique `*-CANARY-*` token that the model is asked to echo, so you can prove the skill was loaded from Foundry (not hallucinated) by checking the response.

> The `name` and `description` values in the YAML front matter must be **unquoted** — quoting them causes the Skills REST API to return HTTP 500 on import.

### Uploading skills (sample convenience only)

The sample includes a convenience provisioning step that checks whether each skill exists in Foundry and uploads it if not, gated behind the `PROVISION_SAMPLE_SKILLS=true` env var. **In production, skill provisioning is an external concern** — it is NOT the hosted agent's responsibility. A real deployment pipeline would provision skills separately (for example via a CI/CD step, a CLI script, or a management portal).

The provisioning uses `ProjectAgentSkills.CreateSkillFromPackageAsync(directoryPath)` from the `Azure.AI.Projects.Agents` SDK. The method packages the `SKILL.md` directory as a ZIP and uploads it to Foundry.

> **Preview opt-in.** The Foundry Skills API is currently a preview surface and requires the `Foundry-Features: Skills=V1Preview` opt-in header on every request (uploads, lookups, and downloads). The `Azure.AI.Projects` SDK does not yet inject this on the Skills sub-client, so the sample registers a small `FoundryFeaturesPolicy` pipeline policy on the `AgentAdministrationClient`. Once the SDK starts emitting the header by default, the policy can be removed.

### Downloading skills at agent startup

[`Program.cs`](src/agent-skills/Program.cs) reads the comma-separated `SKILL_NAMES` env var and, for each skill name, downloads the ZIP archive from Foundry via `ProjectAgentSkills.DownloadSkillAsync(name)`, then unpacks it into a **separate runtime directory** at `downloaded_skills/<name>/` (kept distinct from the static `skills/` source folder). Locally this directory is under the application folder; in Foundry containers it is under the writable per-session home directory.

An `AgentSkillsProvider` is then built over `downloaded_skills/` and attached to the agent as an `AIContextProvider`. The provider follows the [Agent Skills](https://agentskills.io/) progressive-disclosure pattern:

1. **Advertise** — skill names and descriptions are injected into the system prompt at session start (around 100 tokens per skill).
2. **Load** — the model calls the `load_skill` tool when it decides a skill is relevant to the user's turn, and the full `SKILL.md` body is returned.

The model only pays the token cost for a skill's full body when it actually needs it, and updating a skill in Foundry plus restarting the agent is enough to pick up the change — no code redeploy required.

> **Note:** This sample supports instruction-only skills. If your downloaded skills contain resource files or scripts, configure the corresponding readers when constructing the `AgentSkillsProvider`.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the Responses API hosting layer (`AddFoundryResponses` / `MapFoundryResponses`).

See [Program.cs](src/agent-skills/Program.cs) for the full implementation.

## Prerequisites

1. An existing Foundry project with a deployed model (or create them during setup in Option 1 — `azd provision` can create them for you).
2. **[.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)** or later.
3. **Roles (RBAC):** your identity and the deployed agent's managed identity need **Foundry User**
   (formerly **Azure AI User**) on the Foundry project scope. This role covers authoring and
   downloading skills.

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | Foundry project endpoint. Auto-injected in hosted containers; set automatically by `azd ai agent run` locally. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Yes | Model deployment name — must match a deployment in your Foundry project. Declared in `azure.yaml`. |
| `SKILL_NAMES` | Yes | Comma-separated list of Foundry skill names to download at startup (for example `support-style,escalation-policy`). |
| `PROVISION_SAMPLE_SKILLS` | No | Sample convenience: set to `true` on a first run to upload this sample's `SKILL.md` files to Foundry. Leave unset or false in production. |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Recommended | Enables telemetry. Auto-injected in hosted containers; set manually for local dev. |

When using `azd ai agent run`, these are handled automatically. For manual runs, set them in your shell — .NET does not read `.env` files natively.

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
mkdir agent-skills && cd agent-skills
azd ai agent init --deploy-mode container -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/agent-framework/agent-skills/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an existing Foundry project, `azd ai agent init` will guide you through creating one.

> If you already have a Foundry project and model deployment, add `-p <project-id> -d <deployment-name>` to `azd ai agent init` to target existing resources.

### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployment:

```bash
azd provision
```

Tell azd which skills to download at startup, and (first run only) upload the sample's `SKILL.md` files to Foundry:

```bash
azd env set SKILL_NAMES "support-style,escalation-policy"
azd env set PROVISION_SAMPLE_SKILLS true
```

### Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`. On startup you should see:

```text
Skill 'support-style' already exists in Foundry.
Skill 'escalation-policy' already exists in Foundry.
Downloading skill 'support-style' from Foundry...
Downloading skill 'escalation-policy' from Foundry...
```

### Invoke the local agent

In a separate terminal, invoke the running agent:

```bash
azd ai agent invoke --local "Hi, I am Alex. Can I return my tent within 30 days?"
```

| Prompt mentions | Skill that should drive the response |
|---|---|
| Routine return / shipping / care question | Model loads `support-style` (canary `STYLE-CANARY-3318`) — no escalation. |
| Injury, legal threat, press, or refund > $500 | Model loads `escalation-policy` (canary `ESC-CANARY-7742`) **and** `support-style`. |

Because skills are loaded on demand, the canary token in a response also proves the model actually invoked `load_skill` for the matching skill — not just saw its name in the advertised list.

### Deploy to Foundry

Make sure `SKILL_NAMES` is set in your azd environment so it is injected into the hosted container, then deploy to Microsoft Foundry:

```bash
azd env set SKILL_NAMES "support-style,escalation-policy"
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

> The `skills/` source folder is **not** consumed by the deployed agent at runtime — only the skills already present in Foundry are downloaded. The provisioning step (or your own pipeline) must have uploaded the named skills to the same Foundry project before the agent starts.

`azd deploy` does not assign project data-plane roles to the new agent identity. Get the
`instance_identity.principal_id` from `azd ai agent show --output json`, grant that principal
**Foundry User** on the project ARM resource ID, and allow two to three minutes for role propagation
before the first invocation:

```bash
az role assignment create \
  --assignee-object-id <instance-identity-principal-id> \
  --assignee-principal-type ServicePrincipal \
  --role "Foundry User" \
  --scope <foundry-project-arm-resource-id>
```

### Invoke the deployed agent

```bash
azd ai agent invoke "Hi, I am Alex. Can I return my tent within 30 days?"
```

Stream logs from the running agent with `azd ai agent monitor`.

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. [C# Dev Kit](https://marketplace.visualstudio.com/items?itemName=ms-dotnettools.csdevkit) extension.
3. Command Palette (`Ctrl+Shift+P`) → **C#: Check Workspace Requirements** to confirm the toolchain is ready.

### Run and debug the agent

Set `SKILL_NAMES` (and `PROVISION_SAMPLE_SKILLS=true` on a first run) in `.env`, then press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Restore dependencies:

   ```bash
   dotnet restore
   ```

2. Configure the agent: copy `.env.example` to `.env` and fill in the [required variables](#environment-variables) (including `SKILL_NAMES`, plus `PROVISION_SAMPLE_SKILLS=true` on a first run). The sample loads `.env` automatically on startup.

3. Sign in to Azure with the Azure CLI so `DefaultAzureCredential` can authenticate the terminal process (the **F5** path reuses the Azure sign-in from the Foundry Toolkit, so it doesn't need a separate `az login`):

   ```bash
   az login
   ```

4. Start the agent (listens on `http://localhost:8088`):

   ```bash
   dotnet run
   ```

5. Open the Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Troubleshooting

### Local startup times out while probing managed identity

Authenticate with `az login` and use this sample version. The sample excludes
`ManagedIdentityCredential` locally so `DefaultAzureCredential` reaches the Azure CLI login instead
of waiting on the unavailable IMDS endpoint at `169.254.169.254`. Managed identity remains enabled
inside the Foundry hosted container.

### Hosted session does not become ready while downloading a skill

Confirm that the agent version's `instance_identity.principal_id` has **Foundry User** on the
project, wait for role propagation, then create a new hosted session. A session that already failed
readiness must be deleted with `azd ai agent sessions delete <session-id>` before retrying.

### Images built on Apple Silicon or other ARM64 machines do not work on our service

**Deploy with `azd deploy`**, which uses ACR remote build and always produces images with the correct architecture.

If you choose to **build locally**, and your machine is **not `linux/amd64`** (for example, an Apple Silicon Mac), the image will **not be compatible with our service**, causing runtime failures.

**Fix for local builds:**

```bash
docker build --platform=linux/amd64 -t image .
```

This forces the image to be built for the required `amd64` architecture.
