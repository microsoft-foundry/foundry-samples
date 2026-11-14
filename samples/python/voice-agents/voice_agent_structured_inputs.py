"""Personalize a greeting and instructions with connection-time structured inputs.

Set FOUNDRY_PROJECT_ENDPOINT; optionally FOUNDRY_VOICE_AGENT_MODEL.
Run: python voice_agent_structured_inputs.py --customer Casey --department Support
The customer value is required; the department also has an agent-defined default.
"""

import argparse
import os
import time

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    RealtimeConversationItemMessageUser,
    RealtimeConversationItemMessageUserContent,
    RealtimeConversationItemType,
    RealtimeServerEventError,
    RealtimeServerEventResponseAudioDelta,
    RealtimeServerEventResponseAudioTranscriptDone,
    RealtimeServerEventResponseDone,
    StructuredInputDefinition,
    VoiceAgentDefinition,
    VoiceAgentTemplateGreetingConfig,
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
        instructions="Your customer is {{customer}} and your department is {{department}}. Answer briefly.",
        structured_inputs={
            "customer": StructuredInputDefinition(
                schema={"type": "string"}, required=True
            ),
            "department": StructuredInputDefinition(
                schema={"type": "string"}, default_value="Support"
            ),
        },
        greeting=VoiceAgentTemplateGreetingConfig(text="Hello {{customer}}."),
        output_modalities=[VoiceOutputModality.AUDIO],
    )


def receive_turn(connection: RealtimeConnection) -> str:
    transcript = ""
    audio_bytes = 0
    deadline = time.monotonic() + 45
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("The personalized response did not finish.")
        event = connection.recv(timeout=remaining)
        if isinstance(event, RealtimeServerEventError):
            raise RuntimeError(event.error.message)
        if isinstance(event, RealtimeServerEventResponseAudioDelta):
            audio_bytes += len(event.delta)
        elif isinstance(event, RealtimeServerEventResponseAudioTranscriptDone):
            transcript = event.transcript
        elif isinstance(event, RealtimeServerEventResponseDone):
            if (
                event.response.status != "completed"
                or not transcript.strip()
                or not audio_bytes
            ):
                raise RuntimeError(
                    "Expected a completed personalized transcript and nonempty spoken audio."
                )
            safe_print(f"Agent: {transcript}")
            return transcript


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--customer", default="Casey")
    parser.add_argument("--department", default="Support")
    args = parser.parse_args()
    if not args.customer.strip() or not args.department.strip():
        parser.error("Customer and department must be nonempty.")
    load_dotenv()
    agent_name = sample_agent_name("sample-voice-inputs")
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential
        ) as client,
    ):
        require_new_agent(client, agent_name)
        created = client.agents.create_version(
            agent_name=agent_name,
            definition=make_definition(
                os.environ.get("FOUNDRY_VOICE_AGENT_MODEL") or "gpt-realtime"
            ),
        )
        print(f"Created owned agent {agent_name}, version {created.version}.")
        try:
            with client.voice_agents.realtime.connect(
                agent_name=agent_name,
                structured_inputs={
                    "customer": args.customer,
                    "department": args.department,
                },
            ) as connection:
                greeting = receive_turn(connection)
                if args.customer.casefold() not in greeting.casefold():
                    raise RuntimeError(
                        "The greeting did not contain the supplied customer."
                    )
                connection.conversation.item.create(
                    item=RealtimeConversationItemMessageUser(
                        type=RealtimeConversationItemType.MESSAGE,
                        content=[
                            RealtimeConversationItemMessageUserContent(
                                type="input_text",
                                text="What is my customer name and your department?",
                            )
                        ],
                    )
                )
                connection.response.create()
                answer = receive_turn(connection)
                if any(
                    value.casefold() not in answer.casefold()
                    for value in (args.customer, args.department)
                ):
                    raise RuntimeError("The answer did not use both structured inputs.")
        finally:
            client.agents.delete_version(
                agent_name=agent_name, agent_version=created.version
            )


if __name__ == "__main__":
    main()
