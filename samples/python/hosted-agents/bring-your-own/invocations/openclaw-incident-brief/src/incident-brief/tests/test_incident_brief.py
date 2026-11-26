import asyncio
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from azure.ai.agentserver.core.tasks import TaskContext
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
