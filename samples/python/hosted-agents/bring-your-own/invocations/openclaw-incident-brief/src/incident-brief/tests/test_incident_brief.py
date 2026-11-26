import asyncio
import hashlib
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from azure.ai.agentserver.core.tasks import TaskContext, TaskDeferred, TaskFailed
from azure.ai.agentserver.invocations import InvocationAgentServerHost

with patch(
    "azure.ai.agentserver.invocations.InvocationAgentServerHost",
    lambda: InvocationAgentServerHost(configure_observability=None),
):
    import main


@pytest_asyncio.fixture
async def client(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTSERVER_STATE_ROOT", str(tmp_path))
    monkeypatch.delenv("FOUNDRY_HOSTING_ENVIRONMENT", raising=False)
    async with main.app.router.lifespan_context(main.app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://agent"
        ) as client:
            yield client
        if main._observers:
            await asyncio.gather(*list(main._observers))


async def test_retries_share_a_job_and_each_platform_invocation_can_retrieve_it(
    client, monkeypatch
):
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def make_brief(ctx):
        calls.append(ctx.input["updates"])
        started.set()
        await release.wait()
        return "Impact: checkout errors. Priority: investigate the rollout."

    monkeypatch.setattr(main, "make_brief", make_brief)
    params = {"agent_session_id": "incident-session"}
    body = {"request_id": "INC-42-rev1", "updates": "12:01 UTC: checkout errors increased."}
    try:
        first = await client.post("/invocations", params=params, json=body)
        assert first.status_code == 202
        await asyncio.wait_for(started.wait(), timeout=10)

        retry = await client.post("/invocations", params=params, json=body)
        assert retry.status_code == 202
        first_data, retry_data = first.json(), retry.json()
        assert first_data["job_id"] == retry_data["job_id"]
        assert first_data["invocation_id"] != retry_data["invocation_id"]
        assert first_data["invocation_id"] == first.headers["x-agent-invocation-id"]
        assert retry_data["invocation_id"] == retry.headers["x-agent-invocation-id"]

        conflict = await client.post(
            "/invocations", params=params, json={**body, "updates": "A different update."}
        )
        assert conflict.status_code == 409
        for data in (first_data, retry_data):
            pending = await client.get(f"/invocations/{data['invocation_id']}", params=params)
            assert pending.json()["status"] == "pending"
        other_session = await client.get(
            f"/invocations/{first_data['invocation_id']}",
            params={"agent_session_id": "another-session"},
        )
        assert other_session.status_code == 404

        release.set()
        if main._observers:
            await asyncio.wait_for(asyncio.gather(*list(main._observers)), timeout=10)
        for data in (first_data, retry_data):
            completed = await client.get(f"/invocations/{data['invocation_id']}", params=params)
            assert completed.status_code == 200
            assert completed.json()["status"] == "completed"
            assert "checkout errors" in completed.json()["brief"]

        completed_retry = await client.post("/invocations", params=params, json=body)
        assert completed_retry.json()["status"] == "completed"
        assert len(calls) == 1
    finally:
        release.set()


async def test_model_failure_is_visible_as_failed_status(client, monkeypatch):
    async def fail(_ctx):
        raise ValueError("model failed")

    monkeypatch.setattr(main, "make_brief", fail)
    params = {"agent_session_id": "failure-session"}
    response = await client.post(
        "/invocations", params=params, json={"request_id": "failed", "updates": "An update."}
    )
    assert response.status_code == 202
    if main._observers:
        await asyncio.wait_for(asyncio.gather(*list(main._observers)), timeout=10)
    result = await client.get(f"/invocations/{response.json()['invocation_id']}", params=params)
    assert result.json()["status"] == "failed"
    assert "error" in result.json()
    assert "brief" not in result.json()


@pytest.mark.parametrize(
    "content",
    [b"not-json", b"\xff", b"[]", b'{"request_id":"bad space","updates":"ok"}'],
)
async def test_invalid_input_is_rejected(client, content):
    response = await client.post(
        "/invocations?agent_session_id=test-session",
        content=content,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400


async def test_hosted_session_mismatch_is_rejected(client, monkeypatch):
    monkeypatch.setenv("FOUNDRY_HOSTING_ENVIRONMENT", "hosted")
    monkeypatch.setenv("FOUNDRY_AGENT_SESSION_ID", "actual-session")
    response = await client.post(
        "/invocations?agent_session_id=other-session",
        json={"request_id": "id", "updates": "Update."},
    )
    assert response.status_code == 400


async def test_cancellation_stops_the_in_flight_model_call():
    started, closed = asyncio.Event(), asyncio.Event()

    class Responses:
        async def create(self, **_kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                closed.set()

    class Client:
        responses = Responses()

    ctx = TaskContext(task_id="task", session_id="session", input={})
    task = asyncio.create_task(main.call_model(ctx, Client(), "model", "instructions", "input"))
    await asyncio.wait_for(started.wait(), timeout=10)
    ctx.cancel.set()
    with pytest.raises(main.TaskInterrupted):
        await asyncio.wait_for(task, timeout=10)
    assert closed.is_set()


@pytest.mark.parametrize("status", ["incomplete", "failed", "cancelled"])
async def test_partial_model_output_is_not_accepted(status):
    async def create(**_kwargs):
        return SimpleNamespace(status=status, output_text="An unfinished brief.")

    ctx = TaskContext(task_id="partial", session_id="session", input={})
    model = SimpleNamespace(responses=SimpleNamespace(create=create))
    with pytest.raises(ValueError, match="did not complete"):
        await main.call_model(ctx, model, "model", "instructions", "input")


async def test_completed_model_output_is_accepted():
    async def create(**_kwargs):
        return SimpleNamespace(status="completed", output_text="Impact: checkout errors.")

    ctx = TaskContext(task_id="complete", session_id="session", input={})
    model = SimpleNamespace(responses=SimpleNamespace(create=create))
    result = await main.call_model(ctx, model, "model", "instructions", "input")
    assert result == "Impact: checkout errors."


async def reserve_job(session_id, request_id, updates):
    brief_id = main.job_id(session_id, request_id)
    async with main.open_store() as store:
        record = await store.create_item(
            main.job_key(session_id, brief_id),
            {"fingerprint": hashlib.sha256(updates.encode()).hexdigest(), "status": "pending"},
        )
        await store.create_item(
            main.invocation_key(session_id, "seeded-invocation"), {"job_id": brief_id}
        )
    return brief_id, record.created_at


async def test_shutdown_deferral_leaves_the_job_available_for_recovery(client, monkeypatch):
    session_id = "shutdown-session"
    updates = "Checkout errors increased."
    brief_id, created_at = await reserve_job(session_id, "shutdown", updates)
    monkeypatch.setattr(main, "time", lambda: created_at)

    async def interrupted(ctx):
        ctx.shutdown.set()
        raise main.TaskInterrupted()

    monkeypatch.setattr(main, "make_brief", interrupted)
    run = await main.prepare_brief.start(
        task_id=brief_id,
        input={"session_id": session_id, "job_id": brief_id, "updates": updates, "call_id": "test"},
    )
    with pytest.raises(TaskDeferred):
        await asyncio.wait_for(run.result(), timeout=10)
    result = await client.get(
        "/invocations/seeded-invocation", params={"agent_session_id": session_id}
    )
    assert result.json()["status"] == "pending"
    assert "error" not in result.json()


@pytest.mark.parametrize("operation", ["get_or_create", "get_item", "set_item"])
async def test_worker_persists_storage_failure_without_an_observer(client, monkeypatch, operation):
    session_id = "storage-failure"
    updates = "Checkout errors increased."
    brief_id, _ = await reserve_job(session_id, operation, updates)

    async def make_brief(_ctx):
        return "Impact: checkout errors."

    monkeypatch.setattr(main, "make_brief", make_brief)
    original = getattr(main.FoundryStateStore, operation)
    failed = False

    async def fail_once(*args, **kwargs):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("State storage is unavailable")
        return await original(*args, **kwargs)

    replacement = staticmethod(fail_once) if operation == "get_or_create" else fail_once
    monkeypatch.setattr(main.FoundryStateStore, operation, replacement)
    run = await main.prepare_brief.start(
        task_id=brief_id,
        input={"session_id": session_id, "job_id": brief_id, "updates": updates, "call_id": "test"},
    )
    with pytest.raises(TaskFailed):
        await asyncio.wait_for(run.result(), timeout=10)
    async with main.open_store() as store:
        record = await store.get_item(main.job_key(session_id, brief_id))
        assert record.value["status"] == "failed"
        assert "brief" not in record.value

    result = await client.get(
        "/invocations/seeded-invocation", params={"agent_session_id": session_id}
    )
    assert result.json()["status"] == "failed"
    assert "error" in result.json()


async def test_polling_reconciles_a_failure_that_could_not_be_persisted(client, monkeypatch):
    session_id = "storage-outage"
    updates = "Checkout errors increased."
    brief_id, created_at = await reserve_job(session_id, "outage", updates)
    original = main.FoundryStateStore.get_item

    async def unavailable(*_args, **_kwargs):
        raise OSError("State storage is unavailable")

    monkeypatch.setattr(main.FoundryStateStore, "get_item", unavailable)
    run = await main.prepare_brief.start(
        task_id=brief_id,
        input={"session_id": session_id, "job_id": brief_id, "updates": updates, "call_id": "test"},
    )
    with pytest.raises(TaskFailed):
        await asyncio.wait_for(run.result(), timeout=10)
    monkeypatch.setattr(main.FoundryStateStore, "get_item", original)
    params = {"agent_session_id": session_id}
    monkeypatch.setattr(main, "time", lambda: created_at + main.JOB_TIMEOUT_SECONDS - 1)
    pending = await client.get("/invocations/seeded-invocation", params=params)
    assert pending.json()["status"] == "pending"

    monkeypatch.setattr(main, "time", lambda: created_at + main.JOB_TIMEOUT_SECONDS)
    failed = await client.get("/invocations/seeded-invocation", params=params)
    assert failed.json()["status"] == "failed"
    assert "brief" not in failed.json()
    retry = await client.post(
        "/invocations", params=params, json={"request_id": "outage", "updates": updates}
    )
    assert retry.json()["status"] == "failed"


async def test_late_model_output_cannot_complete_an_expired_job(client, monkeypatch):
    started, release = asyncio.Event(), asyncio.Event()

    async def make_brief(_ctx):
        started.set()
        await release.wait()
        return "Impact: checkout errors."

    monkeypatch.setattr(main, "make_brief", make_brief)
    params = {"agent_session_id": "expired-session"}
    try:
        response = await client.post(
            "/invocations", params=params, json={"request_id": "expired", "updates": "Update."}
        )
        await asyncio.wait_for(started.wait(), timeout=10)
        async with main.open_store() as store:
            record = await store.get_item(
                main.job_key("expired-session", response.json()["job_id"])
            )
        monkeypatch.setattr(main, "time", lambda: record.created_at + main.JOB_TIMEOUT_SECONDS)
        release.set()
        await asyncio.wait_for(asyncio.gather(*list(main._observers)), timeout=10)
        result = await client.get(
            f"/invocations/{response.json()['invocation_id']}", params=params
        )
        assert result.json()["status"] == "failed"
        assert "brief" not in result.json()
    finally:
        release.set()


@pytest.mark.parametrize(
    "competing_status, expected_status, expected_brief",
    [
        ("pending", "completed", "The losing brief."),
        ("completed", "completed", "The winning brief."),
        ("failed", "failed", None),
    ],
)
async def test_terminal_transition_rereads_after_a_real_etag_conflict(
    client, monkeypatch, competing_status, expected_status, expected_brief
):
    brief_id, _ = await reserve_job("conflict-session", "conflict", "Update.")
    key = main.job_key("conflict-session", brief_id)
    original = main.FoundryStateStore.set_item
    conflicted = False

    async def competing_write(store, item_key, value, **kwargs):
        nonlocal conflicted
        if not conflicted:
            conflicted = True
            competing = {"fingerprint": "another-etag", "status": competing_status}
            if competing_status == "completed":
                competing["brief"] = "The winning brief."
            elif competing_status == "failed":
                competing["error"] = "The winning failure."
            await original(store, item_key, competing)
        return await original(store, item_key, value, **kwargs)

    monkeypatch.setattr(main.FoundryStateStore, "set_item", competing_write)
    async with main.open_store() as store:
        await main.set_terminal(store, key, "completed", brief="The losing brief.")
        record = await store.get_item(key)
    assert record.value["status"] == expected_status
    assert record.value.get("brief") == expected_brief
