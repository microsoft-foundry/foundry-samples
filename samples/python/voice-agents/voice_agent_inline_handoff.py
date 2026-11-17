"""Route a Realtime conversation to an inline billing specialist (preview).

Set FOUNDRY_PROJECT_ENDPOINT; optionally set FOUNDRY_VOICE_AGENT_MODEL.
Run: python voice_agent_inline_handoff.py
"""

import os
import time

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    InlineVoiceSubagent,
    RealtimeConversationItemMessageUser,
    RealtimeConversationItemMessageUserContent,
    RealtimeConversationItemType,
    RealtimeServerEventError,
    RealtimeServerEventResponseDone,
    RealtimeServerEventResponseTextDone,
    VoiceAgentDefinition,
    VoiceAgentHandoffCondition,
    VoiceAgentHandoffPolicy,
    VoiceAgentInlineSubagentConfig,
    VoiceAgentServerEventSessionHandoffAborted,
    VoiceAgentServerEventSessionHandoffCompleted,
    VoiceAgentServerEventSessionHandoffStarted,
    VoiceModelType,
    VoiceOutputModality,
)
from azure.ai.projects.operations import RealtimeConnection
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from voice_agent_util import require_new_agent, safe_print, sample_agent_name


def make_definition(model: str) -> VoiceAgentDefinition:
    return VoiceAgentDefinition(
        model_type=VoiceModelType.MANAGED,
        model=model,
        instructions="You are a helpful support assistant. Keep answers short.",
        output_modalities=[VoiceOutputModality.TEXT],
        subagent_config=VoiceAgentInlineSubagentConfig(
            handoff_policy=VoiceAgentHandoffPolicy(max_transfers=2, max_attempts=3),
            subagents=[
                InlineVoiceSubagent(
                    id="$entrypoint",
                    display_description="Routes support questions.",
                    instructions="For refunds, hand off to billing instead of answering yourself.",
                    parallel_tool_calls=False,
                    handoff_conditions=[
                        VoiceAgentHandoffCondition(
                            id="refund-to-billing",
                            target="billing",
                            condition="The caller asks about a refund or billing.",
                            target_response="auto",
                        )
                    ],
                ),
                InlineVoiceSubagent(
                    id="billing",
                    display_description="Answers refund questions.",
                    instructions="You are the billing specialist. Refunds take 5 business days.",
                ),
            ],
        ),
    )


def run_handoff(connection: RealtimeConnection) -> None:
    connection.conversation.item.create(
        item=RealtimeConversationItemMessageUser(
            type=RealtimeConversationItemType.MESSAGE,
            content=[
                RealtimeConversationItemMessageUserContent(
                    type="input_text",
                    text="Transfer me to billing. How long does a refund take?",
                )
            ],
        )
    )
    connection.response.create()
    handoff_id = None
    completed = False
    deadline = time.monotonic() + 90
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("The handoff and specialist response did not finish.")
        event = connection.recv(timeout=remaining)
        if isinstance(event, RealtimeServerEventError):
            raise RuntimeError(event.error.message)
        if isinstance(event, VoiceAgentServerEventSessionHandoffStarted):
            handoff_id = event.handoff_id
            print(f"Handoff: {event.from_node_id} -> {event.to_node_id}")
        elif isinstance(event, VoiceAgentServerEventSessionHandoffAborted):
            raise RuntimeError(f"Handoff aborted: {event.reason}")
        elif isinstance(event, VoiceAgentServerEventSessionHandoffCompleted):
            if event.handoff_id != handoff_id or event.to_node_id != "billing":
                raise RuntimeError(
                    "The completed handoff does not match the requested billing handoff."
                )
            completed = True
        elif isinstance(event, RealtimeServerEventResponseTextDone):
            safe_print(f"Agent: {event.text}")
        elif isinstance(event, RealtimeServerEventResponseDone):
            if event.response.status not in ("completed", "cancelled"):
                raise RuntimeError(
                    f"Voice response ended with status {event.response.status}."
                )
            if completed and event.response.status == "completed":
                if any(item.type == "message" for item in event.response.output or []):
                    return


def main() -> None:
    load_dotenv()
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ.get("FOUNDRY_VOICE_AGENT_MODEL") or "gpt-realtime"
    agent_name = sample_agent_name("sample-inline-handoff")
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint, credential=credential, allow_preview=True
        ) as client,
    ):
        require_new_agent(client, agent_name)
        created = client.agents.create_version(
            agent_name=agent_name, definition=make_definition(model)
        )
        try:
            with client.voice_agents.realtime.connect(
                agent_name=agent_name
            ) as connection:
                run_handoff(connection)
        finally:
            client.agents.delete_version(
                agent_name=agent_name, agent_version=created.version
            )


if __name__ == "__main__":
    main()
