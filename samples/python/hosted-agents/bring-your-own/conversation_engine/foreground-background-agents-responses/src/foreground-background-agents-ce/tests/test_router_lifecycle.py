# Copyright (c) Microsoft. All rights reserved.

"""Test the actual async model stream, shared task completion and rejected admission."""

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from openai import AsyncOpenAI

from task_store import TaskStatus
from voice_runtime import Conversation, ResponseContextAdapter


@pytest.mark.parametrize("count", [0, 2])
async def test_router_rejects_non_single_tool_selection_without_partial_dispatch(
    logic, monkeypatch, count
):
    async def router(*_args, **_kwargs):
        for index in range(count):
            yield SimpleNamespace(type="response.output_item.done", item=SimpleNamespace(
                type="function_call", name="start_task" if index else "respond_directly",
                arguments=json.dumps({"message": "Hello.", "request_summary": "work"}),
            ))

    monkeypatch.setattr(logic, "_iter_llm_stream", router)
    conversation = Conversation()
    context = ResponseContextAdapter("r_count", "hello", [], conversation)
    events = []
    with pytest.raises(ValueError, match="exactly one"):
        async for event in logic.handler({"stream": True}, context, asyncio.Event()):
            events.append(event)
    assert not conversation.task_store._tasks
    assert not any(event["type"] in {"response.completed", "response.output_text.delta"}
                   for event in events)


async def test_router_request_disables_parallel_tools_through_real_openai_adapter(
    logic, monkeypatch
):
    requests = []

    async def transport(request):
        requests.append(json.loads(request.content))
        payload = {"id": "chat_single", "object": "chat.completion.chunk", "created": 0,
                   "model": "test-model", "choices": [{"index": 0, "finish_reason": "tool_calls",
                   "delta": {"tool_calls": [{"index": 0, "id": "call_one", "type": "function",
                   "function": {"name": "respond_directly",
                   "arguments": json.dumps({"message": "Hello."})}}]}}]}
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=(
            "data: " + json.dumps(payload) + "\n\ndata: [DONE]\n\n"
        ).encode())

    @asynccontextmanager
    async def router_client():
        async with AsyncOpenAI(api_key="local-test-only", base_url="https://example.invalid/v1",
                               http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)),
                               max_retries=0) as client:
            yield client

    monkeypatch.setattr(logic, "_router_client", router_client)
    context = ResponseContextAdapter("r_single", "hello", [], Conversation())
    events = [event async for event in logic.handler({"stream": True}, context, asyncio.Event())]
    assert requests[0]["parallel_tool_calls"] is False
    assert requests[0]["tool_choice"] == "required"
    assert events[-1]["type"] == "response.completed"


@pytest.fixture
def logic(monkeypatch):
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.invalid/api/projects/test")
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "test-model")
    import agent_logic

    return agent_logic


@pytest.mark.parametrize("cancel_during_read", [False, True])
async def test_repeated_model_cancellation_closes_upstream_and_allows_next_call(
    logic, monkeypatch, cancel_during_read
):
    bodies, clients, requests = [], [], []

    class Body(httpx.AsyncByteStream):
        def __init__(self):
            self.closed = False
            self.reading = asyncio.Event()

        async def __aiter__(self):
            payload = {"id": "chat_test", "object": "chat.completion.chunk", "created": 0,
                       "model": "test-model", "choices": [{"index": 0, "finish_reason": None,
                       "delta": {"content": "first"}}]}
            yield ("data: " + json.dumps(payload) + "\n\n").encode()
            self.reading.set()
            await asyncio.Future()

        async def aclose(self):
            self.closed = True

    async def transport(request):
        requests.append(json.loads(request.content))
        body = Body()
        bodies.append(body)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=body)

    @asynccontextmanager
    async def router_client():
        async with AsyncOpenAI(api_key="local-test-only", base_url="https://example.invalid/v1",
                               http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)),
                               max_retries=0) as client:
            clients.append(client)
            yield client

    monkeypatch.setattr(logic, "_router_client", router_client)
    for _ in range(5):
        source = logic._iter_llm_stream(None, "test-model", "instructions", [], None)
        try:
            assert (await asyncio.wait_for(anext(source), 2)).delta == "first"
            if cancel_during_read:
                pending = asyncio.create_task(anext(source))
                await asyncio.wait_for(bodies[-1].reading.wait(), 2)
                pending.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await pending
        finally:
            await source.aclose()
        assert bodies[-1].closed
        assert clients[-1].is_closed()
    assert len(requests) == 5
    assert all(request["model"] == "test-model" and request["stream"] for request in requests)


async def test_foundry_async_client_keeps_the_existing_project_endpoint_and_closes(logic):
    # Construct and close the real Foundry SDK clients without acquiring a token or sending I/O.
    async with logic._router_client() as client:
        assert isinstance(client, AsyncOpenAI)
        assert str(client.base_url).rstrip("/") == logic._endpoint.rstrip("/") + "/openai/v1"
    assert client.is_closed()


@pytest.mark.parametrize("fail", [False, True])
async def test_model_request_creation_cancellation_or_error_closes_client(logic, monkeypatch, fail):
    entered = asyncio.Event()
    clients = []

    async def transport(_request):
        entered.set()
        if fail:
            return httpx.Response(500, json={"error": {"message": "controlled failure"}})
        await asyncio.Future()

    @asynccontextmanager
    async def router_client():
        async with AsyncOpenAI(api_key="local-test-only", base_url="https://example.invalid/v1",
                               http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)),
                               max_retries=0) as client:
            clients.append(client)
            yield client

    monkeypatch.setattr(logic, "_router_client", router_client)
    source = logic._iter_llm_stream(None, "test-model", None, [], None)
    request = asyncio.create_task(anext(source))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        if fail:
            from openai import APIStatusError

            with pytest.raises(APIStatusError):
                await asyncio.wait_for(request, 2)
        else:
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
        assert clients[0].is_closed()
    finally:
        if not request.done():
            request.cancel()
        await asyncio.gather(request, return_exceptions=True)
        await source.aclose()


async def test_tool_call_fragments_and_required_choice_survive_async_migration(logic, monkeypatch):
    requests, clients = [], []
    arguments = json.dumps({"request_summary": "Quincy North", "ack_message": "On it."})
    chunks = [
        {"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {
            "name": "start_", "arguments": arguments[:10]}}]},
        {"tool_calls": [{"index": 0, "function": {
            "name": "task", "arguments": arguments[10:]}}]},
    ]
    raw = "".join("data: " + json.dumps({
        "id": "chat_test", "object": "chat.completion.chunk", "created": 0,
        "model": "test-model", "choices": [{"index": 0, "delta": delta,
        "finish_reason": "tool_calls" if i == 1 else None}],
    }) + "\n\n" for i, delta in enumerate(chunks)) + "data: [DONE]\n\n"

    async def transport(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=raw)

    @asynccontextmanager
    async def router_client():
        async with AsyncOpenAI(api_key="local-test-only", base_url="https://example.invalid/v1",
                               http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)),
                               max_retries=0) as client:
            clients.append(client)
            yield client

    monkeypatch.setattr(logic, "_router_client", router_client)
    events = [event async for event in logic._iter_llm_stream(
        None, "test-model", "instructions", [{"role": "user", "content": "query"}],
        logic.ROUTER_TOOLS, tool_choice="required",
    )]
    assert len(events) == 1
    assert events[0].item.name == "start_task"
    assert events[0].item.arguments == arguments
    assert events[0].item.call_id == "call_1"
    assert requests[0]["tool_choice"] == "required"
    assert requests[0]["tools"][0]["type"] == "function"
    assert requests[0]["messages"][0] == {"role": "system", "content": "instructions"}
    assert clients[0].is_closed()


async def test_overlapping_waiters_finish_and_only_one_claims_completed_result(logic, monkeypatch):
    conversation = Conversation()
    task = conversation.task_store.create_task("A")
    task.status = TaskStatus.RUNNING
    polling = asyncio.Queue()
    release = asyncio.Event()

    async def sleep(_delay):
        await polling.put(True)
        await release.wait()

    async def router(*_args, **_kwargs):
        yield SimpleNamespace(type="response.output_item.done", item=SimpleNamespace(
            type="function_call", name="respond_directly", arguments={"message": "ack"}
        ))

    monkeypatch.setattr(logic, "_iter_llm_stream", router)
    monkeypatch.setattr(logic, "asyncio", SimpleNamespace(**(vars(asyncio) | {"sleep": sleep})))

    async def consume(response_id):
        context = ResponseContextAdapter(response_id, "hello", [], conversation)
        events = [event async for event in logic.handler(
            {"stream": True}, context, asyncio.Event()
        )]
        # This unit consumer explicitly acknowledges delivery; real SDK tests exercise send failure.
        context.text_sent("".join(event.get("delta", "") for event in events))
        context.completed()
        context.stopped()
        return events

    responses = [asyncio.create_task(consume(f"r_{i}")) for i in range(2)]
    try:
        await asyncio.wait_for(polling.get(), 2)
        await asyncio.wait_for(polling.get(), 2)
        task.result, task.status = "unique result", TaskStatus.COMPLETED
        release.set()
        events = await asyncio.wait_for(asyncio.gather(*responses), 2)
        assert all(stream[-1]["type"] == "response.completed" for stream in events)
        outputs = ["".join(e.get("delta", "") for e in stream) for stream in events]
        assert sum("unique result" in output for output in outputs) == 1
        assert task.status is TaskStatus.DELIVERED
    finally:
        for response in responses:
            if not response.done():
                response.cancel()
        await asyncio.gather(*responses, return_exceptions=True)


@pytest.mark.parametrize("query", ["A", "unrelated B"])
async def test_rejected_new_task_is_not_acknowledged_or_given_another_tasks_result(
    logic, monkeypatch, query
):
    conversation = Conversation()
    existing = conversation.task_store.create_task("A")
    existing.status, existing.result = TaskStatus.RUNNING, "private A result"

    async def router(*_args, **_kwargs):
        yield SimpleNamespace(type="response.output_item.done", item=SimpleNamespace(
            type="function_call", name="start_task",
            arguments={"request_summary": query, "ack_message": "Started the requested work."},
        ))

    async def unexpected_worker(*_args):
        pytest.fail("A rejected request must not start a worker")

    monkeypatch.setattr(logic, "_iter_llm_stream", router)
    monkeypatch.setattr(logic, "run_worker", unexpected_worker)
    context = ResponseContextAdapter("r_rejected", query, [], conversation)

    async def consume():
        return [e async for e in logic.handler({"stream": True}, context, asyncio.Event())]

    events = await asyncio.wait_for(consume(), 2)
    output = "".join(e.get("delta", "") for e in events)
    assert "haven't started a new task" in output
    assert "Started the requested work" not in output
    assert "private A result" not in output
    assert events[-1]["type"] == "response.completed"
    assert conversation.task_store.active_tasks() == [existing]
    assert not conversation.background_tasks
