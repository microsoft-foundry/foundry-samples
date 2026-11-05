# Copyright (c) Microsoft. All rights reserved.
"""Invoke the Echo sample through the official native A2A client."""

import argparse
import asyncio

import httpx2 as httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_artifact_text, new_text_message
from a2a.types import GetTaskRequest, Role, SendMessageRequest, TaskState


async def run(endpoint: str, message: str) -> None:
    async with httpx.AsyncClient(headers={"A2A-Version": "1.0"}, timeout=30) as http:
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
            if len(tasks) != 1:
                raise RuntimeError(f"Expected one Task, received {len(tasks)}")
            task = tasks[0]
            if task.status.state != TaskState.TASK_STATE_COMPLETED:
                raise RuntimeError("Echo Task did not complete")
            if [get_artifact_text(artifact) for artifact in task.artifacts] != [
                f"Echo: {message}"
            ]:
                raise RuntimeError("Echo returned an unexpected artifact")
            if await client.get_task(GetTaskRequest(id=task.id)) != task:
                raise RuntimeError("GetTask did not preserve the completed Task")
            print(f"task_id={task.id}\nEcho: {message}")
        finally:
            await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://localhost:8088")
    parser.add_argument("--message", default="hello")
    args = parser.parse_args()
    asyncio.run(run(args.endpoint, args.message))
