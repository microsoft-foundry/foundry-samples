"""Separate a retrieval failure from a schema-following failure.

    python goldpresent_strata.py --results results/retdist

Splits the turns from an `eval_jga.py --mode retrieved_distractor` run into the
subset where the correct schema really was in the prompt and the subset where it
was not, then reports JGA on each.

Read it this way:

* Low JGA on the gold-absent stratum is expected and uninteresting. The model
  was never shown the answer.
* Low JGA on the **gold-present** stratum is the finding. The correct schema was
  sitting in the context and the model still got the turn wrong, which means
  better retrieval cannot fix it.
* Abstention rate on the gold-absent stratum tells you whether the model
  degrades safely. Emitting `{}` is the correct behaviour there; inventing slots
  from a distractor schema is not.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_records(results_dir: Path) -> list[dict]:
    path = results_dir / "turns.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found - run eval_jga.py with --output-dir {results_dir}"
        )
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def summarise(records: list[dict]) -> dict:
    present = [r for r in records if r["gold_in_prompt"]]
    absent = [r for r in records if not r["gold_in_prompt"]]

    def jga(rows: list[dict]) -> float | None:
        return (
            round(sum(r["correct"] for r in rows) / len(rows) * 100, 2)
            if rows
            else None
        )

    abstained = sum(1 for r in absent if not r["pred"])
    return {
        "n_turns": len(records),
        "jga_overall": jga(records),
        "n_gold_present": len(present),
        "gold_present_rate": round(len(present) / len(records) * 100, 2)
        if records
        else None,
        "jga_gold_present": jga(present),
        "n_gold_absent": len(absent),
        "jga_gold_absent": jga(absent),
        "abstention_rate_gold_absent": round(abstained / len(absent) * 100, 2)
        if absent
        else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--results", type=Path, required=True, help="an eval_jga.py --output-dir"
    )
    args = ap.parse_args()

    s = summarise(load_records(args.results))

    print(f"\nturns                            {s['n_turns']:,}")
    print(f"overall JGA                      {s['jga_overall']:.1f}\n")
    print(
        f"gold schema IN the prompt        {s['n_gold_present']:,} turns "
        f"({s['gold_present_rate']:.1f}%)"
    )
    print(
        f"  JGA on that stratum            {s['jga_gold_present']:.1f}   <-- the finding"
    )
    print(f"\ngold schema NOT in the prompt    {s['n_gold_absent']:,} turns")
    if s["n_gold_absent"]:
        print(f"  JGA on that stratum            {s['jga_gold_absent']:.1f}")
        print(
            f"  correctly abstained            {s['abstention_rate_gold_absent']:.1f}%"
        )

    print("\nIf the gold-present number is far below the oracle run, the model is not")
    print("failing to FIND the schema. It is failing to FOLLOW it, falling back on")
    print("slot inventories memorised during pre-training.")

    out = args.results / "strata.json"
    out.write_text(json.dumps(s, indent=2), encoding="utf-8")
    print(f"\n[out] {out}")


if __name__ == "__main__":
    main()
