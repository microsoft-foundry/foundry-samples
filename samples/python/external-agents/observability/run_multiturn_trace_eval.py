"""Conversation-level (multi-turn) trace evaluation for the external weather agent.

Based on two azure-ai-projects SDK samples:

* ``sample_multiturn_trace_evaluation_agent_filter.py`` — conversation-level
  scoring via the ``azure_ai_trace_data_source`` ``agent_filter`` data
  source (default mode here) and ``extra_body={"evaluation_level": "conversation"}``
* ``sample_multiturn_trace_evaluation_by_id.py`` — the ``trace_id_source`` shape
  used by ``--trace-id-mode``

Conversations are grouped by W3C ``traceparent``: ``generate_multiturn_traffic.py``
opens one root span per conversation and propagates its traceparent to every
turn, so **one trace == one conversation**.

By default the run filters by the registered agent using the
``azure_ai_trace_data_source`` ``agent_filter`` shape (``agent_name`` +
a time window). ``--trace-id-mode`` switches to the ``trace_id_source`` shape
from ``sample_multiturn_trace_evaluation_by_id.py``, resolving trace ids
client-side from Application Insights and passing them explicitly. Both produce
the same conversation-level scores; only trace selection differs.

Usage:
    python run_multiturn_trace_eval.py
    python run_multiturn_trace_eval.py --trace-id-mode
    python run_multiturn_trace_eval.py --no-cleanup --lookback-hours 6
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from pprint import pprint

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"), override=True)

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import TestingCriterionAzureAIEvaluator
from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus

ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
APPINSIGHTS_RESOURCE_ID = os.environ.get("APPINSIGHTS_RESOURCE_ID")
AGENT_NAME = os.environ.get("AGENT_NAME", "weather-agent")
AGENT_ID = f"{AGENT_NAME}-v1"
MODEL_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
DEFAULT_LOOKBACK_HOURS = int(os.environ.get("TRACE_LOOKBACK_HOURS", "24"))

# Upper bound on how long to wait for an eval run before giving up.
POLL_TIMEOUT_SECONDS = 30 * 60

# Conversation-level evaluators score the full conversation, not a single turn.
CONVERSATION_EVALUATORS = [
    ("customer_satisfaction", "builtin.customer_satisfaction"),
    ("task_completion", "builtin.task_completion"),
    ("conversation_coherence", "builtin.coherence"),
    ("groundedness", "builtin.groundedness"),
]


def _conversation_criterion(name: str, evaluator_name: str):
    return TestingCriterionAzureAIEvaluator(
        type="azure_ai_evaluator",
        name=name,
        evaluator_name=evaluator_name,
        data_mapping={"messages": "{{item.messages}}"},
        initialization_parameters={"model": MODEL_DEPLOYMENT},
    )


def get_conversation_traces(start_time: datetime, end_time: datetime):
    """Return (trace_id, conversation_id, turn_count) for the agent's traces."""
    query = f"""
dependencies
| where timestamp between (datetime({start_time.isoformat()}) .. datetime({end_time.isoformat()}))
| extend agent_id = tostring(customDimensions["gen_ai.agent.id"])
| extend conversation_id = tostring(customDimensions["gen_ai.conversation.id"])
| where agent_id == "{AGENT_ID}"
| summarize turns = countif(name startswith "invoke_agent"),
            conversation_id = take_anyif(conversation_id, isnotempty(conversation_id))
  by operation_Id
| order by turns desc
"""
    with DefaultAzureCredential() as credential:
        client = LogsQueryClient(credential)
        response = client.query_resource(
            APPINSIGHTS_RESOURCE_ID, query=query, timespan=None
        )

    if response.status != LogsQueryStatus.SUCCESS:
        print(f"Query failed with status: {response.status}")
        print(getattr(response, "partial_error", None))
        return []

    rows = []
    for table in response.tables:
        for row in table.rows:
            # summarize returns columns as [operation_Id, turns, conversation_id];
            # reorder to (trace_id, conversation_id, turns). operation_Id is the trace id.
            rows.append((row[0], row[2], row[1]))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trace-id-mode",
        action="store_true",
        help="Resolve trace IDs client-side and pass them explicitly, instead of "
             "letting the service filter by agent. Note: this identifies traces "
             "by id rather than by agent, so the run is not associated with the "
             "registered agent.",
    )
    parser.add_argument("--lookback-hours", type=int, default=DEFAULT_LOOKBACK_HOURS)
    parser.add_argument("--max-traces", type=int, default=50)
    parser.add_argument("--no-cleanup", action="store_true")
    args = parser.parse_args()

    end_time = datetime.now(tz=timezone.utc)
    start_time = end_time - timedelta(hours=args.lookback_hours)

    if not args.trace_id_mode:
        # start_time/end_time are Unix seconds; pad the end by 10 min so very
        # recent conversations aren't excluded by ingestion delay.
        start_unix = int(start_time.timestamp())
        end_unix = int(end_time.timestamp()) + 600
        metadata = {"agent_name": AGENT_NAME}
        data_source = {
            "type": "azure_ai_trace_data_source",
            "trace_source": {
                "type": "agent_filter",
                "agent_name": AGENT_NAME,
                "start_time": start_unix,
                "end_time": end_unix,
                "max_traces": args.max_traces,
            },
        }
        print(f"Mode: agent_filter, server-side trace resolution (agent_name={AGENT_NAME})")
    else:
        if not APPINSIGHTS_RESOURCE_ID:
            raise SystemExit("--trace-id-mode requires APPINSIGHTS_RESOURCE_ID")
        print(f"Querying Application Insights for conversations of {AGENT_ID}...")
        conversations = get_conversation_traces(start_time, end_time)
        if not conversations:
            print("No traces found for the provided agent and time window.")
            return
        # Cap how many conversations we send to the eval run.
        conversations = conversations[: args.max_traces]
        print(f"\nFound {len(conversations)} conversations (1 trace = 1 conversation):")
        for trace_id, conversation_id, turns in conversations:
            print(f"  - trace={trace_id}  conversation={conversation_id}  turns={turns}")
        # Scenario 2: trace_id_source — the service reconstructs the full
        # multi-turn message array from the App Insights spans in each trace.
        # This request carries no agent_id (neither the data source nor the
        # metadata), so the run is not associated with the registered agent.
        data_source = {
            "type": "azure_ai_trace_data_source",
            "trace_source": {
                "type": "trace_id_source",
                "trace_ids": [c[0] for c in conversations],
            },
        }
        metadata = {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
        }

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=ENDPOINT, credential=credential
        ) as project_client,
        project_client.get_openai_client() as client,
    ):
        print("\nCreating evaluation")
        eval_object = client.evals.create(
            name=f"{AGENT_NAME}-multiturn-conversation-eval",
            data_source_config={"type": "azure_ai_source", "scenario": "traces"},
            testing_criteria=[
                _conversation_criterion(name, builtin)
                for name, builtin in CONVERSATION_EVALUATORS
            ],
        )
        print(f"Evaluation created (id: {eval_object.id})")

        print("\nCreating eval run with evaluation_level=conversation")
        run_name = f"{AGENT_NAME}_multiturn_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            eval_run_object = client.evals.runs.create(
                eval_id=eval_object.id,
                name=run_name,
                metadata=metadata,
                data_source=data_source,
                extra_body={"evaluation_level": "conversation"},
            )
            print(f"Eval run created (id: {eval_run_object.id})")

            # Poll until the run finishes, bounded so a stuck run can't hang
            # the script forever.
            deadline = time.time() + POLL_TIMEOUT_SECONDS
            run = client.evals.runs.retrieve(
                run_id=eval_run_object.id, eval_id=eval_object.id
            )
            while run.status not in {"completed", "failed", "canceled"}:
                if time.time() > deadline:
                    print(f"Timed out after {POLL_TIMEOUT_SECONDS // 60} min "
                          f"(last status: {run.status})")
                    break
                time.sleep(15)
                run = client.evals.runs.retrieve(
                    run_id=eval_run_object.id, eval_id=eval_object.id
                )
            print(f"Final status: {run.status}")

            if run.status != "completed":
                # Surface the failure instead of printing empty results.
                print(f"Eval run did not complete. Error: {getattr(run, 'error', None)}")
            else:
                print(f"Result Counts: {run.result_counts}")
                for tc in getattr(run, "per_testing_criteria_results", []) or []:
                    name = getattr(tc, "testing_criteria", None) or getattr(tc, "name", "?")
                    print(f"  - {name}: passed={getattr(tc, 'passed', '?')} "
                          f"failed={getattr(tc, 'failed', '?')}")

                output_items = list(
                    client.evals.runs.output_items.list(
                        run_id=run.id, eval_id=eval_object.id
                    )
                )
                print(f"\nOUTPUT ITEMS (expect one per conversation, got {len(output_items)})")
                print("-" * 60)
                pprint(output_items)
                print("-" * 60)
                print(f"\nEval Run Report URL: {getattr(run, 'report_url', None)}")
        finally:
            if args.no_cleanup:
                print(f"Skipping cleanup. Eval ID: {eval_object.id}")
            else:
                client.evals.delete(eval_id=eval_object.id)
                print("Evaluation deleted")


if __name__ == "__main__":
    main()
