# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) workflow
hosted on Microsoft Foundry through Responses protocol **2.0.0**. It restores a
stored background response from a durable workflow checkpoint after the hosted
process exits and Foundry starts a replacement process.

> [!IMPORTANT]
> This sample demonstrates crash recovery, not steering. Resilient Responses
> require both `background=true` and `store=true`.

## How it works

The workflow contains a model-backed executor and a crash-tool executor:

```text
input -> model executor -> crash-tool executor -> model executor -> output
```

The model executor exposes a declaration-only `simulate_crash` tool. When the
model calls it, the executor commits the agent session and pending tool call in
workflow checkpoint state before forwarding the call. The crash-tool executor
then waits five seconds so Agent Server can durably pair the workflow and
response checkpoints before it exits the process.

On a replacement process, Agent Framework restores the same named workflow and
executor state. The crash-tool executor recognizes that restoration and returns
a result with the original tool-call ID instead of exiting again. The restored
model session consumes that result and finishes the original response.

The workflow and executor names are stable because checkpoint compatibility and
recovery routing depend on those identities. No marker file or process-local
cache participates in recovery.

## Prerequisites

1. A Foundry project with a deployed model.
2. Python 3.13 and [uv](https://docs.astral.sh/uv/) 0.11.7.
3. Azure CLI authenticated with `az login`.
4. The hosted agent's managed identity must have **Foundry User** at the
   Foundry project scope so it can access durable checkpoint state.

If the role is assigned after the first failed invocation, create a new agent
version or restart the hosted process. A running container can retain a managed
identity token acquired before the role assignment.

## Option 1: Azure Developer CLI (`azd`)

### Set up the project

```bash
mkdir resilient-workflow && cd resilient-workflow
azd ext install microsoft.foundry
azd auth login
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/23-resilient-workflow/azure.yaml
cd agent-framework-resilient-workflow-responses
```

Follow the prompts to select or provision a Foundry project and model.

### Run locally

```bash
azd ai agent run --no-client
```

The Responses endpoint listens on `http://localhost:8088/responses`.

### Run the inexpensive smoke path

```bash
azd ai agent invoke --local "Reply with the exact marker [RESILIENT-WORKFLOW-OK-731]. Do not call tools."
```

The response includes:

```text
[RESILIENT-WORKFLOW-OK-731]
```

### Deploy

```bash
azd deploy
```

### Grant durable state access

After the first deployment creates the hosted agent identity, grant it
**Foundry User** at the project scope:

```bash
azd ai agent show agent-framework-resilient-workflow-responses -o json
azd env get-value AZURE_AI_PROJECT_ID

az role assignment create \
  --assignee-object-id <instance_identity.principal_id> \
  --assignee-principal-type ServicePrincipal \
  --role "Foundry User" \
  --scope <AZURE_AI_PROJECT_ID>
```

Copy `instance_identity.principal_id` from the first command and the project
resource ID from the second command into the role-assignment command.
Wait for the role assignment to propagate before testing recovery. If an
invocation already failed before the grant, run `azd deploy` again so the next
hosted process acquires a fresh managed identity token.

### Invoke the deployed agent

```bash
azd ai agent invoke "Reply with the exact marker [RESILIENT-WORKFLOW-OK-731]. Do not call tools."
```

## Option 2: Python or VS Code

From `src/agent-framework-resilient-workflow-responses`:

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
open Agent Inspector. Use the REST walkthrough below for crash recovery because
the client must preserve and retrieve the same response ID.

## Validate crash recovery

Start a stored background response in a new session and conversation, then
return after `azd` receives the response ID:

```bash
azd ai agent invoke \
  --new-session \
  --new-conversation \
  --long-running \
  --no-wait \
  "Call simulate_crash once, then report [RECOVERY-SUCCEEDED] after the recovered tool result."
```

The command prints the response ID under `Response` and saves it as the current
invocation. Follow that same stored response through process replacement:

```bash
azd ai agent invocations follow
```

`follow` replays persisted output and waits while Foundry starts a replacement
process. If it exits during a transient replacement timeout, run the same
command again. `azd` retains the response ID, so the next `follow` continues the
same response instead of submitting the input again.

Fetch the recovered session's container logs:

```bash
azd ai agent monitor --tail 300 --utc
```

Successful recovery proves all of the following:

- the final status is `completed`;
- `follow` completes the response ID printed by the original invoke;
- output contains `[RECOVERY-SUCCEEDED]`;
- container logs contain `Reclaimed stale task`, `Recovered task`, and
  `Restored pending crash function call`;
- the crash tool runs only once before recovery.

## Recovery contract

- `background=true` requires `store=true`.
- The response ID is the recovery identity. Retry retrieval after transient
  failures instead of submitting a replacement request.
- Workflow state, pending messages, and agent session state must be serializable.
- Process memory, active HTTP requests, and cancellation events are transient.
- A crash can replay the last checkpoint boundary. External writes therefore
  need stable operation IDs and idempotent handling.
- Grant **Foundry User** at project scope before stateful validation.

## Troubleshooting

**The response fails after the first executor.** Grant the hosted agent managed
identity **Foundry User** at the Foundry project scope, then restart or deploy a
new version so the process obtains a fresh token.

**The replacement process crashes again.** Confirm the workflow and executor
names did not change and that restored executor state is used rather than a
process-local marker.

**Create is rejected.** Confirm both `background` and `store` are `true`.

## Next steps

- [Steering](../24-steering/)
- [LangGraph resilient Responses](../../../langgraph/responses/09-resilient/)
- [Agent Framework workflows](https://learn.microsoft.com/en-us/agent-framework/workflows/)
