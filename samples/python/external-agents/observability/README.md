# External Agent Observability — Local Weather Agent

This sample shows the **end-to-end story for a Foundry "external" agent**:
a third-party agent runtime that lives **outside** Foundry, registered
into Foundry purely so its OpenTelemetry traces and Foundry-side
evaluations light up in the portal.

The runtime here is a tiny [LangChain](https://python.langchain.com/)
weather agent, instrumented with the
[Microsoft OpenTelemetry distro](https://github.com/microsoft/opentelemetry-distro-python)
so its spans flow into the Application Insights connected to your
Foundry project. The sample runs the agent locally to keep the demo
small. You can deploy the same runtime anywhere you host your agents;
just keep the same environment variables and `gen_ai.agent.id` value.

**GA note.** External agents are generally available in `azure-ai-projects`
2.11.0 and later, so these scripts don't need `allow_preview=True`. Only the
schedule script in Step 7 uses a preview API (`project_client.beta.schedules`).

**Distro note.** The Microsoft OTel distro now forwards per-library
kwargs from `instrumentation_options` into the instrumentor call
([microsoft/opentelemetry-distro-python#149](https://github.com/microsoft/opentelemetry-distro-python/pull/149)).
This sample passes `agent_id` and `agent_name` through the LangChain
instrumentation options so the emitted span attribute
`gen_ai.agent.id` matches the Foundry external-agent registration.

## Microsoft OpenTelemetry distro — references

To learn more about the distro or to find samples in another language,
start here:

- **Docs:** [Microsoft OpenTelemetry overview](https://learn.microsoft.com/en-us/azure/microsoft-opentelemetry/overview)
- **Samples by language:**
  - .NET — [microsoft/opentelemetry-distro-dotnet](https://github.com/microsoft/opentelemetry-distro-dotnet)
  - Python — [microsoft/opentelemetry-distro-python](https://github.com/microsoft/opentelemetry-distro-python)
  - JavaScript — [microsoft/opentelemetry-distro-javascript](https://github.com/microsoft/opentelemetry-distro-javascript)

## What's in this folder

| File | Purpose |
| --- | --- |
| [weather_agent.py](weather_agent.py) | LangChain weather agent + Microsoft OTel distro, exposed as a FastAPI HTTP service. This is the "external runtime". |
| [.env.example](.env.example) | Placeholder environment template for local configuration. |
| [generate_traffic.py](generate_traffic.py) | Sends a handful of weather questions to the running agent. |
| [generate_multiturn_traffic.py](generate_multiturn_traffic.py) | Drives multi-turn conversations, propagating one W3C `traceparent` per conversation. |
| [register_external_agent.py](register_external_agent.py) | Registers the runtime in Foundry as `kind=external` via the `azure-ai-projects` SDK. |
| [run_trace_eval.py](run_trace_eval.py) | Runs a one-off trace-based eval over the registered agent and prints scores. |
| [run_multiturn_trace_eval.py](run_multiturn_trace_eval.py) | Runs a conversation-level (multi-turn) trace eval and prints per-conversation scores. |
| [schedule_multiturn_trace_eval.py](schedule_multiturn_trace_eval.py) | Creates/lists/deletes a Foundry schedule that re-runs the multi-turn trace eval on a cron cadence. |
| [create_trace_eval_rule.py](create_trace_eval_rule.py) | Creates an hourly evaluation rule (GA) that continuously evaluates the agent's traces. |
| [run_agent_insights.py](run_agent_insights.py) | Runs Agent Insights over recent traces and prints recurring issues. |
| [generate_dataset_from_traces.py](generate_dataset_from_traces.py) | Generates an evaluation dataset from the agent's traces. |
| [generate_rubric_evaluator.py](generate_rubric_evaluator.py) | Generates a rubric evaluator from the agent's job description and traces. |
| [requirements.txt](requirements.txt) | Python deps for both the runtime and the helper scripts. |

## Architecture

```text
   ┌──────────────────────────┐       OTel spans         ┌──────────────────────┐
   │ Local weather agent      │ ───────────────────────▶ │ Application Insights │
   │ LangChain + MS distro    │  gen_ai.agent.id =       │ (linked to project)  │
   └──────────────────────────┘  "weather-agent-v1"      └─────────┬────────────┘
                                                                    │
                              register_external_agent.py            │ trace view
                                       │                            ▼
                                       ▼                     ┌─────────────────────┐
                              ┌─────────────────────┐        │   Foundry Portal    │
                              │  Foundry Project    │ ◀────  │  Agents → traces    │
                              │  agent kind=external│        │  Evaluations        │
                              └─────────────────────┘        └─────────────────────┘
```

## Prerequisites

1. **Azure resources**
   - A Foundry project with an Application Insights connection.
   - An Azure OpenAI deployment (for example, `gpt-4o-mini`) for both
     the agent LLM and the eval judge.
   - For Agent Insights (Step 8), a GPT-5 or later deployment, set as
     `INSIGHTS_MODEL_DEPLOYMENT`.
2. **Permissions**
   - Permission to create agents in the Foundry project (for example, `Foundry User`).
   - For trace evaluation, the Foundry project managed identity needs
     **Log Analytics Reader** *and* **Privileged Monitoring Data Reader** on the
     connected Application Insights (the latter is required to read GenAI
     message content — see Step 5). These roles also cover the trace reads in
     Steps 7–9.
3. For the status, model, and roles each capability needs, see
   [What you need for each capability](../README.md#what-you-need-for-each-capability).

## Step 1 — Configure environment

Start from [.env.example](.env.example), create a local `.env`, and
fill in your project, Application Insights, and Azure OpenAI values. The
Python scripts load this file automatically, and the local `.env` file is
ignored by git.

```env
FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...;IngestionEndpoint=...
AZURE_OPENAI_ENDPOINT=https://<aoai>.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_API_KEY=...
```

The Foundry scripts authenticate with `DefaultAzureCredential`, so sign in first:

```bash
az login
```

The runtime sets the required OpenTelemetry defaults before instrumentation.
Review the message-content capture setting in [weather_agent.py](weather_agent.py)
before using the sample with sensitive prompts or responses.

## Step 2 — Run the external runtime locally

```bash
cd samples/python/external-agents/observability
python -m pip install -r requirements.txt
python weather_agent.py
```

In another terminal, verify the runtime is healthy:

```bash
python -c "import httpx; print(httpx.get('http://localhost:8000/healthz').json())"
```

## Step 3 — Generate local traffic

```bash
python generate_traffic.py http://localhost:8000
```

Wait a minute or two for OpenTelemetry export and Application Insights
ingestion. The agent spans should include
`gen_ai.agent.id = weather-agent-v1`, `gen_ai.input.messages`, and
`gen_ai.output.messages`.

## Step 4 — Register the external agent in Foundry

```bash
python register_external_agent.py
```

This calls `project_client.agents.create_version(...)` with an
`ExternalAgentDefinition`, which creates the Foundry agent record if it
does not already exist. After registration succeeds, open the Foundry
portal:

> **Project → Agents → `weather-agent` → Traces**

The trace view will show spans attributed to this `external` agent.

## Step 5 — Run a one-off trace evaluation

Before running the trace evaluation, grant the Foundry project managed
identity **two** roles on the connected Application Insights resource:

- **Log Analytics Reader** — to read the trace/span data.
- **Privileged Monitoring Data Reader** — to read the GenAI **message content**
  (`gen_ai.input.messages` / `gen_ai.output.messages`). Depending on your
  Application Insights, this content may live in a separate `genAIContent`
  table that Log Analytics Reader alone cannot read. Without this role the
  evaluation still runs but every conversation fails with
  `Transcript does not have any user message`.

```bash
python run_trace_eval.py
```

This:

1. Creates an OpenAI-compatible eval group with the built-in trace
   evaluator `intent_resolution`.
2. Creates an `azure_ai_trace_data_source` `agent_filter` run scoped
   to that agent over the last 24 hours.
3. Polls until completion and prints per-criterion pass/fail counts.

## Step 6 — Evaluate multi-turn conversations

The steps above score a single turn at a time. To evaluate whole
conversations, the runtime needs to (a) carry state across turns and
(b) emit every turn of a conversation into the *same* trace.

### How turns are grouped

Grouping uses the W3C [trace context](https://www.w3.org/TR/trace-context/)
standard, not an application-level id:

* [generate_multiturn_traffic.py](generate_multiturn_traffic.py) opens one
  root span per conversation and injects that span's `traceparent` header
  into every turn's HTTP request.
* The `/chat` endpoint in [weather_agent.py](weather_agent.py) extracts the
  inbound `traceparent` and attaches it before invoking the agent.

Every turn therefore shares one `trace_id`, so **one trace is one
conversation**. `/chat` additionally passes the thread id through the
LangChain run metadata (`config={"metadata": {"thread_id": ...}}`), which the
Microsoft distro surfaces as the `gen_ai.conversation.id` span attribute.

Generate the traffic:

```bash
python generate_multiturn_traffic.py http://localhost:8000
```

### Run the conversation-level evaluation

```bash
python run_multiturn_trace_eval.py
```

The request differs from the single-turn eval in two ways — the
`azure_ai_trace_data_source` `agent_filter` data source and the
`evaluation_level` field on the run:

```python
data_source={
    "type": "azure_ai_trace_data_source",
    "trace_source": {
        "type": "agent_filter",
        "agent_name": AGENT_NAME,   # filter by the registered agent
        "start_time": start_unix,   # Unix seconds
        "end_time": end_unix,       # Unix seconds (padded for ingestion lag)
        "max_traces": 50,
    },
},
extra_body={"evaluation_level": "conversation"},
```

Two consequences follow from that flag:

* Testing criteria map to the whole conversation, `{"messages":
  "{{item.messages}}"}`, rather than per-turn `{{item.query}}` /
  `{{item.response}}`.
* The criteria are the conversation-level built-ins —
  `customer_satisfaction`, `task_completion`, `coherence`, and
  `groundedness` — configured with `initialization_parameters={"model": ...}`.

The run emits one output item per conversation, each carrying the
`conversation_id`, `trace_id`, contributing `span_ids`, and the full
reconstructed `messages` array.

### Selecting conversations explicitly

`--trace-id-mode` switches to the `trace_id_source` shape, which resolves
trace ids from Application Insights client-side and passes them explicitly:

```bash
python run_multiturn_trace_eval.py --trace-id-mode
```

This mode requires `APPINSIGHTS_RESOURCE_ID`, and — because it queries
Application Insights from your machine — the identity you run it with needs
**Log Analytics Reader** (or **Monitoring Reader**) on that resource. It
produces the same scores, but because the request identifies traces by id
rather than by agent, the resulting run is not associated with the registered
agent in the portal. Prefer the default agent filter unless you need to
evaluate a specific set of traces.

## Step 7 — Run the evaluation continuously

The scripts above are one-off: each invocation scores the traces in its
lookback window and exits. To keep scoring new traces as they arrive, let
Foundry run the evaluation on a timer.

### Turn-level: evaluation rule (GA)

[create_trace_eval_rule.py](create_trace_eval_rule.py) creates an evaluation
rule with a timer trigger. Every hour, the service reads a sample of the
agent's recent traces and adds an evaluation run to the evaluation:

```bash
python create_trace_eval_rule.py            # create or update the hourly rule
python create_trace_eval_rule.py --status   # show provisioning status
python create_trace_eval_rule.py --delete   # remove the rule
```

```python
project_client.evaluation_rules.create_or_update(
    id=RULE_ID,
    evaluation_rule=EvaluationRule(
        display_name="weather-agent hourly trace evaluation",
        action=TraceEvaluationRuleAction(
            eval_id=eval_id,
            source=TracesEvalRunDataSource(agent_name=AGENT_NAME, max_traces=10),
        ),
        event_type=EvaluationRuleEventType.TIMER_TRIGGER,
        schedule=RecurrenceTrigger(interval=1, schedule=HourlyRecurrenceSchedule()),
        enabled=True,
    ),
)
```

The trace lookback window is inferred from the recurrence interval. Re-running
the script updates the rule and keeps its evaluation, so score history stays in
one place; to change the testing criteria, run `--delete` first. This GA rule
scores individual turns; to score whole conversations on a timer, use the
preview schedule below.

### Conversation-level: schedule (preview)

To score whole conversations on a cadence,
[schedule_multiturn_trace_eval.py](schedule_multiturn_trace_eval.py) creates a
**schedule** that re-runs the conversation-level evaluation from Step 6:

```bash
python schedule_multiturn_trace_eval.py                       # hourly
python schedule_multiturn_trace_eval.py --cron "*/30 * * * *" --lookback-hours 1
python schedule_multiturn_trace_eval.py --list                # list schedule runs
python schedule_multiturn_trace_eval.py --delete              # remove the schedule
```

Under the hood it creates a persisted eval group, then attaches a schedule whose
task re-runs that eval. On each run, the service moves the trace window to end at
the run time and keeps its length (`end_time` minus `start_time`, set from
`--lookback-hours`), so every run scores the agent's most recent conversations.
Keep the window a bit longer than the cron interval to absorb Application Insights
ingestion lag:

```python
from azure.ai.projects.models import Schedule, CronTrigger, EvaluationScheduleTask

# The scheduled run payload mirrors what run_multiturn_trace_eval.py passes to
# client.evals.runs.create in Step 6. Two differences when building it by hand:
# it must carry eval_id, and evaluation_level (sent via extra_body by the OpenAI
# client) is just a top-level key here.
eval_run = {
    "eval_id": eval_object.id,
    "name": "weather-agent-multiturn-scheduled",
    "data_source": {
        "type": "azure_ai_trace_data_source",
        "trace_source": {
            "type": "agent_filter",
            "agent_name": AGENT_NAME,   # filter by the registered agent
            "start_time": start_unix,   # Unix seconds
            "end_time": end_unix,       # Unix seconds (padded for ingestion lag)
            "max_traces": 50,
        },
    },
    "metadata": {"agent_name": AGENT_NAME},
    "evaluation_level": "conversation",
}

project_client.beta.schedules.create_or_update(
    schedule_id=SCHEDULE_ID,
    schedule=Schedule(
        display_name="weather-agent multi-turn conversation eval",
        enabled=True,
        trigger=CronTrigger(expression="0 * * * *", time_zone="UTC"),
        task=EvaluationScheduleTask(eval_id=eval_object.id, eval_run=eval_run),
    ),
)
```

The `eval_run` payload is the same shape passed to `client.evals.runs.create`
in Step 6 (data source, metadata, and the `evaluation_level` flag), so the
scheduled runs score conversations just like the manual run. A trailing overlap
means a few conversations near the window edge may be scored twice; that is
harmless. Inspect runs with `--list` and stop the schedule with `--delete`
(these call `project_client.beta.schedules.list_runs` /
`project_client.beta.schedules.delete`). Schedules are in preview.

## Step 8 — Find recurring issues with Agent Insights

[run_agent_insights.py](run_agent_insights.py) runs Agent Insights over the
agent's recent traces. It creates an on-demand monitor for the agent (or reuses
one), starts a run, and prints each active insight with its severity, trace
count, and proposed next step:

```bash
python run_agent_insights.py --lookback-hours 24
python run_agent_insights.py --delete   # remove the monitor
```

Set `INSIGHTS_MODEL_DEPLOYMENT` to a GPT-5 or later deployment for the analysis.
If you change it, the next run switches the existing monitor to the new model. Foundry doesn't have the external
agent's code, so proposed next steps are general guidance to apply in your own
code. The monitor is kept so you can review the insights in the portal
(**Agents** > your agent > **Insights**).

## Step 9 — Turn traces into tests

Two generation jobs turn production traces into reusable evaluation assets.

**Dataset from traces.**
[generate_dataset_from_traces.py](generate_dataset_from_traces.py) turns each
captured turn into a dataset row that you can review and re-run as a test:

```bash
python generate_dataset_from_traces.py --lookback-hours 24 --max-samples 15
```

The project managed identity needs read access to the connected Application
Insights resource; the Log Analytics Reader role from Step 5 covers it. Test-case rubrics (`generate_test_case_rubric=True`) and
conversation-level datasets are in preview and aren't used here.

**Rubric evaluator.**
[generate_rubric_evaluator.py](generate_rubric_evaluator.py) generates a rubric
evaluator with named pass/fail dimensions from a description of the agent's job
plus its traces:

```bash
python generate_rubric_evaluator.py --lookback-hours 24
```

Edit `AGENT_JOB_DESCRIPTION` to describe your own agent. Review and edit the
generated dimensions in the portal, then use the evaluator by name as a testing
criterion in any evaluation.
