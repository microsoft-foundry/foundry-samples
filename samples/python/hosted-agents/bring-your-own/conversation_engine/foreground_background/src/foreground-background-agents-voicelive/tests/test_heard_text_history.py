"""Playback correction preserves actual heard output and subsequent model context."""

import asyncio
from types import SimpleNamespace

import pytest
from azure.ai.agentserver.invocations.voice import (
    InputTextPart,
    ResponseDone,
    ResponseOutputTextDone,
)
from starlette.testclient import TestClient
from test_conversation_engine import (
    Chat,
    RecordingSession,
    Responses,
    answer,
    frame,
    output,
    send,
    start,
    tool,
    until,
    wait_for_server,
)

from agent_logic import Conversation, ForegroundBackgroundAgent, HistoryEntry, Turn
from conversation_runtime import ConversationRuntime, HistorySession, create_app
from task_store import TaskStatus


@pytest.mark.parametrize("event_kind", ["user.barge_in", "response.cancelled"])
@pytest.mark.parametrize(
    "heard_size", [0, 8000, 8011], ids=["unheard", "input-boundary", "full-reply"]
)
@pytest.mark.parametrize("unit", ["x", "界"], ids=["ascii", "unicode"])
def test_real_sdk_retains_complete_heard_worker_reply_then_accepts_next_turn(
    event_kind: str,
    heard_size: int,
    unit: str,
) -> None:
    marker = "FINAL_HEARD_STEP"
    result = unit * (8000 - len(marker)) + marker
    chat = Chat(
        tool("start_task", request_summary="Find panels", ack_message="Checking."),
        tool("respond_directly", message="Next."),
        tool("respond_directly", message="Finished."),
    )
    agent = ForegroundBackgroundAgent(chat, Responses(answer(result)), "test")
    app = create_app(agent, configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/voice_conversation_engine") as ws:
        start(ws)
        send(ws, "in_work", "Find panels")
        frames = until(ws)
        spoken = output(frames)
        assert spoken == "Checking.\n\n" + result and len(spoken) == 8011
        response_id = frames[0]["response_id"]
        runtime = app.state.voice_runtime
        session = next(iter(runtime.conversations))
        conversation = runtime.conversations[session]
        state = runtime._state_for(session)
        task = conversation.tasks.get("latest")
        wait_for_server(client, lambda: task.status is TaskStatus.DELIVERED)
        heard = spoken[:heard_size]
        ws.send_json(frame(event_kind, response_id=response_id, heard_text=heard))
        # A larger playback budget must not relax ordinary user-input admission.
        send(ws, "in_oversized", "x" * 8001)
        declined = until(ws, "response.none")
        assert declined[-1]["reason"] == "input_too_large"
        assert len(chat.requests) == 1
        send(ws, "in_next", "Continue")
        replacement = until(ws)
        assert output(replacement) == "Next."
        assert replacement[0]["in_reply_to"] == ["in_next"]
        assert all(f.get("response_id") != response_id for f in replacement)
        assert state.heard_text_by_response[response_id] == heard
        assert (
            next(e.content for e in conversation.history if e.response_id == response_id) == heard
        )
        assistants = [
            m["content"] for m in chat.requests[1]["messages"] if m["role"] == "assistant"
        ]
        assert assistants == ([heard] if heard else [])
        if heard_size == 8011:
            assert marker in assistants[0]
        assert task.status is TaskStatus.DELIVERED
        # A repeated correction can clear the entry; it must not resurrect old output.
        ws.send_json(frame(event_kind, response_id=response_id, heard_text=""))
        send(ws, "in_later", "Continue again")
        assert output(until(ws)) == "Finished."
        assert state.heard_text_by_response[response_id] == ""
        assert spoken not in repr(chat.requests[2]["messages"])
        ws.send_json(frame("session.end", reason="test_complete"))
        wait_for_server(
            client, lambda: not state.heard_text_by_response and not runtime.conversations
        )
    assert not agent.workers
    assert not app.state.voice_runtime._coordinator._detached_tasks


@pytest.mark.parametrize("callback", ["on_user_barge_in", "on_response_cancelled"])
async def test_long_heard_prefix_during_first_send_survives_cancellation(callback: str) -> None:
    entered, finished, gate = asyncio.Event(), asyncio.Event(), asyncio.Event()
    heard = "界" * 8011
    sent = []

    class GatedSession(RecordingSession):
        async def send(self, message):
            if isinstance(message, ResponseOutputTextDone) and not entered.is_set():
                entered.set()
                await gate.wait()
            sent.append(message)
            if isinstance(message, ResponseDone):
                finished.set()

    agent = ForegroundBackgroundAgent(
        Chat(tool("respond_directly", message="Replacement")), Responses(), "test"
    )
    runtime = ConversationRuntime(agent)
    session = GatedSession()
    state = runtime._store.get_or_create(session)
    state.try_begin_start()
    state.activate()
    conversation = Conversation()
    runtime.conversations[session] = conversation
    turn = Turn("r_pending")
    try:
        runtime._coordinator.start_response(
            HistorySession(session, state, conversation, turn),
            state,
            "in_original",
            text=heard,
            streaming=False,
            response_id=turn.response_id,
        )
        await asyncio.wait_for(entered.wait(), 1)
        await getattr(runtime, callback)(
            session,
            SimpleNamespace(response_id=turn.response_id, heard_text=heard),
        )
        await runtime.on_user_message(
            session,
            SimpleNamespace(
                item_id="in_replacement",
                content=[InputTextPart(text="Continue")],
            ),
        )
        await asyncio.wait_for(finished.wait(), 1)
        assistants = [
            m["content"] for m in agent.chat.requests[0]["messages"] if m["role"] == "assistant"
        ]
        assert assistants == [heard]
        assert state.heard_text_by_response[turn.response_id] == heard
        assert sum(e.response_id == turn.response_id for e in conversation.history) == 1
        assert not any(
            isinstance(m, ResponseDone) and m.response_id == turn.response_id for m in sent
        )
    finally:
        gate.set()
        await runtime.close()
    assert not state.heard_text_by_response and not agent.workers


async def test_oversized_heard_text_uses_same_bounded_value_for_history_and_playback() -> None:
    agent = ForegroundBackgroundAgent(Chat(), Responses(), "test")
    runtime = ConversationRuntime(agent)
    session = RecordingSession()
    state = runtime._store.get_or_create(session)
    state.try_begin_start()
    state.activate()
    state.track_response("r_known")
    conversation = Conversation()
    conversation.history.append(HistoryEntry("assistant", "sent prefix", "r_known"))
    runtime.conversations[session] = conversation
    prefix = "x" * (512 * 1024 - 1)
    try:
        await runtime.on_user_barge_in(
            session,
            SimpleNamespace(
                response_id="r_known",
                heard_text=prefix + "👋",
            ),
        )
        assert len(conversation.history[0].content) == len(prefix)
        assert conversation.history[0].content == state.heard_text_by_response["r_known"] == prefix
        await runtime.on_response_cancelled(
            session,
            SimpleNamespace(
                response_id="r_unknown",
                heard_text="must not be inserted",
            ),
        )
        assert len(conversation.history) == 1 and len(state.heard_text_by_response) == 1
    finally:
        await runtime.close()
