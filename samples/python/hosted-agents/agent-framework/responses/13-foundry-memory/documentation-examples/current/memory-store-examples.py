# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_040():
    # <doc_runtime_components_attach_memory_to_an_agent_preview>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            MemoryStoreDefaultDefinition,
            MemoryStoreDefaultOptions,
        )

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=PROJECT_ENDPOINT,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        options = MemoryStoreDefaultOptions(
            chat_summary_enabled=True, user_profile_enabled=True
        )
        definition = MemoryStoreDefaultDefinition(
            chat_model="gpt-5.2",
            embedding_model="text-embedding-3-small",
            options=options,
        )
        memory_store = project.beta.memory_stores.create(
            name="my_memory_store",
            definition=definition,
            description="Memory store for my agent",
        )
        print(f"Memory store: {memory_store.name}")
    # </doc_runtime_components_attach_memory_to_an_agent_preview>


def example_056():
    # <doc_memory_usage_create_a_memory_store>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from datetime import timedelta
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            MemoryStoreDefaultDefinition,
            MemoryStoreDefaultOptions,
        )
        from azure.identity import DefaultAzureCredential

        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        memory_store_name = "my_memory_store"
        options = MemoryStoreDefaultOptions(
            chat_summary_enabled=True,
            user_profile_enabled=True,
            procedural_memory_enabled=True,
            default_ttl_seconds=timedelta(days=30),
            user_profile_details="Avoid irrelevant or sensitive data, such as age, financials, precise location, and credentials",
        )
        chat_model = os.environ["FOUNDRY_MEMORY_STORE_CHAT_MODEL_DEPLOYMENT_NAME"]
        embedding_model = os.environ[
            "FOUNDRY_MEMORY_STORE_EMBEDDING_MODEL_DEPLOYMENT_NAME"
        ]
        definition = MemoryStoreDefaultDefinition(
            chat_model=chat_model, embedding_model=embedding_model, options=options
        )
        memory_store = project_client.beta.memory_stores.create(
            name=memory_store_name,
            definition=definition,
            description="Memory store with procedural memory and 30-day default TTL",
        )
        print(f"Created memory store: {memory_store.name}")
    # </doc_memory_usage_create_a_memory_store>


def example_134():
    # <doc_quickstart_memory_hosted_agent_step_3_provision_the_memory_store_with_python>
    import asyncio
    import os
    from azure.ai.projects.aio import AIProjectClient
    from azure.ai.projects.models import (
        MemoryStoreDefaultDefinition,
        MemoryStoreDefaultOptions,
    )
    from azure.core.exceptions import ResourceNotFoundError
    from azure.identity.aio import DefaultAzureCredential

    async def main() -> None:
        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        memory_store_name = os.environ["FOUNDRY_MEMORY_STORE_NAME"]
        chat_model = os.environ["FOUNDRY_MODEL_NAME"]
        embedding_model = os.environ["AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME"]
        async with (
            DefaultAzureCredential() as credential,
            AIProjectClient(
                endpoint=endpoint, credential=credential, allow_preview=True
            ) as project,
        ):
            try:
                existing = await project.beta.memory_stores.get(name=memory_store_name)
                print(
                    f"Memory store '{existing.name}' already exists (id={existing.id}); leaving as-is."
                )
                return
            except ResourceNotFoundError:
                pass
            definition = MemoryStoreDefaultDefinition(
                chat_model=chat_model,
                embedding_model=embedding_model,
                options=MemoryStoreDefaultOptions(
                    chat_summary_enabled=False,
                    user_profile_enabled=True,
                    user_profile_details="Avoid irrelevant or sensitive data, such as age, financials, precise location, and credentials",
                ),
            )
            created = await project.beta.memory_stores.create(
                name=memory_store_name,
                description="Memory store for the hosted-agent memory quickstart",
                definition=definition,
            )
            print(f"Created memory store '{created.name}' (id={created.id}).")

    asyncio.run(main())
    # </doc_quickstart_memory_hosted_agent_step_3_provision_the_memory_store_with_python>


def example_144():
    # <doc_langchain_memory_create_the_memory_store>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            MemoryStoreDefaultDefinition,
            MemoryStoreDefaultOptions,
        )
        from azure.core.exceptions import ResourceNotFoundError
        from azure.identity import DefaultAzureCredential

        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        credential = _resources.enter_context(DefaultAzureCredential())
        client = _resources.enter_context(
            AIProjectClient(endpoint=endpoint, credential=credential)
        )
        store_name = "lc-integration-test-store"
        try:
            store = client.beta.memory_stores.get(store_name)
            print(f"✓ Memory store '{store_name}' already exists")
        except ResourceNotFoundError:
            print(f"Creating memory store '{store_name}'...")
            definition = MemoryStoreDefaultDefinition(
                chat_model="gpt-4.1",
                embedding_model="text-embedding-3-large",
                options=MemoryStoreDefaultOptions(
                    user_profile_enabled=True, chat_summary_enabled=True
                ),
            )
            store = client.beta.memory_stores.create(
                name=store_name,
                description="Long-term memory store",
                definition=definition,
            )
            print(f"✓ Memory store '{store_name}' created successfully")
    # </doc_langchain_memory_create_the_memory_store>


def main():
    examples = {
        "aip-python-040": example_040,
        "aip-python-056": example_056,
        "aip-python-134": example_134,
        "aip-python-144": example_144,
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-040")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
