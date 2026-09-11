"""Build the SchemaRAFT fine-tuning file.

    python build_sft_data.py --split train --out data/schemaraft_train.jsonl

The recipe is one idea: assemble every training prompt the way the serving
prompt gets assembled. Concretely, each example carries the retrieved correct
schema plus `--n-distractors` confusable ones, shuffled so position carries no
signal.

`--gold-absent-frac` of examples contain no correct schema at all and are
labelled with an empty state. That fraction is what teaches abstention. Drop it
to zero and the model learns that some schema in the prompt is always the right
one, which is exactly the habit that breaks in production.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from build_prompts import build_messages
from schema_retriever import SchemaRetriever
from sgd_data import DEFAULT_DATA_DIR, load_schema_map, load_turns, resolve_split


def build(args) -> None:
    split_dir = resolve_split(args.data_dir, args.split)
    schema_map = load_schema_map(split_dir)
    turns = load_turns(split_dir, max_dialogues=args.max_dialogues, seed=args.seed)
    retriever = SchemaRetriever(schema_map)
    rng = random.Random(args.seed)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    n_gold_absent = 0
    with args.out.open("w", encoding="utf-8") as f:
        for turn in turns:
            gold = schema_map.get(turn["service"])
            if gold is None:
                continue

            if rng.random() < args.gold_absent_frac:
                # No correct schema anywhere in the prompt; the target is {}.
                schemas = retriever.sample_distractors(
                    {turn["service"]}, args.n_distractors + 1, rng
                )
                target: dict[str, str] = {}
                n_gold_absent += 1
            else:
                schemas = [gold] + retriever.sample_distractors(
                    {turn["service"]}, args.n_distractors, rng
                )
                target = turn["gold_belief"]

            rng.shuffle(schemas)
            messages = build_messages(turn["history"], turn["service"], schemas)
            messages.append(
                {"role": "assistant", "content": json.dumps(target, ensure_ascii=False)}
            )
            f.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")

    total = sum(1 for _ in args.out.open(encoding="utf-8"))
    print(f"[out] {args.out}")
    print(f"      {total:,} examples, {args.out.stat().st_size / 1e6:.1f} MB")
    print(
        f"      gold-absent: {n_gold_absent:,} ({n_gold_absent / max(total, 1) * 100:.1f}%)"
    )
    print(f"      schemas per prompt: {args.n_distractors + 1}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--split", default="train", choices=["train", "dev", "test"])
    ap.add_argument("--n-distractors", type=int, default=2)
    ap.add_argument("--gold-absent-frac", type=float, default=0.2)
    ap.add_argument("--max-dialogues", type=int, default=None)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "data" / "schemaraft_train.jsonl",
    )
    build(ap.parse_args())


if __name__ == "__main__":
    main()
