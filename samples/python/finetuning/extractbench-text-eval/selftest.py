"""Offline checks for the whole pipeline. No network, no model, no credentials.

This is what `sample.yaml` runs to validate the sample, so it has to cover the
parts that are easy to break silently: leaf flattening, the F-beta arithmetic,
refusal detection, split leakage, and the screen thresholds.

    python selftest.py
"""

from __future__ import annotations

import json
import sys

import grader
import prepare_data
from evaluate import SCREEN, _is_broken

CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def eq(actual, expected, note=""):
    if actual != expected:
        raise AssertionError(f"{note}expected {expected!r}, got {actual!r}")


def close(actual, expected, tolerance=1e-6, note=""):
    if abs(actual - expected) > tolerance:
        raise AssertionError(f"{note}expected {expected}, got {actual}")


# --- corpus primitives ----------------------------------------------------


@check
def leaf_count_descends_into_lists_and_dicts():
    eq(prepare_data.leaf_count({"a": 1, "b": [1, 2, 3]}), 4)
    eq(prepare_data.leaf_count([{"x": None}, {"x": "y"}]), 2)
    eq(prepare_data.leaf_count("scalar"), 1)


@check
def source_group_collapses_page_and_region_variants():
    eq(prepare_data.source_group("short/acme-p0003"), "short/acme")
    eq(prepare_data.source_group("short/acme-p0003-r1"), "short/acme")
    eq(prepare_data.source_group("short/acme"), "short/acme")
    # A trailing number that is not a page marker must survive.
    eq(prepare_data.source_group("short/form-1099"), "short/form-1099")


@check
def schema_key_ignores_key_order_but_not_content():
    a = json.dumps({"x": {"type": "string"}, "y": {"type": "number"}})
    b = json.dumps({"y": {"type": "number"}, "x": {"type": "string"}})
    c = json.dumps({"x": {"type": "number"}, "y": {"type": "number"}})
    eq(prepare_data.schema_key(a), prepare_data.schema_key(b))
    if prepare_data.schema_key(a) == prepare_data.schema_key(c):
        raise AssertionError("different schemas collided")


@check
def to_row_emits_a_system_and_user_turn_with_parsed_gold():
    raw = {
        "id": "short/demo",
        "data_schema": json.dumps({"total": {"type": "number"}}),
        "expected_output": json.dumps({"total": 5}),
    }
    row = prepare_data.to_row(raw, "<!-- Page 1 -->\nTotal 5")
    eq([m["role"] for m in row["messages"]], ["system", "user"])
    eq(row["messages"][0]["content"], prepare_data.SYSTEM_PROMPT)
    eq(row["expected_output"], {"total": 5})
    if "Document text:" not in row["messages"][1]["content"]:
        raise AssertionError("user turn is missing the document section")


# --- parsing --------------------------------------------------------------


@check
def parse_output_accepts_bare_and_fenced_json():
    eq(grader.parse_output('{"a": 1}'), {"a": 1})
    eq(grader.parse_output('```json\n{"a": 1}\n```'), {"a": 1})
    eq(grader.parse_output("```\n[1, 2]\n```"), [1, 2])


@check
def parse_output_rejects_prose_scalars_and_garbage():
    # Prose around the JSON is a format failure, not something to dig through.
    eq(grader.parse_output('Here you go:\n```json\n{"a": 1}\n```'), None)
    eq(grader.parse_output("42"), None)
    eq(grader.parse_output('"a string"'), None)
    eq(grader.parse_output("{not json"), None)
    eq(grader.parse_output(""), None)


@check
def leaves_are_order_insensitive_and_mark_empty_containers():
    eq(grader.leaves({"b": 1, "a": 2}), [("$.a", "2"), ("$.b", "1")])
    # List position is not part of the path, so row order does not matter.
    eq(grader.leaves({"r": [1, 2]}), [("$.r[]", "1"), ("$.r[]", "2")])
    eq(grader.leaves({"r": []}), [("$.r", "[]")])
    eq(grader.leaves({"r": {}}), [("$.r", "{}")])


@check
def values_are_normalized_before_comparison():
    eq(grader.leaves({"a": "  Hello   World "}), [("$.a", "hello world")])
    eq(grader.leaves({"a": None}), [("$.a", "null")])
    eq(grader.leaves({"a": True}), [("$.a", "true")])
    # 1 and 1.0 are the same extracted value.
    eq(grader.leaves({"a": 1}), grader.leaves({"a": 1.0}))


# --- scoring --------------------------------------------------------------


@check
def grade_is_one_for_an_exact_match_and_zero_for_no_answer():
    gold = {"a": 1, "rows": [{"x": "p"}, {"x": "q"}]}
    close(grader.grade(gold, gold), 1.0)
    close(grader.grade(None, gold), 0.0)
    close(grader.grade(grader.parse_output("I'm sorry"), gold), 0.0)
    # Gold may arrive as a JSON string.
    close(grader.grade(gold, json.dumps(gold)), 1.0)


@check
def grade_gives_partial_credit_by_leaf():
    gold = {"rows": [{"x": i} for i in range(10)]}
    got = {"rows": [{"x": i} for i in range(8)]}
    close(grader.grade(got, gold), 2 * 8 / (8 + 10))


@check
def f1_pays_a_model_to_stop_early_and_beta_narrows_the_gap():
    """The exact asymmetry quoted in grader.grade's docstring."""
    gold = {"rows": [{"x": i} for i in range(100)]}
    omitted = {"rows": [{"x": i} for i in range(90)]}
    wrong = {
        "rows": [{"x": i} for i in range(90)] + [{"x": f"bad{i}"} for i in range(10)]
    }

    close(grader.grade(omitted, gold), 0.947368, tolerance=1e-5)
    close(grader.grade(wrong, gold), 0.900000, tolerance=1e-5)

    gap_at_1 = grader.grade(omitted, gold) - grader.grade(wrong, gold)
    gap_at_2 = grader.grade(omitted, gold, beta=2) - grader.grade(wrong, gold, beta=2)
    if not 0 < gap_at_2 < gap_at_1:
        raise AssertionError(
            f"beta should shrink the gap, not flip it: {gap_at_1} -> {gap_at_2}"
        )


@check
def score_response_separates_giving_up_from_extracting_badly():
    gold = {"rows": [{"x": i} for i in range(10)]}

    refusal = grader.score_response("I'm sorry, but I can't provide that.", gold)
    eq(refusal["refusal"], 1.0)
    eq(refusal["valid_json"], 0.0)
    eq(refusal["coverage"], 0.0)

    # Curly apostrophes are what models actually emit.
    curly = grader.score_response(
        "I\u2019m sorry, but I can\u2019t complete this.", gold
    )
    eq(curly["refusal"], 1.0)

    gave_up_early = grader.score_response(json.dumps({"rows": [{"x": 0}]}), gold)
    eq(gave_up_early["valid_json"], 1.0)
    close(gave_up_early["coverage"], 0.1)
    close(gave_up_early["precision"], 1.0)

    # An empty object is valid JSON and still an abdication.
    empty = grader.score_response("{}", gold)
    eq(empty["valid_json"], 1.0)
    eq(empty["empty"], 1.0)
    close(empty["f1"], 0.0)


@check
def coverage_is_clamped_so_over_extraction_cannot_look_like_more_than_everything():
    gold = {"rows": [{"x": i} for i in range(10)]}
    over = {"rows": [{"x": i} for i in range(30)]}
    eq(grader.score_response(json.dumps(over), gold)["coverage"], 1.0)


# --- split ----------------------------------------------------------------


def _synthetic_rows():
    rows = []
    for schema in range(8):
        for page in range(3):
            rows.append(
                {
                    "example_id": f"short/doc{schema}-p000{page}",
                    "schema_key": f"schema{schema}",
                    "source_group": f"short/doc{schema}",
                    "leaf_count": 200 + schema,
                }
            )
    return rows


@check
def partition_never_leaks_a_schema_or_a_source_document():
    train, test = prepare_data.partition(_synthetic_rows(), train_target=6, seed=0)
    eq(set(r["schema_key"] for r in train) & set(r["schema_key"] for r in test), set())
    eq(
        set(r["source_group"] for r in train) & set(r["source_group"] for r in test),
        set(),
    )
    eq(len(train) + len(test), 24)


@check
def partition_is_reproducible_and_leaves_test_the_larger_share():
    first = prepare_data.partition(_synthetic_rows(), 6, seed=0)
    again = prepare_data.partition(_synthetic_rows(), 6, seed=0)
    eq([r["example_id"] for r in first[0]], [r["example_id"] for r in again[0]])

    other = prepare_data.partition(_synthetic_rows(), 6, seed=7)
    if [r["example_id"] for r in first[0]] == [r["example_id"] for r in other[0]]:
        raise AssertionError("seed had no effect on the split")

    train, test = first
    if len(test) <= len(train):
        raise AssertionError("test should get the larger share")


# --- screen ---------------------------------------------------------------


@check
def screen_thresholds_reproduce_the_published_verdicts():
    """Five published zero-shot measurements, and the count of broken columns.

    Taken from the study this sample accompanies; they pin the thresholds so a
    later edit cannot quietly reclassify a model.
    """
    published = [
        ("3 broken", {"refusal": 0.250, "valid_json": 0.638, "coverage": 0.471}, 3),
        ("1 broken", {"refusal": 0.000, "valid_json": 0.963, "coverage": 0.741}, 1),
        ("clean, small", {"refusal": 0.000, "valid_json": 0.988, "coverage": 0.914}, 0),
        ("clean, dense", {"refusal": 0.000, "valid_json": 1.000, "coverage": 0.874}, 0),
        (
            "clean, strong",
            {"refusal": 0.000, "valid_json": 1.000, "coverage": 0.986},
            0,
        ),
    ]
    for name, columns, expected_broken in published:
        broken = sum(
            1 for column, _, _ in SCREEN if _is_broken(column, columns[column])
        )
        eq(broken, expected_broken, note=f"{name}: ")


@check
def screen_covers_exactly_the_three_behaviour_columns():
    eq({column for column, _, _ in SCREEN}, {"refusal", "valid_json", "coverage"})


def main() -> int:
    failures = []
    for fn in CHECKS:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - report every failure, not the first
            failures.append((fn.__name__, exc))
            print(f"FAIL  {fn.__name__}: {exc}")
        else:
            print(f"ok    {fn.__name__}")

    print(f"\n{len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed")
    if failures:
        return 1
    print("SELFTEST PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
