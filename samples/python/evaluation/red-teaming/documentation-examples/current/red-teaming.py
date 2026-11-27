# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_146():
    # <doc_run_ai_red_teaming_cloud_create_an_ai_red_team>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        model_deployment = os.environ["FOUNDRY_MODEL_NAME"]
        with DefaultAzureCredential() as credential:
            with AIProjectClient(
                endpoint=endpoint, credential=credential
            ) as project_client:
                client = _resources.enter_context(project_client.get_openai_client())
                red_team = client.evals.create(
                    name="Red Team Agentic Safety Evaluation",
                    data_source_config={
                        "type": "azure_ai_source",
                        "scenario": "red_team",
                    },
                    testing_criteria=[
                        {
                            "type": "azure_ai_evaluator",
                            "name": "Prohibited Actions",
                            "evaluator_name": "builtin.prohibited_actions",
                            "evaluator_version": "1",
                        },
                        {
                            "type": "azure_ai_evaluator",
                            "name": "Task Adherence",
                            "evaluator_name": "builtin.task_adherence",
                            "evaluator_version": "1",
                            "initialization_parameters": {
                                "deployment_name": model_deployment
                            },
                        },
                        {
                            "type": "azure_ai_evaluator",
                            "name": "Sensitive Data Leakage",
                            "evaluator_name": "builtin.sensitive_data_leakage",
                            "evaluator_version": "1",
                        },
                    ],
                )
                print(f"Created red team: {red_team.id}")
    # </doc_run_ai_red_teaming_cloud_create_an_ai_red_team>


def main():
    examples = {"aip-python-146": example_146}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-146")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
