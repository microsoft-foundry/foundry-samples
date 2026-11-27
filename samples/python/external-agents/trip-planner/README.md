# Tutorial: Improve an external agent with Foundry

This tutorial follows Contoso Travel, a fictional company that runs its own
trip-planning agent outside Foundry. You connect the agent to Foundry, find
problems in production, turn expert review into tests, and use those tests to
measure and improve the agent. Each step is one script.

Contoso Travel, its tools, and all data are fictional.

| Step | Script | What it does | Status |
|---|---|---|---|
| 0 | [agent.py](agent.py) | The agent: Microsoft Agent Framework, sending OpenTelemetry traces to Application Insights | GA |
| 1 | [01_register_agent.py](01_register_agent.py) | Register the agent in Foundry as an external agent | GA |
| 2 | [02_send_traffic.py](02_send_traffic.py) | Send production-like requests; each becomes a trace | — |
| 3 | [03_run_agent_insights.py](03_run_agent_insights.py) | Find recurring issues with Agent Insights | GA |
| 4 | [04_annotate_traces.py](04_annotate_traces.py) | Annotate traces as a domain expert would | Preview |
| 5 | [05_create_test_cases.py](05_create_test_cases.py) | Turn annotated traces into test cases with task-level rubrics | Preview |
| 6 | [06_generate_shared_rubric.py](06_generate_shared_rubric.py) | Generate a shared rubric from the agent's job and its traces | GA |
| 7 | [07_evaluate_continuously.py](07_evaluate_continuously.py) | Score a sample of production traces every hour, with a custom policy evaluator | GA (custom evaluator and intelligent sampling: preview) |
| 8 | [08_run_golden_dataset.py](08_run_golden_dataset.py) | Run the golden dataset against an agent version and compare | GA (task-level rubric and custom evaluator: preview) |
| 9 | [09_optimize_skill.py](09_optimize_skill.py) | Propose a skill from past traces with skill optimization, then review and test it | Preview |

Supporting files: [travel_tools.py](travel_tools.py) (mock tools),
[instructions.py](instructions.py) (agent versions),
[golden_dataset.jsonl](golden_dataset.jsonl) (reviewed test cases), and
[tutorial_utils.py](tutorial_utils.py) (shared helpers).

## The two problems in the launch version

The `v1` instructions have two problems on purpose, so they show up in real traces:

- **Outdated carry-on rule.** `v1` answers bag questions from its instructions
  (56 x 45 x 25 cm, 10 kg) instead of calling `policy_lookup`, which returns the
  current rule (55 x 35 x 20 cm, 7 kg). It also adds those outdated "quick facts"
  to unrelated answers.
- **Repeated searches on multi-city trips.** `v1` searches every pair of cities,
  then searches each leg again.

`v2` always calls `policy_lookup` for policy questions and searches each leg once.

## Prerequisites

- A Foundry project with an Application Insights resource connected.
- A chat model deployment for the agent (`AZURE_OPENAI_DEPLOYMENT`), and a GPT-5 or
  later deployment for judging and analysis (`JUDGE_MODEL_DEPLOYMENT`). Agent
  Insights, dataset and rubric generation, the evaluators, and skill optimization
  use the judge model; without it, they fall back to the agent's model.
- Roles:
  - You: **Foundry User** on the project, **Cognitive Services OpenAI User** on
    the model deployment, and **Monitoring Reader** on Application Insights.
  - The project's managed identity: **Reader** and **Privileged Monitoring Data
    Reader** on Application Insights, so evaluations and generation jobs can read
    trace content.
- Python 3.11 or later and the Azure CLI.

## Set up

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env
az login
```

Fill in `.env`. `OTEL_AGENT_ID` is the `gen_ai.agent.id` value on the agent's
traces, and step 1 registers the agent with the same ID.

> [!NOTE]
> `agent.py` sets `enable_sensitive_data=True`, which records prompts and
> responses in your traces. Evaluators that score what the agent said need that
> content. Before you turn it on in production, decide what content you're
> allowed to capture, who can see it, how long you keep it, and whether to
> redact it first.

The scripts save the names of what they create (dataset, evaluators,
evaluation) in `.tutorial_state.json`, so later steps can find them.

## Connect the agent you already have

```powershell
python 01_register_agent.py
python 02_send_traffic.py --instructions v1 --repeat 2
python 02_send_traffic.py --instructions v2 --category policy
```

Open the agent in the Foundry portal (**Build** > **Agents** >
**contoso-trip-planner**) and select **Traces**. Traces usually appear within a
few minutes. Use the trace view to filter by time, status, or tokens and to
open a run step by step. Open a v1 carry-on trace and notice there's no
`policy_lookup` call.

## Find problems in production

```powershell
python 03_run_agent_insights.py --lookback-hours 24
```

Expect an insight about multi-city trips repeating the same searches. Review
the insights in the portal under **Insights**.

## Turn human expert review into reusable tests

```powershell
python 04_annotate_traces.py      # preview
python 05_create_test_cases.py    # preview
python 06_generate_shared_rubric.py
```

- **Step 4** marks the newest v1 carry-on answers as incorrect, with the current
  rule as the expected answer, and one v2 answer as correct. In the portal, a
  reviewer does the same from a trace's **Annotation** panel. There's no SDK or
  REST API for annotations yet, so the script writes the same Application
  Insights event the portal writes (see [Annotation event format](#annotation-event-format)).
- **Step 5** turns the annotated traces into dataset rows with the reviewer's
  expected answer and a task-level rubric for each row, such as "Uses
  policy_lookup to verify the current carry-on allowance before answering." It
  saves the rows to `golden_dataset.generated.jsonl` for review. Edit rows that
  are too strict, then merge the ones you trust into `golden_dataset.jsonl`.
- **Step 6** generates a shared rubric from a description of the agent's job
  plus its traces. It keeps the criterion the team approved ("policy answers
  come from policy_lookup") and adds the rest. Run it again to regenerate.

## Measure and improve

```powershell
python 07_evaluate_continuously.py                     # hourly evaluation rule
python 08_run_golden_dataset.py --instructions v1      # before
python 08_run_golden_dataset.py --instructions v2      # after the fix
```

- **Step 7** creates a custom evaluator (preview) that checks answers against
  the current policy, and an hourly evaluation rule that scores a sample of
  production traces with it and the shared rubric. Add `--smart-sampling` for
  intelligent sampling (preview). Delete it when you're done with `--delete`.
- **Step 8** compares agent versions on the golden dataset. The first run
  uploads `golden_dataset.jsonl` to Foundry as the dataset
  `contoso-trip-planner-golden`, tagged `golden`, so the team shares one
  reviewed set. Because Foundry can't call an external agent, the script runs
  the agent locally on each golden row, uploads the answers as a dataset, and
  scores them in Foundry with the same three evaluators every time. It then
  prints the saved runs for that golden version side by side, and warns if any
  rows had evaluator errors. After you edit `golden_dataset.jsonl`, run with a new
  `--golden-version`; results are compared only within a version.

Example output (your results vary):

```text
Golden dataset version 1
criterion         v1              v2
task_rubric       2/6             6/6
shared_rubric     1/6             6/6
policy_accuracy   1/6             6/6
```

**Learn from past traces with skill optimization (preview).**

```powershell
python 09_optimize_skill.py --lookback-hours 72
```

Skill optimization analyzes past traces, along with annotations and evaluation
results, and proposes a new or updated skill: a versioned folder with a
`SKILL.md` file and optional scripts and reference files. The script prints each
proposed skill with the reason it was proposed, and downloads published skills
into `./skills`. Some proposals can be rejected by validation; the reason is
printed.

A successful run means the run finished, not that the proposal is better.
Review the `SKILL.md`, then test it the same way as any other change:

```powershell
python 08_run_golden_dataset.py --instructions v2 --skills ./skills
```

A skill is guidance the agent loads when it needs it. Explicit instructions
take precedence, so if a skill conflicts with your instructions, update the
instructions when you adopt the skill.

## Annotation event format

> [!NOTE]
> Writing annotation events directly is a preview approach. There's no SDK or
> REST API for annotations yet, and the format may change.

Step 4 sends one `gen_ai.evaluation.result` custom event per annotation to the
project's Application Insights resource. The `gen_ai.*` fields follow the
[OpenTelemetry GenAI evaluation event](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-events/);
the others are Foundry additions that the portal reads.

| Field | From | Value |
|---|---|---|
| `ai.operation.id` (envelope tag) | Application Insights | The trace ID. Links the annotation to the trace. |
| `gen_ai.evaluation.name` | OpenTelemetry | `overall_quality` |
| `gen_ai.evaluation.score.label` / `.score.value` | OpenTelemetry | `pass` / `1.0` or `fail` / `0.0` |
| `gen_ai.evaluation.explanation` | OpenTelemetry | The reviewer's comment |
| `gen_ai.agent.id`, `gen_ai.agent.name` | OpenTelemetry | The agent that produced the trace |
| `microsoft.gen_ai.evaluation.actor.type` | Foundry | `human` |
| `microsoft.gen_ai.human_evaluation.source` | Foundry | `builder` |
| `microsoft.gen_ai.human_evaluation.id` | Foundry | A new ID for each annotation |
| `microsoft.gen_ai.human_evaluation.tags` | Foundry | JSON list of tags |
| `microsoft.gen_ai.human_evaluation.expected_output` | Foundry | The expected answer, if given |
| `internal_properties` | Foundry | `{"gen_ai.evaluation.level": "turn"}` |

Application Insights accepts any custom event, so a successful write doesn't
prove the portal will show it. If annotations don't appear, compare your events
with this table.

## Adapt it to your agent

To run these steps on your own agent instead of the Contoso demo, connect it as
described in [Bring your own agent](../README.md#bring-your-own-agent), then
replace these values:

| Step | Replace |
|---|---|
| `.env` | `FOUNDRY_AGENT_NAME` and `OTEL_AGENT_ID`: your agent's name and `gen_ai.agent.id` |
| 2, 8 | Steps 2 and 8 run the demo agent locally. Send traffic to your own agent instead, and in step 8 call your agent where `answer_rows` calls `ask` |
| 4 | Annotate in the portal, or replace the trace selection and `CURRENT_CARRY_ON_RULE` |
| 6 | `AGENT_JOB_DESCRIPTION` and `APPROVED_DIMENSIONS` |
| 7 | `POLICY_PROMPT`: the facts your custom evaluator checks |
| 8 | `golden_dataset.jsonl`: your reviewed test cases |
| 9 | `FOCUS`: what skill optimization should improve |

## Run somewhere else

The agent runs locally to keep the tutorial small. To run it elsewhere, such as
Azure Kubernetes Service, keep the same environment variables and agent ID, and
replace `AzureCliCredential` in `agent.py` with the credential for your host,
such as `WorkloadIdentityCredential` on AKS.

## Clean up

```powershell
python 07_evaluate_continuously.py --delete
```

The datasets, evaluators, evaluations, and Insights monitor stay in your project
until you delete them in the portal.

## Learn more

- [Register external agents for observability and evaluation](https://learn.microsoft.com/azure/foundry/agents/how-to/register-external-agent)
- [External agent API reference sample (weather agent)](../observability/README.md)
