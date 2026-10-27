# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_120():
    # <doc_work_iq_hosted_agents>
    import os
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import WorkIQPreviewToolboxTool
    from azure.identity import DefaultAzureCredential

    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    work_iq_connection_id = os.environ["FOUNDRY_WORK_IQ_PROJECT_CONNECTION_ID"]
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=project_endpoint, credential=credential) as project,
    ):
        toolbox = project.toolboxes.create_version(
            name="work-iq-toolbox",
            description="Toolbox with the Work IQ tool",
            tools=[
                WorkIQPreviewToolboxTool(project_connection_id=work_iq_connection_id)
            ],
        )
        print(f"Created toolbox: {toolbox.name}, version: {toolbox.version}")
    # </doc_work_iq_hosted_agents>


def main():
    examples = {"aip-python-120": example_120}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-120")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
