import re
import tomllib
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

import client


@pytest.mark.asyncio
async def test_session_evidence_correlates_completed_delegation():
    evidence = client.SessionEvidence()
    transcript = object()
    connection = object()
    events = [
        SimpleNamespace(type="session.input_transcript.delta", delta="He go."),
        SimpleNamespace(type="session.output_transcript.delta", delta="He goes."),
        SimpleNamespace(type="session.output_audio.delta", delta="AAAA"),
        SimpleNamespace(
            type="session.delegation.created",
            delegation=SimpleNamespace(id="d1"),
        ),
        SimpleNamespace(
            type="response.event",
            delegation_id="d1",
            event={"type": "response.output_text.delta", "delta": "Use goes."},
        ),
        SimpleNamespace(
            type="response.event",
            delegation_id="d1",
            event={"type": "response.completed"},
        ),
        SimpleNamespace(type="session.closed"),
    ]
    for event in events:
        await evidence.observe(connection, event, transcript)
    result = evidence.result()
    assert result["input_transcript"] == "He go."
    assert result["output_transcript"] == "He goes."
    assert result["output_audio_base64_chars"] == 4
    assert result["correlated_completed_delegations"] == ["d1"]
    assert result["backend_text"]["d1"] == "Use goes."
    assert result["closed"] is True


@pytest.mark.asyncio
async def test_session_evidence_does_not_correlate_other_response():
    evidence = client.SessionEvidence(delegation_ids=["d1"])
    event = SimpleNamespace(
        type="response.event",
        delegation_id="other",
        event={"type": "response.completed"},
    )
    await evidence.observe(object(), event, object())
    assert evidence.result()["correlated_completed_delegations"] == []


def test_project_endpoint_normalizes_and_rejects_unsafe_values(monkeypatch):
    monkeypatch.setenv(
        "FOUNDRY_PROJECT_ENDPOINT",
        "https://example.services.ai.azure.com/api/projects/project/",
    )
    assert client.project_endpoint() == (
        "https://example.services.ai.azure.com/api/projects/project"
    )
    monkeypatch.setenv(
        "FOUNDRY_PROJECT_ENDPOINT",
        "https://user:secret@example.test/api/projects/project",
    )
    with pytest.raises(client.DemoError):
        client.project_endpoint()


def test_required_rejects_blank(monkeypatch):
    monkeypatch.setenv("AGENT_NAME", "   ")
    with pytest.raises(client.DemoError):
        client.required("AGENT_NAME")


def test_agent_client_does_not_own_agent_lifecycle():
    source = open(client.__file__, encoding="utf-8").read()
    assert "http.post(" not in source
    assert "http.delete(" not in source


@pytest.mark.parametrize(
    ("status", "code", "message", "hint"),
    [
        (400, "InvalidRequest", "Bad model setting", "request and service"),
        (403, "Forbidden", "Access denied", "project permissions"),
        (429, "RateLimitExceeded", "Try later", "quota is exhausted"),
    ],
)
def test_http_errors_include_safe_structured_diagnostics(status, code, message, hint):
    response = httpx.Response(
        status,
        json={"error": {"code": code, "message": message}},
        headers={"x-request-id": "request-123"},
    )
    with pytest.raises(client.DemoError) as raised:
        client.check_response(response, "Read agent")
    detail = str(raised.value)
    assert f"HTTP {status}" in detail
    assert f"code={code}" in detail
    assert f"message={message}" in detail
    assert "request_id=request-123" in detail
    assert hint in detail


def test_http_error_sanitizes_secrets_and_payloads():
    response = httpx.Response(
        400,
        json={
            "error": {
                "code": "BadRequest",
                "message": (
                    "authorization=Bearer top-secret "
                    '"api_key":"json-secret" '
                    "url=https://example.test/path?sig=query-secret "
                    'payload="full request content" audio=UklGRmFrZQ=='
                ),
            }
        },
        headers={"x-ms-request-id": "safe-request-id"},
    )
    detail = client.format_http_error(response, "Connect")
    assert "top-secret" not in detail
    assert "query-secret" not in detail
    assert "json-secret" not in detail
    assert "full request content" not in detail
    assert "UklGRmFrZQ" not in detail
    assert detail.count("[REDACTED]") >= 3
    assert "safe-request-id" in detail


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError(
            "TLS handshake timed out for wss://example.test/live?token=secret"
        ),
        ConnectionError("WebSocket handshake rejected; request_id=req-7"),
    ],
)
def test_unexpected_errors_keep_sanitized_handshake_context(error):
    detail = client.format_unexpected_error(error)
    assert type(error).__name__ in detail
    assert "handshake" in detail
    assert "secret" not in detail


def test_unexpected_http_error_uses_structured_body_not_raw_exception_payload():
    response = httpx.Response(
        403,
        json={"error": {"code": "Forbidden", "message": "Denied token=secret"}},
        headers={"x-request-id": "request-403"},
    )
    error = SimpleNamespace(
        response=response,
        status_code=403,
        __str__=lambda: 'raw body={"audio":"raw-audio", "token":"secret"}',
    )
    detail = client.format_unexpected_error(error)
    assert "code=Forbidden" in detail
    assert "message=Denied token=[REDACTED]" in detail
    assert "request_id=request-403" in detail
    assert "raw-audio" not in detail
    assert "secret" not in detail


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"error": "Preview gate is disabled"}, "Preview gate is disabled"),
        (
            {"error": {"code": "Forbidden"}, "message": "Preview disabled"},
            "Preview disabled",
        ),
        ("Handshake rejected", "Handshake rejected"),
    ],
)
def test_http_error_preserves_safe_noncanonical_service_message(body, expected):
    response = (
        httpx.Response(400, json=body)
        if isinstance(body, dict)
        else httpx.Response(400, text=body)
    )
    detail = client.format_http_error(response, "Connect")
    assert expected in detail


def test_live_error_path_sanitizes_service_message():
    source = Path(client.__file__).read_text(encoding="utf-8")
    assert "Live error: {sanitize_diagnostic(event.error.message)}" in source
    detail = client.sanitize_diagnostic(
        'authorization=Bearer secret-token {"api_key":"json-secret"}'
    )
    assert "secret-token" not in detail
    assert "json-secret" not in detail


def test_declared_runtime_and_extension_versions_are_consistent():
    root = Path(client.__file__).resolve().parent
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    manifest = (root / "azure.yaml").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    extension_match = re.search(r'azure\.ai\.agents:\s*"([^"]+)"', manifest)

    assert extension_match is not None
    extension = extension_match.group(1)
    assert project["tool"]["ruff"]["target-version"] == "py311"
    assert extension == ">=1.0.0-beta.24"
    assert "Python 3.11 or later" in readme
    assert "`>=1.0.0-beta.24`" in readme
    assert "Azure/azure-dev#10685" in readme
    assert "Released beta.23 does not contain" in readme
