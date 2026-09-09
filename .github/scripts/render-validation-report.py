#!/usr/bin/env python3
"""Render a run-scoped summary from validation-pilot result artifacts."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from validation_pilot_common import (
    OUTCOMES,
    REPOSITORY_PATTERN,
    SHA_PATTERN,
    ContractError,
    collect as _common_collect,
    load_expected,
    sample_url,
)

SECTION_ORDER = ("sample failure", "infrastructure/error", "skipped/not-completed", "passed")
SECTION_LABELS = {
    "sample failure": "Sample failures",
    "infrastructure/error": "Infrastructure/errors",
    "skipped/not-completed": "Skipped/not-completed",
}
DIAGNOSTIC_LIMIT = 240
DIAGNOSTIC_PATTERNS = (
    re.compile(r"(?:\berror\b|^FAIL:|^ERROR:|^SKIP:|^runner error:)", re.IGNORECASE),
)
VERDICT_PATTERN = re.compile(r"^verdict=", re.IGNORECASE)


def collect(results_dir: Path, expected: list[dict[str, str]]) -> tuple[list[dict[str, Any]], bool]:
    """Wraps the shared collector, translating its `complete` flag back to
    this module's historical `incomplete` return convention."""
    records, complete = _common_collect(results_dir, expected)
    return records, not complete


def markdown_cell(value: Any) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("`", "'")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def diagnostic_excerpt(record: dict[str, Any]) -> str:
    if record.get("error"):
        value = record["error"]
    else:
        try:
            lines = [
                line.strip()
                for line in record["diagnostic_path"]
                .read_text(encoding="utf-8", errors="replace")
                .splitlines()
                if line.strip() and not line.lstrip().startswith("$ ")
            ]
        except OSError:
            return "No diagnostic excerpt available"
        value = next(
            (
                line
                for line in lines
                if any(pattern.search(line) for pattern in DIAGNOSTIC_PATTERNS)
            ),
            next(
                (line for line in reversed(lines) if VERDICT_PATTERN.search(line)),
                lines[0] if lines else "",
            ),
        )
    value = re.sub(
        r"(?i)(token|secret|password|api[_ -]?key)(\s*[:=]\s*)\S+",
        r"\1\2[redacted]",
        value,
    )
    value = re.sub(r"[\x00-\x1f\x7f]", " ", value)
    value = " ".join(value.split())
    if len(value) > DIAGNOSTIC_LIMIT:
        value = value[: DIAGNOSTIC_LIMIT - 1].rstrip() + "…"
    return value or "No diagnostic excerpt available"


def render_sample(record: dict[str, Any]) -> str:
    path = markdown_cell(record["sample"]["path"])
    url = sample_url(record)
    return f"[`{path}`]({url})" if url else f"`{path}`"


def render_rows(records: list[dict[str, Any]], outcome: str) -> list[str]:
    rows = []
    for record in records:
        sample = render_sample(record)
        stage = markdown_cell(record["completed_stage"])
        if outcome == "passed":
            rows.append(f"| {sample} | {stage} | {record['duration_seconds']}s |")
            continue
        reason = markdown_cell(diagnostic_excerpt(record))
        if outcome == "skipped/not-completed":
            next_action = "Add validator support or retain explicit skip"
        elif outcome == "infrastructure/error":
            next_action = "Inspect workflow job"
        else:
            next_action = "Inspect sample validation output"
        rows.append(f"| {sample} | {stage} | `{reason}` | {next_action} |")
    return rows


def render(records: list[dict[str, Any]], run_url: str | None, complete: bool) -> str:
    counts = {
        outcome: sum(record["outcome"] == outcome for record in records)
        for outcome in OUTCOMES
    }
    action_required = counts["sample failure"] + counts["infrastructure/error"]
    lines = ["## Validation report", ""]
    run = next((record.get("run") for record in records if record.get("run")), {})
    if run:
        metadata = f"Run {run.get('run_id')} · attempt {run.get('run_attempt')}"
        repository = run.get("repository")
        sha = run.get("sha")
        if (
            isinstance(repository, str)
            and REPOSITORY_PATTERN.fullmatch(repository)
            and isinstance(sha, str)
            and SHA_PATTERN.fullmatch(sha)
        ):
            metadata += (
                f" · validated SHA [`{sha[:12]}`]"
                f"(https://github.com/{repository}/commit/{sha})"
            )
        if run_url:
            metadata += f" · [Workflow run]({run_url})"
        lines.extend([f"_{metadata}_", ""])
    lines.extend(
        [
            f"> **Action required:** {action_required} record(s) need maintainer attention",
            f"> **Informational:** {counts['skipped/not-completed']} record(s) are intentionally skipped",
            f"> **Fleet {'complete' if complete else 'incomplete'}:** {len(records)} result record(s) reported",
            "",
            f"**{len(records)} total · {counts['passed']} passed · "
            f"{counts['sample failure']} sample failures · "
            f"{counts['infrastructure/error']} infrastructure/errors · "
            f"{counts['skipped/not-completed']} skipped/not-completed**",
            "",
        ]
    )
    for outcome in SECTION_ORDER[:3]:
        section_records = sorted(
            (record for record in records if record["outcome"] == outcome),
            key=lambda record: (record["sample"]["language"], record["sample"]["path"]),
        )
        if not section_records:
            continue
        lines.extend(
            [
                f"### {OUTCOMES[outcome].split(' ', 1)[0]} {SECTION_LABELS[outcome]} ({len(section_records)})",
                "",
                "| Sample | Stage | Reason | Next action |",
                "|---|---|---|---|",
                *render_rows(section_records, outcome),
                "",
            ]
        )
    passed = sorted(
        (record for record in records if record["outcome"] == "passed"),
        key=lambda record: (record["sample"]["language"], record["sample"]["path"]),
    )
    if passed:
        lines.extend(
            [
                f"<details><summary>{OUTCOMES['passed']} ({len(passed)})</summary>",
                "",
                "| Sample | Stage | Duration |",
                "|---|---|---:|",
                *render_rows(passed, "passed"),
                "",
                "</details>",
                "",
            ]
        )
    lines.extend(
        [
            f"**Legend:** {OUTCOMES['passed']} · {OUTCOMES['sample failure']} · "
            f"{OUTCOMES['infrastructure/error']} · {OUTCOMES['skipped/not-completed']}",
            "",
            "Diagnostics are summarized and sanitized. Full logs remain available from "
            "the workflow run, subject to GitHub Actions retention and authentication.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--expected-samples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-url")
    args = parser.parse_args()
    try:
        records, incomplete = collect(args.results_dir, load_expected(args.expected_samples))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            render(records, args.run_url, not incomplete),
            encoding="utf-8",
            newline="\n",
        )
    except (ContractError, OSError) as exc:
        print(f"render-validation-report: {exc}", file=sys.stderr)
        return 1
    if incomplete:
        print("render-validation-report: incomplete result handoff", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
