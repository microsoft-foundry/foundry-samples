# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_148():
    # <doc_fine_tune_premium_healthcare_models_upload_the_training_file>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        credential = _resources.enter_context(DefaultAzureCredential())
        project_client = _resources.enter_context(
            AIProjectClient(endpoint=project_endpoint, credential=credential)
        )
        openai_client = _resources.enter_context(project_client.get_openai_client())
        with open(os.environ["FOUNDRY_TRAINING_FILE_PATH"], "rb") as f:
            uploaded = openai_client.files.create(file=f, purpose="fine-tune")
        file_id = uploaded.id
        print(f"file id: {file_id}")
        openai_client.files.wait_for_processing(file_id)
        print("file status: processed")
    # </doc_fine_tune_premium_healthcare_models_upload_the_training_file>


def main():
    examples = {"aip-python-148": example_148}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-148")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
