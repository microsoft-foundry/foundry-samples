"""Deterministic partial-credit grader for JSON extraction.

The score is an F-measure over the multiset of (path, value) leaves. Flattening
to leaves rather than comparing trees is what makes partial credit meaningful
here: a model that returns 38 of 40 invoice line items should score close to a
model that returns all 40, and a model that returns an apology should score
zero. Exact tree equality cannot express that difference, and neither can a
per-field accuracy that assumes both sides have the same fields.

Paths carry list membership as `[]` rather than an index, so records are matched
as a bag. Emitting the right rows in the wrong order is not an error; the
documents this grades have no reliable row ordering to begin with.

Standard library only, so it can be lifted into a training loop or a grader
endpoint without dragging dependencies along.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def parse_output(text: str) -> Any | None:
    """Return the JSON value in a model response, or None if there is not one.

    A fenced block is unwrapped, but only when the fence is the whole response.
    Prose wrapped around JSON counts as a format failure: the caller asked for
    one JSON object and cannot be expected to go looking for it.
    """
    text = (text or "").strip()
    match = _FENCE.fullmatch(text)
    if match:
        text = match.group(1)
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _normalize(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value) if not math.isfinite(value) else format(value, ".15g")
    return " ".join(str(value).split()).casefold()


def leaves(value: Any, path: str = "$") -> list[tuple[str, str]]:
    """Flatten to (path, normalized value) pairs.

    Empty containers yield one leaf of their own. Without that, a model that
    replaced a 200-row table with `[]` would be scored as though it had said
    nothing about the table, rather than as having said it was empty.
    """
    if isinstance(value, dict):
        if not value:
            return [(path, "{}")]
        out: list[tuple[str, str]] = []
        for key in sorted(value):
            out.extend(leaves(value[key], f"{path}.{key}"))
        return out
    if isinstance(value, list):
        if not value:
            return [(path, "[]")]
        out = []
        for item in value:
            out.extend(leaves(item, f"{path}[]"))
        return out
    return [(path, _normalize(value))]


def grade(predicted: Any, expected: Any, beta: float = 1.0) -> float:
    """F-beta over the leaf multisets. Returns 0.0 for an unusable prediction.

    beta > 1 weights recall. That matters more than it looks: under F1, against
    100 expected leaves, omitting 10 scores 0.947 while attempting 10 and
    getting them wrong scores 0.900. F1 therefore pays a model to stop early,
    which is the exact behaviour this benchmark exists to detect. Reported
    numbers use beta=1; a training reward may reasonably use more.
    """
    if isinstance(expected, str):
        try:
            expected = json.loads(expected)
        except (TypeError, ValueError):
            return 0.0
    if predicted is None or not isinstance(expected, (dict, list)):
        return 0.0

    predicted_leaves = Counter(leaves(predicted))
    expected_leaves = Counter(leaves(expected))
    matched = sum((predicted_leaves & expected_leaves).values())
    n_predicted = sum(predicted_leaves.values())
    n_expected = sum(expected_leaves.values())

    beta_sq = beta * beta
    denominator = beta_sq * n_expected + n_predicted
    if denominator == 0:
        return 1.0
    return round((1.0 + beta_sq) * matched / denominator, 6)


# Some models decline this task outright rather than extract badly, reasoning
# that the document is too long to be worth finishing. A refusal is never valid
# JSON, so without this it is indistinguishable from a malformed answer - and
# the two call for completely different fixes. Apostrophes may be straight or
# curly.
REFUSAL = re.compile(
    r"(i\W{0,3}m sorry"
    r"|i can\W{0,3}t (provide|complete|do|assist|help|produce)"
    r"|unable to (provide|complete|comply)"
    r"|cannot (provide|complete) )",
    re.IGNORECASE,
)


def score_response(text: str, expected: Any) -> dict[str, float]:
    """Every per-document number the screen needs, from one model response.

    F1 alone cannot tell "extracted forty records badly" from "gave up after
    five" - both land near 0.2. `coverage` separates them by asking how much the
    model emitted at all, and `refusal` isolates the case where it never tried.
    """
    if isinstance(expected, str):
        expected = json.loads(expected)

    predicted = parse_output(text)
    expected_leaves = Counter(leaves(expected))
    n_expected = sum(expected_leaves.values())

    if predicted is None:
        matched = n_predicted = 0
    else:
        predicted_leaves = Counter(leaves(predicted))
        n_predicted = sum(predicted_leaves.values())
        matched = sum((predicted_leaves & expected_leaves).values())

    return {
        "f1": 2.0 * matched / (n_predicted + n_expected)
        if n_predicted + n_expected
        else 1.0,
        "precision": matched / n_predicted if n_predicted else 0.0,
        "recall": matched / n_expected if n_expected else 1.0,
        "coverage": min(n_predicted / n_expected, 1.0) if n_expected else 1.0,
        "valid_json": float(predicted is not None),
        "refusal": float(bool(REFUSAL.search(text or ""))),
        # Parseable JSON with nothing in it scores 1 on format and 0 on content.
        # Without this column an apology and an empty object look like a format
        # improvement, when both are the same abdication.
        "empty": float(isinstance(predicted, (dict, list)) and not predicted),
    }
