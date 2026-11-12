# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_016():
    # <doc_quickstart_python_configure_and_run_an_agent>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from pathlib import Path
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential
        from azure.ai.agents.models import CodeInterpreterTool

        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=os.getenv("FOUNDRY_PROJECT_ENDPOINT"),
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        with project_client:
            code_interpreter = CodeInterpreterTool()
            agent = project_client.agents.create_agent(
                model=os.getenv("FOUNDRY_MODEL_NAME"),
                name="my-agent",
                instructions="You politely help with math questions. \n        Use the Code Interpreter tool when asked to visualize numbers.",
                tools=code_interpreter.definitions,
                tool_resources=code_interpreter.resources,
            )
            print(f"Created agent, ID: {agent.id}")
            thread = project_client.agents.threads.create()
            print(f"Created thread, ID: {thread.id}")
            question = "Draw a graph for a line with a slope of 4 \n    and y-intercept of 9 and provide the file to me?"
            message = project_client.agents.messages.create(
                thread_id=thread.id, role="user", content=question
            )
            print(f"Created message, ID: {message['id']}")
            run = project_client.agents.runs.create_and_process(
                thread_id=thread.id,
                agent_id=agent.id,
                additional_instructions="Please address the user as Jane Doe.\n        The user has a premium account.",
            )
            print(f"Run finished with status: {run.status}")
            if run.status == "failed":
                print(f"Run failed: {run.last_error}")
            messages = project_client.agents.messages.list(thread_id=thread.id)
            print(f"Messages: {messages}")
            for message in messages:
                print(f"Role: {message.role}, Content: {message.content}")
                for this_content in message.content:
                    print(
                        f"Content Type: {this_content.type}, Content Data: {this_content}"
                    )
                    if this_content.text.annotations:
                        for annotation in this_content.text.annotations:
                            print(
                                f"Annotation Type: {annotation.type}, Text: {annotation.text}"
                            )
                            print(f"Start Index: {annotation.start_index}")
                            print(f"End Index: {annotation.end_index}")
                            print(f"File ID: {annotation.file_path.file_id}")
                            file_id = annotation.file_path.file_id
                            file_name = f"{file_id}_image_file.png"
                            project_client.agents.files.save(
                                file_id=file_id, file_name=file_name
                            )
                            print(f"Saved image file to: {Path.cwd() / file_name}")
    # </doc_quickstart_python_configure_and_run_an_agent>


def main():
    examples = {"aip-python-016": example_016}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-016")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
