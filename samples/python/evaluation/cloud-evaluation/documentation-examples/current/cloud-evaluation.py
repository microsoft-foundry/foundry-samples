# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_159():
    # <doc_cloud_evaluation_set_up_the_sdk_client>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import TestingCriterionAzureAIEvaluator
        from openai.types.eval_create_params import DataSourceConfigCustom
        from openai.types.evals.create_eval_jsonl_run_data_source_param import (
            CreateEvalJSONLRunDataSourceParam,
            SourceFileContent,
            SourceFileContentContent,
            SourceFileID,
        )

        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        model_deployment_name = os.environ.get("FOUNDRY_MODEL_NAME", "")
        dataset_name = os.environ.get("FOUNDRY_DATASET_NAME", "")
        dataset_version = os.environ.get("FOUNDRY_DATASET_VERSION", "1")
        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=endpoint,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        openai_client = _resources.enter_context(project_client.get_openai_client())
    # </doc_cloud_evaluation_set_up_the_sdk_client>


def main():
    examples = {"aip-python-159": example_159}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-159")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
