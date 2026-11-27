# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_063():
    # <doc_structured_inputs_use_structured_inputs_with_file_search>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            PromptAgentDefinition,
            FileSearchTool,
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
        vector_store = openai.vector_stores.create(name="ProductInfoStore")
        with open("assets/product_info.md", "rb") as f:
            file = openai.vector_stores.files.upload_and_poll(
                vector_store_id=vector_store.id, file=f
            )
        print(f"Vector store created (id: {vector_store.id})")
        tool = FileSearchTool(vector_store_ids=["{{vector_store_id}}"])
        agent = project.agents.create_version(
            agent_name="file-search-structured",
            definition=PromptAgentDefinition(
                model="gpt-5-mini",
                instructions="You are a helpful assistant that searches product information.",
                tools=[tool],
                structured_inputs={
                    "vector_store_id": StructuredInputDefinition(
                        description="Vector store ID for file search",
                        required=True,
                        schema={"type": "string"},
                    )
                },
            ),
        )
        conversation = openai.conversations.create()
        response = openai.responses.create(
            conversation=conversation.id,
            input="Tell me about Contoso products",
            extra_body={
                "agent_reference": {"name": agent.name, "type": "agent_reference"},
                "structured_inputs": {"vector_store_id": vector_store.id},
            },
        )
        print(response.output_text)
    # </doc_structured_inputs_use_structured_inputs_with_file_search>


def main():
    examples = {"aip-python-063": example_063}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-063")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
