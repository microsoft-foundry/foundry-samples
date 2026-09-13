"""Build a text-only extraction dataset from the public ExtractBench corpus.

ExtractBench ships a PDF, a JSON Schema and a gold JSON answer per test case.
This script keeps only the text layer of each PDF, so the dataset it produces
measures schema-following and enumeration rather than page perception. Documents
tagged as perception-dependent are dropped rather than scored badly.

Two stages:

    prepare  select a difficulty band, extract text, write chat-format rows
    split    partition those rows into train and test without schema leakage

Nothing here contacts a model. The output of `split` is the input to
`evaluate.py`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DATASET_REPO = "llamaindex/ExtractBench"
BUCKETS = ("short", "medium", "long")

# Documents whose answers cannot be recovered from the text layer - they need
# the rendered page. Keeping them would charge a text-only model for a task it
# was never given.
PERCEPTION_TAGS = {"perception:P1", "perception:P2", "perception:P3"}

# The instruction every document is asked under. Changing it changes every
# number produced downstream, so it is a constant rather than a flag; pass a
# different one to evaluate.py with --system-prompt-file if you want to measure
# a variant.
SYSTEM_PROMPT = (
    "Extract every requested value from the document. Follow the supplied JSON "
    "Schema exactly. Return only one JSON object, use null for absent scalar "
    "values, and do not omit repeated records."
)


# --- corpus primitives ----------------------------------------------------


def leaf_count(value: Any) -> int:
    """Number of scalar leaves in a JSON value.

    This is the unit of difficulty for this benchmark. Document length is a poor
    proxy: a 60-page contract can have twenty fields, while a two-page price list
    can have two thousand.
    """
    if isinstance(value, dict):
        return sum(leaf_count(child) for child in value.values())
    if isinstance(value, list):
        return sum(leaf_count(child) for child in value)
    return 1


def schema_key(data_schema: str) -> str:
    """Stable id for a schema, so train and test can be kept schema-disjoint."""
    canonical = json.dumps(
        json.loads(data_schema), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def source_group(example_id: str) -> str:
    """Collapse per-page and per-region variants of one source document.

    `short/acme-p0003-r1` and `short/acme-p0007` are the same underlying PDF. A
    split that separated them would leak.
    """
    return re.sub(r"-p\d+(?:-r\d+)?$", "", example_id)


def extract_text(pdf_path: Path) -> str:
    """Concatenate the text layer, one marked block per page."""
    from pypdf import PdfReader

    pages = []
    for number, page in enumerate(PdfReader(pdf_path).pages, start=1):
        body = (page.extract_text() or "").strip()
        pages.append(f"<!-- Page {number} -->\n{body}")
    return "\n\n".join(pages).strip()


def to_row(raw: dict[str, Any], document_text: str) -> dict[str, Any]:
    """One chat-format example: schema plus document text in, gold JSON aside."""
    schema = json.loads(raw["data_schema"])
    user = (
        "JSON Schema:\n"
        + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        + "\n\nDocument text:\n"
        + document_text
    )
    return {
        "example_id": raw["id"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        "expected_output": json.loads(raw["expected_output"]),
    }


# --- stage 1: prepare -----------------------------------------------------


def _load_bucket(bucket: str, cache_dir: Path) -> Iterable[dict[str, Any]]:
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        repo_id=DATASET_REPO,
        repo_type="dataset",
        filename=f"{bucket}.jsonl",
        local_dir=cache_dir,
    )
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                row["bucket"] = bucket
                yield row


def _fetch_pdf(raw: dict[str, Any], cache_dir: Path) -> Path:
    from huggingface_hub import hf_hub_download

    local = cache_dir / raw["pdf"]
    if local.exists():
        return local
    return Path(
        hf_hub_download(
            repo_id=DATASET_REPO,
            repo_type="dataset",
            filename=raw["pdf"],
            local_dir=cache_dir,
        )
    )


def _annotate_tokens(rows: list[dict[str, Any]], tokenizer_name: str) -> None:
    """Attach prompt and gold token counts under one model's tokenizer."""
    try:
        from transformers import AutoTokenizer
    except ImportError:  # pragma: no cover - optional dependency
        raise SystemExit(
            "--tokenizer needs transformers: pip install transformers"
        ) from None

    tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
    for row in rows:
        user = next(m["content"] for m in row["messages"] if m["role"] == "user")
        gold = json.dumps(row["expected_output"], ensure_ascii=False)
        # The chat template adds a fixed preamble the raw encode does not see.
        row["prompt_tokens"] = len(tokenizer.encode(user)) + 64
        row["gold_tokens"] = len(tokenizer.encode(gold))


def cmd_prepare(args: argparse.Namespace) -> None:
    cache_dir = args.cache_dir.resolve()
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []

    for bucket in BUCKETS:
        if args.limit and len(selected) >= args.limit:
            break
        for raw in _load_bucket(bucket, cache_dir):
            if args.limit and len(selected) >= args.limit:
                break
            example_id = raw["id"]
            if set(raw.get("tags", [])) & PERCEPTION_TAGS:
                rejected.append({"id": example_id, "reason": "perception"})
                continue
            leaves = leaf_count(json.loads(raw["expected_output"]))
            if not args.min_leaves < leaves <= args.max_leaves:
                rejected.append({"id": example_id, "reason": f"leaves={leaves}"})
                continue
            if len(raw["data_schema"]) > args.max_schema_chars:
                rejected.append({"id": example_id, "reason": "schema_too_long"})
                continue

            # The PDF is fetched last: everything above is decidable from the
            # metadata, and the corpus is many gigabytes of documents that this
            # band does not want.
            try:
                text = extract_text(_fetch_pdf(raw, cache_dir))
            except (
                Exception
            ) as exc:  # noqa: BLE001 - one bad PDF must not stop the build
                rejected.append({"id": example_id, "reason": f"pdf_error: {exc}"})
                continue
            if len(text) < args.min_text_chars:
                rejected.append({"id": example_id, "reason": f"text={len(text)}"})
                continue

            row = to_row(raw, text)
            row["bucket"] = raw["bucket"]
            row["leaf_count"] = leaves
            row["schema_key"] = schema_key(raw["data_schema"])
            row["source_group"] = source_group(example_id)
            selected.append(row)
            print(f"[keep {len(selected):3d}] {example_id} leaves={leaves}")

    if not selected:
        raise SystemExit("no documents survived the filters")

    if args.tokenizer:
        _annotate_tokens(selected, args.tokenizer)
        budget = args.context - args.max_output_tokens
        kept = []
        for row in selected:
            if row["prompt_tokens"] > budget:
                rejected.append(
                    {"id": row["example_id"], "reason": "prompt_over_budget"}
                )
            elif row["gold_tokens"] * args.gold_margin > args.max_output_tokens:
                rejected.append({"id": row["example_id"], "reason": "gold_over_budget"})
            else:
                kept.append(row)
        print(f"\ntoken envelope ({args.tokenizer}): {len(selected)} -> {len(kept)}")
        selected = kept

    selected.sort(key=lambda row: row["example_id"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(args.out, selected)

    leaves = sorted(row["leaf_count"] for row in selected)
    print(f"\nwrote {args.out}: {len(selected)} documents")
    print(f"  schemas       {len({r['schema_key'] for r in selected})}")
    print(f"  source groups {len({r['source_group'] for r in selected})}")
    print(
        f"  leaf count    min {leaves[0]} / median {leaves[len(leaves) // 2]} / max {leaves[-1]}"
    )
    print(f"  buckets       {dict(Counter(r['bucket'] for r in selected))}")
    print(
        f"  rejected      {len(rejected)} {dict(Counter(r['reason'].split(':')[0].split('=')[0] for r in rejected))}"
    )


# --- stage 2: split -------------------------------------------------------


def partition(
    rows: list[dict[str, Any]], train_target: int, seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split by schema, blind to model behaviour.

    Schemas are the unit because a shared schema is the strongest form of leak
    here: half the answer is the shape of the answer. Assignment is a seeded
    shuffle and never looks at how any model scores, so the defects the test set
    is meant to expose are not quietly routed into training.

    Test deliberately gets the larger share. Reinforcement fine-tuning draws
    several rollouts per training document, so training documents are reused and
    evaluation documents are not; the test set is the scarce resource.
    """
    by_schema: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_schema[row["schema_key"]].append(row)

    schemas = sorted(by_schema)
    random.Random(seed).shuffle(schemas)

    train_schemas: set[str] = set()
    count = 0
    for schema in schemas:
        if count >= train_target:
            break
        train_schemas.add(schema)
        count += len(by_schema[schema])

    train = [row for row in rows if row["schema_key"] in train_schemas]
    test = [row for row in rows if row["schema_key"] not in train_schemas]
    if not train or not test:
        raise SystemExit("degenerate split: lower --train-target")

    leaked_schemas = {r["schema_key"] for r in train} & {r["schema_key"] for r in test}
    if leaked_schemas:
        raise SystemExit(f"schema leak: {sorted(leaked_schemas)}")
    leaked_groups = {r["source_group"] for r in train} & {
        r["source_group"] for r in test
    }
    if leaked_groups:
        raise SystemExit(f"source_group leak: {sorted(leaked_groups)}")
    return train, test


def cmd_split(args: argparse.Namespace) -> None:
    rows = _read_jsonl(args.source)
    train, test = partition(rows, args.train_target, args.seed)
    _write_jsonl(args.train_out, train)
    _write_jsonl(args.test_out, test)
    print(f"source {args.source}: {len(rows)} documents, seed {args.seed}")
    for name, split, path in (
        ("train", train, args.train_out),
        ("test", test, args.test_out),
    ):
        leaves = sorted(row["leaf_count"] for row in split)
        schemas = len({row["schema_key"] for row in split})
        print(
            f"  {name:5s} {len(split):3d} documents  {schemas:2d} schemas  "
            f"leaves {leaves[0]}-{leaves[-1]} (median {int(statistics.median(leaves))})  -> {path}"
        )


# --- io -------------------------------------------------------------------


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prep = sub.add_parser("prepare", help="download and filter into a difficulty band")
    prep.add_argument("--out", type=Path, default=Path("data/band.jsonl"))
    prep.add_argument("--cache-dir", type=Path, default=Path("data/corpus"))
    prep.add_argument("--min-leaves", type=int, default=200)
    prep.add_argument("--max-leaves", type=int, default=3000)
    prep.add_argument("--max-schema-chars", type=int, default=50_000)
    prep.add_argument("--min-text-chars", type=int, default=500)
    prep.add_argument(
        "--limit",
        type=int,
        help="stop after N documents, for a cheap smoke test of the download path",
    )
    prep.add_argument(
        "--tokenizer",
        help="optional: drop rows that do not fit this model's context window",
    )
    prep.add_argument("--context", type=int, default=32_768)
    prep.add_argument("--max-output-tokens", type=int, default=15_360)
    prep.add_argument("--gold-margin", type=float, default=1.3)
    prep.set_defaults(func=cmd_prepare)

    split = sub.add_parser(
        "split", help="partition into schema-disjoint train and test"
    )
    split.add_argument("--source", type=Path, default=Path("data/band.jsonl"))
    split.add_argument("--train-out", type=Path, default=Path("data/band_train.jsonl"))
    split.add_argument("--test-out", type=Path, default=Path("data/band_test.jsonl"))
    split.add_argument("--train-target", type=int, default=16)
    split.add_argument("--seed", type=int, default=0)
    split.set_defaults(func=cmd_split)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
