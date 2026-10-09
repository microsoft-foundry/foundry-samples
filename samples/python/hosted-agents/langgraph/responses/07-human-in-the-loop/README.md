# What this sample demonstrates

A [LangGraph](https://langchain-ai.github.io/langgraph/) **human-in-the-loop** agent hosted on Foundry over the **Responses protocol** using [`langchain_azure_ai.agents.hosting`](https://github.com/langchain-ai/langchain-azure/tree/main/libs/azure-ai/langchain_azure_ai/agents/hosting). The agent drafts a proposal for the user's task, pauses for human review via [`langgraph.types.interrupt`](https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/), and supports three decisions — **approve**, **revise** (with feedback), or **reject** — surfaced to the client as the standard OpenAI `mcp_approval_request` output item plus a paired `function_call` channel for rich resume payloads.

## How It Works

### Graph shape

```
START → draft → await_approval ──approve──► END (emit final draft)
                       │
                       └──revise(feedback)──► draft (loop)
                       │
                       └──reject──► host returns response.failed (interrupt_rejected)
```

The graph state declares three channels:

- **`messages`** — the channel the Responses host emits to the client. Only the **final approved draft** is appended to it.
- **`draft`** — the current proposal text under review.
- **`revision_history`** — list of `{draft, feedback}` pairs from prior revision rounds; each round seeds the next `draft` call with the rejected draft and the reviewer's feedback.

Routing out of `await_approval` is done by returning a [`Command(goto=...)`](https://langchain-ai.github.io/langgraph/how-tos/command/) instead of static edges, so the same node can finalize, loop, or stay paused depending on the resume value.

State is persisted by `FoundryCheckpointSaver` and keyed by the `conversation.id` from the Responses request, so follow-up requests continue the paused run even after a process restart. The saver uses Foundry State Store when hosted and a local file-backed store during local development. See [main.py](src/langgraph-human-in-the-loop-responses/main.py) for the full implementation.

### Review decisions

The Responses host emits two paired output items for each pause, both keyed by the same interrupt id:

* an `mcp_approval_request` item (`server_label == "langgraph"`, `arguments` JSON contains `{"interrupt_id": "<id>", "value": {"draft": "<text>"}}`) — the OpenAI-standard approval channel, and
* a `function_call` item with `name == "__hosted_agent_adapter_interrupt__"` — a parallel rich channel for callers that want to send arbitrary resume payloads via `function_call_output`.

| Decision | Client sends | Resume value seen by `await_approval` | Outcome |
|---|---|---|---|
| **Approve** | `mcp_approval_response` with `approve: true` and `approval_request_id: "<id>"` | `{"draft": "<original draft>"}` (proposed dict echoed; no `feedback`) | Final draft appended to `messages`; turn ends with `response.completed`. |
| **Reject** | `mcp_approval_response` with `approve: false` (optionally `reason: "<text>"`) | _(node never re-enters)_ | Host returns `response.failed` with `code="interrupt_rejected"`. Checkpoint preserved; client can retry. |
| **Revise** | `function_call_output` with `call_id: "<id>"` and `output: '{"resume": {"feedback": "<text>"}}'` | `{"feedback": "<text>"}` | Graph loops back to `draft` with `revision_history` appended; a new draft is generated and re-paused for review. |

### Agent Hosting

The graph factory is registered in `langgraph.json` and loaded by `langchain_azure_ai.agents.hosting.run`, which exposes the OpenAI-compatible Responses endpoint at `/responses` and handles conversation history, interrupt serialization, and streaming lifecycle events automatically.

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
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/responses/07-human-in-the-loop/azure.yaml
```

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

This sample uses a human-in-the-loop approval flow: submit a task, then approve, reject, or revise the proposed draft. Run the requests below from a separate terminal.

**Step 1 — Submit the task.** Send a POST request with a `conversation.id` so the checkpoint can be matched on subsequent requests:

```bash
curl -X POST http://localhost:8088/responses \
    -H "Content-Type: application/json" \
    -d '{"input": "Draft a marketing email for our new AI product launch.", "conversation": {"id": "demo-hitl-1"}}'
```

The response `output` will contain an `mcp_approval_request` whose `arguments` JSON describes the proposed draft:

```json
{"interrupt_id": "<id>", "value": {"draft": "Subject: ...\n\nHi ..."}}
```

Note the `id` field of the `mcp_approval_request` item — you will reference it as `approval_request_id` (or as the `call_id` of the paired `function_call`) in the next request.

**Step 2 — Send a decision.**

*Approve* — the host resumes the graph and emits the final draft:

```bash
curl -X POST http://localhost:8088/responses \
    -H "Content-Type: application/json" \
    -d '{"conversation": {"id": "demo-hitl-1"}, "input": [{"type": "mcp_approval_response", "approval_request_id": "<id>", "approve": true}]}'
```

*Reject* — the turn ends with `response.failed` `code="interrupt_rejected"`; the pending interrupt remains in the checkpoint:

```bash
curl -X POST http://localhost:8088/responses \
    -H "Content-Type: application/json" \
    -d '{"conversation": {"id": "demo-hitl-1"}, "input": [{"type": "mcp_approval_response", "approval_request_id": "<id>", "approve": false, "reason": "tone is too casual"}]}'
```

*Revise* — target the paired `function_call` item (its `call_id` is the same interrupt id) and send the feedback:

```bash
curl -X POST http://localhost:8088/responses \
    -H "Content-Type: application/json" \
    -d '{"conversation": {"id": "demo-hitl-1"}, "input": [{"type": "function_call_output", "call_id": "<id>", "output": "{\"resume\": {\"feedback\": \"Shorter and more energetic, add a clear call to action.\"}}"}]}'
```

The graph generates a new draft incorporating the feedback and pauses again with a fresh `mcp_approval_request` — repeat Step 2 until you approve or reject.

### Deploy to Foundry

Deploy the agent to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Azure AI Foundry hosted agents](https://aka.ms/azdaiagent/docs).

### Invoke the deployed agent

```bash
azd ai agent invoke "Draft a marketing email for our new AI product launch."
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

### Set up the Python virtual environment

- Install uv if it is not already available:

  ```bash
  python -m pip install uv
  ```

- From the sample root, sync the committed environment:

  ```bash
  cd src/langgraph-human-in-the-loop-responses
  uv sync --frozen
  ```

- In VS Code, select `src/langgraph-human-in-the-loop-responses/.venv` as the Python interpreter.
### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Send the following message in the Inspector:

```
Draft a marketing email for our new AI product launch.
```

When the agent pauses with an approval request, the Inspector renders an interactive approval card. Approve, reject, or send revision feedback directly from there.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `uv run --no-sync python -m langchain_azure_ai.agents.hosting.run --protocol responses` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

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
