# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_062():
    # <doc_structured_inputs_use_structured_inputs_with_code_interpreter>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from io import BytesIO
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            PromptAgentDefinition,
            CodeInterpreterTool,
            AutoCodeInterpreterToolParam,
            StructuredInputDefinition,
        )
        from azure.identity import DefaultAzureCredential

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        openai = _resources.enter_context(project.get_openai_client())
        csv_file = BytesIO(b"x\n1\n2\n3\n")
        csv_file.name = "numbers.csv"
        uploaded = openai.files.create(purpose="assistants", file=csv_file)
        print(f"File uploaded (id: {uploaded.id})")
        tool = CodeInterpreterTool(
            container=AutoCodeInterpreterToolParam(file_ids=["{{analysis_file_id}}"])
        )
        agent = project.agents.create_version(
            agent_name="code-interp-structured",
            definition=PromptAgentDefinition(
                model="gpt-5-mini",
                instructions="You are a helpful data analyst.",
                tools=[tool],
                structured_inputs={
                    "analysis_file_id": StructuredInputDefinition(
                        description="File ID for the code interpreter",
                        required=True,
                        schema={"type": "string"},
                    )
                },
            ),
        )
        conversation = openai.conversations.create()
        response = openai.responses.create(
            conversation=conversation.id,
            input="Read numbers.csv and return the sum of x.",
            extra_body={
                "agent_reference": {"name": agent.name, "type": "agent_reference"},
                "structured_inputs": {"analysis_file_id": uploaded.id},
            },
            tool_choice="required",
        )
        print(response.output_text)
    # </doc_structured_inputs_use_structured_inputs_with_code_interpreter>


def main():
    examples = {"aip-python-062": example_062}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-062")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
