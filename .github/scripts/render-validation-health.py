#!/usr/bin/env python3
"""Render the public validation health dashboard pilot as Markdown."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse


STATUS_DISPLAY = {
    "pass": "✅ Pass",
    "failure": "❌ Failed",
    "error": "⚠️ Warning",
}
LEVELS = ("l3", "l4")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class ContractError(ValueError):
    """Raised when dashboard configuration or result data is invalid."""


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"{label} file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be a JSON object")
    return value


def validate_path(path: Any) -> str:
    if not isinstance(path, str) or not path.startswith("samples/"):
        raise ContractError(f"sample path must be a string under samples/: {path!r}")
    parts = Path(path).parts
    if Path(path).is_absolute() or ".." in parts or "." in parts:
        raise ContractError(f"sample path must be repository-relative: {path!r}")
    if any(character in path for character in ("|", "`", "\r", "\n")):
        raise ContractError(f"sample path contains unsupported Markdown characters: {path!r}")
    return Path(path).as_posix()


def load_config(path: Path, repo_root: Path) -> tuple[str, list[str]]:
    config = load_json(path, "pilot config")
    if config.get("schema_version") != 1:
        raise ContractError("pilot config schema_version must be 1")

    repository = config.get("repository")
    if not isinstance(repository, str) or not REPOSITORY_PATTERN.fullmatch(repository):
        raise ContractError("pilot config repository must be owner/name")

    raw_samples = config.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ContractError("pilot config samples must be a non-empty list")

    samples = [validate_path(sample) for sample in raw_samples]
    if len(samples) != len(set(samples)):
        raise ContractError("pilot config samples must not contain duplicates")
    if samples != sorted(samples):
        raise ContractError("pilot config samples must be sorted")

    for sample in samples:
        if not (repo_root / sample).is_dir():
            raise ContractError(f"configured sample directory does not exist: {sample}")

    return repository, samples


def parse_utc_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError(f"{field} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{field} is not a valid timestamp: {value!r}") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ContractError(f"{field} must use UTC")
    return parsed


def validate_url(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractError(f"{field} must be a string")
    try:
        parsed = urlparse(value)
    except ValueError as exc:
        raise ContractError(f"{field} must be an absolute HTTP(S) URL") from exc
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ContractError(f"{field} must be an absolute HTTP(S) URL")
    if any(ord(character) < 32 for character in value):
        raise ContractError(f"{field} must not contain control characters")
    return value


def markdown_url(value: str) -> str:
    return quote(value, safe=":/?#@!$&'*+,;=%._~-")


def load_results(path: Path | None, selected_samples: set[str]) -> tuple[str | None, dict[str, Any]]:
    if path is None:
        return None, {}

    payload = load_json(path, "results")
    if payload.get("schema_version") != 1:
        raise ContractError("results schema_version must be 1")

    source_sha = payload.get("source_sha")
    if not isinstance(source_sha, str) or not SHA_PATTERN.fullmatch(source_sha):
        raise ContractError("results source_sha must be a full lowercase Git SHA")

    raw_results = payload.get("results")
    if not isinstance(raw_results, dict):
        raise ContractError("results must be a JSON object")

    selected: dict[str, Any] = {}
    for sample in selected_samples:
        if sample not in raw_results:
            continue
        sample_result = raw_results[sample]
        if not isinstance(sample_result, dict):
            raise ContractError(f"result for {sample} must be a JSON object")
        unknown_levels = set(sample_result) - set(LEVELS)
        if unknown_levels:
            raise ContractError(
                f"result for {sample} has unsupported levels: {sorted(unknown_levels)}"
            )

        selected[sample] = {}
        for level in LEVELS:
            if level not in sample_result:
                continue
            level_result = sample_result[level]
            if not isinstance(level_result, dict):
                raise ContractError(f"{sample}.{level} must be a JSON object")
            unknown_fields = set(level_result) - {"status", "run_at", "evidence_url"}
            if unknown_fields:
                raise ContractError(
                    f"{sample}.{level} has unsupported fields: {sorted(unknown_fields)}"
                )
            status = level_result.get("status")
            if not isinstance(status, str) or status not in STATUS_DISPLAY:
                raise ContractError(
                    f"{sample}.{level}.status must be one of {sorted(STATUS_DISPLAY)}"
                )
            run_at = parse_utc_timestamp(level_result.get("run_at"), f"{sample}.{level}.run_at")
            evidence_url = validate_url(
                level_result.get("evidence_url"), f"{sample}.{level}.evidence_url"
            )
            selected[sample][level] = {
                "status": status,
                "run_at": run_at,
                "evidence_url": evidence_url,
            }

    return source_sha, selected


def resolve_source_sha(repo_root: Path, result_sha: str | None, argument_sha: str | None) -> str:
    if result_sha is not None:
        if argument_sha is not None and argument_sha != result_sha:
            raise ContractError("--source-sha does not match results source_sha")
        return result_sha
    if argument_sha is not None:
        if not SHA_PATTERN.fullmatch(argument_sha):
            raise ContractError("--source-sha must be a full lowercase Git SHA")
        return argument_sha
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ContractError("could not resolve source SHA from the repository") from exc


def render_status(result: dict[str, Any] | None) -> tuple[str, str]:
    if result is None:
        return "⚪ Never run", "—"
    display = STATUS_DISPLAY[result["status"]]
    evidence_url = result["evidence_url"]
    if evidence_url:
        display = f"[{display}]({markdown_url(evidence_url)})"
    run_at = result["run_at"].strftime("%Y-%m-%d %H:%M UTC")
    return display, run_at


def render_markdown(
    repository: str,
    samples: list[str],
    results: dict[str, Any],
    source_sha: str,
    generated_at: datetime,
) -> str:
    lines = [
        "# Validation Health Dashboard",
        "",
        (
            f"_Generated {generated_at.strftime('%Y-%m-%d %H:%M UTC')} from "
            f"[`{source_sha[:12]}`](https://github.com/{repository}/commit/{source_sha}). "
            f"Pilot scope: {len(samples)} samples._"
        ),
        "",
        "| Sample | L3 | Last L3 run | L4 | Last L4 run |",
        "|---|---|---|---|---|",
    ]

    for sample in samples:
        link = f"https://github.com/{repository}/tree/main/{quote(sample, safe='/')}"
        sample_result = results.get(sample, {})
        l3_status, l3_run = render_status(sample_result.get("l3"))
        l4_status, l4_run = render_status(sample_result.get("l4"))
        lines.append(
            f"| [`{sample}`]({link}) | {l3_status} | {l3_run} | {l4_status} | {l4_run} |"
        )

    lines.extend(
        [
            "",
            "**Legend:** ✅ pass · ❌ sample failure · ⚠️ infrastructure/error · ⚪ never run",
            "",
            "> This pilot uses public validation results only. A missing result means "
            "“never run,” not “pass.”",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(".github/validation-health-pilot.json"),
        help="pilot scope JSON",
    )
    parser.add_argument("--results", type=Path, help="optional normalized result JSON")
    parser.add_argument("--output", type=Path, required=True, help="Markdown output path")
    parser.add_argument("--repo-root", type=Path, default=Path("."), help="repository root")
    parser.add_argument("--source-sha", help="source SHA when no results document is supplied")
    parser.add_argument(
        "--generated-at",
        help="override generation timestamp for deterministic tests (ISO-8601 UTC)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    try:
        repository, samples = load_config(args.config, repo_root)
        result_sha, results = load_results(args.results, set(samples))
        source_sha = resolve_source_sha(repo_root, result_sha, args.source_sha)
        if not SHA_PATTERN.fullmatch(source_sha):
            raise ContractError("resolved source SHA must be a full lowercase Git SHA")
        generated_at = (
            parse_utc_timestamp(args.generated_at, "--generated-at")
            if args.generated_at
            else datetime.now(timezone.utc)
        )
        markdown = render_markdown(repository, samples, results, source_sha, generated_at)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8", newline="\n")
    except (ContractError, OSError) as exc:
        print(f"render-validation-health: {exc}", file=sys.stderr)
        return 1
    print(f"render-validation-health: wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
