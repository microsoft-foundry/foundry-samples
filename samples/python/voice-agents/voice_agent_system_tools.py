"""
Configure IVR tools and observe their real events (azure-ai-projects==2.11.0).

Run: python voice_agent_system_tools.py --scenario language --create-agent --observe
Set FOUNDRY_PROJECT_ENDPOINT; optionally FOUNDRY_VOICE_AGENT_MODEL and an UNUSED
FOUNDRY_VOICE_AGENT_NAME. Digits needs a speech-to-speech model (managed
gpt-realtime by default); the other recipes default to managed cascaded gpt-5.1.
A new disposable agent is created; --keep-agent retains only that new version
for inbound tests, with automatic responses to caller speech enabled.
Scenarios: language, digits, dtmf, sms. SMS additionally requires an explicitly
consenting FOUNDRY_TELEPHONY_SMS_NUMBER. Merely configuring tools sends nothing.
For DTMF/SMS, --operation collect (default) observes input collection; --operation
send requests one outbound action. With a real provider transport, observing send
may send tones or a billable SMS; obtain separate recipient consent first.
--soundscape adds quiet built-in office ambience and a closing cue; no custom URL.
Soundscape is rendered only on telephony, not WebSocket/WebRTC or stored recordings.

Language can run over WebSocket. For digits, pass --audio-file with a short,
non-sensitive PCM16 mono 24-kHz WAV of spoken test digits; the tool retrieves the
unchanged last-audio transcript, not normalized keypad digits. DTMF requires a
connected telephony transport; SMS requires an SMS-capable number and provider
receiver configuration. Use the retained agent with your own telephony binding.
WebSocket observation is NOT a substitute for provider delivery/collection tests.
The observer disables automatic responses only for its own session and waits
for acknowledgement before starting the test turn. It observes the service's
post-tool reply instead of requesting a duplicate continuation.
The service rejects DTMF/SMS tools on a direct WebSocket with unsupported_channel;
retain those recipes for phone-side testing rather than treating --observe as IVR E2E.

Argument deltas/done are model INTENT, not execution success or customer function
calls. Never send function_call_output for a system tool. Collection/telephony
outcomes arrive separately as input_collection.status. This sample prints only
tool names, invocation IDs, and statuses, never arguments, digits, SMS, or audio.
"""

import argparse
import json
import os
import time
import wave
from datetime import timedelta
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    RealtimeAudioFormatsAudioPcm,
    RealtimeConversationItemMessageUser,
    RealtimeConversationItemMessageUserContent,
    RealtimeConversationItemType,
    RealtimeServerEventConversationItemInputAudioTranscriptionCompleted,
    RealtimeServerEventError,
    RealtimeServerEventResponseAudioTranscriptDone,
    RealtimeServerEventResponseCreated,
    RealtimeServerEventResponseDone,
    RealtimeServerEventResponseTextDone,
    RealtimeServerEventSessionCreated,
    RealtimeServerEventSessionUpdated,
    VoiceAgentAudioConfig,
    VoiceAgentAudioInputConfig,
    VoiceAgentAudioOutputConfig,
    VoiceAgentAzureSemanticVadMultilingualTurnDetection,
    VoiceAgentCollectDtmfStartArguments,
    VoiceAgentCollectDtmfSystemTool,
    VoiceAgentCollectSmsStartArguments,
    VoiceAgentCollectSmsSystemTool,
    VoiceAgentDefinition,
    VoiceAgentDigitRecognitionSystemTool,
    VoiceAgentDtmfFixedLengthCompletionMode,
    VoiceAgentEndConversationSystemTool,
    VoiceAgentInputTranscription,
    VoiceAgentLanguageDetectionArguments,
    VoiceAgentLanguageDetectionSystemTool,
    VoiceAgentResponseCreateParams,
    VoiceAgentSendDtmfSystemTool,
    VoiceAgentSendSmsSystemTool,
    VoiceAgentServerEventInputCollectionStatus,
    VoiceAgentServerEventSystemToolArgumentsDelta,
    VoiceAgentServerEventSystemToolArgumentsDone,
    VoiceAgentSoundscapeConfig,
    VoiceAgentSoundscapeSourceConfig,
    VoiceAgentSoundscapeTrackConfig,
    VoiceAgentSessionUpdateConfig,
    VoiceAgentTool,
    VoiceModelType,
    VoiceOutputModality,
    VoiceType,
)
from azure.ai.projects.operations import RealtimeConnection
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from voice_agent_util import (
    phone_number,
    required_env,
    require_new_agent,
    sample_agent_name,
)

SCENARIOS = ("language", "digits", "dtmf", "sms")
EXPECTED_TOOLS = {
    "language": "language_detection",
    "digits": "digit_recognition",
    "dtmf": "collect_dtmf",
    "sms": "collect_sms",
}
COLLECTION_TERMINAL_STATUSES = {
    "completed",
    "expired",
    "cancelled",
    "failed",
    "busy",
    "invalid_input",
    "invalid_arguments",
    "stale_collection",
    "unsupported_channel",
    "dispatch_failed",
    "provider_failed_or_unsupported",
    "provider_result_uncertain",
    "provider_not_executed",
}


def make_turn_detection(
    create_response: bool,
) -> VoiceAgentAzureSemanticVadMultilingualTurnDetection:
    return VoiceAgentAzureSemanticVadMultilingualTurnDetection(
        create_response=create_response,
        silence_duration_ms=timedelta(milliseconds=500),
        languages=["en-US", "es-ES"],
    )


def build_definition(
    scenario: str, *, soundscape: bool = False
) -> VoiceAgentDefinition:
    tools: list[VoiceAgentTool] = [VoiceAgentEndConversationSystemTool()]
    instructions = (
        "You are a brief, consented SDK test assistant. Use only harmless canned "
        "test data, never ask for personal information. End the conversation on "
        "request. Never transfer, dial, or message an unapproved destination. "
    )
    timeout = timedelta(seconds=15)
    if scenario == "language":
        tools.append(VoiceAgentLanguageDetectionSystemTool(timeout=timeout))
        arguments = VoiceAgentLanguageDetectionArguments(
            language="es", reason="The test caller explicitly requested Spanish."
        )
        instructions += (
            "When the user requests Spanish, invoke language_detection once with "
            f"these arguments: {json.dumps(arguments.as_dict())}. Then briefly greet them."
        )
    elif scenario == "digits":
        tools.append(VoiceAgentDigitRecognitionSystemTool(timeout=timeout))
        instructions += (
            "After the user's audio turn, invoke digit_recognition once to retrieve "
            "its unchanged transcript. This does not collect DTMF or normalize digits."
        )
    elif scenario == "dtmf":
        tools.extend(
            [
                VoiceAgentCollectDtmfSystemTool(timeout=timeout),
                VoiceAgentSendDtmfSystemTool(timeout=timeout),
            ]
        )
        arguments = VoiceAgentCollectDtmfStartArguments(
            secret=True,
            output_variable_name="sample_digits",
            timeout=15,
            first_digit_timeout=10,
            completion_mode=VoiceAgentDtmfFixedLengthCompletionMode(length=2),
        )
        instructions += (
            "On an explicit request to collect two test keypad digits, invoke "
            f"collect_dtmf with {json.dumps(arguments.as_dict())}. "
            "Do not repeat or disclose collected values. On an explicit request "
            "to send test keypad tones, send only 12 once using send_dtmf. "
            "Never retry after an uncertain provider outcome."
        )
    elif scenario == "sms":
        sender = phone_number(required_env("FOUNDRY_TELEPHONY_SMS_NUMBER")).value
        tools.extend(
            [
                VoiceAgentCollectSmsSystemTool(timeout=timeout),
                VoiceAgentSendSmsSystemTool(timeout=timeout),
            ]
        )
        arguments = VoiceAgentCollectSmsStartArguments(
            secret=True,
            output_variable_name="sample_sms",
            from_phone_number=sender,
            timeout=15,
        )
        instructions += (
            "On an explicit request to collect a test SMS, invoke collect_sms "
            f"with {json.dumps(arguments.as_dict())}. Do not disclose the message. "
            f"Only on explicit request, send exactly one SMS to {sender} with "
            "the harmless text 'Foundry SDK test'. Do not send anything else, "
            "do not change recipient, and never retry an uncertain provider result."
        )
    else:
        raise ValueError(f"Unknown system-tool scenario: {scenario}")
    return VoiceAgentDefinition(
        model_type=VoiceModelType.MANAGED,
        model=os.environ.get("FOUNDRY_VOICE_AGENT_MODEL")
        or ("gpt-realtime" if scenario == "digits" else "gpt-5.1"),
        instructions=instructions,
        store=False,
        tools=tools,
        audio=VoiceAgentAudioConfig(
            input=VoiceAgentAudioInputConfig(
                format=RealtimeAudioFormatsAudioPcm(rate=24000),
                transcription=VoiceAgentInputTranscription(
                    model="azure-speech", language="en-US"
                ),
                turn_detection=make_turn_detection(True),
            ),
            output=VoiceAgentAudioOutputConfig(
                voice="en-US-AvaMultilingualNeural",
                voice_type=VoiceType.AZURE_STANDARD,
            ),
        ),
        soundscape=(
            VoiceAgentSoundscapeConfig(
                background=VoiceAgentSoundscapeTrackConfig(
                    source=VoiceAgentSoundscapeSourceConfig(name="office"), gain=0.1
                ),
                closing=VoiceAgentSoundscapeTrackConfig(
                    source=VoiceAgentSoundscapeSourceConfig(name="ding1"), gain=0.2
                ),
            )
            if soundscape
            else None
        ),
    )


def system_event_summary(event: object) -> dict[str, str] | None:
    """Deliberately omit argument fragments and all collection values/references."""
    if isinstance(event, VoiceAgentServerEventSystemToolArgumentsDelta):
        return {"type": event.type, "call_id": event.call_id}
    if isinstance(event, VoiceAgentServerEventSystemToolArgumentsDone):
        return {
            "type": event.type,
            "call_id": event.call_id,
            "name": event.name,
        }
    if isinstance(event, VoiceAgentServerEventInputCollectionStatus):
        return {
            "type": event.type,
            "call_id": event.call_id,
            "status": event.status,
        }
    return None


def read_test_audio(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wav:
        if (
            wav.getnchannels() != 1
            or wav.getsampwidth() != 2
            or wav.getframerate() != 24000
            or wav.getcomptype() != "NONE"
            or not 2400 <= wav.getnframes() <= 24000 * 15
        ):
            raise ValueError(
                "Use an uncompressed PCM16 mono 24-kHz WAV, 0.1–15 seconds."
            )
        return wav.readframes(wav.getnframes())


def observe_system_tool(
    connection: RealtimeConnection,
    scenario: str,
    *,
    operation: str = "collect",
    audio: bytes | None = None,
    timeout: float = 30,
) -> list[dict[str, str]]:
    """Observe intent and, for collection, the separate terminal outcome."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown system-tool scenario: {scenario}")
    if operation not in {"collect", "send"} or (
        operation == "send" and scenario not in {"dtmf", "sms"}
    ):
        raise ValueError("The send operation is only available for DTMF or SMS.")
    if scenario == "digits" and audio is None:
        raise ValueError("Digit recognition needs a real spoken test-audio turn.")
    if not 0 < timeout <= 120:
        raise ValueError("Use a timeout greater than 0 and at most 120 seconds.")
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("The system-tool session did not start.")
        event = connection.recv(timeout=remaining)
        if isinstance(event, RealtimeServerEventError):
            raise RuntimeError(f"Session error: {event.error.code}")
        if isinstance(event, RealtimeServerEventSessionCreated):
            break
    connection.session.update(
        session=VoiceAgentSessionUpdateConfig(
            audio=VoiceAgentAudioConfig(
                input=VoiceAgentAudioInputConfig(
                    turn_detection=make_turn_detection(False)
                )
            )
        )
    )
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("The manual observer setting was not acknowledged.")
        event = connection.recv(timeout=remaining)
        if isinstance(event, RealtimeServerEventError):
            raise RuntimeError(f"Session error: {event.error.code}")
        if isinstance(event, RealtimeServerEventSessionUpdated):
            detection = (
                event.session.get("audio", {})
                .get("input", {})
                .get("turn_detection", {})
            )
            if (
                detection.get("type") == "azure_semantic_vad_multilingual"
                and detection.get("create_response") is False
            ):
                break
    if audio is not None:
        # Azure Speech requires semantic VAD, not manual commit. Supply trailing silence.
        audio += bytes(48000)
        for offset in range(0, len(audio), 4800):
            chunk = audio[offset : offset + 4800]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("The spoken test turn exceeded the deadline.")
            connection.input_audio_buffer.append(audio=chunk)
            time.sleep(min(len(chunk) / 48000, remaining))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("The spoken test turn was not transcribed.")
            event = connection.recv(timeout=remaining)
            if isinstance(event, RealtimeServerEventError):
                raise RuntimeError(f"Session error: {event.error.code}")
            if isinstance(
                event,
                RealtimeServerEventConversationItemInputAudioTranscriptionCompleted,
            ):
                if not event.transcript.strip():
                    raise RuntimeError("The spoken test turn has an empty transcript.")
                break
    else:
        if operation == "send":
            prompt = (
                "Please send the harmless test keypad tones 12 exactly once."
                if scenario == "dtmf"
                else "Please send exactly one 'Foundry SDK test' SMS to the approved test recipient."
            )
        else:
            prompt = {
                "language": "Please switch the conversation to Spanish and briefly say hello.",
                "dtmf": "Please collect exactly two harmless test keypad digits.",
                "sms": "Please collect one harmless test SMS from the approved test sender.",
            }[scenario]
        connection.conversation.item.create(
            item=RealtimeConversationItemMessageUser(
                type=RealtimeConversationItemType.MESSAGE,
                content=[
                    RealtimeConversationItemMessageUserContent(
                        type="input_text", text=prompt
                    )
                ],
            )
        )
    connection.response.create(
        response=VoiceAgentResponseCreateParams(
            output_modalities=[VoiceOutputModality.TEXT], max_output_tokens=256
        )
    )
    summaries: list[dict[str, str]] = []
    invocations: set[str] = set()
    terminal: dict[str, str] = {}
    response_done = False
    continuation_response_id: str | None = None
    continuation_text_received = False
    expected_tool = (
        f"send_{scenario}" if operation == "send" else EXPECTED_TOOLS[scenario]
    )
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                "No complete system-tool outcome before the deadline; do not retry dispatch blindly."
            )
        event = connection.recv(timeout=remaining)
        if isinstance(event, RealtimeServerEventError):
            raise RuntimeError(f"Session error: {event.error.code}")
        summary = system_event_summary(event)
        if summary is not None:
            summaries.append(summary)
            print(json.dumps(summary))
        if (
            isinstance(event, VoiceAgentServerEventSystemToolArgumentsDone)
            and event.name == expected_tool
        ):
            invocations.add(event.call_id)
        elif isinstance(event, VoiceAgentServerEventInputCollectionStatus):
            if event.status in COLLECTION_TERMINAL_STATUSES or (
                operation == "send" and event.status == "provider_accepted"
            ):
                terminal[event.call_id] = event.status
        elif isinstance(event, RealtimeServerEventResponseCreated):
            if response_done and invocations and scenario not in {"dtmf", "sms"}:
                continuation_response_id = event.response.id
                if not continuation_response_id:
                    raise RuntimeError("The post-tool response omitted its ID.")
                continuation_text_received = False
                response_done = False
        elif isinstance(event, RealtimeServerEventResponseDone):
            if event.response.status != "completed":
                raise RuntimeError(f"Response failed: {event.response.status}")
            if (
                continuation_response_id is None
                or event.response.id == continuation_response_id
            ):
                response_done = True
        elif (
            isinstance(event, RealtimeServerEventResponseTextDone)
            and event.response_id == continuation_response_id
        ):
            continuation_text_received = bool(event.text.strip())
        elif (
            isinstance(event, RealtimeServerEventResponseAudioTranscriptDone)
            and event.response_id == continuation_response_id
        ):
            continuation_text_received = bool(event.transcript.strip())
        if response_done and invocations:
            if scenario not in {"dtmf", "sms"}:
                if continuation_response_id is None:
                    continue
                if continuation_text_received:
                    print(
                        "Observed system-tool intent and a post-tool response; "
                        "no telephony delivery is claimed."
                    )
                    return summaries
                else:
                    raise RuntimeError(
                        "The post-tool response contained no text or audio transcript."
                    )
            if invocations <= terminal.keys():
                print(
                    "Observed terminal system-tool feedback; only 'completed' means "
                    "input was collected. Provider acceptance is not delivery."
                )
                return summaries


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="language")
    parser.add_argument("--operation", choices=("collect", "send"), default="collect")
    parser.add_argument("--create-agent", action="store_true")
    parser.add_argument("--observe", action="store_true")
    parser.add_argument("--keep-agent", action="store_true")
    parser.add_argument("--soundscape", action="store_true")
    parser.add_argument("--audio-file", type=Path)
    args = parser.parse_args(argv)
    if not args.create_agent:
        print("No changes made. Opt in with --create-agent; --observe opens a session.")
        return
    if args.observe and args.scenario == "digits" and args.audio_file is None:
        parser.error("--observe --scenario digits requires --audio-file.")
    if args.audio_file is not None and args.scenario != "digits":
        parser.error("--audio-file is only used by --scenario digits.")
    if args.operation == "send" and args.scenario not in {"dtmf", "sms"}:
        parser.error("--operation send requires --scenario dtmf or sms.")

    load_dotenv()
    endpoint = required_env("FOUNDRY_PROJECT_ENDPOINT")
    definition = build_definition(args.scenario, soundscape=args.soundscape)
    audio = read_test_audio(args.audio_file) if args.audio_file is not None else None
    name = sample_agent_name("voice-system-tools")
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint,
            credential=credential,
            connection_timeout=10,
            read_timeout=20,
            retry_total=0,
        ) as client,
    ):
        require_new_agent(client, name)
        created = client.agents.create_version(agent_name=name, definition=definition)
        try:
            print(f"Configured {name}, version {created.version}, for {args.scenario}.")
            if args.observe:
                with client.voice_agents.realtime.connect(
                    agent_name=name
                ) as connection:
                    observe_system_tool(
                        connection,
                        args.scenario,
                        operation=args.operation,
                        audio=audio,
                    )
            else:
                print(
                    "Configuration only: no call, tool execution, or delivery verified."
                )
        finally:
            if args.keep_agent:
                print(
                    f"Retained {name}, version {created.version}; delete after testing."
                )
            else:
                client.agents.delete_version(
                    agent_name=name, agent_version=created.version
                )


if __name__ == "__main__":
    main()
