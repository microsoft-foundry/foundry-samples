"""Deterministic A/B forwarders and C session observer; no model required."""

import hashlib
import json
import logging
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

os.environ.setdefault("OTEL_INSTRUMENTATION_A2A_SDK_ENABLED", "false")

from a2a.helpers import get_message_text, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a.utils.errors import TaskNotCancelableError
from azure.ai.agentserver.a2a import A2AAgentServerHost
from azure.ai.agentserver.core import AgentConfig, get_request_context
from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential
from client import send

logger = logging.getLogger("session-repro")
BOOT_ID = str(uuid4())


def digest(value: str | None) -> str | None:
    return hashlib.sha256(value.encode()).hexdigest()[:20] if value else None


def downstream_context(payload: dict, incoming_context: str) -> str | None:
    mode = payload.get("mode", "fresh")
    if mode == "fresh":
        return None
    if mode == "inherit":
        if not incoming_context:
            raise ValueError("inherit requires an incoming context ID")
        return incoming_context
    if mode == "explicit":
        value = payload.get("c_context_id")
        if isinstance(value, str) and value:
            return value
        raise ValueError("explicit requires c_context_id")
    raise ValueError(f"Unknown forwarding mode: {mode}")


def record(database: Path, context_id: str, payload: dict) -> dict:
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database, timeout=30, isolation_level=None)) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS calls "
            "(sequence INTEGER PRIMARY KEY, context_id TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        db.execute("BEGIN IMMEDIATE")
        previous = [
            {"sequence": row[0], "context_id": row[1], **json.loads(row[2])}
            for row in db.execute("SELECT sequence, context_id, payload FROM calls ORDER BY sequence")
        ]
        cursor = db.execute(
            "INSERT INTO calls(context_id, payload) VALUES (?, ?)",
            (context_id, json.dumps(payload)),
        )
        sequence = cursor.lastrowid
        db.execute("COMMIT")
    return {
        "sequence": sequence,
        "prior_session_messages": previous,
        "prior_context_messages": [
            item for item in previous if item["context_id"] == context_id
        ],
    }


class RoutingExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.message is None:
            raise ValueError("A2A message is required")
        payload = json.loads(get_message_text(context.message))
        if not isinstance(payload, dict) or not isinstance(payload.get("marker"), str):
            raise ValueError("Expected an object with a synthetic marker string")
        role = os.environ["REPRO_ROLE"]
        if role not in {"A", "B", "C"}:
            raise ValueError("REPRO_ROLE must be A, B or C")
        task = new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()
        caller = get_request_context()
        receipt = {
            "agent": role,
            "marker": payload["marker"],
            "task_id": task.id,
            "context_id": task.context_id,
            "input_context_id": context.message.context_id,
            "hosted_session_id": os.environ.get("FOUNDRY_AGENT_SESSION_ID"),
            "hosted_session_guid": os.environ.get("FOUNDRY_AGENT_SESSION_GUID"),
            "request_session_id": caller.session_id,
            "boot_id": BOOT_ID,
            "user_fingerprint": digest(caller.user_id),
            "call_fingerprint": digest(caller.call_id),
        }
        try:
            if role == "C":
                # HOME is platform-session scoped; this ledger exposes actual reuse.
                database = Path(os.environ.get("REPRO_STATE_DIR", str(Path.home()))) / "session-repro.sqlite"
                receipt.update(record(database, task.context_id, payload))
                receipt["caller_agent"] = payload.get("caller_agent")
            else:
                c_context = downstream_context(payload, task.context_id)
                hosted = bool(os.environ.get("FOUNDRY_HOSTING_ENVIRONMENT"))
                credential = (
                    ManagedIdentityCredential(
                        client_id=os.environ["FOUNDRY_AGENT_INSTANCE_CLIENT_ID"]
                    )
                    if hosted
                    else DefaultAzureCredential()
                )
                async with credential:
                    receipt["downstream"] = await send(
                        os.environ["C_AGENT_ENDPOINT"],
                        {"marker": payload["marker"], "caller_agent": role},
                        c_context,
                        credential,
                        caller.platform_headers(),
                    )
                receipt["forwarding_mode"] = payload.get("mode", "fresh")
            await updater.add_artifact(
                parts=[new_text_part(json.dumps(receipt), media_type="application/json")],
                name="session-observation",
            )
            await updater.complete()
            logger.info("SESSION_OBSERVATION %s", json.dumps(receipt))
        except Exception:
            logger.exception("SESSION_REPRO_FAILED role=%s task=%s", role, task.id)
            await updater.failed()
            raise

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise TaskNotCancelableError(message="This diagnostic agent does not support cancellation")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    config = AgentConfig.from_env()
    role = os.environ["REPRO_ROLE"]
    card = AgentCard(
        name=f"Session Repro {role}",
        description="Deterministic A2A session routing observer",
        version="1.0.0",
        capabilities=AgentCapabilities(),
        default_input_modes=["text/plain"],
        default_output_modes=["application/json"],
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                protocol_version="1.0",
                url=f"http://127.0.0.1:{config.port}/a2a",
            )
        ],
        skills=[
            AgentSkill(
                id="observe", name="Observe session routing",
                description="Accept JSON with marker, mode and optional c_context_id",
                tags=["diagnostics"],
            )
        ],
    )
    A2AAgentServerHost(agent_card=card, agent_executor=RoutingExecutor()).run(
        host="0.0.0.0" if config.is_hosted else "127.0.0.1"
    )
