# Copyright (c) Microsoft. All rights reserved.

"""Privacy-safe Hosted Agent response telemetry."""

from __future__ import annotations

import time
from contextlib import AbstractContextManager

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

TRACER_NAME = "VoiceHostedAgent.Response"
RESPONSE_DURATION_ATTRIBUTE = "voice_agent.hosted_agent.response_duration_ms"
RESPONSE_ID_ATTRIBUTE = "gen_ai.response.id"
INPUT_ITEM_ID_ATTRIBUTE = "voice_agent.input.item_id"
OUTCOME_ATTRIBUTE = "voice_agent.hosted_agent.outcome"

_ERROR_OUTCOMES = frozenset({"abandoned", "error", "timeout", "transport_error"})

_tracer = trace.get_tracer(TRACER_NAME)


class ResponseTelemetry:
    """Own one response span from user.message receipt through response.done send."""

    def __init__(self, response_id: str, input_item_id: str, received_at: float) -> None:
        self._received_at = received_at
        self._span = _tracer.start_span(
            "process_response",
            attributes={
                RESPONSE_ID_ATTRIBUTE: response_id,
                INPUT_ITEM_ID_ATTRIBUTE: input_item_id,
            },
        )
        self._ended = False

    def activate(self) -> AbstractContextManager[Span]:
        """Make this response current while creating its background task."""
        return trace.use_span(self._span, end_on_exit=False)

    def record_response_done_sent(self) -> None:
        """Record duration after response.done send completes, then end successfully."""
        self.record_outcome("response")

    def record_outcome(self, outcome: str) -> None:
        """Record one sanitized terminal outcome and end the span exactly once."""
        if self._ended:
            return
        self._span.set_attribute(
            RESPONSE_DURATION_ATTRIBUTE,
            (time.monotonic() - self._received_at) * 1000,
        )
        self._span.set_attribute(OUTCOME_ATTRIBUTE, outcome)
        self._span.set_status(
            Status(StatusCode.ERROR if outcome in _ERROR_OUTCOMES else StatusCode.OK)
        )
        self.end()

    def record_failure(self, exception: BaseException) -> None:
        """Mark response processing failed without recording exception content."""
        error_type = f"{type(exception).__module__}.{type(exception).__qualname__}"
        self._span.set_attribute("error.type", error_type)
        self.record_outcome("error")

    def end(self) -> None:
        """End the span exactly once."""
        if self._ended:
            return
        self._ended = True
        self._span.end()
