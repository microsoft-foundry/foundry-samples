"""Exercise the default echo entry point without model configuration or calls."""

import pytest
from starlette.testclient import TestClient
from test_voice_runtime import frame, receive_type, receive_until, send_user, start

from main import create_app


@pytest.fixture
def no_model(monkeypatch):
    for name in (
        "FOUNDRY_PROJECT_ENDPOINT",
        "AZURE_AI_MODEL_DEPLOYMENT_NAME",
        "AZURE_OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("Echo must not construct a model client")

    monkeypatch.setattr("model_client.AzureOpenAIResponsesClient.from_environment", forbidden)


@pytest.mark.parametrize(
    "text",
    ["Hello echo", "你好，echo 👋", "  trimmed input  ", "x" * 8000],
    ids=["ascii", "unicode", "legacy-normalization", "input-limit-stream"],
)
def test_default_app_echoes_input_without_a_model_and_accepts_next_turn(no_model, text):
    app = create_app(configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/invocations_ws") as ws:
        assert start(ws)["type"] == "session.ready"
        for index, value in enumerate((text, "second turn")):
            send_user(ws, f"in_{index}", value)
            frames = receive_until(ws, "response.done")
            expected = value.strip()
            assert frames[0]["in_reply_to"] == [f"in_{index}"]
            assert "".join(
                f["delta"] for f in frames if f["type"] == "response.output_text.delta"
            ) == (expected)
            assert frames[-2]["text"] == expected
            assert sum(f["type"] == "response.done" for f in frames) == 1
            assert not any(f["type"] == "error" for f in frames)
        ws.send_json(frame("session.end", reason="test_complete"))
    assert not app.state.voice_runtime._coordinator._detached_tasks


@pytest.mark.parametrize("command", ["/stream", "/done", "/voice"])
def test_echo_commands_keep_output_modes(no_model, command):
    app = create_app(configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/invocations_ws") as ws:
        start(ws)
        send_user(ws, "in_command", f"{command} 你好 echo")
        frames = receive_until(ws, "response.done")
        assert frames[-2]["text"] == "你好 echo"
        deltas = [f for f in frames if f["type"] == "response.output_text.delta"]
        assert bool(deltas) is (command == "/stream")
        if command == "/voice":
            assert frames[-2]["voice"] == {"rate": "+10%"}


def test_proactive_echo_still_requires_acceptance(no_model):
    app = create_app(configure_observability=None)
    with TestClient(app) as client, client.websocket_connect("/invocations_ws") as ws:
        start(ws)
        send_user(ws, "in_proactive", "/proactive check in")
        assert ws.receive_json()["type"] == "response.none"
        created = ws.receive_json()
        assert created["type"] == "response.created"
        assert "in_reply_to" not in created
        ws.send_json(frame("response.accepted", response_id=created["response_id"]))
        frames = receive_until(ws, "response.done")
        assert frames[-2]["text"] == "check in"
        assert all(f["response_id"] == created["response_id"] for f in frames)
        send_user(ws, "in_next", "after proactive")
        assert receive_until(ws, "response.done")[-2]["text"] == "after proactive"


def test_rejected_handshake_and_oversized_input_still_do_not_echo(no_model):
    app = create_app(configure_observability=None)
    with TestClient(app) as client:
        with client.websocket_connect("/invocations_ws") as ws:
            assert start(ws, "2.0")["type"] == "session.rejected"
        with client.websocket_connect("/invocations_ws") as ws:
            start(ws)
            send_user(ws, "in_large", "x" * 8001)
            assert receive_type(ws, "response.none")["reason"] == "input_too_large"
            send_user(ws, "in_valid", "valid")
            assert receive_until(ws, "response.done")[-2]["text"] == "valid"
