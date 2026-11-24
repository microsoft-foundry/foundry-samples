"""
DESCRIPTION:
    This sample demonstrates the richer parts of a voice agent definition:

    * Input (microphone) audio configuration: audio format, server-side turn
      detection (VAD), input-audio transcription.
    * Tools the agent may use during a live session: a client-executed
      `function` tool and a service-managed `system` control tool. Optionally
      attach your own MCP server or existing Foundry toolbox.
    * Bring-your-own-model (BYOM): set `model_type="self_deployed"` to point
      the agent at your own Foundry model deployment instead of a
      service-managed model.

USAGE:
    python voice_agent_with_tools.py

    Before running the sample:

    pip install "azure-ai-projects==2.11.0" python-dotenv

    Set these environment variables with your own values:
    1) FOUNDRY_PROJECT_ENDPOINT - The Azure AI Project endpoint.
    2) FOUNDRY_VOICE_AGENT_MODEL - Optional. The realtime model (managed) or the
       Foundry deployment name (BYOM). Defaults to "gpt-realtime".
    3) FOUNDRY_VOICE_MODEL_TYPE - Optional. "managed" (default) for a
       service-hosted model, or "self_deployed" to bring your own deployment.
    4) FOUNDRY_VOICE_AGENT_NAME - Optional unused name. Otherwise a unique
       sample-owned name is generated.
    5) FOUNDRY_VOICE_MCP_SERVER_URL - Optional. Your own MCP endpoint.
    6) FOUNDRY_VOICE_TOOLBOX_NAME and FOUNDRY_VOICE_TOOLBOX_VERSION - Optional.
       An existing Foundry toolbox to attach.
"""

import os

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    RealtimeAudioFormatsAudioPcm,
    RealtimeFunctionToolParameters,
    VoiceAgentDefinition,
    VoiceAgentFunctionTool,
    VoiceAgentMcpTool,
    VoiceAgentAudioConfig,
    VoiceAgentAudioInputConfig,
    VoiceAgentAudioOutputConfig,
    VoiceAgentEndConversationSystemTool,
    VoiceAgentInputTranscription,
    VoiceAgentInputTranscriptionModel,
    VoiceAgentSystemTool,
    VoiceModelType,
    VoiceOutputModality,
    VoiceAgentServerVadTurnDetection,
    VoiceAgentToolboxTool,
    VoiceAgentTool,
    VoiceType,
)

from voice_agent_util import require_new_agent, sample_agent_name

load_dotenv()

endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
model = os.environ.get("FOUNDRY_VOICE_AGENT_MODEL") or "gpt-realtime"
# "managed" runs a service-hosted model; "self_deployed" (BYOM) uses your own
# Foundry deployment named by `model`. The service derives whether the model is
# realtime or cascaded; you don't set that here.
model_type = os.environ.get("FOUNDRY_VOICE_MODEL_TYPE") or VoiceModelType.MANAGED
agent_name = sample_agent_name("sample-voice-agent-with-tools")

# A client-executed tool: the service forwards the function call to your app,
# and your app returns the result over the live session.
get_weather = VoiceAgentFunctionTool(
    name="get_weather",
    description="Get the current weather for a city.",
    parameters=RealtimeFunctionToolParameters(
        {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name, e.g. Seattle."}
            },
            "required": ["city"],
        }
    ),
)

# A service-managed control tool: the platform can end the call on the agent's behalf.
end_call = VoiceAgentEndConversationSystemTool()

tools: list[VoiceAgentTool] = [get_weather, end_call]
if mcp_url := os.environ.get("FOUNDRY_VOICE_MCP_SERVER_URL"):
    tools.append(
        VoiceAgentMcpTool(
            server_label="sample-mcp-server",
            server_url=mcp_url,
            require_approval="never",
        )
    )
if toolbox_name := os.environ.get("FOUNDRY_VOICE_TOOLBOX_NAME"):
    tools.append(
        VoiceAgentToolboxTool(
            toolbox_name=toolbox_name,
            toolbox_version=os.environ["FOUNDRY_VOICE_TOOLBOX_VERSION"],
        )
    )

definition = VoiceAgentDefinition(
    model_type=model_type,
    model=model,
    instructions="You are a helpful voice assistant. Use tools when they help answer the caller.",
    audio=VoiceAgentAudioConfig(
        # Input (microphone) side: 24 kHz PCM, server-side VAD so the agent
        # auto-responds when the caller stops speaking, plus input-audio
        # transcription so user speech is transcribed.
        input=VoiceAgentAudioInputConfig(
            format=RealtimeAudioFormatsAudioPcm(rate=24000),
            turn_detection=VoiceAgentServerVadTurnDetection(
                threshold=0.5,
                prefix_padding_ms=300,
                silence_duration_ms=500,
            ),
            transcription=VoiceAgentInputTranscription(
                model=VoiceAgentInputTranscriptionModel.WHISPER_1
            ),
        ),
        # Output (agent speech) side: the voice the agent speaks with.
        output=VoiceAgentAudioOutputConfig(
            voice="en-US-AvaNeural", voice_type=VoiceType.AZURE_STANDARD
        ),
    ),
    output_modalities=[VoiceOutputModality.AUDIO],
    tools=tools,
    store=True,
)

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
):
    require_new_agent(project_client, agent_name)
    created_version = None
    try:
        created_version = project_client.agents.create_version(
            agent_name=agent_name, definition=definition
        )
        print(
            f"Created voice agent '{agent_name}' (model_type={model_type}, model={model})"
        )

        agent_version = project_client.agents.get_version(
            agent_name=agent_name, agent_version=created_version.version
        )
        # `definition` is typed as the base `AgentDefinition`; narrow to `VoiceAgentDefinition`
        # to access voice-specific fields like `tools`.
        fetched_definition = agent_version.definition
        if not isinstance(fetched_definition, VoiceAgentDefinition):
            raise TypeError("Expected a Realtime voice-agent definition.")
        tools = fetched_definition.tools or []
        print(f"Configured {len(tools)} tool(s):")
        for tool in tools:
            # `name` is declared on function and system tools, but not on MCP or toolbox tools
            # (which instead have `server_label` / `toolbox_name`), so narrow before reading it.
            if isinstance(tool, (VoiceAgentFunctionTool, VoiceAgentSystemTool)):
                print(f"  - {tool.type}: {tool.name}")
            else:
                print(f"  - {tool.type}")
    finally:
        if created_version is not None:
            project_client.agents.delete_version(
                agent_name=agent_name, agent_version=created_version.version
            )
            print(f"Deleted voice agent version: {created_version.version}")
