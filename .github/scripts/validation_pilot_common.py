#!/usr/bin/env python3
"""Shared contract/normalization logic for validation-pilot result consumers.

This module owns only the data layer that every consumer of validation-pilot
result artifacts (the Markdown report, the static dashboard, ...) must agree
on: manifest/result schema validation, sample identity checks, timestamp
parsing, and safe construction of a link to a sample at its validated commit.
Presentation (Markdown vs. HTML, escaping, layout) stays in each renderer.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

OUTCOMES = {
    "passed": "✅ Passed",
    "sample failure": "❌ Sample failure",
    "infrastructure/error": "⚠️ Infrastructure/error",
    "skipped/not-completed": "⏭️ Skipped/not-completed",
}
REQUIRED = {
    "schema_version", "sample", "outcome", "completed_stage", "duration_seconds",
    "diagnostic_reference", "artifact_reference", "completed_at", "run",
}
RUN_FIELDS = {"repository", "workflow", "run_id", "run_attempt", "sha", "ref", "started_at"}
SUPPORTED_SCHEMA_VERSIONS = {1, 2}
LEGACY_COMPLETED_STAGES = {
    "L3 validation": "build readiness validation",
    "L3 validation invocation": "build readiness invocation",
    "L4 validation": "live-service validation",
    "L4 validation invocation": "live-service validation invocation",
}
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")


class ContractError(ValueError):
    pass


class ExpectedSamples(list[dict[str, str]]):
    def __init__(self, samples: list[dict[str, str]], schema_version: int) -> None:
        super().__init__(samples)
        self.schema_version = schema_version


def _in(value: Any, container: Any) -> bool:
    """Membership test that treats an unhashable value as simply absent.

    Several checks below test membership of an untrusted JSON value (which
    may be a list or dict) against a fixed set/dict of valid values. A bare
    ``value in container`` raises ``TypeError`` for unhashable ``value``,
    which would abort normalization instead of producing the
    ``ContractError`` (and, in ``collect``, the infrastructure/error row)
    callers expect for any malformed artifact.
    """
    try:
        return value in container
    except TypeError:
        return False


def _is_supported_schema_version(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value in SUPPORTED_SCHEMA_VERSIONS


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"{label} not found: {path}") from exc
    except UnicodeError as exc:
        raise ContractError(f"{label} is not valid UTF-8: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"{label} is not valid JSON: {exc}") from exc


def timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError(f"{field} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{field} is not a valid timestamp") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ContractError(f"{field} must be UTC")
    return parsed


def sample_identity(value: Any, field: str) -> dict[str, str]:
    keys = {"id", "path", "language", "shape"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ContractError(f"{field} must contain exactly id, path, language, and shape")
    if any(not isinstance(value[key], str) or not value[key] for key in keys):
        raise ContractError(f"{field} fields must be non-empty strings")
    if not value["path"].startswith("samples/") or ".." in Path(value["path"]).parts:
        raise ContractError(f"{field}.path must be a safe repository-relative samples/ path")
    return {key: value[key] for key in keys}


def load_expected(path: Path) -> ExpectedSamples:
    payload = load_json(path, "sample manifest")
    if (
        not isinstance(payload, dict)
        or not _is_supported_schema_version(payload.get("schema_version"))
        or not isinstance(payload.get("samples"), list)
        or not payload["samples"]
    ):
        raise ContractError("sample manifest must contain a non-empty samples array")
    samples = [sample_identity(value, "manifest sample") for value in payload["samples"]]
    ids = [value["id"] for value in samples]
    if ids != sorted(set(ids)):
        raise ContractError("manifest samples must be sorted and unique by id")
    return ExpectedSamples(samples, payload["schema_version"])


def load_record(path: Path, expected: dict[str, str], expected_schema_version: int | None = None) -> dict[str, Any]:
    value = load_json(path, f"result artifact {path}")
    if (
        not isinstance(value, dict)
        or set(value) != REQUIRED
        or not _is_supported_schema_version(value.get("schema_version"))
    ):
        raise ContractError("result must be a supported schema object")
    missing = REQUIRED - value.keys()
    if missing:
        raise ContractError(f"result is missing fields: {sorted(missing)}")
    if expected_schema_version is not None and value["schema_version"] != expected_schema_version:
        raise ContractError(
            f"result schema_version {value['schema_version']!r} does not match manifest schema_version {expected_schema_version!r}"
        )
    sample = sample_identity(value["sample"], "result sample")
    if sample != expected:
        raise ContractError(f"sample identity does not match manifest: {sample['id']}")
    if not _in(value["outcome"], OUTCOMES):
        raise ContractError(f"unsupported outcome: {value['outcome']!r}")
    if not isinstance(value["completed_stage"], str) or not value["completed_stage"]:
        raise ContractError("completed_stage must be non-empty")
    if (
        not isinstance(value["duration_seconds"], (int, float))
        or isinstance(value["duration_seconds"], bool)
        or not math.isfinite(value["duration_seconds"])
        or value["duration_seconds"] < 0
    ):
        raise ContractError("duration_seconds must be a finite non-negative number")
    timestamp(value["completed_at"], "completed_at")
    run = value["run"]
    if not isinstance(run, dict):
        raise ContractError("run must be an object")
    run_fields = set(run)
    missing_run_fields = RUN_FIELDS - run_fields
    extra_run_fields = run_fields - RUN_FIELDS
    if missing_run_fields or extra_run_fields:
        problems = []
        if missing_run_fields:
            problems.append(f"missing fields: {sorted(missing_run_fields)}")
        if extra_run_fields:
            problems.append(f"extra fields: {sorted(extra_run_fields)}")
        raise ContractError(f"run has {'; '.join(problems)}")
    for field in RUN_FIELDS:
        if not isinstance(run[field], str) or not run[field]:
            raise ContractError(f"run.{field} must be a non-empty string")
    timestamp(run["started_at"], "run.started_at")
    for field in ("diagnostic_reference", "artifact_reference"):
        reference = value[field]
        if (
            not isinstance(reference, str)
            or not reference
            or Path(reference).is_absolute()
            or ".." in Path(reference).parts
            or len(Path(reference).parts) != 1
        ):
            raise ContractError(f"{field} must be a relative filename")
    diagnostic = path.parent / value["diagnostic_reference"]
    if not diagnostic.is_file():
        raise ContractError(f"missing diagnostic: {diagnostic}")
    completed_stage = LEGACY_COMPLETED_STAGES.get(
        value["completed_stage"], value["completed_stage"]
    )
    return {
        **value,
        "completed_stage": completed_stage,
        "completed_at": timestamp(value["completed_at"], "completed_at"),
        "diagnostic_path": diagnostic,
    }


def _load_run_fallback(results_dir: Path) -> dict[str, Any]:
    """Best-effort run metadata for synthetic missing/invalid records.

    The completeness job persists ``run-metadata.json`` alongside the
    per-sample result directories in the same combined artifact. Synthetic
    missing/invalid records have no per-sample ``run`` block of their own
    (there's no successful result to draw one from); without this fallback
    their Sample column can't link to the validated commit, and if every
    sample is missing/invalid, callers relying on the first populated `run`
    across all records get nothing at all and lose the run/commit context
    entirely. Any read/parse problem here is non-fatal -- it just falls back
    to an empty dict, matching the previous behavior.
    """
    try:
        payload = json.loads((results_dir / "run-metadata.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {key: payload[key] for key in RUN_FIELDS if key in payload}


def collect(results_dir: Path, expected: list[dict[str, str]]) -> tuple[list[dict[str, Any]], bool]:
    """Normalize every result artifact against the manifest.

    Returns (records sorted by sample path, complete). ``complete`` is False
    when any expected sample has no valid result, or an artifact is malformed.
    Missing/invalid entries are represented as `infrastructure/error` records
    carrying an `error` string, so callers can render a full picture without
    re-implementing the completeness contract.
    """
    if not results_dir.is_dir():
        raise ContractError(f"result artifact directory not found: {results_dir}")
    expected_by_id = {value["id"]: value for value in expected}
    expected_schema_version = getattr(expected, "schema_version", None)
    records: dict[str, dict[str, Any]] = {}
    incomplete = False
    run_fallback = _load_run_fallback(results_dir)
    for path in sorted(results_dir.glob("*/sample-result.json")):
        sample_id: Any = None
        try:
            raw = load_json(path, f"result artifact {path}")
            raw_sample = raw.get("sample") if isinstance(raw, dict) else None
            sample_id = raw_sample.get("id") if isinstance(raw_sample, dict) else None
            if not _in(sample_id, expected_by_id):
                raise ContractError(f"unexpected sample id: {sample_id!r}")
            if sample_id in records:
                raise ContractError(f"duplicate result artifact for {sample_id}")
            record = load_record(path, expected_by_id[sample_id], expected_schema_version)
            records[sample_id] = record
        except ContractError as exc:
            incomplete = True
            # Attribute the failure to the expected sample it claims to be,
            # so long as that sample doesn't already have a record -- that
            # keeps this one row per sample instead of also producing a
            # separate "missing" row for the same sample below. An artifact
            # that can't be attributed to any expected sample (or duplicates
            # one already recorded) becomes its own extra, orphaned row.
            if _in(sample_id, expected_by_id) and sample_id not in records:
                key = sample_id
                placeholder_sample = expected_by_id[sample_id]
            else:
                artifact_path = path.relative_to(results_dir).as_posix()
                key = f"invalid:{artifact_path}"
                placeholder_sample = {
                    "id": key,
                    "path": f"<invalid artifact: {artifact_path}>",
                    "language": "reporting", "shape": "error",
                }
            records[key] = {
                "sample": placeholder_sample,
                "outcome": "infrastructure/error", "completed_stage": "reporting",
                "duration_seconds": 0, "completed_at": None,
                "diagnostic_reference": "—", "artifact_reference": path.name, "run": dict(run_fallback),
                "error": str(exc),
            }
    for sample in expected:
        if sample["id"] not in records:
            incomplete = True
            records[f"missing:{sample['id']}"] = {
                "sample": sample, "outcome": "infrastructure/error",
                "completed_stage": "reporting", "duration_seconds": 0,
                "completed_at": None, "diagnostic_reference": "—",
                "artifact_reference": "—", "run": dict(run_fallback),
                "error": f"expected result artifact is missing for {sample['id']}",
            }
    return sorted(records.values(), key=lambda value: value["sample"]["path"]), not incomplete


def sample_url(record: dict[str, Any]) -> str | None:
    run = record.get("run", {})
    repository = run.get("repository")
    sha = run.get("sha")
    path = record["sample"]["path"]
    if (
        not isinstance(repository, str)
        or not REPOSITORY_PATTERN.fullmatch(repository)
        or not isinstance(sha, str)
        or not SHA_PATTERN.fullmatch(sha)
        or not isinstance(path, str)
        or not path.startswith("samples/")
        or ".." in Path(path).parts
    ):
        return None
    return f"https://github.com/{repository}/tree/{sha}/{quote(path, safe='/')}"
