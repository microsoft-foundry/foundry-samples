# Copyright (c) Microsoft. All rights reserved.

"""Local CE protocol client, not an argument or endpoint used by the business agent."""

import argparse
import asyncio
import json
import uuid

from websockets.asyncio.client import connect


def frame(kind, **fields):
    return {"type": kind, "id": f"m_{uuid.uuid4().hex}", "ts": "2026-11-02T00:00:00Z", **fields}


async def run(uri: str, message: str, expected: str | None) -> None:
    async with connect(uri, max_size=1_048_576) as ws:
        await ws.send(
            json.dumps(
                frame(
                    "session.start",
                    protocol_version="1.0",
                    reconnect=False,
                    response_timeouts={
                        "first_output_ms": 30_000,
                        "idle_ms": 30_000,
                        "max_duration_ms": 180_000,
                    },
                )
            )
        )
        ready = json.loads(await asyncio.wait_for(ws.recv(), 30))
        if ready["type"] != "session.ready":
            raise RuntimeError(f"Expected session.ready, got {ready['type']}")
        await ws.send(
            json.dumps(
                frame(
                    "user.message",
                    item_id="in_smoke",
                    content=[{"type": "input_text", "text": message}],
                )
            )
        )
        deltas = ""
        response_id = None
        async with asyncio.timeout(240):
            while True:
                event = json.loads(await ws.recv())
                if event["type"] == "response.created":
                    assert event["in_reply_to"] == ["in_smoke"]
                    response_id = event["response_id"]
                elif event["type"] == "response.output_text.delta":
                    assert event["response_id"] == response_id
                    deltas += event["delta"]
                    print(event["delta"], end="", flush=True)
                elif event["type"] == "response.output_text.done":
                    assert event["text"] == deltas
                elif event["type"] == "response.done":
                    assert response_id == event["response_id"] and deltas.strip()
                    if expected:
                        assert expected in deltas, f"Missing expected output: {expected}"
                    print()
                    break
                elif event["type"] in {"error", "response.none", "session.rejected", "end_call"}:
                    raise RuntimeError(f"Unexpected terminal event: {event['type']}")
        await ws.send(json.dumps(frame("session.end", reason="caller_hangup")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default="ws://localhost:8088/voice_conversation_engine")
    parser.add_argument("--message", default="Search site specs for Quincy North.")
    parser.add_argument("--expect")
    args = parser.parse_args()
    asyncio.run(run(args.uri, args.message, args.expect))
