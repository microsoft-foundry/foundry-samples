"""Create a temporary MCP toolbox and actually invoke it through a voice agent.

Set FOUNDRY_PROJECT_ENDPOINT. Optional: FOUNDRY_VOICE_AGENT_MODEL,
FOUNDRY_VOICE_MCP_SERVER_URL and FOUNDRY_VOICE_MCP_TOOL_NAME.
Run: python voice_agent_toolbox.py
Only this run's unique toolbox and agent are deleted. The default tool searches
public Microsoft Learn documentation; do not substitute a write tool without review.
"""

import os
from contextlib import ExitStack
from uuid import uuid4

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    MCPToolboxTool,
    VoiceAgentDefinition,
    VoiceAgentToolboxTool,
    VoiceModelType,
    VoiceOutputModality,
)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from voice_agent_realtime_mcp import (
    DEFAULT_MCP_URL,
    DEFAULT_TOOL_NAME,
    SERVER_LABEL,
    run_tool_turn,
)
from voice_agent_util import require_new_agent, sample_agent_name


def main() -> None:
    load_dotenv()
    agent_name = sample_agent_name("sample-voice-toolbox")
    toolbox_name = f"sample-voice-tools-{uuid4().hex[:12]}"
    model = os.environ.get("FOUNDRY_VOICE_AGENT_MODEL") or "gpt-realtime"
    tool_name = os.environ.get("FOUNDRY_VOICE_MCP_TOOL_NAME") or DEFAULT_TOOL_NAME
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential
        ) as client,
        ExitStack() as cleanup,
    ):
        require_new_agent(client, agent_name)
        toolbox = client.toolboxes.create_version(
            name=toolbox_name,
            tools=[
                MCPToolboxTool(
                    server_label=SERVER_LABEL,
                    server_url=os.environ.get("FOUNDRY_VOICE_MCP_SERVER_URL")
                    or DEFAULT_MCP_URL,
                    allowed_tools=[tool_name],
                    require_approval="never",
                )
            ],
        )
        cleanup.callback(client.toolboxes.delete, name=toolbox_name)
        print(f"Created owned toolbox {toolbox_name}, version {toolbox.version}.")
        created = client.agents.create_version(
            agent_name=agent_name,
            definition=VoiceAgentDefinition(
                model_type=VoiceModelType.MANAGED,
                model=model,
                instructions=f"Use the toolbox's {tool_name} tool before answering.",
                tools=[
                    VoiceAgentToolboxTool(
                        toolbox_name=toolbox_name, toolbox_version=toolbox.version
                    )
                ],
                output_modalities=[VoiceOutputModality.TEXT],
            ),
        )
        cleanup.callback(
            client.agents.delete_version,
            agent_name=agent_name,
            agent_version=created.version,
        )
        print(f"Created owned agent {agent_name}, version {created.version}.")
        with client.voice_agents.realtime.connect(agent_name=agent_name) as connection:
            # The advertised toolbox catalog qualifies an MCP tool with its server label.
            run_tool_turn(
                connection,
                approval="never",
                server_label=toolbox_name,
                tool_name=f"{SERVER_LABEL}___{tool_name}",
            )


if __name__ == "__main__":
    main()
