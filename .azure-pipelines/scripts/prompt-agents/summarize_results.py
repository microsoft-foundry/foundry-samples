#!/usr/bin/env python3
"""Summarize every expected matrix cell, treating missing results as failures."""

import argparse
import json
from pathlib import Path
import re


def summarize(entries: list, artifacts: Path) -> tuple[str, bool]:
    lines = ["# Prompt Agent E2E", "", "| Sample | Profile | Result |", "|---|---|---|"]
    failed = False
    for entry in entries:
        combo = entry["comboId"]
        if not isinstance(combo, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", combo):
            raise ValueError("unsafe combo ID in discovery artifact")
        path = artifacts / f"PromptAgentResult-{combo}" / "run" / "result.json"
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
            status = result.get("status") if isinstance(result, dict) else None
        except (OSError, ValueError):
            status = None
        if status not in ("passed", "failed"):
            status = "missing/invalid result"
        recovery_path = path.parent / "recovery-result.json"
        try:
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            recovered = (isinstance(recovery, dict) and recovery.get("status") == "cleanup-only"
                         and type(recovery.get("exit_code")) is int and recovery["exit_code"] == 0
                         and recovery.get("cleanup_status") == "complete")
        except (OSError, ValueError):
            recovered = False
        if not recovered and status == "passed":
            status = "failed recovery"
        provision = path.parent.parent / "provision-ledger.json"
        if provision.exists():
            teardown = path.parent.parent / "teardown-result.json"
            try:
                teardown_status = json.loads(teardown.read_text(encoding="utf-8"))["status"]
            except (OSError, ValueError, KeyError, TypeError):
                teardown_status = None
            if teardown_status != "passed":
                status = "failed teardown"
        failed |= status != "passed"
        sample = entry["samplePath"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {sample} | {entry['executionProfile']} | {status} |")
    return "\n".join(lines) + "\n", failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entries", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    text, failed = summarize(json.loads(args.entries.read_text(encoding="utf-8")), args.artifacts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(text)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
