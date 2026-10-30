# Copyright (c) Microsoft. All rights reserved.

"""Store complete native Tasks and read them after reconstructing the host."""

import logging
import os

os.environ.setdefault("OTEL_INSTRUMENTATION_A2A_SDK_ENABLED", "false")

from a2a.helpers import get_message_text, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a.utils.errors import TaskNotCancelableError

from azure.ai.agentserver.a2a import A2AAgentServerHost, FoundryTaskStore
from azure.ai.agentserver.core import AgentConfig

logger = logging.getLogger("a2a.persistence")


class PersistentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.message is None:
            raise ValueError("A2A request did not contain a message")
        task = new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.add_artifact(
            parts=[
                new_text_part(
                    f"Persisted: {get_message_text(context.message)}",
                    media_type="text/plain",
                )
            ]
        )
        await updater.complete()
        logger.info("A2A_PERSISTED task_id=%s", task.id)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise TaskNotCancelableError(
            message="Persistence example completes within the request"
        )


config = AgentConfig.from_env()
card = AgentCard(
    name="A2A Persistent Tasks",
    description="Saves Task status, history and artifacts for later retrieval",
    version="1.0.0",
    capabilities=AgentCapabilities(),
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    supported_interfaces=[
        AgentInterface(
            protocol_binding="JSONRPC",
            protocol_version="1.0",
            url=os.environ.get("A2A_AGENT_URL", f"http://localhost:{config.port}/a2a"),
        )
    ],
    skills=[
        AgentSkill(
            id="persist", name="Persist", description="Save a Task", tags=["storage"]
        )
    ],
)
# Hosted execution uses the host's agent-scoped Foundry store. Locally, opt in
# to Core's file-backed implementation so a process restart keeps the snapshots.
local_store = None if config.is_hosted else FoundryTaskStore("a2a-persistence-sample")
host = A2AAgentServerHost(
    agent_card=card,
    agent_executor=PersistentExecutor(),
    task_store=local_store,
)


@host.shutdown_handler
async def close_storage() -> None:
    if local_store is not None:
        await local_store.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    host.run()
