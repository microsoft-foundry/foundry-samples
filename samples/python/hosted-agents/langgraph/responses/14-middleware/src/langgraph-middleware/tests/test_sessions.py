"""Keep pending reviews and tool receipts isolated across real conversations."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from uuid import uuid4

from client import build_resume_items, create_response
import pytest
from test_middleware import EMAIL_ARGS, open_review_client


@pytest.mark.parametrize("stream", [False, True])
def test_new_conversations_do_not_reuse_another_review(stream: bool) -> None:
    with open_review_client([dict(EMAIL_ARGS)]) as (client, model):
        paused = [
            create_response(
                client,
                input=marker,
                conversation={"id": "conv_" + uuid4().hex},
                stream=stream,
            )
            for marker in ("SESSION-FIRST-REQUEST", "SESSION-SECOND-REQUEST")
        ]
        approvals = [
            next(
                item
                for item in response["output"]
                if item["type"] == "mcp_approval_request"
            )
            for response in paused
        ]
        assert approvals[0]["id"] != approvals[1]["id"]
        for response, decision in zip(paused, ("edit", "approve"), strict=True):
            resumed = create_response(
                client,
                input=build_resume_items(response, decision, "bob@example.com"),
                previous_response_id=response["id"],
                stream=stream,
            )
            recipient = "bob@example.com" if decision == "edit" else "alice@example.com"
            assert f"Simulated email to {recipient}" in json.dumps(resumed)
        third = create_response(
            client,
            input="SESSION-THIRD-REQUEST",
            conversation={"id": "conv_" + uuid4().hex},
            stream=stream,
        )
        assert any(item["type"] == "mcp_approval_request" for item in third["output"])
        history = str(model.seen[-1])
        assert "SESSION-THIRD-REQUEST" in history
        assert "SESSION-FIRST-REQUEST" not in history
        assert "SESSION-SECOND-REQUEST" not in history
        assert len(model.seen) == 5


@pytest.mark.parametrize("stream", [False, True])
def test_concurrent_reviews_keep_decisions_and_history_isolated(
    stream: bool, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="agent")
    plans = [
        ("CONCURRENT-FIRST", "approve"),
        ("CONCURRENT-SECOND", "edit"),
        ("CONCURRENT-THIRD", "reject"),
    ]
    with open_review_client([dict(EMAIL_ARGS)]) as (client, model):

        def pause(plan):
            marker, decision = plan
            return create_response(
                client,
                input=marker,
                conversation={"id": "conv_" + uuid4().hex},
                stream=stream,
            )

        def resume(plan_and_response):
            plan, response = plan_and_response
            marker, decision = plan
            return create_response(
                client,
                input=build_resume_items(response, decision, "carol@example.com"),
                previous_response_id=response["id"],
                stream=stream,
            )

        with ThreadPoolExecutor(max_workers=3) as executor:
            paused = list(executor.map(pause, plans))
            assert len({response["id"] for response in paused}) == 3
            assert "Simulated send_email tool executed" not in caplog.text
            resumed = list(executor.map(resume, zip(plans, paused, strict=True)))
        assert "Simulated email to alice@example.com" in json.dumps(resumed[0])
        assert "Simulated email to carol@example.com" in json.dumps(resumed[1])
        assert "Simulated email to" not in json.dumps(resumed[2])
        assert all(
            not any(
                item["type"] == "mcp_approval_request" for item in response["output"]
            )
            for response in resumed
        )
        calls = Counter()
        for messages in model.seen:
            markers = [marker for marker, decision in plans if marker in str(messages)]
            assert len(markers) == 1, messages
            calls[markers[0]] += 1
        assert calls == Counter({marker: 2 for marker, decision in plans})
    assert caplog.text.count("Simulated send_email tool executed") == 2
