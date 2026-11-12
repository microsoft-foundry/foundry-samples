# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_158():
    # <doc_cloud_evaluation_synthetic_conversations_configure_the_client_and_agent>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        import time
        from pprint import pprint
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            AzureAIDataSourceConfig,
            PromptAgentDefinition,
            TestingCriterionAzureAIEvaluator,
        )

        SEED_COUNT = 1
        CONVERSATIONS_PER_SEED = 1
        MAX_TURNS = 2
        DESIRED_TURNS = 1
        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        model_deployment_name = os.environ["FOUNDRY_MODEL_NAME"]
        agent_name = os.environ.get("FOUNDRY_AGENT_NAME", "MyAgent")
        credential = _resources.enter_context(DefaultAzureCredential())
        project_client = _resources.enter_context(
            AIProjectClient(endpoint=endpoint, credential=credential)
        )
        client = _resources.enter_context(project_client.get_openai_client())
        agent = project_client.agents.create_version(
            agent_name=agent_name,
            definition=PromptAgentDefinition(
                model=model_deployment_name,
                instructions="You are a helpful customer service agent. Be empathetic and solution-oriented.",
            ),
        )
    # </doc_cloud_evaluation_synthetic_conversations_configure_the_client_and_agent>


def main():
    examples = {"aip-python-158": example_158}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-158")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
