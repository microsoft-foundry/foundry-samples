"""Let a Realtime voice agent consult a same-project prompt agent.

Set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_VOICE_SUBAGENT_MODEL (a chat deployment).
Optional: FOUNDRY_VOICE_AGENT_MODEL, default gpt-realtime.
Run: python voice_agent_subagents.py
"""

import os
import time
from contextlib import ExitStack
from datetime import timedelta
from uuid import uuid4

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    RealtimeConversationItemMessageUser,
    RealtimeConversationItemMessageUserContent,
    RealtimeConversationItemType,
    RealtimeServerEventError,
    RealtimeServerEventResponseDone,
    RealtimeServerEventResponseTextDone,
    VoiceAgentDefinition,
    VoiceAgentDelegateSubagentConfig,
    VoiceAgentServerEventSessionSubagentAborted,
    VoiceAgentServerEventSessionSubagentCompleted,
    VoiceAgentServerEventSessionSubagentStarted,
    VoiceAgentSubagent,
    VoiceAgentSubagentResponsePolicy,
    VoiceModelType,
    VoiceOutputModality,
)
from azure.ai.projects.operations import RealtimeConnection
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from voice_agent_util import require_new_agent, safe_print, sample_agent_name


def consult_specialist(connection: RealtimeConnection) -> None:
    """Wait for a completed consultation and the frontend's final answer."""
    connection.conversation.item.create(
        item=RealtimeConversationItemMessageUser(
            type=RealtimeConversationItemType.MESSAGE,
            content=[
                RealtimeConversationItemMessageUserContent(
                    type="input_text",
                    text="Ask the policy specialist: how long do I have to return a purchase?",
                )
            ],
        )
    )
    connection.response.create()
    consultation_id = None
    completed = False
    answered = False
    deadline = time.monotonic() + 90
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("The specialist consultation did not finish.")
        event = connection.recv(timeout=remaining)
        if isinstance(event, RealtimeServerEventError):
            raise RuntimeError(event.error.message)
        if isinstance(event, VoiceAgentServerEventSessionSubagentStarted):
            if consultation_id is not None and consultation_id != event.consultation_id:
                raise RuntimeError("This sample expects one specialist consultation.")
            consultation_id = event.consultation_id
            print(f"Consulting {event.subagent_name}: {consultation_id}")
        elif isinstance(event, VoiceAgentServerEventSessionSubagentAborted):
            raise RuntimeError(f"Specialist consultation aborted: {event.reason}")
        elif isinstance(event, VoiceAgentServerEventSessionSubagentCompleted):
            if event.consultation_id != consultation_id:
                raise RuntimeError(
                    "The completed consultation does not match the started consultation."
                )
            completed = True
        elif isinstance(event, RealtimeServerEventResponseTextDone):
            safe_print(f"Agent: {event.text}")
        elif isinstance(event, RealtimeServerEventResponseDone):
            if event.response.status != "completed":
                raise RuntimeError(
                    f"Voice response ended with status {event.response.status}."
                )
            if consultation_id is not None and any(
                item.type == "message" for item in event.response.output or []
            ):
                answered = True
        # The service may emit the final response before subagent.completed.
        if completed and answered:
            return


def main() -> None:
    load_dotenv()
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    chat_model = os.environ["FOUNDRY_VOICE_SUBAGENT_MODEL"]
    voice_model = os.environ.get("FOUNDRY_VOICE_AGENT_MODEL") or "gpt-realtime"
    agent_name = sample_agent_name("sample-voice-specialist")
    specialist_name = f"sample-return-policy-{uuid4().hex[:8]}"

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as client,
        ExitStack() as cleanup,
    ):
        require_new_agent(client, agent_name)
        require_new_agent(client, specialist_name)
        specialist = client.agents.create_version(
            agent_name=specialist_name,
            definition=PromptAgentDefinition(
                model=chat_model,
                instructions="You are a return-policy specialist. Purchases may be returned within 30 days.",
            ),
        )
        cleanup.callback(
            client.agents.delete_version,
            agent_name=specialist_name,
            agent_version=specialist.version,
        )
        voice = client.agents.create_version(
            agent_name=agent_name,
            definition=VoiceAgentDefinition(
                model_type=VoiceModelType.MANAGED,
                model=voice_model,
                instructions="Always consult the return-policy specialist before answering policy questions.",
                output_modalities=[VoiceOutputModality.TEXT],
                subagent_config=VoiceAgentDelegateSubagentConfig(
                    subagents=[
                        VoiceAgentSubagent(
                            agent_name=specialist_name,
                            agent_version=specialist.version,
                            agent_capabilities="Answers questions about the purchase return policy.",
                            invoke_timeout=timedelta(seconds=30),
                            response_policy=VoiceAgentSubagentResponsePolicy(
                                immediate_ack=False, enable_delta_progress=False
                            ),
                        )
                    ]
                ),
            ),
        )
        cleanup.callback(
            client.agents.delete_version,
            agent_name=agent_name,
            agent_version=voice.version,
        )
        with client.voice_agents.realtime.connect(agent_name=agent_name) as connection:
            consult_specialist(connection)


if __name__ == "__main__":
    main()
