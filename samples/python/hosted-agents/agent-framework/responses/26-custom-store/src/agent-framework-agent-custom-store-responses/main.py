# Copyright (c) Microsoft. All rights reserved.

"""Host an Agent Framework agent with four custom Redis-backed stores."""

import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from redis_database import create_database
from redis_response_store import create_response_store
from redis_state_stores import (
    RedisAgentSessionStoreProvider,
    RedisCheckpointStoreProvider,
    RedisFunctionApprovalStoreProvider,
)
from store_validation_tools import create_store_validation_tools

load_dotenv()

INSTRUCTIONS = (
    "You are the Contoso Service Operations assistant. Help operators triage and "
    "resolve incidents. Keep answers brief and actionable. When asked to validate "
    "a custom store, call the named validation tool exactly once and include its "
    "result verbatim in your response."
)


def main() -> None:
    """Create and host the operations agent with fully custom Redis storage."""
    credential = DefaultAzureCredential()
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )
    host_kwargs: dict[str, object] = {}
    if "APPLICATIONINSIGHTS_CONNECTION_STRING" not in os.environ:
        host_kwargs["configure_observability"] = None

    # One shared Redis instance backs all four hosting storage extension points.
    database = create_database()
    agent = Agent(
        client=client,
        instructions=INSTRUCTIONS,
        tools=create_store_validation_tools(database),
        # The Responses host supplies the complete transcript on each turn.
        # This setting controls downstream model-provider storage, not the
        # custom stores configured below.
        default_options={"store": False},
    )

    server = ResponsesHostServer(
        agent,
        store=create_response_store(database),
        agent_session_store_provider=RedisAgentSessionStoreProvider(database),
        checkpoint_store_provider=RedisCheckpointStoreProvider(database),
        function_approval_store_provider=RedisFunctionApprovalStoreProvider(database),
        **host_kwargs,
    )
    server.run()


if __name__ == "__main__":
    main()