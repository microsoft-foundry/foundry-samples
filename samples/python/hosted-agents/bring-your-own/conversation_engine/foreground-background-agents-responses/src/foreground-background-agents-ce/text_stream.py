# Copyright (c) Microsoft. All rights reserved.

"""Internal text events at the unchanged handler/CE transport boundary.

These are not an HTTP endpoint or a replacement Responses SDK. The old handler's
text chunks are passed directly to the CE response coordinator.
"""

from typing import Any


class TextEventStream:
    def __init__(self, response_id: str, request: dict[str, Any]) -> None:
        self.response_id = response_id
        self._index = -1

    def emit_created(self) -> dict[str, Any]:
        return {"type": "response.created"}

    def emit_in_progress(self) -> dict[str, Any]:
        return {"type": "response.in_progress"}

    def emit_completed(self) -> dict[str, Any]:
        return {"type": "response.completed"}

    def text_events(self, text: str) -> list[dict[str, Any]]:
        self._index += 1
        return [
            {
                "type": "response.output_text.delta",
                "delta": text[i : i + 40],
                "output_index": self._index,
            }
            for i in range(0, len(text), 40)
        ]
