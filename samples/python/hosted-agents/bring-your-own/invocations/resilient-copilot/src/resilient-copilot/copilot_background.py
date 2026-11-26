"""Track SDK background work before a durable Copilot turn completes.

Ported from the Microsoft 365 Autopilot hosted-agent sample. Parent
``session.idle`` alone does not mean the work is done: background subagents
and detached shell commands keep running after the parent turn idles, and the
model normally takes a follow-up turn when they finish. The turn therefore
stays alive until the parent is idle *and* the SDK-tracked inventory
(``session.rpc.tasks``) is empty.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from copilot.session_events import SessionEventType

logger = logging.getLogger(__name__)

POLL_SECONDS = 30.0
IDLE_GRACE_SECONDS = 10.0


def _field(value: Any, snake: str, camel: str | None = None) -> Any:
    if isinstance(value, dict):
        return value.get(camel or snake)
    return getattr(value, snake, None)


def is_main_event(event: Any) -> bool:
    """True for parent-session events; subagent events carry a parent link."""
    data = _field(event, "data")
    return not (
        _field(event, "agent_id", "agentId")
        or _field(data, "parent_tool_call_id", "parentToolCallId")
        or _field(data, "parent_agent_task_id", "parentAgentTaskId")
    )


class BackgroundWork:
    """Parent idle plus running subagents and SDK background tasks."""

    def __init__(self) -> None:
        self.session_idle = False
        self.subagents: set[str] = set()
        self.running: set[str] = set()
        self.observed = False
        self.inventory_required = False
        self.refresh_required = False
        self.inventory_known = True
        self._idle_since: float | None = None
        self._rpc_failed = False

    def mark_busy(self) -> None:
        """A parent send starts new work; a prior idle no longer completes it."""
        self.session_idle = False
        self._idle_since = None

    def observe(self, event: Any) -> None:
        kind = _field(event, "type")
        data = _field(event, "data")
        top = is_main_event(event)
        if top and kind in {
            SessionEventType.USER_MESSAGE,
            SessionEventType.ASSISTANT_TURN_START,
            SessionEventType.SYSTEM_NOTIFICATION,
        }:
            self.session_idle = False
            self._idle_since = None
        if kind == SessionEventType.SUBAGENT_STARTED:
            key = _field(data, "tool_call_id", "toolCallId") or _field(
                event, "agent_id", "agentId"
            )
            if key:
                self.subagents.add(str(key))
            self.observed = True
            self.refresh_required = True
        elif kind in {SessionEventType.SUBAGENT_COMPLETED, SessionEventType.SUBAGENT_FAILED}:
            key = _field(data, "tool_call_id", "toolCallId") or _field(
                event, "agent_id", "agentId"
            )
            self.subagents.discard(str(key))
            self.refresh_required = True
        elif kind == SessionEventType.SESSION_BACKGROUND_TASKS_CHANGED:
            self.inventory_required = True
            self.refresh_required = True
        elif top and kind == SessionEventType.SESSION_IDLE:
            # Background subagents remain visible in the task inventory.
            self.session_idle = True
            self.subagents.clear()
            self.refresh_required = True
        if self.subagents or self.running:
            self._idle_since = None

    async def refresh(self, session: Any) -> None:
        """Re-read ``session.rpc.tasks``; keep the last known set on failure."""
        self.refresh_required = False
        api = getattr(getattr(session, "rpc", None), "tasks", None)
        if api is None and not self.observed and not self.inventory_required:
            return
        try:
            if api is None:
                raise RuntimeError("Background task inventory is unavailable")
            async with asyncio.timeout(POLL_SECONDS):
                await api.refresh()
                listed = await api.list()
            items = listed.get("tasks", []) if isinstance(listed, dict) else listed.tasks
            tasks = [item.to_dict() if hasattr(item, "to_dict") else item for item in items]
            self.running = {
                str(item["id"]) for item in tasks if item.get("status") == "running"
            }
            self.observed = self.observed or bool(self.running)
            self.inventory_known = True
            self._rpc_failed = False
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self.inventory_known = False
            if not self._rpc_failed:
                logger.warning(
                    "Could not refresh Copilot background tasks | error_type=%s | "
                    "retaining_running=%d",
                    type(exc).__name__,
                    len(self.running),
                )
                self._rpc_failed = True
        if self.running or not self.inventory_known:
            self._idle_since = None

    def completed(self) -> bool:
        if not self.session_idle or self.subagents or self.running or not self.inventory_known:
            self._idle_since = None
            return False
        if not self.observed:
            return True
        # Let the completion notification start the model's follow-up turn.
        now = asyncio.get_running_loop().time()
        if self._idle_since is None:
            self._idle_since = now
        return now - self._idle_since >= IDLE_GRACE_SECONDS

    def poll_delay(self) -> float | None:
        if self._idle_since is not None:
            return max(
                0.0,
                IDLE_GRACE_SECONDS - (asyncio.get_running_loop().time() - self._idle_since),
            )
        if self.observed or not self.inventory_known:
            return POLL_SECONDS
        return None
