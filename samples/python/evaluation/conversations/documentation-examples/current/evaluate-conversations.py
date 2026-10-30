# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_154():
    # <doc_cloud_evaluation_conversations_define_the_data_schema_and_evaluators>
    import os
    from openai.types.eval_create_params import DataSourceConfigCustom
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import TestingCriterionAzureAIEvaluator

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model_deployment_name = os.environ["FOUNDRY_MODEL_NAME"]
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
        project_client.get_openai_client() as openai_client,
    ):
        data_source_config = DataSourceConfigCustom(
            type="custom",
            item_schema={
                "type": "object",
                "properties": {
                    "messages": {"type": "array"},
                    "tool_definitions": {"type": "array"},
                },
                "required": ["messages"],
            },
            include_sample_schema=False,
        )
        testing_criteria = [
            TestingCriterionAzureAIEvaluator(
                type="azure_ai_evaluator",
                name="output_quality",
                evaluator_name="builtin.output_quality",
                initialization_parameters={"model": model_deployment_name},
                data_mapping={
                    "messages": "{{item.messages}}",
                    "tool_definitions": "{{item.tool_definitions}}",
                },
            ),
            TestingCriterionAzureAIEvaluator(
                type="azure_ai_evaluator",
                name="tool_use_quality",
                evaluator_name="builtin.tool_use_quality",
                initialization_parameters={"model": model_deployment_name},
                data_mapping={
                    "messages": "{{item.messages}}",
                    "tool_definitions": "{{item.tool_definitions}}",
                },
            ),
            TestingCriterionAzureAIEvaluator(
                type="azure_ai_evaluator",
                name="deflection_rate",
                evaluator_name="builtin.deflection_rate",
                initialization_parameters={"model": model_deployment_name},
                data_mapping={
                    "messages": "{{item.messages}}",
                    "tool_definitions": "{{item.tool_definitions}}",
                },
            ),
            TestingCriterionAzureAIEvaluator(
                type="azure_ai_evaluator",
                name="customer_satisfaction",
                evaluator_name="builtin.customer_satisfaction",
                initialization_parameters={"model": model_deployment_name},
                data_mapping={"messages": "{{item.messages}}"},
            ),
            TestingCriterionAzureAIEvaluator(
                type="azure_ai_evaluator",
                name="task_completion",
                evaluator_name="builtin.task_completion",
                initialization_parameters={"model": model_deployment_name},
                data_mapping={"messages": "{{item.messages}}"},
            ),
            TestingCriterionAzureAIEvaluator(
                type="azure_ai_evaluator",
                name="coherence",
                evaluator_name="builtin.coherence",
                initialization_parameters={"model": model_deployment_name},
                data_mapping={"messages": "{{item.messages}}"},
            ),
            TestingCriterionAzureAIEvaluator(
                type="azure_ai_evaluator",
                name="groundedness",
                evaluator_name="builtin.groundedness",
                initialization_parameters={"model": model_deployment_name},
                data_mapping={"messages": "{{item.messages}}"},
            ),
        ]
    # </doc_cloud_evaluation_conversations_define_the_data_schema_and_evaluators>


def main():
    examples = {"aip-python-154": example_154}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-154")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
