# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_121():
    # <doc_use_routines_choose_a_dispatch_identity>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import RoutineAuthorization
        from azure.identity import AzureCliCredential

        client = _resources.enter_context(
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=_resources.enter_context(AzureCliCredential()),
            )
        )
        routine_name = "my-creator-routine"
        routine = client.beta.routines.create_or_update(
            routine_name=routine_name,
            enabled=False,
            authorization=RoutineAuthorization(identity="creator"),
            triggers={
                "default": {
                    "type": "schedule",
                    "cron_expression": "0 9 * * *",
                    "time_zone": "America/Los_Angeles",
                }
            },
            action={
                "type": "invoke_agent_responses_api",
                "agent_name": os.environ["FOUNDRY_AGENT_NAME"],
                "input": "test",
            },
        )
        saved_routine = client.beta.routines.get(routine_name)
        print(saved_routine.authorization.identity)
    # </doc_use_routines_choose_a_dispatch_identity>


def example_122():
    # <doc_use_routines_schedule_trigger>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        agent_name = os.environ["FOUNDRY_AGENT_NAME"]
        client = _resources.enter_context(
            AIProjectClient(
                endpoint=endpoint,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        from datetime import datetime, timezone

        routine = client.beta.routines.create_or_update(
            routine_name="daily-summary",
            description="Runs a daily summary agent on weekday mornings.",
            enabled=True,
            triggers={
                "weekday-morning": {
                    "type": "schedule",
                    "cron_expression": "0 7 * * 1-5",
                    "time_zone": "UTC",
                }
            },
            action={
                "type": "invoke_agent_responses_api",
                "agent_name": agent_name,
                "input": "Summarize activity from the last 24 hours.",
            },
        )
        print(f"Routine created: {routine.name}, enabled={routine.enabled}")
    # </doc_use_routines_schedule_trigger>


def main():
    examples = {"aip-python-121": example_121, "aip-python-122": example_122}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-121")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
