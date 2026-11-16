"""Continuously evaluate the external weather agent's traces with an evaluation rule.

An evaluation rule with a timer trigger runs on a schedule. On each run, the
service reads the agent's recent traces from Application Insights and adds an
evaluation run to the evaluation, so you can watch scores over time. Timer
evaluation rules are generally available through
``project_client.evaluation_rules``. The trace lookback window is inferred from
the recurrence interval. Re-running the script updates the rule and keeps its
evaluation; to change the testing criteria, run ``--delete`` first.

This GA rule scores individual turns. For conversation-level (multi-turn)
scoring on a schedule, see ``schedule_multiturn_trace_eval.py``, which uses the
preview schedules API.

Usage:
    python create_trace_eval_rule.py            # create or update an hourly rule
    python create_trace_eval_rule.py --status   # show the rule and its provisioning status
    python create_trace_eval_rule.py --delete   # delete the rule
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"), override=True)

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    EvaluationRule,
    EvaluationRuleEventType,
    HourlyRecurrenceSchedule,
    RecurrenceTrigger,
    ScheduleProvisioningStatus,
    TestingCriterionAzureAIEvaluator,
    TraceEvaluationRuleAction,
    TracesEvalRunDataSource,
)
from azure.identity import DefaultAzureCredential

AGENT_NAME = os.environ.get("AGENT_NAME", "weather-agent")
EVAL_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
RULE_ID = os.environ.get("EVAL_RULE_ID", f"{AGENT_NAME}-hourly-trace-eval")


def create_eval_group(openai_client) -> str:
    """Create the evaluation that each scheduled run is added to."""
    eval_group = openai_client.evals.create(
        name=f"{AGENT_NAME}-continuous-trace-eval",
        data_source_config={"type": "azure_ai_source", "scenario": "traces"},
        testing_criteria=[
            TestingCriterionAzureAIEvaluator(
                type="azure_ai_evaluator",
                name="intent_resolution",
                evaluator_name="builtin.intent_resolution",
                initialization_parameters={"deployment_name": EVAL_DEPLOYMENT},
                data_mapping={
                    "query": "{{item.query}}",
                    "response": "{{item.response}}",
                    "tool_definitions": "{{item.tool_definitions}}",
                },
            ),
        ],
    )
    return eval_group.id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-traces", type=int, default=10)
    parser.add_argument("--status", action="store_true", help="Show the rule and exit.")
    parser.add_argument(
        "--delete", action="store_true", help="Delete the rule and exit."
    )
    args = parser.parse_args()

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential
        ) as project_client,
        project_client.get_openai_client() as openai_client,
    ):
        rules = project_client.evaluation_rules
        if args.delete:
            rules.delete(id=RULE_ID)
            print(f"Deleted evaluation rule {RULE_ID}")
            return
        if args.status:
            rule = rules.get(id=RULE_ID)
            print(
                f"{rule.id}: enabled={rule.enabled}, provisioning={rule.provisioning_status}, "
                f"eval_id={rule.action.eval_id}, error={rule.error}"
            )
            return

        # Reuse the rule's evaluation so score history stays in one place across re-runs.
        existing = next(
            (r for r in rules.list(agent_name=AGENT_NAME) if r.id == RULE_ID), None
        )
        if existing:
            eval_id = existing.action.eval_id
            print(f"Reusing evaluation {eval_id}")
        else:
            eval_id = create_eval_group(openai_client)
            print(f"Evaluation created: {eval_id}")

        rule = rules.create_or_update(
            id=RULE_ID,
            evaluation_rule=EvaluationRule(
                display_name=f"{AGENT_NAME} hourly trace evaluation",
                description="Evaluates a sample of the agent's traces every hour.",
                action=TraceEvaluationRuleAction(
                    eval_id=eval_id,
                    # azure_ai_traces: the lookback follows the recurrence interval. The
                    # agent_filter trace source used elsewhere takes a fixed start/end window.
                    source=TracesEvalRunDataSource(
                        agent_name=AGENT_NAME, max_traces=args.max_traces
                    ),
                ),
                event_type=EvaluationRuleEventType.TIMER_TRIGGER,
                schedule=RecurrenceTrigger(
                    interval=1, schedule=HourlyRecurrenceSchedule()
                ),
                enabled=True,
            ),
        )

        # The schedule behind the rule is provisioned in the background.
        while rule.provisioning_status in (
            ScheduleProvisioningStatus.CREATING,
            ScheduleProvisioningStatus.UPDATING,
        ):
            time.sleep(5)
            rule = rules.get(id=rule.id)
        print(
            f"Evaluation rule {rule.id}: provisioning={rule.provisioning_status}, error={rule.error}"
        )
        if rule.provisioning_status != ScheduleProvisioningStatus.SUCCEEDED:
            raise SystemExit(
                "The rule wasn't provisioned, so no hourly runs will be added."
            )
        print(
            "Runs are added to the evaluation every hour. Delete the rule with --delete."
        )


if __name__ == "__main__":
    main()
