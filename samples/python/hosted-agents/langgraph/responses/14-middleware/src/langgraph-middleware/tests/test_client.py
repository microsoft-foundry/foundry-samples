"""Reject failed or malformed reviewer traffic using the real OpenAI client."""

from argparse import Namespace
from copy import deepcopy
import json

from client import INTERRUPT_NAME, review_agent
import httpx
from openai import APIError, APIStatusError, OpenAI
import pytest
from test_middleware import EMAIL_ARGS, open_review_client


def response_payload(status):
    payload = {
        "id": "resp_failure",
        "object": "response",
        "created_at": 1,
        "model": "test-model",
        "output": [],
        "status": status,
    }
    if status == "failed":
        payload["error"] = {
            "code": "server_error",
            "message": "Synthetic backend failure",
        }
    elif status == "incomplete":
        payload["incomplete_details"] = {"reason": "max_output_tokens"}
    return payload


def run_reviewer(handler, *, stream=False, decision="approve", recipient=None):
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        with OpenAI(
            base_url="http://testserver",
            api_key="local",
            http_client=transport,
            max_retries=0,
        ) as client:
            review_agent(
                client,
                Namespace(
                    prompt="Send the email.",
                    stream=stream,
                    decision=decision,
                    recipient=recipient,
                ),
            )


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("status", ["failed", "incomplete"])
def test_noncompleted_response_never_resumes_review(stream, status):
    requests = []

    def handle(request):
        requests.append(request)
        payload = response_payload(status)
        if stream:
            event = {
                "type": "response." + status,
                "response": payload,
                "sequence_number": 1,
            }
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=f"event: response.{status}\ndata: {json.dumps(event)}\n\ndata: [DONE]\n\n",
            )
        return httpx.Response(200, json=payload)

    with pytest.raises(RuntimeError, match="Response did not complete"):
        run_reviewer(handle, stream=stream)
    assert len(requests) == 1


@pytest.mark.parametrize("named_event", [False, True])
def test_stream_error_never_resumes_review(named_event):
    requests = []

    def handle(request):
        requests.append(request)
        prefix = "event: error\n" if named_event else ""
        data = {
            "type": "error",
            "code": "server_error",
            "message": "Synthetic stream error",
        }
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=prefix + "data: " + json.dumps(data) + "\n\n",
        )

    with pytest.raises((RuntimeError, APIError), match="Synthetic stream error"):
        run_reviewer(handle, stream=True)
    assert len(requests) == 1


def test_truncated_stream_never_resumes_review():
    requests = []

    def handle(request):
        requests.append(request)
        event = {
            "type": "response.created",
            "response": response_payload("in_progress"),
            "sequence_number": 1,
        }
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content="event: response.created\ndata: " + json.dumps(event) + "\n\n",
        )

    with pytest.raises(RuntimeError, match="without a terminal event"):
        run_reviewer(handle, stream=True)
    assert len(requests) == 1


def test_http_failure_never_resumes_review():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            500, json={"error": {"message": "Synthetic HTTP failure"}}
        )

    with pytest.raises(APIStatusError):
        run_reviewer(handle)
    assert len(requests) == 1


@pytest.fixture
def pending_review():
    with open_review_client([dict(EMAIL_ARGS)]) as (client, model):
        return client.responses.create(input="Send the email.").model_dump(mode="json")


@pytest.mark.parametrize("decision", ["edit", "reject", "unknown"])
def test_disallowed_decision_never_sends_resume(pending_review, decision):
    payload = deepcopy(pending_review)
    rewritten = 0
    for item in payload["output"]:
        if (
            item["type"] in {"mcp_approval_request", "function_call"}
            and item.get("name") == INTERRUPT_NAME
        ):
            arguments = json.loads(item["arguments"])
            for configuration in arguments["value"]["review_configs"]:
                configuration["allowed_decisions"] = ["approve"]
            item["arguments"] = json.dumps(arguments)
            rewritten += 1
    assert rewritten == 2
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=payload)

    with pytest.raises(ValueError):
        run_reviewer(handle, decision=decision, recipient="bob@example.com")
    assert len(requests) == 1


def test_missing_approval_channel_never_sends_resume(pending_review):
    payload = deepcopy(pending_review)
    payload["output"] = [
        item for item in payload["output"] if item["type"] != "mcp_approval_request"
    ]
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=payload)

    with pytest.raises(RuntimeError, match="missing its mcp_approval_request"):
        run_reviewer(handle)
    assert len(requests) == 1


def test_another_pending_review_does_not_start_a_third_request(pending_review):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=pending_review)

    with pytest.raises(RuntimeError, match="one review round only"):
        run_reviewer(handle)
    assert len(requests) == 2
