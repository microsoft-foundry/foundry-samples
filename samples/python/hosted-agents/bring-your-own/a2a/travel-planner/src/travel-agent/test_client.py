# Copyright (c) Microsoft. All rights reserved.
"""Invoke a local Travel Planner using an ordinary native A2A client."""

import argparse
import asyncio
import json

import httpx2 as httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_artifact_text, new_text_message
from a2a.types import GetTaskRequest, Role, SendMessageRequest, TaskState

EXAMPLE = (
    "Plan a synthetic business trip for 1 traveler from SFO to SEA. "
    "Depart 2027-01-10 and return 2027-01-13. "
    "Arrive before 2027-01-11T09:00:00-08:00. "
    "Both flight and hotel must be refundable. "
    "Hotel must be within 3000 meters of the office. "
    "Total flight and hotel budget is USD 1200. Do not book anything."
)


async def run(endpoint: str, message: str) -> None:
    async with httpx.AsyncClient(headers={"A2A-Version": "1.0"}, timeout=240) as http:
        card = await A2ACardResolver(http, endpoint).get_agent_card(
            relative_card_path="a2a/.well-known/agent-card.json"
        )
        client = await create_client(
            card, ClientConfig(streaming=False, httpx_client=http)
        )
        try:
            tasks = [
                response.task
                async for response in client.send_message(
                    SendMessageRequest(
                        message=new_text_message(message, role=Role.ROLE_USER)
                    )
                )
                if response.HasField("task")
            ]
            if (
                len(tasks) != 1
                or tasks[0].status.state != TaskState.TASK_STATE_COMPLETED
            ):
                raise RuntimeError("Travel Planner did not return one completed Task")
            task = tasks[0]
            if len(task.artifacts) != 1:
                raise ValueError("Expected one travel result artifact")
            result = json.loads(get_artifact_text(task.artifacts[0]))
            if (
                result.get("synthetic") is not True
                or result.get("booking_created") is not False
            ):
                raise ValueError("Result must be synthetic with no booking")
            if result.get("status") in {"proposed", "no_match"}:
                delegations = result.get("delegations", [])
                if (
                    result.get("toolbox_verified") is not True
                    or {item.get("role") for item in delegations}
                    != {"flights", "hotels"}
                    or len(delegations) != 2
                    or len({item.get("task_id") for item in delegations}) != 2
                    or any(
                        not item.get("task_id") or not item.get("execution_id")
                        for item in delegations
                    )
                ):
                    raise ValueError(
                        "Missing or inconsistent managed Toolbox delegation evidence"
                    )
                if result["status"] == "proposed":
                    total = (
                        result["flight"]["total_cents"] + result["hotel"]["total_cents"]
                    )
                    if total != result["total_cents"] or total > result["budget_cents"]:
                        raise ValueError("Incorrect or over-budget itinerary")
            elif result.get("status") != "needs_clarification" or not result.get(
                "question"
            ):
                raise ValueError("Unknown travel result status")
            if await client.get_task(GetTaskRequest(id=task.id)) != task:
                raise RuntimeError("Task retrieval did not preserve the travel result")
            print(f"Travel Planner Task: {task.id}")
            print(json.dumps(result, indent=2))
        finally:
            await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8088")
    parser.add_argument("--message", default=EXAMPLE)
    args = parser.parse_args()
    asyncio.run(run(args.endpoint, args.message))
