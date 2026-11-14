"""Step 7: Evaluate production traces continuously.

Creates a custom evaluator (preview) that checks each answer against the current policy
(a fact a general-purpose judge wouldn't know), then an hourly evaluation rule
that scores a sample of the agent's recent traces with that evaluator and the
shared rubric from step 6. Each run records its scores, so you can see when
quality drops and set an alert on it in Azure Monitor.

    python 07_evaluate_continuously.py                  # hourly, random sample (GA)
    python 07_evaluate_continuously.py --smart-sampling  # hourly, intelligent sampling (preview)
    python 07_evaluate_continuously.py --delete

Intelligent sampling picks a varied set of traces instead of a random one. It
uses the preview schedules API (project.beta.schedules).
"""

from __future__ import annotations

import argparse
import sys
import time

from azure.ai.projects.models import (
    EvaluationRule,
    EvaluationRuleEventType,
    EvaluationScheduleTask,
    HourlyRecurrenceSchedule,
    RecurrenceTrigger,
    Schedule,
    ScheduleProvisioningStatus,
    TraceEvaluationRuleAction,
    TracesEvalRunDataSource,
)
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError

from tutorial_utils import AGENT_NAME, JUDGE_MODEL, TutorialState, project_client

POLICY_EVALUATOR = "policy-accuracy"
CONTINUOUS_ID = f"{AGENT_NAME}-hourly"
POLICY_PROMPT = """You check a travel assistant's answer against Contoso Travel's CURRENT partner-airline policy.

Current policy:
- Carry-on: one bag up to 55 x 35 x 20 cm and 7 kg, plus one personal item up to 40 x 30 x 15 cm.
- Checked bag: first bag USD 35, second bag USD 45, max 23 kg.
- Changes: free up to 24 hours before departure on Flex fares; USD 75 on Saver fares.
- Seats: free on Flex fares; USD 15-40 on Saver fares.

Query: {{query}}
Response: {{response}}

Score from 1 to 5:
- 5: the response states no policy facts, or every policy fact it states matches the current policy.
- 3: a policy fact is vague or incomplete but not wrong.
- 1: the response states an outdated or wrong policy fact (for example a different carry-on size or weight).

Return JSON: {"result": <integer 1-5>, "reason": "<one sentence naming any wrong fact>"}"""


def create_policy_evaluator(project) -> str:
    """Create a new version of the custom policy-accuracy evaluator and return the version."""
    # Custom prompt evaluators are in preview, so this call opts in explicitly.
    evaluator = project.evaluators.create_version(
        name=POLICY_EVALUATOR,
        headers={"Foundry-Features": "Evaluations=V1Preview"},
        evaluator_version={
            "display_name": "Policy accuracy",
            "description": "Fails answers that state outdated or wrong bag, fee, change, or seat policy.",
            "categories": ["quality"],
            "definition": {
                "type": "prompt",
                "prompt_text": POLICY_PROMPT,
                "init_parameters": {
                    "type": "object",
                    "required": ["deployment_name", "threshold"],
                    "properties": {
                        "deployment_name": {"type": "string"},
                        "threshold": {"type": "number", "minimum": 1, "maximum": 5},
                    },
                },
                "data_schema": {
                    "type": "object",
                    "required": ["query", "response"],
                    "properties": {
                        "query": {"type": "string"},
                        "response": {"type": "array"},
                    },
                },
                "metrics": {
                    "policy_accuracy": {
                        "type": "ordinal",
                        "min_value": 1,
                        "max_value": 5,
                        "desirable_direction": "increase",
                    }
                },
            },
        },
    )
    TutorialState.update(
        policy_evaluator={"name": evaluator.name, "version": evaluator.version}
    )
    return evaluator.version


def create_eval_group(openai_client) -> str:
    """Create the evaluation that each scheduled run is added to."""
    shared_rubric = TutorialState.require(
        "shared_rubric", "06_generate_shared_rubric.py"
    )
    mapping = {"query": "{{item.query}}", "response": "{{item.response}}"}
    criteria = [
        {
            "type": "azure_ai_evaluator",
            "name": "policy_accuracy",
            "evaluator_name": POLICY_EVALUATOR,
            "data_mapping": mapping,
            "initialization_parameters": {
                "deployment_name": JUDGE_MODEL,
                "threshold": 3,
            },
        },
        {
            "type": "azure_ai_evaluator",
            "name": "shared_rubric",
            "evaluator_name": shared_rubric["name"],
            "data_mapping": {
                **mapping,
                "tool_definitions": "{{item.tool_definitions}}",
            },
            "initialization_parameters": {"deployment_name": JUDGE_MODEL},
        },
    ]
    group = openai_client.evals.create(
        name=f"{AGENT_NAME} continuous evaluation",
        data_source_config={"type": "azure_ai_source", "scenario": "traces"},
        testing_criteria=criteria,
    )
    return group.id


def create_rule(project, eval_id: str) -> None:
    """Score up to 10 random traces every hour with a GA evaluation rule."""
    rule = project.evaluation_rules.create_or_update(
        id=CONTINUOUS_ID,
        evaluation_rule=EvaluationRule(
            display_name=f"{AGENT_NAME} hourly evaluation",
            action=TraceEvaluationRuleAction(
                eval_id=eval_id,
                source=TracesEvalRunDataSource(agent_name=AGENT_NAME, max_traces=10),
            ),
            event_type=EvaluationRuleEventType.TIMER_TRIGGER,
            schedule=RecurrenceTrigger(interval=1, schedule=HourlyRecurrenceSchedule()),
            enabled=True,
        ),
    )
    while rule.provisioning_status in (
        ScheduleProvisioningStatus.CREATING,
        ScheduleProvisioningStatus.UPDATING,
    ):
        time.sleep(5)
        rule = project.evaluation_rules.get(id=rule.id)
    print(f"Evaluation rule {rule.id}: {rule.provisioning_status}")


def create_smart_schedule(project, eval_id: str) -> None:
    """Score up to 10 intelligently sampled traces every hour (preview schedules API)."""
    eval_run = {
        "eval_id": eval_id,
        "name": f"{AGENT_NAME}-hourly",
        "data_source": {
            "type": "azure_ai_trace_data_source",
            "trace_source": {
                "type": "agent_filter",
                "agent_name": AGENT_NAME,
                "max_traces": 10,
                "filter_strategy": "smart_filtering",
            },
        },
    }
    schedule = project.beta.schedules.create_or_update(
        schedule_id=CONTINUOUS_ID,
        schedule=Schedule(
            display_name=f"{AGENT_NAME} hourly evaluation (intelligent sampling)",
            enabled=True,
            trigger=RecurrenceTrigger(interval=1, schedule=HourlyRecurrenceSchedule()),
            task=EvaluationScheduleTask(eval_id=eval_id, eval_run=eval_run),
        ),
    )
    print(f"Schedule {schedule.schedule_id}: {schedule.provisioning_status}")
    while schedule.provisioning_status in (
        ScheduleProvisioningStatus.CREATING,
        ScheduleProvisioningStatus.UPDATING,
    ):
        time.sleep(5)
        schedule = project.beta.schedules.get(schedule_id=CONTINUOUS_ID)
    print(f"Schedule {schedule.schedule_id}: {schedule.provisioning_status}")


def delete_continuous(project) -> None:
    """Delete the hourly schedule or rule, whichever exists.

    Rules and schedules share one ID space. Deleting a missing rule succeeds quietly.
    """
    try:
        project.beta.schedules.delete(CONTINUOUS_ID)
        print(f"Deleted schedule {CONTINUOUS_ID}")
        return
    except ResourceNotFoundError:
        pass
    except ResourceExistsError:
        print(f"A delete of {CONTINUOUS_ID} is already in progress.")
        return
    project.evaluation_rules.delete(CONTINUOUS_ID)
    print(f"Deleted rule {CONTINUOUS_ID} (if it existed)")


def main() -> None:
    """Create the policy evaluator and the hourly evaluation, or delete it."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--smart-sampling",
        action="store_true",
        help="Use intelligent sampling (preview).",
    )
    parser.add_argument(
        "--delete", action="store_true", help="Delete the hourly rule or schedule."
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    with project_client() as project, project.get_openai_client() as openai_client:
        if args.delete:
            delete_continuous(project)
            return
        version = create_policy_evaluator(project)
        print(f"Created evaluator {POLICY_EVALUATOR} version {version}")
        eval_id = create_eval_group(openai_client)
        print(f"Created evaluation {eval_id}")
        if args.smart_sampling:
            create_smart_schedule(project, eval_id)
        else:
            create_rule(project, eval_id)
        TutorialState.update(continuous_eval_id=eval_id)
    print(
        "Runs are added to the evaluation every hour. Low scores are good traces to annotate next."
    )


if __name__ == "__main__":
    main()
