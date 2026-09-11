"""Offline smoke test. No network, no Azure, no tokens spent.

    python selftest.py

Runs the retrieval, prompt-assembly, parsing, scoring, training-data and
stratification paths against the bundled fixtures in `fixtures/test/`, so you
can tell a broken checkout apart from a broken deployment before step 2.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
from pathlib import Path

from build_prompts import (
    build_messages,
    exact_match,
    parse_belief_json,
    select_schemas,
    slot_f1,
)
from build_sft_data import build as build_sft
from goldpresent_strata import summarise
from schema_retriever import SchemaRetriever
from sgd_data import load_schema_map, load_turns, schema_to_text

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SPLIT_DIR = FIXTURES / "test"

_failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{'  -> ' + detail if detail else ''}")
        _failures.append(name)


def test_data_layer() -> tuple[dict, list[dict]]:
    print("\n[1] data layer")
    schema_map = load_schema_map(SPLIT_DIR)
    turns = load_turns(SPLIT_DIR, seed=42)
    check("schema registry loads", len(schema_map) == 4, f"got {len(schema_map)}")
    check("turns extracted", len(turns) == 4, f"got {len(turns)}")
    check(
        "gold belief is flattened and lowercased",
        turns[0]["gold_belief"].get("location") == "san francisco",
        str(turns[0]["gold_belief"]),
    )
    check(
        "belief state is cumulative",
        set(turns[1]["gold_belief"]) > set(turns[0]["gold_belief"]),
    )
    text = schema_to_text(schema_map["Restaurants_2"])
    check(
        "schema serialises with slots and intents",
        "price_range" in text and "ReserveRestaurant" in text,
    )
    return schema_map, turns


def test_retrieval(schema_map: dict, turns: list[dict]) -> SchemaRetriever:
    print("\n[2] retrieval")
    r = SchemaRetriever(schema_map)
    ranked = r.rank(turns[0]["history"])
    check("ranking covers the whole registry", len(ranked) == len(schema_map))
    check(
        "scores are sorted descending",
        all(ranked[i][1] >= ranked[i + 1][1] for i in range(len(ranked) - 1)),
    )
    check(
        "restaurant dialogue retrieves a restaurant schema",
        ranked[0][0].startswith("Restaurants_"),
        f"top1={ranked[0][0]}",
    )
    check(
        "bus dialogue retrieves the bus schema",
        r.rank(turns[2]["history"])[0][0] == "Buses_3",
    )

    rng = random.Random(0)
    d = r.sample_distractors({"Restaurants_2"}, 2, rng)
    check(
        "distractors exclude the gold service",
        len(d) == 2 and all(s["service_name"] != "Restaurants_2" for s in d),
    )
    return r


def test_prompt_modes(schema_map: dict, turns: list[dict], r: SchemaRetriever) -> None:
    print("\n[3] prompt modes")
    t = turns[0]

    def pick(mode: str, seed: int = 42, n_distractors: int = 2) -> list[str]:
        schemas = select_schemas(
            t["history"],
            t["service"],
            schema_map,
            mode,
            r,
            1,
            n_distractors,
            random.Random(seed),
        )
        return [s["service_name"] for s in schemas]

    check("mode=none shows no schema", pick("none") == [])
    check(
        "mode=oracle shows exactly the gold schema", pick("oracle") == ["Restaurants_2"]
    )
    check("mode=retrieved shows one schema", len(pick("retrieved")) == 1)

    shown = pick("retrieved_distractor")
    check("retrieved_distractor shows 1 + n_distractors", len(shown) == 3, str(shown))
    check("schemas shown are distinct", len(set(shown)) == len(shown), str(shown))
    check("same seed reproduces the same prompt", shown == pick("retrieved_distractor"))
    check(
        "different seed reshuffles",
        any(pick("retrieved_distractor", seed=s) != shown for s in (1, 2, 3, 7)),
    )

    msgs = build_messages(t["history"], t["service"], [schema_map["Restaurants_2"]])
    check("messages are system+user", [m["role"] for m in msgs] == ["system", "user"])
    check(
        "gold schema reaches the system prompt", "Restaurants_2" in msgs[0]["content"]
    )
    check("history reaches the user prompt", "Italian" in msgs[1]["content"])
    check(
        "no-schema prompt has no schema block",
        "Service schemas"
        not in build_messages(t["history"], t["service"], [])[0]["content"],
    )


def test_parsing_and_metrics() -> None:
    print("\n[4] parsing and metrics")
    check("plain json", parse_belief_json('{"city": "SF"}') == {"city": "sf"})
    check(
        "markdown fenced",
        parse_belief_json('```json\n{"city": "SF"}\n```') == {"city": "sf"},
    )
    check(
        "json with trailing prose",
        parse_belief_json('Here you go: {"city": "SF"} hope that helps')
        == {"city": "sf"},
    )
    check("empty state", parse_belief_json("{}") == {})
    check("unparseable becomes empty", parse_belief_json("I am not sure.") == {})
    check("non-dict becomes empty", parse_belief_json("[1, 2, 3]") == {})

    gold = {"city": "sf", "cuisine": "italian"}
    check(
        "exact match is exact", exact_match({"city": "sf", "cuisine": "italian"}, gold)
    )
    check(
        "one wrong slot fails the turn",
        not exact_match({"city": "sf", "cuisine": "mexican"}, gold),
    )
    check(
        "an extra slot fails the turn",
        not exact_match({"city": "sf", "cuisine": "italian", "time": "7 pm"}, gold),
    )
    p, rec, f1 = slot_f1({"city": "sf", "cuisine": "mexican"}, gold)
    check(
        "slot f1 gives partial credit",
        abs(p - 0.5) < 1e-9 and abs(f1 - 0.5) < 1e-9,
        f"p={p} r={rec} f1={f1}",
    )


def test_training_data() -> None:
    print("\n[5] training data")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "train.jsonl"

        def run(frac: float) -> list[dict]:
            build_sft(
                argparse.Namespace(
                    data_dir=FIXTURES,
                    split="test",
                    n_distractors=2,
                    gold_absent_frac=frac,
                    max_dialogues=None,
                    seed=42,
                    out=out,
                )
            )
            return [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]

        rows = run(0.0)
        check("one training row per turn", len(rows) == 4, f"got {len(rows)}")
        roles = [m["role"] for m in rows[0]["messages"]]
        check(
            "chat format is system/user/assistant",
            roles == ["system", "user", "assistant"],
            str(roles),
        )
        check(
            "assistant turn is valid json",
            isinstance(json.loads(rows[0]["messages"][-1]["content"]), dict),
        )
        check(
            "gold_absent_frac=0 always labels a real state",
            all(json.loads(r["messages"][-1]["content"]) for r in rows),
        )
        check(
            "prompt carries 3 schemas",
            rows[0]["messages"][0]["content"].count("Service: ") == 3,
        )

        rows = run(1.0)
        check(
            "gold_absent_frac=1 labels every row with {}",
            all(json.loads(r["messages"][-1]["content"]) == {} for r in rows),
        )
        check(
            "gold-absent rows hide the correct schema",
            all(
                "Service: Restaurants_2" not in r["messages"][0]["content"]
                for r in rows[:2]
            ),
        )


def test_strata() -> None:
    print("\n[6] stratification")
    records = (
        [{"gold_in_prompt": True, "correct": True, "pred": {"a": "1"}}] * 3
        + [{"gold_in_prompt": True, "correct": False, "pred": {"a": "2"}}] * 7
        + [{"gold_in_prompt": False, "correct": False, "pred": {}}] * 6
        + [{"gold_in_prompt": False, "correct": False, "pred": {"a": "3"}}] * 4
    )
    s = summarise(records)
    check("overall jga", s["jga_overall"] == 15.0, str(s["jga_overall"]))
    check(
        "gold-present jga is conditional, not overall",
        s["jga_gold_present"] == 30.0,
        str(s["jga_gold_present"]),
    )
    check("gold-present rate", s["gold_present_rate"] == 50.0)
    check(
        "abstention counted only on gold-absent turns",
        s["abstention_rate_gold_absent"] == 60.0,
        str(s["abstention_rate_gold_absent"]),
    )


def main() -> int:
    print("SchemaRAFT offline selftest (no Azure calls)")
    schema_map, turns = test_data_layer()
    retriever = test_retrieval(schema_map, turns)
    test_prompt_modes(schema_map, turns, retriever)
    test_parsing_and_metrics()
    test_training_data()
    test_strata()

    print()
    if _failures:
        print(f"FAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print("All checks passed. You are ready for step 1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
