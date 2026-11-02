# Copyright (c) Microsoft. All rights reserved.
"""Native A2A Travel Planner using the Copilot SDK and managed Toolbox tools."""

import logging
import os

os.environ.setdefault("OTEL_INSTRUMENTATION_A2A_SDK_ENABLED", "false")

from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Role
from azure.ai.agentserver.a2a import A2AAgentServerHost
from azure.ai.agentserver.core import AgentConfig
from client import ask

logger = logging.getLogger("a2a.travel")
INSTRUCTIONS = """You are a synthetic business-travel planner.
Use the Flight and Hotel agents exposed by the configured Foundry Toolbox.
Discover their descriptions and send each a self-contained request as a text message
using its advertised A2A tool schema. If a specialist description lists JSON fields,
encode exactly those fields as a JSON object in the message string, with no prose
or extra fields. Use origin/destination airport codes, explicit timezone arrive_by,
integer travelers and boolean refundable. Map hotel check_in/out from trip dates.
Both specialists must answer before proposing
a trip or concluding no match. Do not invent a successful specialist response.
If tools fail, explain that the trip could not be planned; do not make up an itinerary.
Ask a concise clarification question if dates, origin/destination, traveler count,
arrival deadline, office distance or USD budget are missing.
Evaluate specialist answers yourself. Calculate the combined price and remaining
budget yourself, compare alternatives and recommend the cheapest eligible pair.
Do not use Python or a calculator: all travel reasoning and arithmetic are yours.
Respond in readable Markdown with flight, hotel, cost breakdown, total, remaining
budget and reasons. Cite specialist Task IDs when returned by the tools.
All inventory is dummy data. Never claim live prices, bookings or payments."""


class TravelExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.message is None:
            raise ValueError("A2A request must contain a message")
        task = new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()
        try:
            answer = await ask(
                INSTRUCTIONS, get_message_text(context.message), toolbox=True
            )
            await updater.add_artifact(
                parts=[new_text_part(answer, media_type="text/plain")]
            )
            await updater.complete()
        except Exception as error:
            logger.exception("Travel planning failed: task_id=%s", task.id)
            await updater.failed(
                new_text_message(
                    f"Travel planning failed: {error}", role=Role.ROLE_AGENT
                )
            )
            raise

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    config = AgentConfig.from_env()
    card = AgentCard(
        name="Travel Planner",
        description="Copilot SDK travel planner using Flight and Hotel A2A tools.",
        version="1.0.0",
        capabilities=AgentCapabilities(),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                protocol_version="1.0",
                url=f"http://localhost:{config.port}/a2a",
            )
        ],
        skills=[
            AgentSkill(
                id="planner",
                name="Travel Planner",
                description=INSTRUCTIONS,
                tags=["travel", "copilot"],
            )
        ],
    )
    A2AAgentServerHost(agent_card=card, agent_executor=TravelExecutor()).run(
        host="0.0.0.0" if config.is_hosted else "127.0.0.1"
    )
