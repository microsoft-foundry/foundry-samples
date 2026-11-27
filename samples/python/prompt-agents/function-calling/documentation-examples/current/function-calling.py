# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_094():
    # <doc_function_calling_create_an_agent_with_function_tools>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        import json
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import PromptAgentDefinition, Tool, FunctionTool
        from azure.identity import DefaultAzureCredential
        from openai.types.responses.response_input_param import (
            FunctionCallOutput,
            ResponseInputParam,
        )

        def get_horoscope(sign: str) -> str:
            """Generate a horoscope for the given astrological sign."""
            return f"{sign}: Next Tuesday you will befriend a baby otter."

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "MyAgent"
        with AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=_resources.enter_context(DefaultAzureCredential()),
        ) as project:
            func_tool = FunctionTool(
                name="get_horoscope",
                parameters={
                    "type": "object",
                    "properties": {
                        "sign": {
                            "type": "string",
                            "description": "An astrological sign like Taurus or Aquarius",
                        }
                    },
                    "required": ["sign"],
                    "additionalProperties": False,
                },
                description="Get today's horoscope for an astrological sign.",
                strict=True,
            )
            tools: list[Tool] = [func_tool]
            agent = project.agents.create_version(
                agent_name=AGENT_NAME,
                definition=PromptAgentDefinition(
                    model="gpt-4.1-mini",
                    instructions="You are a helpful assistant that can use function tools.",
                    tools=tools,
                ),
            )
            with project.get_openai_client(agent_name=agent.name) as openai:
                conversation = openai.conversations.create()
                response = openai.responses.create(
                    input="What is my horoscope? I am an Aquarius.",
                    conversation=conversation.id,
                )
                input_list: ResponseInputParam = []
                for item in response.output:
                    if item.type == "function_call":
                        if item.name == "get_horoscope":
                            horoscope = get_horoscope(**json.loads(item.arguments))
                            input_list.append(
                                FunctionCallOutput(
                                    type="function_call_output",
                                    call_id=item.call_id,
                                    output=json.dumps({"horoscope": horoscope}),
                                )
                            )
                response = openai.responses.create(
                    input=input_list, conversation=conversation.id
                )
                print(f"Agent response: {response.output_text}")
                openai.conversations.delete(conversation_id=conversation.id)
            project.agents.delete_version(
                agent_name=agent.name, agent_version=agent.version
            )
    # </doc_function_calling_create_an_agent_with_function_tools>


def main():
    examples = {"aip-python-094": example_094}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-094")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
