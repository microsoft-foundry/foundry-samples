"""Schedule the multi-turn conversation trace eval to run continuously.

Instead of invoking ``run_multiturn_trace_eval.py`` by hand, this creates a
Foundry **schedule** (``project_client.beta.schedules``) that re-runs the same
conversation-level trace eval on a cron cadence, so new conversations are scored
as they arrive. For turn-level scoring, the GA timer evaluation rule in
``create_trace_eval_rule.py`` is simpler.

The scheduled ``eval_run`` mirrors the payload ``run_multiturn_trace_eval.py``
passes to ``client.evals.runs.create``: the
``azure_ai_trace_data_source`` ``agent_filter`` data source keyed on
``agent_name``, plus ``evaluation_level: conversation``. On each run, the service
moves the trace window to end at the run time and keeps its length (``end_time``
minus ``start_time``, set from ``--lookback-hours``), so every run scores the
agent's most recent conversations.
Keep the window a bit longer than the cron interval to absorb Application
Insights ingestion lag.

Usage:
    python schedule_multiturn_trace_eval.py                      # hourly schedule
    python schedule_multiturn_trace_eval.py --cron "*/30 * * * *" --lookback-hours 1
    python schedule_multiturn_trace_eval.py --list               # list schedule runs
    python schedule_multiturn_trace_eval.py --delete             # remove the schedule
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from pprint import pprint

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"), override=True)

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    CronTrigger,
    EvaluationScheduleTask,
    Schedule,
    TestingCriterionAzureAIEvaluator,
)
from azure.identity import DefaultAzureCredential

ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
AGENT_NAME = os.environ.get("AGENT_NAME", "weather-agent")
MODEL_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
SCHEDULE_ID = os.environ.get("EVAL_SCHEDULE_ID", f"{AGENT_NAME}-multiturn-schedule")

# Same conversation-level evaluators as run_multiturn_trace_eval.py.
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cron", default="0 * * * *",
                        help="Cron expression for the cadence (default: hourly).")
    parser.add_argument("--time-zone", default="UTC")
    parser.add_argument("--lookback-hours", type=int, default=2,
                        help="Length of the trace window each run scores, ending at the "
                             "run time; keep it a bit longer than the cron interval.")
    parser.add_argument("--max-traces", type=int, default=50,
                        help="Max traces to evaluate per run.")
    parser.add_argument("--list", action="store_true", help="List schedule runs and exit.")
    parser.add_argument("--delete", action="store_true", help="Delete the schedule and exit.")
    args = parser.parse_args()

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=ENDPOINT, credential=credential) as project_client,
    ):
        if args.delete:
            project_client.beta.schedules.delete(SCHEDULE_ID)
            print(f"Deleted schedule: {SCHEDULE_ID}")
            return

        if args.list:
            print(f"Runs for schedule {SCHEDULE_ID}:")
            for run in project_client.beta.schedules.list_runs(SCHEDULE_ID):
                pprint(run)
            return

        # The schedule references a persisted eval group by id, so create it first.
        with project_client.get_openai_client() as client:
            eval_object = client.evals.create(
                name=f"{AGENT_NAME}-multiturn-conversation-eval",
                data_source_config={"type": "azure_ai_source", "scenario": "traces"},
                testing_criteria=[
                    _conversation_criterion(name, builtin)
                    for name, builtin in CONVERSATION_EVALUATORS
                ],
            )
        print(f"Evaluation created (id: {eval_object.id})")

        end_time = datetime.now(tz=timezone.utc)
        start_time = end_time - timedelta(hours=args.lookback_hours)
        eval_run = {
            "eval_id": eval_object.id,
            "name": f"{AGENT_NAME}-multiturn-scheduled",
            "data_source": {
                "type": "azure_ai_trace_data_source",
                "trace_source": {
                    "type": "agent_filter",
                    "agent_name": AGENT_NAME,
                    "start_time": int(start_time.timestamp()),
                    "end_time": int(end_time.timestamp()) + 600,
                    "max_traces": args.max_traces,
                },
            },
            "metadata": {"agent_name": AGENT_NAME},
            "evaluation_level": "conversation",
        }

        schedule = project_client.beta.schedules.create_or_update(
            schedule_id=SCHEDULE_ID,
            schedule=Schedule(
                display_name=f"{AGENT_NAME} multi-turn conversation eval",
                enabled=True,
                trigger=CronTrigger(expression=args.cron, time_zone=args.time_zone),
                task=EvaluationScheduleTask(eval_id=eval_object.id, eval_run=eval_run),
            ),
        )
        print(f"Schedule created: {schedule.schedule_id} "
              f"(cron '{args.cron}' {args.time_zone}, lookback {args.lookback_hours}h)")
        print("Inspect runs: python schedule_multiturn_trace_eval.py --list")
        print("Remove:       python schedule_multiturn_trace_eval.py --delete")


if __name__ == "__main__":
    main()
