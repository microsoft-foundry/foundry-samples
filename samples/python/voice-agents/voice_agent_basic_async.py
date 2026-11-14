"""
DESCRIPTION:
    This sample demonstrates the voice-agent management lifecycle using the
    asynchronous AIProjectClient: creating a voice agent, retrieving it,
    listing the voice agents in the project, and deleting it.

USAGE:
    python voice_agent_basic_async.py

    Before running the sample:

    pip install "azure-ai-projects==2.11.0" aiohttp python-dotenv

    Set these environment variables with your own values:
    1) FOUNDRY_PROJECT_ENDPOINT - The Azure AI Project endpoint, as found in the Overview
       page of your Microsoft Foundry portal.
    2) FOUNDRY_VOICE_AGENT_MODEL - Optional. The realtime model deployment name.
       Defaults to "gpt-realtime".
    3) FOUNDRY_VOICE_AGENT_NAME - Optional unused name. Otherwise a unique
       sample-owned name is generated.
"""

import asyncio
import os
from dotenv import load_dotenv
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import AgentKind, VoiceAgentDefinition, VoiceModelType

from voice_agent_util import require_new_agent_async, sample_agent_name

load_dotenv()


async def main() -> None:
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ.get("FOUNDRY_VOICE_AGENT_MODEL") or "gpt-realtime"
    agent_name = sample_agent_name("sample-voice-agent-async")

    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        await require_new_agent_async(project_client, agent_name)
        created_version = None
        try:
            created_version = await project_client.agents.create_version(
                agent_name=agent_name,
                definition=VoiceAgentDefinition(
                    model_type=VoiceModelType.MANAGED,
                    model=model,
                    instructions="You are a friendly voice assistant. Keep replies short and natural.",
                    # Persist conversations so they can be read back later. Defaults to False.
                    store=True,
                ),
            )
            print(
                f"Created voice agent '{agent_name}', version: {created_version.version}"
            )

            agent = await project_client.agents.get(agent_name=agent_name)
            print(f"Retrieved voice agent: {agent.name}")

            print("Voice agents in this project (up to five):")
            shown = 0
            async for item in project_client.agents.list(kind=AgentKind.VOICE, limit=5):
                print(f"  - {item.name}")
                shown += 1
                if shown == 5:
                    break
        finally:
            if created_version is not None:
                await project_client.agents.delete_version(
                    agent_name=agent_name, agent_version=created_version.version
                )
                print(f"Deleted voice agent version: {created_version.version}")


if __name__ == "__main__":
    asyncio.run(main())
