# Copyright (c) Microsoft. All rights reserved.

"""Simulate redirected Windows output without changing process encoding settings."""

import io
import json
import re
from contextlib import redirect_stdout

import pytest

from scripts import smoke_test as smoke


class Socket:
    def __init__(self, output, data=None):
        self.sent = []
        self.frames = [
            {"type": "session.ready"}, {"type": "response.created", "response_id": "r_1"},
        ]
        if data is not None:
            self.frames.append({
                "type": "response.output_data.done", "response_id": "r_1",
                "item_id": "out_1", "data": data,
            })
        else:
            self.frames.extend({
                "type": "response.output_text.delta", "response_id": "r_1",
                "item_id": "out_1", "delta": chunk,
            } for chunk in re.findall(r"\s*\S+|\s+$", output))
            self.frames.append({
                "type": "response.output_text.done", "response_id": "r_1",
                "item_id": "out_1", "text": output,
            })
        self.frames.append({"type": "response.done", "response_id": "r_1"})
        self.incoming = iter(self.frames)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def send(self, value):
        self.sent.append(json.loads(value))

    async def recv(self):
        return json.dumps(next(self.incoming), ensure_ascii=False)


@pytest.mark.parametrize("data", [None], ids=["text"])
async def test_cp1252_reporting_preserves_wire_data_and_ends_the_session(monkeypatch, data):
    text = "你好 👋"
    output = smoke.EXPECTED_STORY
    socket = Socket(output, data)
    monkeypatch.setattr(smoke.websockets, "connect", lambda *_a, **_kw: socket)
    raw = io.BytesIO()
    writer = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
    with redirect_stdout(writer):
        await smoke.run("ws://test", text)
    writer.flush()
    report = raw.getvalue().decode("ascii")
    assert "response=" in report
    assert socket.sent[-1]["type"] == "session.end"
    expected = {"type": "input_data", "data": data} if data is not None else {
        "type": "input_text", "text": text,
    }
    assert socket.sent[1]["content"] == [expected]
    assert socket.frames[-1]["type"] == "response.done"
    writer.detach()


async def test_reporting_failure_does_not_skip_explicit_session_end(monkeypatch):
    socket = Socket(smoke.EXPECTED_STORY)
    monkeypatch.setattr(smoke.websockets, "connect", lambda *_a, **_kw: socket)

    class BrokenOutput:
        def write(self, _value):
            raise OSError("controlled reporting failure")

    with redirect_stdout(BrokenOutput()), pytest.raises(OSError, match="reporting failure"):
        await smoke.run("ws://test", "hello")
    assert socket.sent[-1]["type"] == "session.end"
