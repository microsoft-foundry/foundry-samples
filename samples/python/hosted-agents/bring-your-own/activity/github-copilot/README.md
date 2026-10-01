<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# What this sample demonstrates

A **conversational assistant** hosted agent built with the **Bring Your Own** approach on the **Activity protocol** in Python. Unlike the [echo](../echo) sample, this is a real assistant: it chats through the **[GitHub Copilot SDK](https://pypi.org/project/github-copilot-sdk/)** — which runs its own model + tool-calling loop — and exposes a few custom tools plus rich Teams UI.

It demonstrates how [`azure-ai-agentserver-activity`](https://pypi.org/project/azure-ai-agentserver-activity/) acts as the Foundry host — bridging to the [M365 Agents SDK](https://github.com/microsoft/Agents-for-python) for activity processing and outbound Teams delivery — while the **Copilot SDK** does the AI heavy lifting. You don't hand-write a tool-calling loop: you point the SDK at a model, register a few tools, and stream the reply.

## Features

| Feature | What it does |
|---------|--------------|
| **Streaming chat** | Replies stream token-by-token into Teams, with transient “working…” status updates while the model runs tools. |
| **To-do list** | Model tools to add / list / complete tasks, persisted per conversation. Asking to see them renders an **interactive Adaptive Card** with Done / Delete / Add buttons. |
| **Read shared files** | Attach any file in Teams (PDF, DOCX, PPTX, code, …) and the model reads it directly with its own file tools — no server-side extraction. |
| **Image understanding (vision)** | Paste or attach an image and the model sees it (sent inline as a base64 blob). |
| **Generate downloadable files** | Ask it to "write a doc / essay / report / slides" and the model **creates the file itself** — text formats (`.txt`, `.md`, `.csv`, `.json`, `.html`, code) directly, and `.docx` / `.pptx` / `.pdf` by running its own Python — then hands it back as a Teams **File Consent** download. |

> The Adaptive Card task board and File Consent download flow are **Teams personal-scope** features; in M365 Copilot (BizChat) the same actions fall back to text.

### How the agent creates files (the model does it, code-interpreter style)

A language model's only output is a **stream of text tokens** — it can write a
document's *content*, but it can't emit the *bytes* of a `.docx`, `.pptx`, or
`.pdf` (those are ZIP-of-XML archives and binary object graphs, not text). So the
model does what a code-interpreter tool does: it **writes and runs its own Python**
in the workspace using the Copilot SDK's built-in shell/file tools. For text
formats it just writes the file; for Office/PDF it `pip install`s a library
(`python-docx`, `python-pptx`, `reportlab`) at runtime and builds the file. Then it
calls the `deliver_file` tool with the path, and [`outfiles.py`](src/github-copilot-activity/outfiles.py)
reads the bytes and offers them as a download. This keeps the sample's own code
tiny — no server-side renderers — and lets the model handle whatever format it can
write. Image *generation* isn't supported (that needs an image model).

## How It Works

The message handler streams the model's reply and then attaches any model-requested UI (a task card or a generated file) to the same streaming response:

```python
from azure.ai.agentserver.activity import ActivityAgentServerHost
import client as copilot_client

host = ActivityAgentServerHost()  # simple Teams agent model (default)
app = host.agent_app

@app.activity("message")
async def on_message(context, _state):
    conversation_id = context.activity.conversation.id
    text = (context.activity.text or "").strip()
    stream = context.streaming_response
    async for kind, chunk in copilot_client.ask_stream(conversation_id, text):
        if kind == "progress":
            stream.queue_informative_update(chunk)   # transient “working…” line
        elif chunk:
            stream.queue_text_chunk(chunk)           # streamed reply text
    await _deliver_ui(context, conversation_id, stream)  # attach card/file, if any
    await stream.end_stream()

host.run()
```

The logic lives in a few small modules alongside `main.py`:

| File | Responsibility |
|------|----------------|
| [`client.py`](src/github-copilot-activity/client.py) | The Copilot SDK harness. Creates **one session per conversation**, wires your **Foundry model** as the provider, registers the tools, and exposes `ask_stream(conversation_id, text, files)` which yields streaming `(kind, text)` events. |
| [`tools.py`](src/github-copilot-activity/tools.py) | The custom tools defined with `copilot.define_tool` (JSON schema from Pydantic models): a per-conversation to-do list (`add_task` / `list_tasks` / `complete_task`) and `deliver_file` (sends a file the model created for download). Tools that need UI queue a request in a per-turn **outbox**. |
| [`files.py`](src/github-copilot-activity/files.py) | Downloads files/images the user shares (verbatim, no extraction) and hands the raw path (or an inline image blob for vision) to the model. |
| [`outfiles.py`](src/github-copilot-activity/outfiles.py) | The outbound Teams **File Consent** flow — reads the file the model created and, on *Allow*, uploads the bytes so the file renders as a download. |
| [`cards.py`](src/github-copilot-activity/cards.py) | The Adaptive Card to-do board (Universal Actions) and the invoke-response helpers for its buttons. |

### The Copilot SDK runs the agent loop

The key difference from a raw-LLM sample: **you don't write the tool-calling loop.** The Copilot SDK's session internally calls the model, invokes any tools the model requests, feeds the results back, re-prompts the model, and repeats until it produces a final answer. The agent just registers tools with `define_tool` and streams the reply.

Because SDK tools are pure functions and can't send Teams activities themselves, a tool that needs to show UI (a task card, a generated file) records the request in a per-turn **outbox**; `main.py` drains it after the turn and attaches the card/file to the streaming response.

```python
# client.py (abridged)
session = await client.create_session(
    session_id=_sdk_session_id(conversation_id),   # one session per conversation
    provider=ProviderConfig(
        type="azure",
        base_url=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        wire_api="responses",
        bearer_token=DefaultAzureCredential().get_token("https://ai.azure.com/.default").token,
    ),
    model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    tools=tools.build_tools(conversation_id),
    available_tools=ToolSet().add_builtin("*").add_custom("*"),
    system_message={"mode": "replace", "content": SYSTEM_MESSAGE},
    on_permission_request=PermissionHandler.approve_all,
    streaming=True,
)
await session.send(text, attachments=attachments or None)
# events (tool activity + streamed text) arrive via session.on(...)
```

### Model auth (your Foundry model via Managed Identity)

The assistant uses a **Foundry model deployment** (`gpt-5-mini` by default). The Copilot SDK talks to it over the **Responses** wire API using a bearer token minted from `DefaultAzureCredential` — the hosted agent's built-in Managed Identity model access, so there's **no GitHub token** and **no extra per-agent RBAC grant** required. The provider is pointed at the platform-injected `FOUNDRY_PROJECT_ENDPOINT`, and the deployment name comes from `AZURE_AI_MODEL_DEPLOYMENT_NAME` (both set for you at deploy time from [azure.yaml](azure.yaml)).

### Session model

Each Teams conversation gets **its own Copilot SDK session**, keyed by a hash of the conversation id (the id doubles as the provider's `prompt_cache_key`, which has a 64-char limit). Keeping sessions per-conversation isolates each chat's context and tools and means a redeploy doesn't strand anyone on stale state. To-do items are persisted to a small JSON file under the hosted agent's durable `$HOME`, so they survive container idle/recycle.

### Agent Hosting

The agent runs on the [Azure AI AgentServer Activity SDK](https://pypi.org/project/azure-ai-agentserver-activity/), which exposes a REST API endpoint that speaks the Azure AI Activity protocol (`POST /activity/messages`), plus platform headers, session resolution, OpenTelemetry tracing, and health probes.

### Agent Deployment

You build and ship the agent to Microsoft Foundry with the [Azure Developer CLI](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?view=foundry&pivots=azd) using the **native** `azure.ai.agent` flow. The [azure.yaml](azure.yaml) is checked in (Foundry provider) and declares a `gpt-5-mini` model deployment, so `azd provision` stands up the platform (Foundry project + Container Registry + model), and `azd deploy` builds the image, creates the agent version, and the azd foundry extension registers the Azure Bot + Microsoft Teams channel for you.

## Prerequisites

Make sure the following are installed and available:

| Requirement | Why you need it |
|-------------|-----------------|
| [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) | Provisions infrastructure and deploys the agent. Use **1.25 or later**. Install the agent service target with `azd extension install azure.ai.agents`. |
| [Azure CLI (`az`)](https://learn.microsoft.com/cli/azure/install-azure-cli) | Authentication (`az login`). |
| [Python 3.13+](https://www.python.org/downloads/) | The agent runtime (built inside the Docker image; also handy for local edits). |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Creates the locked local Python environment. Install it outside the project virtual environment. |
| [Docker](https://www.docker.com/products/docker-desktop/) | **Optional.** `azd deploy` uses a remote ACR build, so you don't need Docker unless you want to build the image locally. |
| **Model quota** | A `gpt-5-mini` (GlobalStandard) deployment is created by `azd provision`. Make sure your subscription has capacity in the target region. |

### Required permissions

For the default flow (provision + deploy + sideload into your own Teams):

- **Owner** (or **Contributor + User Access Administrator**) on the target subscription — the deploy creates role assignments.
- **Azure AI User** or **Cognitive Services User** at the subscription or resource-group scope.

Only needed for the **org-wide** path (publishing to your tenant app catalog), not the default sideload:

- **Teams admin** (`AppCatalog.ReadWrite.All`) to publish to the org app catalog.
- **Tenant admin** to approve a tenant-wide configuration.

> [!IMPORTANT]
> **Pick a unique agent name before your first deploy.** The agent name becomes the GLOBAL
> Azure Bot name (`<agent-name>-bot-uai`), which must be unique. If you keep the default
> `github-copilot-activity`, the bot-creation step can fail with `"The requested bot name is not available"`
> because someone (or a previous deploy) already claimed it. Pick a short, lowercase name and
> set it as the service key and `name:` in [azure.yaml](azure.yaml) (keep the two in sync).

> [!NOTE]
> **Region availability:** This sample relies on [Foundry hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?pivots=azd), so your Foundry account and related resources must live in a region that supports them (and has `gpt-5-mini` capacity). See the [hosted-agent region list](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?pivots=azd) for the current set.

## Local Debug in VS Code

### Step 1: Open the correct workspace folder

The launch configuration and tasks are defined inside `src/github-copilot/`, not the repo root. VS Code must have that folder loaded as a workspace root before F5 works.

If you opened the repo root folder, add the inner folder first:

1. **File → Add Folder to Workspace…**
2. Select `src/github-copilot/` and click **Add**.

The Explorer panel should now show `github-copilot` as a workspace root (with its own `.vscode/` visible). You can then save this as a multi-root workspace file if you like.

### Step 2: Prepare the LLM model and .env file

Sign in to the Azure account that owns your Foundry project. The agent uses `DefaultAzureCredential` to acquire auth tokens at runtime, and Azure CLI credentials are one of the credential sources it checks — so `az login` is required for local runs:

```powershell
az login
```

Copy `.env.example` to `.env` and fill in the required values:

```powershell
Copy-Item src/github-copilot-activity/.env.example src/github-copilot-activity/.env
```

Then open `.env` and set:

| Variable | Description |
|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | Your Foundry project endpoint, e.g. `https://<account>.services.ai.azure.com/api/projects/<project>` |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | The model deployment name, e.g. `gpt-5-mini` |

### Step 3: Press F5

Press **F5** (or **Run → Start Debugging**). The launch configuration will:

1. Install `agentsplayground` if not already installed (one-time, via winget).
2. Run `uv sync --frozen` to create the locked Python environment.
3. Start the agent (`main.py`) under the VS Code debugger.
4. Launch **M365 Agents Playground** automatically once port 8088 is ready.

When the debug session ends, the `postDebugTask` kills `agentsplayground` and any process still bound to port 8088.

Once the Playground window opens, type a message — the assistant replies via the Copilot SDK (try "add a task: buy coffee", or ask it to write a short doc). You can set breakpoints in `main.py` as with any Python project.

## Deploying the Agent to Microsoft Foundry

### Step 1: Sign in

```powershell
# Install the azd extension that provides `host: azure.ai.agent` (one-time)
azd extension install azure.ai.agents

# Sign in to both CLIs
az login
azd auth login

# Initialize the azd environment for this agent
azd ai agent init
```

### Step 2: Provision and deploy

```bash
azd provision   # Foundry project + Container Registry + gpt-5-mini deployment
azd deploy      # remote ACR build → agent version → Bot + Teams channel (postdeploy)
```

`azd deploy` runs a remote ACR build, pushes the image, creates the **agent version** from the
checked-in [azure.yaml](azure.yaml), and patches the `activity` protocol onto the agent endpoint.
The azd foundry extension's postdeploy then registers the **Azure Bot** (instance identity) and
the **Microsoft Teams** channel.

### Step 3: Chat with it in Teams

Package and install the Teams app using the generated `TEAMS_APP_SETUP.md` guide, then open
**Microsoft Teams**, find your agent in the chat list (or under **Apps → Manage your apps**),
and start chatting. Try:

- "Hi, what can you do?"
- "Add a task: buy coffee" → "Show my tasks" (renders the card) → tap **Done**
- Share a PDF/DOCX and ask "What are the key points?"
- Attach an image and ask "What's in this picture?"
- "Write a short markdown doc about black holes" → click **Allow** to download it
- "Make a 3-slide pptx introducing our team" → click **Allow** to download the deck

> [!NOTE]
> If **Upload a custom app** is greyed out, custom-app upload is disabled for your account —
> ask an admin to enable it (Teams Admin Center → **Teams apps** → **Setup policies**), or
> publish the package to your organization's app catalog for tenant-wide availability.

## Related samples

- [echo](../echo) — the minimal Activity-protocol "hello world" (no model).
