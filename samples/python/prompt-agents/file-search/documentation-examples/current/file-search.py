# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_092():
    # <doc_file_search_prompt_agents>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from pathlib import Path
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import FileSearchTool, PromptAgentDefinition
        from azure.identity import DefaultAzureCredential

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        asset_file_path = (Path(__file__).parent / "assets/product_info.md").resolve()
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        openai = _resources.enter_context(project.get_openai_client())
        vector_store = openai.vector_stores.create(name="ProductInfoStore")
        with asset_file_path.open("rb") as file_handle:
            vector_store_file = openai.vector_stores.files.upload_and_poll(
                vector_store_id=vector_store.id, file=file_handle
            )
        agent = project.agents.create_version(
            agent_name="MyAgent",
            definition=PromptAgentDefinition(
                model="gpt-5-mini",
                instructions="You are a helpful agent that can search through product information. Use file search to answer questions from the uploaded files.",
                tools=[FileSearchTool(vector_store_ids=[vector_store.id])],
            ),
            description="File search agent for product information queries.",
        )
        conversation = openai.conversations.create()
        response = openai.responses.create(
            conversation=conversation.id,
            input="Tell me about Contoso products",
            extra_body={
                "agent_reference": {"name": agent.name, "type": "agent_reference"}
            },
        )
        print(response.output_text)
        project.agents.delete_version(
            agent_name=agent.name, agent_version=agent.version
        )
        openai.vector_stores.delete(vector_store.id)
    # </doc_file_search_prompt_agents>


def main():
    examples = {"aip-python-092": example_092}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-092")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
