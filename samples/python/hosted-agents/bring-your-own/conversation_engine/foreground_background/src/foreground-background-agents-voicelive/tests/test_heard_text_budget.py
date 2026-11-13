"""Heard prefixes use the response byte budget, not the user-input limit."""

import pytest

from response_coordinator import MAX_OUTPUT_BYTES
from state import MAX_MESSAGE_CHARACTERS, MAX_TRACKED_PLAYBACK_RESPONSES, SessionState


@pytest.mark.parametrize(
    "unit,count,tail,expected_count",
    [
        ("x", 7999, "", 7999),
        ("x", 8000, "", 8000),
        ("x", 8001, "", 8001),
        ("x", 8011, "", 8011),
        ("👋", 8001, "", 8001),
        ("x", 524288, "", 524288),
        ("x", 524289, "", 524288),
        ("👋", 131072, "", 131072),
        ("👋", 131073, "", 131072),
        ("界", 174763, "", 174762),
        ("x", 524287, "👋", 524287),
    ],
    ids=[
        "below-input-limit",
        "at-input-limit",
        "above-input-limit",
        "result-plus-ack",
        "long-unicode",
        "exact-byte-budget",
        "over-byte-budget",
        "unicode-exact-budget",
        "unicode-over-budget",
        "three-byte-boundary",
        "partial-rune-must-not-be-retained",
    ],
)
def test_heard_prefix_is_complete_within_output_budget_and_bounded_above_it(
    unit: str,
    count: int,
    tail: str,
    expected_count: int,
) -> None:
    state = SessionState()
    state.track_response("r_known")
    heard = unit * count + tail
    state.record_heard_text("r_known", heard)
    stored = state.heard_text_by_response["r_known"]
    assert len(stored) == len(unit * expected_count)
    assert stored == unit * expected_count
    assert heard.startswith(stored)
    assert len(stored.encode("utf-8")) <= 512 * 1024
    if len(heard.encode("utf-8")) <= 512 * 1024:
        assert stored == heard
    state.record_heard_text("r_known", "")
    assert state.heard_text_by_response["r_known"] == ""
    state.record_heard_text("r_known", "retry prefix")
    assert state.heard_text_by_response == {"r_known": "retry prefix"}


def test_unknown_and_evicted_responses_cannot_repopulate_playback_cache() -> None:
    state = SessionState()
    state.record_heard_text("r_unknown", "x" * 8011)
    assert not state.heard_text_by_response
    for index in range(MAX_TRACKED_PLAYBACK_RESPONSES + 1):
        state.track_response(f"r_{index}")
    state.record_heard_text("r_0", "evicted prefix")
    assert "r_0" not in state.heard_text_by_response
    assert len(state.heard_text_by_response) == 64
    state.record_heard_text("r_64", "x" * 8011)
    assert len(state.heard_text_by_response["r_64"]) == 8011
    assert sum(len(text.encode("utf-8")) for text in state.heard_text_by_response.values()) <= (
        64 * 512 * 1024
    )


def test_response_budget_does_not_expand_user_input_or_output_limits() -> None:
    assert MAX_MESSAGE_CHARACTERS == 8000
    assert MAX_OUTPUT_BYTES == 512 * 1024
