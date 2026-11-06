# Copyright (c) Microsoft. All rights reserved.

"""Cancellation/finalization through the actual SDK dispatcher and SSE adapter."""

import asyncio
import threading

import pytest
from starlette.responses import StreamingResponse
from starlette.testclient import TestClient
from test_voice_runtime import frame, receive_until, send_user, start

from adapter.runtime import create_app
from echo_agent import handle_invocation


@pytest.mark.parametrize("own_cancel", [False, True])
def test_body_setup_failure_closes_resources_before_error_and_allows_next_turn(own_cancel):
    from starlette.background import BackgroundTask

    calls = []

    class Body:
        def __aiter__(self):
            if own_cancel:
                raise asyncio.CancelledError("controlled body setup cancellation")
            raise RuntimeError("controlled body setup failure")

        async def aclose(self):
            calls.append("body")

    async def background():
        calls.append("background")

    async def handler(request):
        if calls:
            return await handle_invocation(request)
        return StreamingResponse(
            Body(), media_type="text/event-stream", background=BackgroundTask(background),
        )

    app = create_app(handler, configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        assert start(ws)["type"] == "session.ready"
        send_user(ws, "in_bad_body", "input")
        failed = receive_until(ws, "error")
        assert [event["type"] for event in failed] == ["response.created", "error"]
        assert failed[-1]["code"] == "generation_failed"
        assert calls == ["body", "background"]
        send_user(ws, "in_next", "retry")
        following = receive_until(ws, "response.done")
        assert not any(event["type"] == "error" for event in following)
        assert following[0]["in_reply_to"] == ["in_next"]
    assert calls == ["body", "background"]
    assert not app.state.voice_runtime._coordinator._detached_tasks


@pytest.mark.parametrize("behavior", ["cleanup_error", "swallow_cancel"])
def test_cancelled_handler_cannot_emit_after_replacement(behavior: str) -> None:
    waiting, closing, finished = (threading.Event() for _ in range(3))
    release = asyncio.Event()
    invocation_count = 0

    async def handler(request):
        nonlocal invocation_count
        invocation_count += 1
        if invocation_count > 1:
            return await handle_invocation(request)

        async def body():
            try:
                yield 'data: {"type":"token","content":"first"}\n\n'
                waiting.set()
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    if behavior == "swallow_cancel":
                        yield 'data: {"type":"token","content":"STALE"}\n\n'
                    else:
                        raise
            finally:
                closing.set()
                await release.wait()
                finished.set()
                if behavior == "cleanup_error":
                    raise RuntimeError("controlled cleanup failure")

        return StreamingResponse(body(), media_type="text/event-stream")

    app = create_app(handler, configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        try:
            assert start(ws)["type"] == "session.ready"
            send_user(ws, "in_old", "first")
            created = ws.receive_json()
            delta = ws.receive_json()
            assert created["type"] == "response.created"
            assert delta["type"] == "response.output_text.delta"
            assert waiting.wait(2)
            ws.send_json(frame(
                "user.barge_in", response_id=created["response_id"], heard_text="first",
            ))
            assert closing.wait(2)
            send_user(ws, "in_replacement", "second")
            replacement = receive_until(ws, "response.done")
            assert all(item.get("response_id") != created["response_id"] for item in replacement)
            assert not any(item["type"] == "error" for item in replacement)
            client.portal.call(release.set)
            assert finished.wait(2)
            # A further response must not be preceded by an old error or duplicate terminal.
            send_user(ws, "in_followup", "third")
            followup = receive_until(ws, "response.done")
            assert all(item.get("response_id") != created["response_id"] for item in followup)
            assert not any(item["type"] == "error" for item in followup)
        finally:
            client.portal.call(release.set)
    assert not app.state.voice_runtime._coordinator._detached_tasks
