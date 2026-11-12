# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_079():
    # <doc_code_interpreter_prompt_agents>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            PromptAgentDefinition,
            CodeInterpreterTool,
            AutoCodeInterpreterToolParam,
        )

        CSV_DATA = "name,sector,operating_profit\nSkyBridge Logistics,TRANSPORTATION,185.2\nVelocity Rail Freight,TRANSPORTATION,310.2\nAeroJet Airlines,TRANSPORTATION,510.6\n"
        csv_path = os.path.abspath("synthetic-company-financial-results.csv")
        with open(csv_path, "w", encoding="utf-8", newline="") as csv_file:
            csv_file.write(CSV_DATA)
        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        openai = _resources.enter_context(project.get_openai_client())
        with open(csv_path, "rb") as csv_file:
            file = openai.files.create(purpose="assistants", file=csv_file)
        os.remove(csv_path)
        agent = project.agents.create_version(
            agent_name="MyAgent",
            definition=PromptAgentDefinition(
                model="gpt-5-mini",
                instructions="You are a helpful assistant.",
                tools=[
                    CodeInterpreterTool(
                        container=AutoCodeInterpreterToolParam(file_ids=[file.id])
                    )
                ],
            ),
            description="Code interpreter agent for data analysis and visualization.",
        )
        conversation = openai.conversations.create()
        response = openai.responses.create(
            conversation=conversation.id,
            input="Could you please create bar chart in TRANSPORTATION sector for the operating profit from the uploaded csv file and provide file to me?",
            extra_body={
                "agent_reference": {"name": agent.name, "type": "agent_reference"}
            },
        )
        file_id = ""
        filename = ""
        container_id = ""
        last_message = response.output[-1]
        if (
            last_message.type == "message"
            and last_message.content
            and (last_message.content[-1].type == "output_text")
            and last_message.content[-1].annotations
        ):
            file_citation = last_message.content[-1].annotations[-1]
            if file_citation.type == "container_file_citation":
                file_id = file_citation.file_id
                filename = file_citation.filename
                container_id = file_citation.container_id
                print(f"Found generated file: {filename} (ID: {file_id})")
        project.agents.delete_version(
            agent_name=agent.name, agent_version=agent.version
        )
        if file_id and filename:
            file_content = openai.containers.files.content.retrieve(
                file_id=file_id, container_id=container_id
            )
            print(f"File ready for download: {filename}")
            file_path = os.path.join(
                os.path.dirname(__file__), os.path.basename(filename.replace("\\", "/"))
            )
            with open(file_path, "xb") as f:
                f.write(file_content.read())
            print(f"File downloaded successfully: {file_path}")
        else:
            print("No file generated in response")
    # </doc_code_interpreter_prompt_agents>


def main():
    examples = {"aip-python-079": example_079}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-079")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
