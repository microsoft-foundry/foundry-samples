# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_136():
    # <doc_quickstart_memory_hosted_agent_clean_up_resources>
    import os
    import asyncio
    from azure.identity.aio import DefaultAzureCredential
    from azure.ai.projects.aio import AIProjectClient

    async def delete():
        async with (
            DefaultAzureCredential() as credential,
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=credential,
                allow_preview=True,
            ) as project,
        ):
            await project.beta.memory_stores.delete("agent_framework_memory")

    asyncio.run(delete())
    # </doc_quickstart_memory_hosted_agent_clean_up_resources>


def example_137():
    # <doc_quickstart_memory_hosted_agent_clean_up_resources_137>
    import asyncio
    import os
    from azure.ai.projects.aio import AIProjectClient
    from azure.identity.aio import DefaultAzureCredential

    async def delete() -> None:
        async with (
            DefaultAzureCredential() as credential,
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=credential,
                allow_preview=True,
            ) as project,
        ):
            await project.beta.memory_stores.delete(
                os.environ["FOUNDRY_MEMORY_STORE_NAME"]
            )

    asyncio.run(delete())
    # </doc_quickstart_memory_hosted_agent_clean_up_resources_137>


def main():
    examples = {"aip-python-136": example_136, "aip-python-137": example_137}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-136")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
