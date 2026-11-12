# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_021():
    # <doc_run_ai_red_teaming_cloud_create_an_ai_red_teaming_run>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os

        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        model_deployment_name = os.environ["FOUNDRY_MODEL_NAME"]
        model_endpoint = os.environ["FOUNDRY_MODEL_ENDPOINT"]
        model_api_key = os.environ["FOUNDRY_MODEL_API_KEY"]
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            RedTeam,
            AzureOpenAIModelConfiguration,
            AttackStrategy,
            RiskCategory,
        )

        with AIProjectClient(
            endpoint=endpoint,
            credential=_resources.enter_context(
                DefaultAzureCredential(exclude_interactive_browser_credential=False)
            ),
        ) as project_client:
            target_config = AzureOpenAIModelConfiguration(
                model_deployment_name=model_deployment_name
            )
            red_team_agent = RedTeam(
                attack_strategies=[AttackStrategy.BASE64],
                risk_categories=[RiskCategory.VIOLENCE],
                display_name="red-team-cloud-run",
                target=target_config,
            )
            headers = {"model-endpoint": model_endpoint, "api-key": model_api_key}
            red_team_response = project_client.red_teams.create(
                red_team=red_team_agent, headers=headers
            )
    # </doc_run_ai_red_teaming_cloud_create_an_ai_red_teaming_run>


def main():
    examples = {"aip-python-021": example_021}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-021")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
