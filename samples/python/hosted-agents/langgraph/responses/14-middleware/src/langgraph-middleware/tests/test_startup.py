"""Verify real startup resource ownership on exit, failure, and cancellation."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from langchain_azure_ai.agents.hosting import FoundryCheckpointSaver
from langchain_openai import ChatOpenAI
import main as startup
import pytest


@pytest.mark.parametrize("outcome", ["normal", "initialization-error", "cancelled"])
def test_main_closes_owned_resources(
    outcome: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = []
    resources = {}
    original_build_agent = startup.build_agent

    @contextmanager
    def track(resource, name):
        resources[name] = resource
        try:
            with resource as opened:
                events.append(f"{name}:entered")
                yield opened
        finally:
            events.append(f"{name}:exited")

    def open_project(**arguments):
        project = AIProjectClient(**arguments)
        original_openai = project.get_openai_client

        def open_endpoint_client():
            return track(original_openai(), "endpoint")

        monkeypatch.setattr(project, "get_openai_client", open_endpoint_client)
        return track(project, "project")

    def open_model(**arguments):
        model = ChatOpenAI(**arguments)
        resources["model"] = model
        return model

    @asynccontextmanager
    async def open_checkpointer():
        saver = FoundryCheckpointSaver()
        resources["checkpointer"] = saver
        try:
            async with saver:
                events.append("checkpointer:entered")
                yield saver
        finally:
            events.append("checkpointer:exited")

    def build_graph(model, saver):
        if outcome == "initialization-error":
            raise RuntimeError("graph initialization failed")
        return original_build_agent(model, saver)

    async def exercise():
        entered_host = asyncio.Event()

        async def run_host(host, *, port):
            assert port == 8088
            entered_host.set()
            if outcome == "cancelled":
                await asyncio.Future()

        monkeypatch.setattr(startup.ResponsesHostServer, "run_async", run_host)
        if outcome == "cancelled":
            task = asyncio.create_task(startup.main())
            try:
                await asyncio.wait_for(entered_host.wait(), timeout=20)
            finally:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        elif outcome == "initialization-error":
            with pytest.raises(RuntimeError, match="graph initialization failed"):
                await startup.main()
            assert not entered_host.is_set()
        else:
            await startup.main()
            assert entered_host.is_set()

    monkeypatch.setenv(
        "FOUNDRY_PROJECT_ENDPOINT",
        "https://example.services.ai.azure.com/api/projects/test",
    )
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "test-deployment")
    monkeypatch.setenv("PORT", "8088")
    monkeypatch.setattr(startup, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        startup,
        "DefaultAzureCredential",
        lambda: track(DefaultAzureCredential(), "credential"),
    )
    monkeypatch.setattr(startup, "AIProjectClient", open_project)
    monkeypatch.setattr(startup, "ChatOpenAI", open_model)
    monkeypatch.setattr(startup, "FoundryCheckpointSaver", open_checkpointer)
    monkeypatch.setattr(startup, "build_agent", build_graph)
    asyncio.run(exercise())
    assert events == [
        "credential:entered",
        "project:entered",
        "endpoint:entered",
        "endpoint:exited",
        "project:exited",
        "checkpointer:entered",
        "checkpointer:exited",
        "credential:exited",
    ]
    assert resources["endpoint"].is_closed()
    assert resources["model"].root_client.is_closed()
    assert resources["model"].root_async_client.is_closed()
    assert not resources["checkpointer"]._owns_credential
