# Copyright (c) Microsoft. All rights reserved.

"""Submit a report Task, poll its state, or cancel its in-process execution."""

import asyncio
import logging
import os

os.environ.setdefault("OTEL_INSTRUMENTATION_A2A_SDK_ENABLED", "false")

from a2a.helpers import get_message_text, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill

from azure.ai.agentserver.a2a import A2AAgentServerHost
from azure.ai.agentserver.core import AgentConfig

logger = logging.getLogger("a2a.report")


class ReportExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.message is None:
            raise ValueError("A2A request did not contain a message")
        task = new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()
        logger.info("A2A_REPORT_WORKING task_id=%s", task.id)
        await asyncio.sleep(2)
        await updater.add_artifact(
            parts=[
                new_text_part(
                    f"Report: {get_message_text(context.message)}",
                    media_type="text/plain",
                )
            ]
        )
        await updater.complete()
        logger.info("A2A_REPORT_COMPLETED task_id=%s", task.id)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()
        logger.info("A2A_REPORT_CANCELED task_id=%s", context.task_id)


config = AgentConfig.from_env()
card = AgentCard(
    name="A2A Report Writer",
    description="Returns a Task immediately while preparing a report",
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
            id="report", name="Report", description="Prepare a report", tags=["tasks"]
        )
    ],
)
host = A2AAgentServerHost(agent_card=card, agent_executor=ReportExecutor())

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    host.run()
