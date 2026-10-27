# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_155():
    # <doc_cloud_evaluation_deployed_conversations_parameters_for_conversation_id_lookup>
    import os
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import TestingCriterionAzureAIEvaluator

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model_deployment_name = os.environ["FOUNDRY_MODEL_NAME"]
    conversation_ids = ["conversation_1234", "conversation_5678"]
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
        project_client.get_openai_client() as openai_client,
    ):
        data_source_config = {"type": "azure_ai_source", "scenario": "traces"}
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
        eval_object = openai_client.evals.create(
            name="Multi-turn Trace Evaluation (by ID)",
            data_source_config=data_source_config,
            testing_criteria=testing_criteria,
        )
        eval_run = openai_client.evals.runs.create(
            eval_id=eval_object.id,
            name="multiturn-trace-by-id-run",
            data_source={
                "type": "azure_ai_trace_data_source_preview",
                "trace_source": {
                    "type": "conversation_id_source",
                    "conversation_ids": conversation_ids,
                },
            },
            extra_body={"evaluation_level": "conversation"},
        )
    # </doc_cloud_evaluation_deployed_conversations_parameters_for_conversation_id_lookup>


def main():
    examples = {"aip-python-155": example_155}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-155")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
