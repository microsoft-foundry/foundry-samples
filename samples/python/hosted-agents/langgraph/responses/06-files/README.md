# What this sample demonstrates

A [LangGraph](https://langchain-ai.github.io/langgraph/) agent that **manipulates files** using three local filesystem tools (`get_cwd`, `list_files`, `read_file`) and the **`code_interpreter`** tool loaded from a [Foundry Toolbox](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox) via [`langchain_azure_ai.tools.AzureAIProjectToolbox`](https://github.com/langchain-ai/langchain-azure/tree/main/libs/azure-ai/langchain_azure_ai/tools). Hosted on Foundry over the **Responses protocol** using [`langchain_azure_ai.agents.hosting`](https://github.com/langchain-ai/langchain-azure/tree/main/libs/azure-ai/langchain_azure_ai/agents/hosting).

In hosted mode the platform mounts files uploaded to a hosted agent session into the agent's working directory, so the same local tools work against user-provided files. The bundled `resources/contoso_q1_2026_report.txt` ships inside the container image so the demo flow works without uploading anything.

The sample also includes a [local attachment client](src/langgraph-files-responses/send_attachment.py)
for sending images and PDFs directly in a Responses request. Request attachments
go to the model; session files remain available to filesystem tools.

## How It Works

### Tools

| Tool | Source |
|---|---|
| `get_cwd` | Local `@tool` — returns the agent's current working directory. |
| `list_files` | Local `@tool` — lists entries under a directory. |
| `read_file` | Local `@tool` — returns the contents of a UTF-8 text file. |
| `code_interpreter` | Foundry Toolbox — runs Python in a managed sandbox for math/data work. |

System prompt: *"You are a friendly assistant. Keep your answers brief. Make sure all mathematical calculations are performed using the code interpreter instead of mental arithmetic."*

### LangGraph Agent

The compiled graph is built with `langchain.agents.create_agent(model, tools=[...], system_prompt=...)`, which returns a compiled LangGraph runnable implementing the standard ReAct loop (call model → if tool calls were requested, run them → loop back → return the final message).

See [main.py](src/langgraph-files-responses/main.py) for the full implementation.

### Agent Hosting

The async graph factory is registered in `langgraph.json` and loaded by `langchain_azure_ai.agents.hosting.run`, which exposes the OpenAI-compatible Responses endpoint at `/responses` and handles conversation history, streaming lifecycle events, and tool-call surfacing automatically.

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
mkdir hosted-langgraph-agent && cd hosted-langgraph-agent
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/responses/06-files/azure.yaml
```

### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployment, provision them. This sample also requires `TOOLBOX_NAME` to point at a Foundry Toolbox that exposes the `code_interpreter` tool:

```bash
azd provision
```

### Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

### Invoke the local agent

In a separate terminal, ask the agent to discover and analyze the bundled quarterly report:

```bash
azd ai agent invoke --local "Find the quarterly report under \`{cwd}/resources\` and tell me the difference of revenue between q1 2026 and q1 2025."
```

Or invoke directly with curl:

```bash
curl -X POST http://localhost:8088/responses \
    -H "Content-Type: application/json" \
    -d '{"input": "Find the quarterly report under `{cwd}/resources` and tell me the difference of revenue between q1 2026 and q1 2025."}'
```

The agent will call `get_cwd` and `list_files` to locate the file, `read_file` to load its contents, and `code_interpreter` to compute the revenue delta.

### Deploy to Foundry

Deploy the agent to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).

### Invoke the deployed agent

```bash
azd ai agent invoke "Find the quarterly report under \`{cwd}/resources\` and tell me the difference of revenue between q1 2026 and q1 2025."
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

### Set up the Python virtual environment

- Open the Command Palette (`Ctrl+Shift+P`) and run **Python: Create Environment...** to create a virtual environment in the workspace (or **Python: Select Interpreter** to use an existing one).
- Ensure `pip` is version 26.1 or newer (check with `pip --version`). Older versions fail to resolve this sample's dependencies. Upgrade if needed:

  ```bash
  python -m pip install --upgrade pip
  ```

- Change to the agent source directory before installing dependencies:

  ```bash
  cd src/langgraph-files-responses
  ```

- Install dependencies in the virtual environment. One transitive dependency ships as a pre-release, so pre-releases must be allowed when using `uv`:

  ```bash
  # use uv to accelerate
  pip install uv
  uv pip install --prerelease=allow -r requirements.txt

  # or pure pip
  pip install -r requirements.txt
  ```

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables (including `TOOLBOX_NAME`), and sign in to Azure with the Azure CLI (`az login`).
2. From `src/langgraph-files-responses`, start the agent: `python -m langchain_azure_ai.agents.hosting.run --protocol responses`
   (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `azure.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Sending an image or PDF as a request attachment

> **Prerequisite:** This path depends on
> [langchain-azure#1072](https://github.com/langchain-ai/langchain-azure/pull/1072).
> The currently committed `langchain-azure-ai==1.2.9` lock does not contain that fix.
> Update the dependency lock to a published version containing the fix before
> using this path. The session-file walkthrough below works with the existing lock.

Start the agent using the local run instructions above. In another terminal,
activate the same Python environment and change to `src/langgraph-files-responses`:

```bash
python send_attachment.py ./chart.png --prompt "Describe this chart using the attached image."
python send_attachment.py ./report.pdf --prompt "Summarize the attached PDF."
```

Use your own image or PDF; those two filenames are examples, not bundled files.
The client uses the official OpenAI SDK already installed by the sample. It sends
the file inline to `http://localhost:8088/responses`, together with the prompt.
Use `--port` if the host runs on a different local port. The local agent calls the
configured Foundry model, so this walkthrough requires the same project credentials,
Toolbox configuration, and model access as the rest of the sample.

Choose a deployed model that supports the attachment type and keep files within
its input limits. The agent already uses `use_responses_api=True`; no custom host
or text extraction is needed. The model receives `input_image` or `input_file`
content alongside the prompt. Verify that the answer refers to the contents of
the attachment, rather than only its name. Use the client when your Inspector
version does not expose an attachment picker.

This does not upload the attachment into a hosted session or make it available
as a path to `read_file` or the code interpreter. Conversely, uploading a session
file does not automatically include it in the model request. An `input_file.file_id`
must belong to a file accessible to the downstream model service and identity;
do not substitute a session path or session ID for a model file ID.

## Uploading files to a hosted session

After deploying the agent to Foundry, uploaded session files are mounted into the agent's working directory, where the same local tools can read them. Upload a file to the current session with:

```bash
azd ai agent files upload -f src/langgraph-files-responses/resources/contoso_q1_2026_report.txt
```

Then ask the agent about it:

```bash
azd ai agent invoke "Read the quarterly report I just uploaded and summarize the year-over-year revenue change."
```

## Troubleshooting

### Azure OpenAI Permission Denied (401)

If you see an error like:

```
Error calling Azure OpenAI: Error code: 401 - {'error': {'code': 'PermissionDenied', 'message': 'The principal <principal-id> lacks the required data action Microsoft.CognitiveServices/accounts/OpenAI/deployments/chat/completions/action to perform POST /openai/deployments/{deployment-id}/chat/completions operation.'}}
```

This sample uses its own LangChain (`ChatOpenAI`) client to call the project's Chat Completions endpoint directly, so the agent's managed identity needs the **Foundry User** role on the project — an ["Agent access beyond defaults"](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agent-permissions#agent-access-beyond-defaults) case:

- **Foundry User**

Use the Azure CLI to assign it:

```bash
# Set your variables
SUBSCRIPTION_ID="<your-subscription-id>"
RESOURCE_GROUP="<your-resource-group>"
ACCOUNT_NAME="<your-ai-foundry-account-name>"
PROJECT_NAME="<your-ai-foundry-project-name>"
PRINCIPAL_ID="<principal-id-from-error-message>"

# Assign "Foundry User" role
az role assignment create \
  --assignee "$PRINCIPAL_ID" \
  --role "Foundry User" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$ACCOUNT_NAME/projects/$PROJECT_NAME"
```

> **Note:** It may take a few minutes for role assignments to propagate. Retry the request after waiting.
