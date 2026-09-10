"""Prompt construction, response parsing, and DST metrics.

`MODES` is the whole point of this sample. Every mode shows the model the same
dialogue and asks for the same JSON; the only thing that changes is how the
schema reaches the prompt.
"""
from __future__ import annotations

import json
import random
import re

from schema_retriever import SchemaRetriever
from sgd_data import schema_to_text

MODES = ("none", "oracle", "retrieved", "retrieved_distractor")

SYSTEM_TEMPLATE = """\
You are a dialogue state tracker for task-oriented conversations.

Your task: given a conversation history and the service schemas below, output \
the CURRENT CUMULATIVE belief state as a JSON object mapping slot names to values.

Rules:
- Output ONLY a valid JSON object on a single line.
- Use only slot names that appear in the schemas below.
- Include ALL slots mentioned so far (cumulative, not just the last turn).
- If no relevant slots have been mentioned, output: {{}}

{schemas_block}"""

SYSTEM_TEMPLATE_NO_SCHEMA = """\
You are a dialogue state tracker for task-oriented conversations.

Your task: given a conversation history, output the CURRENT CUMULATIVE belief \
state as a JSON object mapping slot names to values.

Rules:
- Output ONLY a valid JSON object on a single line.
- Include ALL slots mentioned so far (cumulative, not just the last turn).
- If no relevant slots have been mentioned, output: {}"""

USER_TEMPLATE = """\
Conversation history:
{history}

Extract the current belief state for service: {service}"""

SCHEMA_HEADER = "Service schemas (one is relevant; others may be distractors):\n"
SCHEMA_SEP = "\n" + "-" * 50 + "\n"


def build_schemas_block(schemas: list[dict]) -> str:
    return SCHEMA_HEADER + SCHEMA_SEP.join(schema_to_text(s) for s in schemas)


def select_schemas(
    history: list[str],
    service: str,
    schema_map: dict[str, dict],
    mode: str,
    retriever: SchemaRetriever | None,
    n_schemas: int,
    n_distractors: int,
    rng: random.Random,
) -> list[dict]:
    """Choose which schemas the model gets to see."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")
    if mode == "none":
        return []
    if mode == "oracle":
        gold = schema_map.get(service)
        return [gold] if gold else []

    if retriever is None:
        raise ValueError(f"mode={mode} requires a SchemaRetriever")
    schemas = retriever.retrieve(history, k=max(1, n_schemas))
    if mode == "retrieved_distractor" and n_distractors > 0:
        exclude = {s["service_name"] for s in schemas}
        schemas = schemas + retriever.sample_distractors(exclude, n_distractors, rng)
        rng.shuffle(schemas)
    return schemas


def build_messages(
    history: list[str],
    service: str,
    schemas: list[dict],
) -> list[dict]:
    system = (
        SYSTEM_TEMPLATE_NO_SCHEMA
        if not schemas
        else SYSTEM_TEMPLATE.format(schemas_block=build_schemas_block(schemas))
    )
    user = USER_TEMPLATE.format(history="\n".join(history), service=service)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_belief_json(raw: str) -> dict[str, str]:
    """Extract the belief state, tolerating markdown fences and trailing prose."""
    raw = re.sub(r"```(?:json)?\s*", "", raw.strip()).strip("`").strip()
    for candidate in (raw, (re.search(r"\{[^{}]*\}", raw, re.DOTALL) or [None])[0]):
        if not candidate:
            continue
        try:
            obj = json.loads(
                candidate if isinstance(candidate, str) else candidate.group()
            )
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue
        if isinstance(obj, dict):
            return {k: str(v).strip().lower() for k, v in obj.items()}
    return {}


def exact_match(pred: dict[str, str], gold: dict[str, str]) -> bool:
    """Joint goal accuracy for one turn: every slot exactly right, no extras."""
    return pred == gold


def slot_f1(pred: dict[str, str], gold: dict[str, str]) -> tuple[float, float, float]:
    pred_set = {f"{k}={v}" for k, v in pred.items()}
    gold_set = {f"{k}={v}" for k, v in gold.items()}
    if not gold_set and not pred_set:
        return 1.0, 1.0, 1.0
    if not pred_set or not gold_set:
        return 0.0, 0.0, 0.0
    tp = len(pred_set & gold_set)
    prec, rec = tp / len(pred_set), tp / len(gold_set)
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return prec, rec, f1
