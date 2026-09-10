"""Load SGD and turn it into dialogue-state-tracking examples.

The serialisation here is the single source of truth: the retriever indexes
schemas through `schema_to_text`, and both evaluation and training render them
the same way, so nothing shifts between the two.
"""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data" / "sgd"


def load_schema_map(split_dir: Path) -> dict[str, dict]:
    """service_name -> schema dict. This is the registry the retriever searches."""
    entries = json.loads((split_dir / "schema.json").read_text(encoding="utf-8"))
    return {e["service_name"]: e for e in entries}


def schema_to_text(svc: dict) -> str:
    lines = [
        f"Service: {svc['service_name']}",
        f"  {svc['description']}",
        "  Slots:",
    ]
    for slot in svc.get("slots", []):
        kind = "categorical" if slot.get("is_categorical") else "free-text"
        vals = ""
        if slot.get("is_categorical") and slot.get("possible_values"):
            vals = f" (values: {', '.join(slot['possible_values'][:8])})"
        lines.append(f"    - {slot['name']} [{kind}]{vals}: {slot['description']}")
    lines.append("  Intents:")
    for intent in svc.get("intents", []):
        req = intent.get("required_slots", [])
        lines.append(
            f"    - {intent['name']}: {intent['description']}"
            + (f" | required: {', '.join(req)}" if req else "")
        )
    return "\n".join(lines)


def _flatten_slot_values(slot_values: dict[str, list[str]]) -> dict[str, str]:
    """SGD stores {slot: [variant, ...]}; take the first (canonical) variant."""
    return {k: v[0] for k, v in slot_values.items() if v}


def _normalise(belief: dict[str, str]) -> dict[str, str]:
    return {k: str(v).strip().lower() for k, v in belief.items()}


def load_turns(
    split_dir: Path,
    max_dialogues: int | None = None,
    seed: int = 42,
) -> list[dict]:
    """Return DST turns: {history, service, gold_belief}.

    One turn per USER utterance that carries a non-empty cumulative belief
    state. Turns with an empty gold state are dropped, which is what the
    official SGD evaluator does for joint goal accuracy.
    """
    import random

    dialogues: list[dict] = []
    for f in sorted(split_dir.glob("dialogues_*.json")):
        dialogues.extend(json.loads(f.read_text(encoding="utf-8")))
    if not dialogues:
        raise FileNotFoundError(
            f"no dialogues_*.json under {split_dir} - run download_sgd.py first"
        )

    if max_dialogues and max_dialogues < len(dialogues):
        dialogues = random.Random(seed).sample(dialogues, max_dialogues)

    turns: list[dict] = []
    for dlg in dialogues:
        history: list[str] = []
        services = dlg.get("services") or ["unknown"]
        service = services[0]

        for turn in dlg["turns"]:
            label = "User" if turn["speaker"] == "USER" else "System"
            history.append(f"{label}: {turn['utterance'].strip()}")
            if turn["speaker"] != "USER":
                continue

            belief: dict[str, str] = {}
            for frame in turn.get("frames", []):
                belief.update(
                    _flatten_slot_values(frame.get("state", {}).get("slot_values", {}))
                )
            if not belief:
                continue

            turns.append(
                {
                    "dialogue_id": dlg.get("dialogue_id", ""),
                    "history": list(history),
                    "service": service,
                    "gold_belief": _normalise(belief),
                }
            )
    return turns


def resolve_split(data_dir: Path, split: str) -> Path:
    d = data_dir / split
    if not d.exists():
        raise FileNotFoundError(
            f"{d} not found - run: python download_sgd.py --splits {split}"
        )
    return d
