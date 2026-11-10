"""Model-backed protocol smoke; no audio or cloud resources are provisioned."""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import UTC, datetime

import websockets
from websockets.exceptions import ConnectionClosed


async def run(uri: str, text: str) -> None:
    async with websockets.connect(uri, open_timeout=30, close_timeout=10) as socket:

        async def send(kind: str, **fields: object) -> None:
            await socket.send(
                json.dumps(
                    {
                        "type": kind,
                        "id": f"m_{uuid.uuid4().hex}",
                        "ts": datetime.now(UTC).isoformat(),
                        **fields,
                    }
                )
            )

        await send(
            "session.start",
            protocol_version="1.0",
            reconnect=False,
            response_timeouts={
                "first_output_ms": 30000,
                "idle_ms": 30000,
                "max_duration_ms": 120000,
            },
        )
        try:
            ready = json.loads(await asyncio.wait_for(socket.recv(), 30))
            if ready["type"] != "session.ready":
                raise RuntimeError("The conversation engine did not accept the session")
            await send(
                "user.message", item_id="in_smoke", content=[{"type": "input_text", "text": text}]
            )
            frames: list[str] = []
            response_id = None
            item_id = None
            accumulated = ""
            text_done = False
            while True:
                frame = json.loads(await asyncio.wait_for(socket.recv(), 90))
                kind = frame["type"]
                frames.append(kind)
                if response_id is None:
                    if kind != "response.created" or frame.get("in_reply_to") != ["in_smoke"]:
                        raise RuntimeError("Expected a correlated response.created")
                    response_id = frame["response_id"]
                    continue
                if frame.get("response_id") != response_id:
                    raise RuntimeError("Response ID changed during generation")
                if kind in ("response.output_text.delta", "response.output_text.done"):
                    if text_done:
                        raise RuntimeError("Output arrived after text completion")
                    item_id = item_id or frame["item_id"]
                    if frame["item_id"] != item_id:
                        raise RuntimeError("Output item ID changed")
                    if kind == "response.output_text.delta":
                        accumulated += frame["delta"]
                    else:
                        if not accumulated or frame["text"] != accumulated:
                            raise RuntimeError("Completed text does not match streamed text")
                        text_done = True
                elif kind == "response.done" and text_done:
                    print(json.dumps({"frames": frames, "text": accumulated}, ensure_ascii=True))
                    return
                else:
                    raise RuntimeError(f"Unexpected CE frame type: {kind}")
        finally:
            try:
                await send("session.end", reason="validation_complete")
            except ConnectionClosed:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default="ws://127.0.0.1:8088/voice_conversation_engine")
    parser.add_argument("--text", default="Hello!")
    options = parser.parse_args()
    asyncio.run(run(options.uri, options.text))


if __name__ == "__main__":
    main()
