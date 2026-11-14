"""
DESCRIPTION:
    This sample demonstrates guided authoring: generating and creating a voice
    agent through `create_from_prompt` with `kind="voice"`.
    The service creates a voice agent with a service-selected starter definition,
    which is fully editable afterward through the standard create_version/update flow.

USAGE:
    python voice_agent_generate.py

    Before running the sample:

    pip install "azure-ai-projects==2.11.0" python-dotenv

    Set these environment variables with your own values:
    1) FOUNDRY_PROJECT_ENDPOINT - The Azure AI Project endpoint.
    2) FOUNDRY_VOICE_AGENT_NAME - Optional unused name. Otherwise a unique
       sample-owned name is generated.
"""

import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AgentKind,
    GenerateVoiceAgentRequest,
    VoiceAgentDefinition,
)

from voice_agent_util import require_new_agent, safe_print, sample_agent_name

load_dotenv()

endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
agent_name = sample_agent_name("sample-generated-voice-agent")

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
):
    require_new_agent(project_client, agent_name)
    agent = project_client.agents.create_from_prompt(
        GenerateVoiceAgentRequest(kind=AgentKind.VOICE, name=agent_name)
    )
    try:
        print(f"Generated voice agent: {agent.name}")
        definition = agent.versions.latest.definition
        if not isinstance(definition, VoiceAgentDefinition):
            raise TypeError("The generated definition is not a Realtime voice agent.")
        safe_print(f"Instructions:\n{definition.instructions}")
    finally:
        project_client.agents.delete_version(
            agent_name=agent.name, agent_version=agent.versions.latest.version
        )
        print(f"Deleted generated voice agent version: {agent.versions.latest.version}")
