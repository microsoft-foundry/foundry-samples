# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) regular agent
hosted on Microsoft Foundry through Responses protocol **2.0.0**. It accepts a
second stored background request on the same active conversation instead of
rejecting it with `conversation_locked`.

> [!IMPORTANT]
> Steering is separate from crash recovery. This sample does not use workflow
> checkpoints or resilient background recovery.

## How it works

`ResponsesHostServer` enables `steerable_conversations` for a normal
model-backed `Agent`. A finite asynchronous tool keeps the first model turn
active long enough to send a second instruction deterministically.

Agent Server owns conversation admission:

1. The first stored background response starts on a conversation.
2. A second request uses the same `conversation` while the first response is
   active.
3. The second response is accepted while the first remains `in_progress`.
4. Both response IDs independently reach a terminal state.

Do not include `previous_response_id` in the steering request. Responses rejects
a request that supplies both `conversation` and `previous_response_id`.

> [!NOTE]
> The current published Python hosting beta differs from the .NET host used by
> the reference sample. It reports the admitted second response as
> `in_progress`, not `queued`, and does not guarantee serialized completion
> order. This sample demonstrates the Python API that is currently supported;
> it does not claim the .NET queue semantics.

## Prerequisites

1. A Foundry project with a deployed model.
2. Python 3.13 and [uv](https://docs.astral.sh/uv/) 0.11.7.
3. Azure CLI authenticated with `az login`.
4. The hosted agent's managed identity must have **Foundry User** at the
   Foundry project scope before testing stored background responses.

## Option 1: Azure Developer CLI (`azd`)

### Set up the project

```bash
mkdir steering && cd steering
azd ext install microsoft.foundry
azd auth login
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/24-steering/azure.yaml
cd agent-framework-steering-responses
```

Follow the prompts to select or provision a Foundry project and model.

### Run locally

```bash
azd ai agent run --no-client
```

The Responses endpoint listens on `http://localhost:8088/responses`.

### Run the inexpensive smoke path

```bash
azd ai agent invoke --local "Reply with the exact marker [STEERING-READY-731]."
```

The response includes:

```text
[STEERING-READY-731]
```

### Deploy

```bash
azd deploy
```

### Grant stored response access

After the first deployment creates the hosted agent identity, grant it
**Foundry User** at the project scope:

```bash
azd ai agent show agent-framework-steering-responses -o json
azd env get-value AZURE_AI_PROJECT_ID

az role assignment create \
  --assignee-object-id <instance_identity.principal_id> \
  --assignee-principal-type ServicePrincipal \
  --role "Foundry User" \
  --scope <AZURE_AI_PROJECT_ID>
```

Copy `instance_identity.principal_id` from the first command and the project
resource ID from the second command into the role-assignment command.
Wait for the role assignment to propagate before testing stored background
responses.

### Invoke the deployed agent

```bash
azd ai agent invoke "Reply with the exact marker [STEERING-READY-731]."
```

## Option 2: Python or VS Code

From `src/agent-framework-steering-responses`:

```bash
python -m pip install "uv==0.11.7"
uv sync --frozen
cp .env.example .env
az login
uv run python main.py
```

Fill in `FOUNDRY_PROJECT_ENDPOINT` and
`AZURE_AI_MODEL_DEPLOYMENT_NAME` in `.env`.

In VS Code, the Foundry Toolkit can generate the local debug configuration and
open Agent Inspector. Use the REST walkthrough below to submit overlapping
requests on one explicit conversation.

## Validate same-conversation steering

Start a long-running stored response in a new session and conversation:

```bash
azd ai agent invoke \
  --new-session \
  --new-conversation \
  --long-running \
  --no-wait \
  "Start the long-running task for 60 seconds. Report [FIRST-NATURAL-COMPLETE] only after the tool finishes."
```

Copy the ID printed under `Response`; it is the
`<first-response-id>` used below. Before that response finishes, invoke the
agent again without creating a new session or conversation:

```bash
azd ai agent invoke \
  --long-running \
  --no-wait \
  "Steering input: reply with [STEERING-SUCCEEDED:AZD]."
```

`azd` reuses the active session and conversation. The second response becomes
the current invocation. Follow both stored responses:

```bash
azd ai agent invocations follow --id <first-response-id>
azd ai agent invocations follow
```

The current published Python beta reports the admitted second response as
`in_progress`, not `queued`, and it can complete before or after the first.
Use `show` to inspect either response without following its output:

```bash
azd ai agent invocations show --id <first-response-id>
azd ai agent invocations show
```

Successful steering proves all of the following:

- the first create returned `in_progress`;
- the second create was accepted before the first completed;
- `azd` reused the same session and conversation;
- the second response completed and contains
  `[STEERING-SUCCEEDED:AZD]`;
- the second request did not use `previous_response_id`;
- the first response eventually completed with `[FIRST-NATURAL-COMPLETE]`.

## Steering contract

- Use `background=true` and `store=true` for both turns.
- Send steering on the same explicit conversation while the first response is
  active.
- Do not send `previous_response_id` with that explicit conversation.
- Keep active-turn work finite and release resources in `finally`.
- Do not use steering as a crash-recovery mechanism.

## Troubleshooting

**The second create is rejected.** Remove `previous_response_id` from the
request when `conversation` is present.

**The second turn is rejected with `conversation_locked`.** Confirm
`ResponsesServerOptions(steerable_conversations=True)` is passed to the host.

## Next steps

- [Resilient Workflow](../23-resilient-workflow/)
- [LangGraph resilient Responses](../../../langgraph/responses/09-resilient/)
- [Agent Framework agents](https://learn.microsoft.com/en-us/agent-framework/agents/)
