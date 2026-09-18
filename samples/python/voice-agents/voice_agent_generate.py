"""
DESCRIPTION:
    This sample demonstrates guided authoring: generating and creating a voice
    agent through `create_from_prompt` with `kind="voice"`.
    The service creates a voice agent with a service-selected starter definition,
    which is fully editable afterward through the standard create_version/update flow.

USAGE:
    python voice_agent_generate.py

    Before running the sample:

    pip install "azure-ai-projects==2.7.0" python-dotenv

    Set these environment variables with your own values:
    1) FOUNDRY_PROJECT_ENDPOINT - The Azure AI Project endpoint.
    2) FOUNDRY_VOICE_AGENT_NAME - Optional. The name of the voice agent. If not
       set, defaults to "MyGeneratedVoiceAgent".
"""

import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import AgentKind, GenerateVoiceAgentRequest, VoiceAgentDefinition

from voice_agent_util import safe_print

load_dotenv()

endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
agent_name = os.environ.get("FOUNDRY_VOICE_AGENT_NAME") or "MyGeneratedVoiceAgent"

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True) as project_client,
):
    agent = project_client.beta.agents.create_from_prompt(
        GenerateVoiceAgentRequest(kind=AgentKind.VOICE, name=agent_name)
    )
    print(f"Generated voice agent: {agent.name}")

    # `AgentVersionDetails.definition` is typed as the base `AgentDefinition`; narrow to
    # `VoiceAgentDefinition` to access voice-specific fields like `instructions`.
    definition = agent.versions.latest.definition
    if isinstance(definition, VoiceAgentDefinition):
        safe_print(f"Instructions:\n{definition.instructions}")

    project_client.agents.delete(agent_name=agent.name)
    print(f"Deleted voice agent: {agent.name}")
