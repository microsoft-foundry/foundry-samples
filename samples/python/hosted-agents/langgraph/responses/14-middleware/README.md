# What this sample demonstrates

A LangChain `create_agent` with built-in and custom middleware, hosted on
Microsoft Foundry over the **Responses protocol**. The email tool is simulated;
no real email is sent.

Ported from [langchain-ai/langchain-azure PR #1179](https://github.com/langchain-ai/langchain-azure/pull/1179),
using the [merged sample at `ed7b1ee`](https://github.com/langchain-ai/langchain-azure/tree/ed7b1ee2d9b7b94ddaa3ae5d73317b6bc504952e/samples/hosting/langgraph-hosted-agents/responses/11_middleware)
as the baseline. Unlike [07-human-in-the-loop](../07-human-in-the-loop/), which
implements its own review node, this sample uses native LangChain middleware.

## How it works

- [agent.py](src/langgraph-middleware/agent.py) composes
  [`HumanInTheLoopMiddleware`](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
  with a custom `@before_model` hook. The hook stops the turn at 50 accumulated
  messages before calling the model. It is not a pre-tool limit: a reviewed
  tool can execute on resume before the following model call is stopped.
- [main.py](src/langgraph-middleware/main.py) connects `ChatOpenAI` to the Foundry
  project endpoint using `DefaultAzureCredential`, `use_responses_api=True`, and
  `output_version="responses/v1"`.
- `ResponsesHostServer` handles interrupt serialization and resume translation;
  `FoundryCheckpointSaver` persists graph state locally during development and
  in Foundry State Store when deployed. Keep local `.agentserver` data when
  restarting a paused local run. The explicit host entry point owns the async
  checkpoint and model-client lifetimes; it does not reimplement middleware.
- [client.py](src/langgraph-middleware/client.py) displays the proposed actions,
  then resumes the paused response using `previous_response_id`.

| Decision | Expected result |
| --- | --- |
| Approve | Execute the proposed simulated email. |
| Edit | Replace only the recipient, preserving subject and body. The tool receipt reports the executed arguments. |
| Reject | Feed rejection back to the agent without executing the tool. |

Approve and reject use `mcp_approval_response`. Edit uses the paired
`__hosted_agent_adapter_interrupt__` function-call channel with native
LangChain `decisions` wrapped in an interrupt-keyed `resume` payload. A rejected
tool action is middleware feedback, not a rejected host-level interrupt.

### Tracing and privacy

Both `AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED` and
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` default to `false` in the
host and deployment manifest. Enabling either can export messages, tool
arguments, and results. These switches control telemetry, not checkpoint or
Responses persistence; stored conversations and checkpoints still contain
message/tool content. Use only synthetic email data when trying the sample.

Tracing uses Application Insights when available, or an OTLP HTTP exporter when
`OTEL_EXPORTER_OTLP_ENDPOINT` or `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is set.
Set `OTEL_SDK_DISABLED=true` to disable tracing locally.

## Prerequisites

- An Azure subscription with access to hosted agents and a Foundry project with
  a chat model deployment. The manifest provisions `gpt-5.4-mini` by default;
  change its model, version, and SKU if your region requires another model.
- **Python 3.13+**, matching the declared hosted runtime.
- **uv 0.11.7**, matching this repository's dependency-policy validation version.
- Permission to provision the declared resources, or access to an existing
  project and model deployment.

## Option 1: Azure Developer CLI (`azd`)

### Set up and initialize

Install [Azure Developer CLI](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd),
then install the Foundry extension and authenticate:

```bash
azd ext install microsoft.foundry
azd auth login
mkdir hosted-langchain-middleware
cd hosted-langchain-middleware
azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/langgraph/responses/14-middleware/azure.yaml
```

When testing an unmerged PR, replace `main` in that URL with the PR branch.

### Provision Azure resources (if needed)

```bash
azd provision
```

### Run the agent locally

```bash
azd ai agent run
```

The host listens on `http://localhost:8088`.

### Invoke the local agent

In another terminal, from the initialized project directory:

```bash
azd ai agent invoke --local "Hello!"
```

Use the [review client](#review-an-email) for the full approve/edit/reject flow.
A plain invocation of an email prompt pauses; it does not send an email.

### Deploy to Foundry

```bash
azd deploy
```

The manifest defaults to **direct code deployment** (`codeConfiguration`). This
path does not require Docker on your machine.

The sample also includes a [Dockerfile](src/langgraph-middleware/Dockerfile) and
[.dockerignore](src/langgraph-middleware/.dockerignore), matching neighboring
samples. To use container deployment, install and start Docker, initialize a
separate workspace with the same manifest URL and `--deploy-mode container`,
then follow the same provision/deploy steps. The image uses Python 3.13 and
uv 0.11.7 and installs only the frozen production dependencies.

Repository cloud CI validates both container and direct-code deployment. The
Dockerfile is excluded from direct-code uploads by `.agentignore`; local
environments, secrets, tests, and generated state are excluded from the image.

### Invoke the deployed agent

```bash
azd ai agent invoke "Hello!"
```

## Option 2: VS Code (Foundry Toolkit)

### Set up the environment

Install [VS Code](https://code.visualstudio.com/), the
[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio),
the Python extension, and [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).
Sign in with `az login`, clone this repository, and open this sample folder.

From the VS Code terminal:

```bash
cd src/langgraph-middleware
uv sync --frozen
```

Copy [.env.example](src/langgraph-middleware/.env.example) to `.env` in that source
directory. Set `FOUNDRY_PROJECT_ENDPOINT` and
`AZURE_AI_MODEL_DEPLOYMENT_NAME` for your existing project. Do not commit `.env`.
Select the source directory's `.venv` interpreter in VS Code.

### Run and debug

Press **F5** in the Toolkit-scaffolded workspace. The Toolkit generates its
launch/task files and opens the **Agent Inspector** automatically. Those
generated files are not part of this sample.

Or run manually from `src/langgraph-middleware`:

```bash
uv run --frozen main.py
```

Then use **Foundry Toolkit: Open Agent Inspector** from the Command Palette.
Use `client.py` when exercising edit or reject decisions.

### Deploy to Foundry

Run **Foundry Toolkit: Deploy Hosted Agent**, select your Foundry project,
choose **Code**, confirm `main.py` as the entry point, and deploy. Invoke the
agent in the playground and inspect its **Logs** tab.

## Review an email

Run the following commands from `src/langgraph-middleware` in a second terminal
while the local host is running:

```bash
uv run --frozen client.py
uv run --frozen client.py --decision approve
uv run --frozen client.py --decision edit --recipient bob@example.com
uv run --frozen client.py --decision reject
uv run --frozen client.py --stream --decision approve
```

The default prompt proposes an email to `alice@example.com`. The first command
asks for a decision interactively; the others apply the supplied decision.
Each command begins a new review. Inspect the final response for the executed
recipient, subject, and body. Rejection must not execute `send_email`.

For a deployed agent, use the same project endpoint and model configuration,
authenticate with Azure CLI, and add its registered name:

```bash
uv run --frozen client.py --agent-name langgraph-middleware --decision approve
uv run --frozen client.py --agent-name langgraph-middleware --decision edit --recipient bob@example.com
```

## Validation

From `src/langgraph-middleware`, run the credential-free regression suite:

```bash
uv run --frozen pytest tests -q
uv run --frozen ruff check agent.py main.py client.py tests
```

The tests use real LangChain middleware and the real Responses host, replacing
only model/network dependencies. They cover pause/resume, approve/edit/reject,
message limits, streaming completion, and default telemetry redaction.

The repository's [cloud behavior contract](../../../../../../.azure-pipelines/hosted-agent-tests/python/langgraph/responses/14-middleware/test-spec.yml)
checks the pending email review and that a specifically approved email executes.
The local tests additionally assert no execution before review. The shared cloud
harness supports automatic approval, not edit
or rejection; use the local tests and review client for those decisions.
Registering the contract does not itself constitute a successful cloud run.

## Troubleshooting

- **Missing project endpoint:** set `FOUNDRY_PROJECT_ENDPOINT` in the source
  directory's `.env`, or initialize the project with `azd` first.
- **Model not found:** set `AZURE_AI_MODEL_DEPLOYMENT_NAME` to your actual
  deployment name, not merely a model family name.
- **Review not returned:** ask explicitly to send an email with recipient,
  subject, and body. Greetings do not trigger human review.
- **Conversation limit reached:** begin a new conversation. The limit counts
  accumulated graph messages, including tool calls and results.
- **Interrupted local run cannot resume:** keep the local checkpoint/response
  data and resume against the same host state; do not delete `.agentserver`
  or switch projects while a review is pending.

## Next steps

- [Human-in-the-Loop graph sample](../07-human-in-the-loop/)
- [Observability sample](../08-observability/)
- [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
- Run `azd down` when finished to remove resources provisioned for this sample.
