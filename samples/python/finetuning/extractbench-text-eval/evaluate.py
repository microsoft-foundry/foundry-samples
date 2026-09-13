"""Screen a model on text-only document extraction before fine-tuning it.

Reinforcement fine-tuning on this task moves models that have a broken
behaviour and barely moves models that do not. The three behaviour columns below
are measurable zero-shot, in one pass, on a model you have not touched - so the
decision to spend a training run can be made before the training run.

    refusal      the model declined to attempt the document at all
    valid JSON   the response parsed as a single JSON value
    coverage     how much of the expected leaf volume it emitted

A model failing none of these has no behaviour left to repair, and fine-tuning
it against this metric is usually a null result. A model failing several has
room, and that room is where the gain comes from.

    python evaluate.py --model gpt-4.1-mini --data data/band_test.jsonl

Temperature is 0 and repeats default to 4, because temperature 0 is not
deterministic on mixture-of-experts serving stacks: a single pass on this
benchmark can move by more than the effect you are trying to measure.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import grader

# Column, threshold, and the direction that counts as broken. The thresholds are
# deliberately loose: this is a screen meant to separate "nothing to repair"
# from "plenty to repair", not a quality bar.
SCREEN = (
    ("refusal", 0.0, "above"),
    ("valid_json", 0.95, "below"),
    ("coverage", 0.85, "below"),
)
REPORTED = ("f1", "precision", "recall", "coverage", "valid_json", "refusal", "empty")


# --- model access ---------------------------------------------------------


class _CachedToken:
    """Bearer token for keyless access, cached until shortly before expiry.

    Without the cache the OpenAI SDK calls the provider on every request, and
    under DefaultAzureCredential that can spawn a CLI subprocess each time -
    slow enough to dominate a long evaluation.
    """

    def __init__(self, scope: str = "https://ai.azure.com/.default"):
        from azure.identity import DefaultAzureCredential

        self._scope = scope
        self._credential = DefaultAzureCredential(process_timeout=60)
        self._token: str | None = None
        self._expires = 0.0

    def __call__(self) -> str:
        if self._token and time.time() < self._expires - 300:
            return self._token
        token = self._credential.get_token(self._scope)
        self._token = token.token
        self._expires = float(token.expires_on)
        return self._token


def make_client(base_url: str | None, endpoint: str | None):
    from openai import OpenAI

    if base_url:  # any OpenAI-compatible server, including a local one
        return OpenAI(
            base_url=base_url, api_key=os.environ.get("OPENAI_API_KEY", "none")
        )

    endpoint = endpoint or os.environ.get("AOAI_ENDPOINT")
    if not endpoint:
        raise SystemExit(
            "set AOAI_ENDPOINT (https://<your-resource>.openai.azure.com) or pass --base-url"
        )
    endpoint = endpoint.rstrip("/")
    if not endpoint.endswith("/openai/v1"):
        endpoint += "/openai/v1"
    return OpenAI(base_url=endpoint + "/", api_key=_CachedToken())


# --- one pass over the document set ---------------------------------------


def _ask(client, model: str, messages: list[dict[str, str]], max_tokens: int) -> str:
    """One completion, with a short retry on transient service errors.

    max_tokens matters more here than in most evaluations. The gold answers run
    to thousands of tokens, and a response cut off mid-object is not valid JSON,
    so a budget that is merely generous elsewhere reports this model as unable
    to produce JSON at all.
    """
    last: Exception | None = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - retry, then surface
            last = exc
            time.sleep(2**attempt)
    raise RuntimeError(f"completion failed after 3 attempts: {last}")


def run_pass(
    client,
    model: str,
    rows: list[dict[str, Any]],
    max_tokens: int,
    concurrency: int,
    system_prompt: str | None,
) -> list[dict[str, Any]]:
    def one(row: dict[str, Any]) -> dict[str, Any]:
        messages = list(row["messages"])
        if system_prompt is not None:
            messages = [
                {"role": "system", "content": system_prompt}
                if m["role"] == "system"
                else m
                for m in messages
            ]
        text = _ask(client, model, messages, max_tokens)
        record = {"example_id": row["example_id"], "response": text}
        record.update(grader.score_response(text, row["expected_output"]))
        return record

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        return list(pool.map(one, rows))


def macro_average(records: list[dict[str, Any]]) -> dict[str, float]:
    """Mean over documents, so a 2000-leaf document does not outvote fifty small ones."""
    return {key: statistics.fmean(r[key] for r in records) for key in REPORTED}


# --- reporting ------------------------------------------------------------


def _is_broken(column: str, value: float) -> bool:
    for name, threshold, direction in SCREEN:
        if name == column:
            return value > threshold if direction == "above" else value < threshold
    return False


def report(
    passes: list[dict[str, float]], model: str, data: Path, repeats: int
) -> None:
    print(f"\nmodel      {model}")
    print(f"documents  {data}")
    print(f"repeats    {repeats} at temperature 0\n")

    summary = {}
    for key in REPORTED:
        values = [p[key] for p in passes]
        summary[key] = (
            statistics.fmean(values),
            statistics.stdev(values) if len(values) > 1 else 0.0,
        )

    print(f"{'metric':<12}{'mean':>8}{'sd':>8}   screen")
    for key in REPORTED:
        mean, sd = summary[key]
        flag = ""
        threshold = next((t for n, t, _ in SCREEN if n == key), None)
        if threshold is not None:
            broken = _is_broken(key, mean)
            flag = "BROKEN" if broken else "ok"
            # A column sitting on its threshold is a judgement call, not a
            # measurement. Say so rather than letting the label decide.
            if abs(mean - threshold) < 0.05:
                flag += "  (borderline)"
        print(f"{key:<12}{mean:>8.4f}{sd:>8.4f}   {flag}")

    broken = [key for key, _, _ in SCREEN if _is_broken(key, summary[key][0])]
    f1 = summary["f1"][0]
    print(
        f"\nbroken behaviours  {len(broken)} of {len(SCREEN)}"
        + (f"  ({', '.join(broken)})" if broken else "")
    )
    print(f"room left (1 - f1) {1.0 - f1:.3f}")
    if broken:
        print(
            "\nThis model has behaviour to repair. Historically most of the room left\n"
            "is reachable, and the gain grows with the number of broken columns."
        )
    else:
        print(
            "\nNo broken behaviour. The room left is capability, not behaviour, and\n"
            "fine-tuning against this metric has tended to return nothing here.\n"
            "Spend the run on a model that fails a column, or change the metric."
        )
    if repeats < 4:
        print(
            f"\nWarning: {repeats} repeat(s). Temperature 0 is not deterministic on every\n"
            "serving stack; on this benchmark single passes have differed by more than\n"
            "0.10 f1. Use --repeats 4 before comparing two models."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model", required=True, help="deployment or model name")
    parser.add_argument("--data", type=Path, default=Path("data/band_test.jsonl"))
    parser.add_argument("--repeats", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=16_000)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--endpoint", help="defaults to $AOAI_ENDPOINT")
    parser.add_argument("--base-url", help="any OpenAI-compatible server instead")
    parser.add_argument(
        "--system-prompt-file", type=Path, help="override the baked-in prompt"
    )
    parser.add_argument(
        "--save", type=Path, help="write every response and per-document score"
    )
    args = parser.parse_args(argv)

    with open(args.data, encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if not rows:
        raise SystemExit(f"{args.data} is empty")

    system_prompt = (
        args.system_prompt_file.read_text(encoding="utf-8").strip()
        if args.system_prompt_file
        else None
    )
    client = make_client(args.base_url, args.endpoint)

    passes, everything = [], []
    for index in range(args.repeats):
        print(
            f"pass {index + 1}/{args.repeats} over {len(rows)} documents ...",
            flush=True,
        )
        records = run_pass(
            client, args.model, rows, args.max_tokens, args.concurrency, system_prompt
        )
        for record in records:
            record["pass"] = index
        everything.extend(records)
        passes.append(macro_average(records))

    report(passes, args.model, args.data, args.repeats)

    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        with open(args.save, "w", encoding="utf-8") as handle:
            for record in everything:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"\nwrote {args.save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
