"""Evaluate dialogue state tracking under a chosen schema-delivery mode.

    python eval_jga.py --mode oracle               --n 200
    python eval_jga.py --mode retrieved_distractor --n 200

Everything except `--mode` is held fixed: same turns, same order, same prompt
template, same metric. The per-turn JSONL this writes records which schemas were
actually shown, which is what `goldpresent_strata.py` later needs to separate a
retrieval failure from a schema-following failure.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from build_prompts import (
    MODES,
    build_messages,
    exact_match,
    parse_belief_json,
    select_schemas,
    slot_f1,
)
from foundry_client import make_client
from schema_retriever import SchemaRetriever
from sgd_data import DEFAULT_DATA_DIR, load_schema_map, load_turns, resolve_split

HERE = Path(__file__).resolve().parent


def load_dotenv_if_present() -> None:
    env = HERE / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def call_model(
    client,
    deployment: str,
    messages: list[dict],
    max_attempts: int = 3,
    timeout: float = 60.0,
) -> str:
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.chat.completions.create(
                model=deployment,
                messages=messages,
                temperature=0.0,
                max_tokens=256,
                timeout=timeout,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:
            last_exc = exc
            status = getattr(exc, "status_code", None)
            if status is not None and 400 <= status < 500 and status != 429:
                return ""  # content filter / bad request: score as an empty prediction
            time.sleep(2**attempt)
    print(f"  [warn] giving up on a turn: {last_exc}", file=sys.stderr)
    return ""


def evaluate(args) -> dict:
    split_dir = resolve_split(args.data_dir, args.split)
    schema_map = load_schema_map(split_dir)
    turns = load_turns(split_dir, seed=args.seed)
    if args.n and args.n < len(turns):
        turns = random.Random(args.seed).sample(turns, args.n)

    print(f"[data] {len(turns):,} turns | registry: {len(schema_map)} services")
    print(
        f"[mode] {args.mode}  n_schemas={args.n_schemas}  n_distractors={args.n_distractors}"
    )

    retriever = None
    if args.mode in ("retrieved", "retrieved_distractor"):
        retriever = SchemaRetriever(schema_map)

    # One RNG, consumed in turn order, so a run is reproducible from --seed alone.
    rng = random.Random(args.seed)
    prepared = []
    for turn in turns:
        schemas = select_schemas(
            turn["history"],
            turn["service"],
            schema_map,
            args.mode,
            retriever,
            args.n_schemas,
            args.n_distractors,
            rng,
        )
        prepared.append(
            (
                turn,
                [s["service_name"] for s in schemas],
                build_messages(turn["history"], turn["service"], schemas),
            )
        )

    client = make_client(args.endpoint)

    def run_one(idx_item):
        idx, (turn, shown, messages) = idx_item
        raw = call_model(client, args.deployment, messages)
        pred = parse_belief_json(raw)
        return idx, turn, shown, pred

    records: list[dict] = [None] * len(prepared)  # type: ignore[list-item]
    done = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for idx, turn, shown, pred in pool.map(run_one, enumerate(prepared)):
            prec, rec, f1 = slot_f1(pred, turn["gold_belief"])
            records[idx] = {
                "dialogue_id": turn["dialogue_id"],
                "service": turn["service"],
                "schemas_shown": shown,
                "gold_in_prompt": turn["service"] in shown,
                "gold": turn["gold_belief"],
                "pred": pred,
                "correct": exact_match(pred, turn["gold_belief"]),
                "slot_precision": prec,
                "slot_recall": rec,
                "slot_f1": f1,
            }
            done += 1
            if done % 50 == 0 or done == len(prepared):
                jga_so_far = sum(r["correct"] for r in records if r) / done * 100
                print(f"  [{done:>5}/{len(prepared)}] running JGA {jga_so_far:.1f}")

    n = len(records)
    summary = {
        "mode": args.mode,
        "deployment": args.deployment,
        "split": args.split,
        "n_turns": n,
        "seed": args.seed,
        "n_schemas": args.n_schemas,
        "n_distractors": args.n_distractors,
        "jga": round(sum(r["correct"] for r in records) / n * 100, 2),
        "slot_f1": round(sum(r["slot_f1"] for r in records) / n * 100, 2),
        "gold_in_prompt_rate": round(
            sum(r["gold_in_prompt"] for r in records) / n * 100, 2
        ),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    with (args.output_dir / "turns.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n  JGA                 {summary['jga']:.1f}")
    print(f"  Slot F1             {summary['slot_f1']:.1f}")
    print(f"  Gold in prompt      {summary['gold_in_prompt_rate']:.1f}%")
    print(f"\n[out] {args.output_dir}/summary.json  and  turns.jsonl")
    return summary


def main() -> None:
    load_dotenv_if_present()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=MODES, required=True)
    ap.add_argument(
        "--deployment", default=os.environ.get("DEPLOYMENT", "gpt-4.1-mini")
    )
    ap.add_argument("--endpoint", default=None, help="defaults to $AOAI_ENDPOINT")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--split", default="test", choices=["train", "dev", "test"])
    ap.add_argument("--n", type=int, default=200, help="turns to sample; 0 = all")
    ap.add_argument("--n-schemas", type=int, default=1, help="how many to retrieve")
    ap.add_argument("--n-distractors", type=int, default=2)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output-dir", type=Path, default=HERE / "results" / "run")
    evaluate(ap.parse_args())


if __name__ == "__main__":
    main()
