"""Consume actual avatar WebSocket video or viseme/blendshape animation.

Requires requirements.txt, FOUNDRY_PROJECT_ENDPOINT, and a model/region enabled
for avatar output. FOUNDRY_VOICE_AGENT_MODEL defaults to gpt-realtime.
FOUNDRY_VOICE_AVATAR_CHARACTER defaults to lisa; FOUNDRY_VOICE_AVATAR_STYLE
defaults to casual-sitting. Use an authorized character/style for your region.
FOUNDRY_VOICE_ANIMATION_MODEL defaults to default for animation output.
Run: python voice_agent_avatar.py --mode video --output-dir avatar-output
Run: python voice_agent_avatar.py --mode animation --output-dir animation-output

Outputs encoded avatar.video (which can multiplex H.264/AAC), its reported codec
in result.json, and timestamped animation.jsonl. Separate PCM16 mono 24 kHz
audit audio is saved when emitted. A new output directory is required.
Use ffprobe/ffmpeg with the reported codec to inspect/decode encoded video.
No microphone, SDP-only success, or placeholder frames are used.
Animation is separately model/voice/region dependent: a completed video stream
does not prove viseme or blendshape support. Missing requested events fail
with their observed counts instead of being treated as success.
"""

import argparse
import base64
import json
import math
import os
import time
import wave
from pathlib import Path
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    RealtimeConversationItemMessageUser,
    RealtimeConversationItemMessageUserContent,
    RealtimeConversationItemType,
    RealtimeServerEventError,
    RealtimeServerEventResponseAudioDelta,
    RealtimeServerEventResponseDone,
    RealtimeServerEventSessionCreated,
    RealtimeServerEventSessionUpdated,
    VoiceAgentAnimationConfig,
    VoiceAgentAnimationOutputType,
    VoiceAgentAudioConfig,
    VoiceAgentAudioOutputConfig,
    VoiceAgentAvatarConfig,
    VoiceAgentAvatarOutputProtocol,
    VoiceAgentAvatarType,
    VoiceAgentDefinition,
    VoiceAgentServerEventResponseAnimationBlendshapesDelta,
    VoiceAgentServerEventResponseAnimationBlendshapesDone,
    VoiceAgentServerEventResponseAnimationVisemeDelta,
    VoiceAgentServerEventResponseAnimationVisemeDone,
    VoiceAgentServerEventResponseVideoDelta,
    VoiceAgentServerEventSessionAvatarSwitchToIdle,
    VoiceAgentServerEventSessionAvatarSwitchToSpeaking,
    VoiceAgentSessionUpdateConfig,
    VoiceModelType,
    VoiceOutputModality,
    VoiceType,
)
from azure.ai.projects.operations import RealtimeConnection
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from voice_agent_util import require_new_agent, sample_agent_name


def build_definition(mode: str) -> VoiceAgentDefinition:
    if mode not in ("video", "animation"):
        raise ValueError("Choose video or animation.")
    return VoiceAgentDefinition(
        model_type=VoiceModelType.MANAGED,
        model=os.environ.get("FOUNDRY_VOICE_AGENT_MODEL") or "gpt-realtime",
        instructions="Say a short, friendly hello in one sentence.",
        store=False,
        audio=VoiceAgentAudioConfig(
            output=VoiceAgentAudioOutputConfig(
                voice="en-US-AvaNeural", voice_type=VoiceType.AZURE_STANDARD
            )
        ),
        avatar=VoiceAgentAvatarConfig(
            type=VoiceAgentAvatarType.VIDEO_AVATAR,
            character=os.environ.get("FOUNDRY_VOICE_AVATAR_CHARACTER") or "lisa",
            style=os.environ.get("FOUNDRY_VOICE_AVATAR_STYLE") or "casual-sitting",
            output_protocol=VoiceAgentAvatarOutputProtocol.WEBSOCKET,
            output_audit_audio=True,
        ),
        output_modalities=[
            VoiceOutputModality.AUDIO,
            (
                VoiceOutputModality.AVATAR
                if mode == "video"
                else VoiceOutputModality.ANIMATION
            ),
        ],
    )


def consume_avatar(
    connection: RealtimeConnection,
    output_dir: Path,
    *,
    mode: str,
    timeout: float = 60,
) -> dict[str, Any]:
    """Save media and require the requested output events, not just session setup."""
    if mode not in ("video", "animation"):
        raise ValueError("Choose video or animation.")
    output_dir.mkdir()
    result: dict[str, Any] = {
        "mode": mode,
        "audio_bytes": 0,
        "audio_chunks": 0,
        "video_bytes": 0,
        "video_chunks": 0,
        "video_codec": None,
        "visemes": 0,
        "blendshape_frames": 0,
        "viseme_done": False,
        "blendshapes_done": False,
        "response_status": None,
        "avatar_speaking": False,
        "avatar_idle_after_speech": False,
        "animation_modalities_acknowledged": False,
        "animation_config_acknowledged": False,
    }
    deadline = time.monotonic() + timeout
    ready = False
    request_sent = False
    with (
        (output_dir / "audio.wav").open("xb") as raw,
        wave.open(raw, "wb") as audio,
        (output_dir / "avatar.video").open("xb") as video,
        (output_dir / "animation.jsonl").open("x", encoding="utf-8") as animation,
    ):
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Missing avatar {mode} output; received counts: {result}"
                )
            try:
                event = connection.recv(timeout=remaining)
            except TimeoutError as exc:
                raise TimeoutError(
                    f"Missing avatar {mode} output; received counts: {result}"
                ) from exc
            if isinstance(event, RealtimeServerEventError):
                raise RuntimeError(event.error.message)
            if isinstance(event, RealtimeServerEventSessionCreated):
                if mode == "animation":
                    connection.session.update(
                        session=VoiceAgentSessionUpdateConfig(
                            output_modalities=[
                                VoiceOutputModality.AUDIO,
                                VoiceOutputModality.ANIMATION,
                            ],
                            animation=VoiceAgentAnimationConfig(
                                model_name=os.environ.get(
                                    "FOUNDRY_VOICE_ANIMATION_MODEL"
                                )
                                or "default",
                                outputs=[
                                    VoiceAgentAnimationOutputType.VISEME_ID,
                                    VoiceAgentAnimationOutputType.BLENDSHAPES,
                                ],
                            ),
                        )
                    )
                else:
                    ready = True
            elif isinstance(event, RealtimeServerEventSessionUpdated):
                if mode == "animation":
                    if VoiceOutputModality.ANIMATION not in (
                        event.session.get("output_modalities") or []
                    ):
                        continue
                    result["animation_modalities_acknowledged"] = True
                    result["animation_config_acknowledged"] = (
                        event.session.get("animation") is not None
                    )
                ready = True
            elif isinstance(event, RealtimeServerEventResponseAudioDelta):
                if not event.delta or len(event.delta) % 2:
                    raise ValueError("Invalid PCM16 avatar response.")
                audio.writeframes(event.delta)
                result["audio_bytes"] += len(event.delta)
                result["audio_chunks"] += 1
            elif isinstance(event, VoiceAgentServerEventResponseVideoDelta):
                frame = base64.b64decode(event.delta, validate=True)
                if not frame:
                    raise ValueError("Empty encoded avatar video delta.")
                if result["video_codec"] not in (None, event.codec):
                    raise ValueError("Video codec changed within the encoded stream.")
                result["video_codec"] = event.codec
                video.write(frame)
                result["video_bytes"] += len(frame)
                result["video_chunks"] += 1
            elif isinstance(event, VoiceAgentServerEventResponseAnimationVisemeDelta):
                if event.viseme_id < 0 or event.audio_offset_ms.total_seconds() < 0:
                    raise ValueError("Invalid viseme event.")
                animation.write(
                    json.dumps(
                        {
                            "type": event.type,
                            "item_id": event.item_id,
                            "audio_offset_ms": int(
                                event.audio_offset_ms.total_seconds() * 1000
                            ),
                            "viseme_id": event.viseme_id,
                        }
                    )
                    + "\n"
                )
                result["visemes"] += 1
            elif isinstance(
                event, VoiceAgentServerEventResponseAnimationBlendshapesDelta
            ):
                if not event.frames or any(
                    not frame or any(not math.isfinite(value) for value in frame)
                    for frame in event.frames
                ):
                    raise ValueError("Empty or invalid blendshape frames.")
                animation.write(
                    json.dumps(
                        {
                            "type": event.type,
                            "item_id": event.item_id,
                            "frame_index": event.frame_index,
                            "frames": event.frames,
                        }
                    )
                    + "\n"
                )
                result["blendshape_frames"] += len(event.frames)
            elif isinstance(event, VoiceAgentServerEventResponseAnimationVisemeDone):
                result["viseme_done"] = True
            elif isinstance(
                event, VoiceAgentServerEventResponseAnimationBlendshapesDone
            ):
                result["blendshapes_done"] = True
            elif isinstance(event, VoiceAgentServerEventSessionAvatarSwitchToSpeaking):
                result["avatar_speaking"] = True
            elif isinstance(event, VoiceAgentServerEventSessionAvatarSwitchToIdle):
                if result["avatar_speaking"]:
                    result["avatar_idle_after_speech"] = True
            elif isinstance(event, RealtimeServerEventResponseDone):
                result["response_status"] = event.response.status
                if event.response.status != "completed":
                    raise RuntimeError(
                        f"Avatar response ended with status {event.response.status}."
                    )
            if ready and not request_sent:
                connection.conversation.item.create(
                    item=RealtimeConversationItemMessageUser(
                        type=RealtimeConversationItemType.MESSAGE,
                        content=[
                            RealtimeConversationItemMessageUserContent(
                                type="input_text", text="Say a short, friendly hello."
                            )
                        ],
                    )
                )
                connection.response.create()
                request_sent = True
                ready = False
            media_complete = (
                (result["video_chunks"] > 1 and result["avatar_idle_after_speech"])
                if mode == "video"
                else (
                    result["visemes"] > 0
                    and result["blendshape_frames"] > 0
                    and result["viseme_done"]
                    and result["blendshapes_done"]
                )
            )
            if result["response_status"] == "completed" and media_complete:
                break
    (output_dir / "result.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("video", "animation"), default="video")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output_dir}.")
    definition = build_definition(args.mode)
    agent_name = sample_agent_name("sample-avatar")
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            credential=credential,
            allow_preview=True,
        ) as client,
    ):
        require_new_agent(client, agent_name)
        created = None
        try:
            created = client.agents.create_version(
                agent_name=agent_name, definition=definition
            )
            with client.voice_agents.realtime.connect(
                agent_name=agent_name
            ) as connection:
                print(
                    json.dumps(
                        consume_avatar(connection, args.output_dir, mode=args.mode)
                    )
                )
        finally:
            if created is not None:
                client.agents.delete_version(
                    agent_name=agent_name, agent_version=created.version
                )


if __name__ == "__main__":
    main()
