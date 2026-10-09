r"""Replay unchanged meeting events through the installed SDK, entirely offline.

PowerShell (from samples\python\autopilot-agents):
  .\meeting-assistant\.venv\Scripts\python.exe .\meeting-assistant\scripts\replay-sdk-payloads.py
Append JSON file paths to replay private captures; payload values/paths are not printed.

Seams: only ChannelAdapter outbound transport methods and Connections are inert,
fail-closed doubles. The inherited adapter pipeline, AgentApplication, Authorization
(empty configuration/no route auth_handlers), MemoryStorage, TurnContext,
TeamsAgentExtension before_turn, TeamsTurnContext, channel-data helpers and meeting
route wrappers are real SDK code. No identity, credentials, production configuration,
HTTP ingress, AGENTIC authentication, transcript fetching or lifecycle business logic
is exercised. Typing is disabled; callbacks only record entry. Real Teams API clients
are constructed by the SDK but no API method is called.

The fixtures preserve the observed wire shapes. This independent regression replay
uses the installed SDK's native meeting wrappers, without application business logic. There is
no casing conversion, missing-field synthesis or SDK patching. SDK channel_data
conversion and Activity class changes are observed, not repaired. Exit zero means
both events reached the callbacks with the correct fields/timestamps and unchanged
payloads. Validation or earlier before_turn failures are reported, never bypassed.
"""

import argparse
import asyncio
from copy import deepcopy
from importlib.metadata import version
import json
import logging
from datetime import datetime
from pathlib import Path
import platform

from microsoft_agents.activity import Activity
from microsoft_agents.hosting.core import AgentApplication, MemoryStorage, TurnContext
from microsoft_agents.hosting.core.channel_adapter import ChannelAdapter
from microsoft_agents.hosting.msteams import TeamsAgentExtension
from pydantic import ValidationError


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
EVENTS = {
    "application/vnd.microsoft.meetingStart",
    "application/vnd.microsoft.meetingEnd",
}
DISTRIBUTIONS = (
    "microsoft-agents-activity",
    "microsoft-agents-hosting-core",
    "microsoft-agents-hosting-msteams",
    "microsoft-teams-api",
    "microsoft-teams-common",
    "microsoft-teams-cards",
    "pydantic",
)


class OfflineConnections:
    """No token acquisition is allowed in this payload-only reproduction."""

    def get_connection(self, connection_name):
        raise RuntimeError("Offline replay attempted connection lookup")

    def get_default_connection(self):
        raise RuntimeError("Offline replay attempted default connection lookup")

    def get_token_provider(self, claims_identity, service_url):
        raise RuntimeError("Offline replay attempted token acquisition")

    def get_token_provider_from_activity(self, claims_identity, activity):
        raise RuntimeError("Offline replay attempted activity token acquisition")

    def get_default_connection_configuration(self):
        raise RuntimeError("Offline replay attempted authentication configuration lookup")


class OfflineAdapter(ChannelAdapter):
    """Use the real SDK pipeline, but fail if any outbound send is attempted."""

    async def send_activities(self, context, activities):
        raise RuntimeError("Offline replay attempted outbound send")

    async def update_activity(self, context, activity):
        raise RuntimeError("Offline replay attempted outbound update")

    async def delete_activity(self, context, reference):
        raise RuntimeError("Offline replay attempted outbound delete")


class UnexpectedDispatchError(RuntimeError):
    """Propagate unexpected pipeline failures without exposing payload values."""

    def __init__(self, result):
        super().__init__("Unexpected SDK dispatch failure; see sanitized result")
        self.result = result


def _sdk_frames(error):
    frames = []
    traceback = error.__traceback__
    while traceback:
        frame = traceback.tb_frame
        module = frame.f_globals.get("__name__", "")
        if module.startswith(("microsoft_agents.", "microsoft_teams.")):
            frames.append({"module": module, "function": frame.f_code.co_name})
        traceback = traceback.tb_next
    return frames


async def replay_payload(payload):
    """Dispatch one complete Activity without modifying the caller's JSON object."""
    original = deepcopy(payload)
    activity = Activity.model_validate(payload)
    original_value = deepcopy(activity.value)
    original_channel_data_type = type(activity.channel_data).__name__
    result = {
        "event": activity.name if activity.name in EVENTS else "unsupported",
        "stage": "before_on_turn",
        "sdk_before_turn_entered": False,
        "sdk_before_turn_completed": False,
        "callback_reached": False,
        "error": None,
    }
    adapter = OfflineAdapter()
    app = AgentApplication(
        storage=MemoryStorage(),
        adapter=adapter,
        connection_manager=OfflineConnections(),
        start_typing_timer=False,
    )

    @app.before_turn
    async def before_sdk(context, state):
        result["stage"] = "sdk_before_turn"
        result["sdk_before_turn_entered"] = True
        return True

    teams = TeamsAgentExtension(app)

    @app.before_turn
    async def after_sdk(context, state):
        result["stage"] = "after_sdk_before_turn"
        result["sdk_before_turn_completed"] = True
        return True

    async def callback(context, state, meeting):
        result["stage"] = "sdk_meeting_callback"
        result["callback_reached"] = True
        result["meeting_model"] = type(meeting).__name__
        result["common_fields_match"] = all(
            getattr(meeting, field) == original["value"][wire_field]
            for field, wire_field in (
                ("id", "Id"), ("title", "Title"),
                ("meeting_type", "MeetingType"), ("join_url", "JoinUrl"),
            )
        )
        field, wire_field = (
            ("start_time", "StartTime")
            if activity.name == "application/vnd.microsoft.meetingStart"
            else ("end_time", "EndTime")
        )
        result["timestamp_matches"] = getattr(meeting, field) == datetime.fromisoformat(
            original["value"][wire_field].replace("Z", "+00:00")
        )

    teams.meetings.start()(callback)
    teams.meetings.end()(callback)

    @app.error
    async def on_error(context, error):
        frames = _sdk_frames(error)
        if any(frame["module"].endswith(".meeting.meeting") for frame in frames):
            result["stage"] = "sdk_meeting_dispatch"
        result["error"] = {
            "type": type(error).__name__,
            "sdk_frames": frames,
        }
        if not isinstance(error, ValidationError):
            raise UnexpectedDispatchError(result) from None
        details = error.errors(include_input=False, include_context=False, include_url=False)
        result["error"].update(
            model=error.title,
            fields=[{"type": item["type"], "loc": list(item["loc"])} for item in details],
            missing_fields=[list(item["loc"]) for item in details if item["type"] == "missing"],
        )

    context = TurnContext(adapter, activity)
    try:
        await adapter.run_pipeline(context, app.on_turn)
    finally:
        result["activity_value_unchanged"] = (
            activity.value == original_value == original.get("value")
        )
        result["input_payload_unchanged"] = payload == original
        result["channel_data_types"] = {
            "before": original_channel_data_type,
            "after": type(activity.channel_data).__name__,
        }
        result["activity_class_after"] = type(activity).__name__
        result["dispatch_succeeded"] = successful_dispatch(result)
    return result


def successful_dispatch(result):
    return (
        result["event"] in EVENTS
        and result["stage"] == "sdk_meeting_callback"
        and result["sdk_before_turn_completed"]
        and result["callback_reached"]
        and result["error"] is None
        and result.get("meeting_model") == (
            "MeetingStartEventValue"
            if result["event"] == "application/vnd.microsoft.meetingStart"
            else "MeetingEndEventValue"
        )
        and result.get("common_fields_match") is True
        and result.get("timestamp_matches") is True
        and result["activity_value_unchanged"]
        and result["input_payload_unchanged"]
    )


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="Complete Activity JSON files")
    args = parser.parse_args()
    paths = args.paths or [
        FIXTURE_DIR / "meeting-start.json",
        FIXTURE_DIR / "meeting-end.json",
    ]
    results = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            results.append(await replay_payload(payload))
        except UnexpectedDispatchError as error:
            results.append(error.result)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            results.append({
                "stage": "input_loading",
                "error": {"type": type(error).__name__},
                "dispatch_succeeded": False,
            })
    print(json.dumps({
        "python": platform.python_version(),
        "versions": {name: version(name) for name in DISTRIBUTIONS},
        "results": results,
    }))
    return 0 if all(item["dispatch_succeeded"] for item in results) else 1


if __name__ == "__main__":
    # SDK diagnostics may interpolate a ValidationError's input; emit only our report.
    logging.disable(logging.CRITICAL)
    raise SystemExit(asyncio.run(main()))
