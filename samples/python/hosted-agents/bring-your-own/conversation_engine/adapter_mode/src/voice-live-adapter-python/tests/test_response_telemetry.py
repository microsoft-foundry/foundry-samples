# Copyright (c) Microsoft. All rights reserved.

"""Tests for privacy-safe response terminal telemetry."""

from __future__ import annotations

import time
from typing import Any

from opentelemetry.trace import StatusCode

from adapter import response_telemetry
from adapter.response_coordinator import ResponseCoordinator
from adapter.state import OperationOutcome, SessionState


class FakeSpan:
    def __init__(self) -> None:
        self.attributes: dict[str, Any] = {}
        self.status_code = StatusCode.UNSET
        self.end_count = 0

    def set_attribute(self, name: str, value: Any) -> None:
        self.attributes[name] = value

    def set_status(self, status: Any) -> None:
        self.status_code = status.status_code

    def end(self) -> None:
        self.end_count += 1


class FakeTracer:
    def __init__(self, span: FakeSpan) -> None:
        self.span = span

    def start_span(self, *_args: Any, **_kwargs: Any) -> FakeSpan:
        return self.span


def test_timeout_completion_records_sanitized_outcome_and_duration(monkeypatch: Any) -> None:
    span = FakeSpan()
    monkeypatch.setattr(response_telemetry, "_tracer", FakeTracer(span))
    coordinator = ResponseCoordinator()
    monkeypatch.setattr(
        coordinator,
        "_start_task",
        lambda _state, _operation, coroutine: coroutine.close(),
    )
    state = SessionState()
    assert state.try_begin_start()
    state.activate()

    assert coordinator.start_self_cancel(
        object(),  # type: ignore[arg-type]
        state,
        "input_1",
        "cancel",
        time.monotonic(),
    )
    operation = next(iter(state.responses.values()))

    operation.complete(OperationOutcome.TIMEOUT)
    operation.complete(OperationOutcome.ABANDONED)

    assert span.attributes[response_telemetry.OUTCOME_ATTRIBUTE] == "timeout"
    assert span.attributes[response_telemetry.RESPONSE_DURATION_ATTRIBUTE] >= 0
    assert span.status_code is StatusCode.ERROR
    assert span.end_count == 1
