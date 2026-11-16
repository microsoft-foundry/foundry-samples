# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent
from agent_framework.foundry import AnthropicFoundryClient
from agent_framework_foundry_hosting import FoundryToolbox, ResponsesHostServer
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def main():
    credential = DefaultAzureCredential()

    # AnthropicFoundryClient talks to the Claude deployment through Foundry.
    # Claude's Foundry endpoint expects the Foundry token audience. FoundryToolbox
    # uses the same scope internally from the credential below.
    client = AnthropicFoundryClient(
        resource=os.environ["AZURE_AI_RESOURCE_NAME"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        azure_ad_token_provider=get_bearer_token_provider(
            credential, "https://ai.azure.com/.default"
        ),
    )

    # FoundryToolbox resolves the toolbox endpoint from the environment
    # (TOOLBOX_ENDPOINT, or FOUNDRY_PROJECT_ENDPOINT + TOOLBOX_NAME), authenticates
    # every request with the credential using the toolbox scope
    # (https://ai.azure.com/.default), and transparently forwards the platform
    # per-request call-id (x-agent-foundry-call-id) to the toolbox. The hosting
    # server enters the agent, which connects the toolbox on first use and closes
    # it at shutdown. This sample reuses an existing toolbox (e.g. web search);
    # it does not provision one.
    toolbox = FoundryToolbox(credential)

    agent = Agent(
        client=client,
        instructions=(
            "Use configured web search and cite grounded URLs; report tool errors honestly."
        ),
        tools=toolbox,
        # Anthropic models do not support the OpenAI-specific `store` option;
        # cap generation length instead via `max_tokens`.
        default_options={"max_tokens": 2048},
    )

    server = ResponsesHostServer(agent)
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
