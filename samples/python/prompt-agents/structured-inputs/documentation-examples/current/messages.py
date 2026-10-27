# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_066():
    # <doc_structured_inputs_system_and_developer_messages_with_structured_inputs>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        openai = _resources.enter_context(project.get_openai_client())
        response = openai.responses.create(
            model="gpt-5-mini",
            instructions="You are assisting {{customerName}} from {{companyName}} located in {{location}}.",
            input=[{"type": "message", "role": "user", "content": "Hello, who am I?"}],
            extra_body={
                "structured_inputs": {
                    "customerName": "Bob Johnson",
                    "companyName": "Tech Corp",
                    "location": "San Francisco",
                }
            },
        )
        print(response.output_text)
    # </doc_structured_inputs_system_and_developer_messages_with_structured_inputs>


def main():
    examples = {"aip-python-066": example_066}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-066")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
