# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_095():
    # <doc_image_generation_prompt_agents>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import base64
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import PromptAgentDefinition, ImageGenTool

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "agent-image-generation"
        IMAGE_MODEL = "gpt-image-1"
        with AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=_resources.enter_context(DefaultAzureCredential()),
        ) as project:
            agent = project.agents.create_version(
                agent_name=AGENT_NAME,
                definition=PromptAgentDefinition(
                    model="gpt-5",
                    instructions="Generate images based on user prompts.",
                    tools=[
                        ImageGenTool(model=IMAGE_MODEL, quality="low", size="1024x1024")
                    ],
                ),
                description="Agent for image generation.",
            )
            print(
                f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})"
            )
            with project.get_openai_client(agent_name=agent.name) as openai:
                response = openai.responses.create(
                    input="Generate an image of the Microsoft logo.",
                    extra_headers={"x-ms-oai-image-generation-deployment": IMAGE_MODEL},
                )
            project.agents.delete_version(
                agent_name=agent.name, agent_version=agent.version
            )
            image_data = [
                output.result
                for output in response.output
                if output.type == "image_generation_call"
            ]
            if image_data and image_data[0]:
                file_path = os.path.abspath("microsoft.png")
                with open(file_path, "wb") as f:
                    f.write(base64.b64decode(image_data[0]))
                print(f"Image saved to: {file_path}")
    # </doc_image_generation_prompt_agents>


def main():
    examples = {"aip-python-095": example_095}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-095")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
