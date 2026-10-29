#!/usr/bin/env python3
# Copyright (c) Microsoft. All rights reserved.

"""Run a model-free Voice Live Bridge Protocol 1.0 smoke test."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime

import websockets

EXPECTED_STORY = (
    "Once a little rabbit found a lonely star. She carried it up the tallest hill, "
    "where friendly fireflies helped it shine again. "
    "That night, everyone dreamed of kindness and adventure."
)

UNEXPECTED_TERMINALS = {
    "end_call",
    "error",
    "response.cancel",
    "response.cancelled",
    "response.none",
    "session.rejected",
}


class ResponseValidator:
    """Validate one successful Bridge response sequence."""

    def __init__(self) -> None:
        self.stage = "created"
        self.response_id: str | None = None
        self.item_id: str | None = None
        self.completed_text = ""
        self.streamed_text = ""
        self.frames: list[str] = []

    def consume(self, response: object) -> bool:
        if not isinstance(response, dict):
            raise RuntimeError(f"Expected a JSON object, received {response!r}")
        response_type = response.get("type")
        if not isinstance(response_type, str):
            raise RuntimeError(f"Frame has no string type: {response!r}")
        if response_type in UNEXPECTED_TERMINALS:
            raise RuntimeError(f"Unexpected terminal frame: {response!r}")
        self.frames.append(response_type)

        if self.stage == "created":
            if response_type != "response.created":
                raise RuntimeError(f"Expected response.created, received {response!r}")
            self.response_id = self._required_id(response, "response_id")
            self.stage = "output"
            return False

        if response_type in {"response.output_text.delta", "response.output_text.done"}:
            self._match_id(response, "response_id", self.response_id)
            item_id = self._required_id(response, "item_id")
            if self.item_id is None:
                self.item_id = item_id
            elif item_id != self.item_id:
                raise RuntimeError(f"Mismatched item_id: {response!r}")
            if self.stage != "output":
                raise RuntimeError(f"Output received out of order: {response!r}")
            if response_type == "response.output_text.delta":
                delta = response.get("delta")
                if not isinstance(delta, str) or not delta:
                    raise RuntimeError(f"Streaming delta is empty: {response!r}")
                self.streamed_text += delta
            if response_type == "response.output_text.done":
                text = response.get("text")
                if not isinstance(text, str) or not text:
                    raise RuntimeError(f"Completed response text is empty: {response!r}")
                self.completed_text = text
                self.stage = "done"
            return False

        if response_type == "response.done":
            self._match_id(response, "response_id", self.response_id)
            if self.stage != "done":
                raise RuntimeError(f"response.done received before completed text: {response!r}")
            self.stage = "complete"
            return True

        raise RuntimeError(f"Unexpected or out-of-order frame: {response!r}")

    @staticmethod
    def _required_id(response: dict[object, object], field: str) -> str:
        value = response.get(field)
        if not isinstance(value, str) or not value:
            raise RuntimeError(f"Frame has no {field}: {response!r}")
        return value

    @staticmethod
    def _match_id(response: dict[object, object], field: str, expected: str | None) -> None:
        actual = ResponseValidator._required_id(response, field)
        if actual != expected:
            raise RuntimeError(f"Mismatched {field}: {response!r}")


def timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


async def run(uri: str, text: str) -> None:
    async with websockets.connect(uri, open_timeout=30, close_timeout=10) as socket:
        await socket.send(
            json.dumps(
                {
                    "type": "session.start",
                    "id": "m_smoke_start",
                    "ts": timestamp(),
                    "protocol_version": "1.0",
                    "reconnect": False,
                    "response_timeouts": {
                        "first_output_ms": 30_000,
                        "idle_ms": 30_000,
                        "max_duration_ms": 120_000,
                    },
                }
            )
        )
        ready = json.loads(await asyncio.wait_for(socket.recv(), timeout=30))
        if ready.get("type") != "session.ready":
            raise RuntimeError(f"Expected session.ready, received {ready!r}")

        await socket.send(
            json.dumps(
                {
                    "type": "user.message",
                    "id": "m_smoke_user",
                    "ts": timestamp(),
                    "item_id": "in_smoke_user",
                    "content": [{"type": "input_text", "text": text}],
                }
            )
        )

        validator = ResponseValidator()
        while True:
            response = json.loads(await asyncio.wait_for(socket.recv(), timeout=60))
            if validator.consume(response):
                break

        if (
            validator.completed_text != EXPECTED_STORY
            or validator.streamed_text != EXPECTED_STORY
            or validator.frames.count("response.output_text.delta") != 30
        ):
            raise RuntimeError("Expected the thirty-word story streamed in thirty word deltas")

        print("frames=" + ",".join(validator.frames))
        print("response=" + validator.completed_text)
        await socket.send(
            json.dumps(
                {
                    "type": "session.end",
                    "id": "m_smoke_end",
                    "ts": timestamp(),
                    "reason": "validation_complete",
                }
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default="ws://127.0.0.1:8088/voice_conversation_engine")
    parser.add_argument("--text", default="Hello, Voice Live!")
    args = parser.parse_args()
    asyncio.run(run(args.uri, args.text))


if __name__ == "__main__":
    main()
