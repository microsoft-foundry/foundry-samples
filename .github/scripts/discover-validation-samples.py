#!/usr/bin/env python3
"""Discover the full sample inventory and emit deterministic validation matrices."""

from __future__ import annotations

import argparse
import json
import re
import stat
from pathlib import Path

import yaml

SUPPORTED_LANGUAGES = {
    "csharp": "csharp",
    "java": "java",
    "python": "python",
    "typescript": "typescript",
    "javascript": "typescript",
}


SAMPLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
RESERVED_SAMPLE_IDS = {"manifest"}
RESERVED_SAMPLE_ID_PATTERN = re.compile(r"^run-\d+-\d+$")


class DiscoveryError(ValueError):
    """A sample metadata error that should stop discovery."""


def sample_id(path: str) -> str:
    return path.removeprefix("samples/").replace("/", "-")


def validate_sample_id(identifier: str, path: str) -> None:
    """Reject IDs that would be unsafe or ambiguous downstream.

    Consumers embed a sample's derived ID directly in artifact names
    (``validation-pilot-{id}``) and in GitHub Actions matrix job display
    names (parsed as the first comma-separated field, e.g.
    ``build-readiness ({id}, ...)``). An ID containing a comma or
    parenthesis would break that parsing, and an ID equal to "manifest" or
    matching "run-<digits>-<digits>" would collide with this workflow's own
    reserved artifact names (``validation-pilot-manifest``,
    ``validation-pilot-run-{run_id}-{run_attempt}``).
    """
    if not SAMPLE_ID_PATTERN.fullmatch(identifier):
        raise DiscoveryError(
            f"{path}: derived sample ID '{identifier}' must contain only "
            "letters, digits, '-', and '_'"
        )
    if identifier in RESERVED_SAMPLE_IDS or RESERVED_SAMPLE_ID_PATTERN.fullmatch(identifier):
        raise DiscoveryError(
            f"{path}: derived sample ID '{identifier}' collides with a reserved "
            "validation-pilot artifact name"
        )


def metadata_path(root: Path, metadata: Path) -> str:
    return metadata.relative_to(root).as_posix()


def validate_metadata_file(root: Path, metadata: Path) -> None:
    path = metadata_path(root, metadata)
    try:
        resolved = metadata.resolve(strict=True)
        mode = resolved.stat().st_mode
    except OSError as exc:
        raise DiscoveryError(f"{path}: could not inspect sample metadata: {exc}") from exc

    if not resolved.is_relative_to(root):
        raise DiscoveryError(f"{path}: sample metadata resolves outside the repository root")
    if not stat.S_ISREG(mode):
        raise DiscoveryError(f"{path}: sample metadata is not a regular file")


def live_service_declaration(root: Path, metadata: Path) -> tuple[bool, str]:
    path = metadata_path(root, metadata)
    try:
        contents = metadata.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return False, f"{path}: could not read sample metadata: {exc}"

    try:
        document = yaml.safe_load(contents)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        problem = getattr(exc, "problem", None) or str(exc)
        return False, f"{path}: invalid YAML{location}: {problem}"

    if isinstance(document, dict) and "l4" in document:
        raise DiscoveryError(
            f"{path}: legacy top-level key 'l4' is unsupported; "
            "rename it to 'live_service_validation'"
        )
    return isinstance(document, dict) and "live_service_validation" in document, ""


def discover(root: Path) -> dict:
    root = root.resolve()
    discovered = []
    paths_by_id = {}
    for metadata in sorted(root.glob("samples/**/sample.yaml")):
        validate_metadata_file(root, metadata)
        path = metadata.parent.relative_to(root).as_posix()
        identifier = sample_id(path)
        validate_sample_id(identifier, path)
        if identifier in paths_by_id:
            raise DiscoveryError(
                f"{metadata_path(root, metadata)}: duplicate derived sample ID "
                f"'{identifier}' also produced by {paths_by_id[identifier]}/sample.yaml"
            )
        paths_by_id[identifier] = path
        discovered.append((identifier, path, metadata))

    samples = []
    for identifier, path, metadata in discovered:
        language = path.split("/")[1]
        validator_language = SUPPORTED_LANGUAGES.get(language)
        live_service_validation_declared, metadata_error = live_service_declaration(
            root, metadata
        )
        sample = {
            "id": identifier,
            "path": path,
            "language": language,
            "shape": "full-fleet",
        }
        samples.append(sample)
        sample["validator_language"] = validator_language or ""
        sample["eligible"] = validator_language is not None and not metadata_error
        sample["skip_reason"] = (
            metadata_error
            or (
                ""
                if validator_language
                else f"language '{language}' is not supported by build readiness"
            )
        )
        sample["live_service_validation_declared"] = live_service_validation_declared

    identities = [
        {key: sample[key] for key in ("id", "path", "language", "shape")}
        for sample in samples
    ]
    return {
        "schema_version": 2,
        "samples": identities,
        "validation": {
            sample["id"]: {
                key: sample[key]
                for key in (
                    "validator_language",
                    "eligible",
                    "skip_reason",
                    "live_service_validation_declared",
                )
            }
            for sample in samples
        },
        "matrix": samples,
    }


def write_matrix(path: Path, samples: list[dict]) -> None:
    path.write_text(
        json.dumps({"include": samples}, separators=(",", ":")),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--build-readiness-matrix", type=Path)
    parser.add_argument("--live-service-matrix", type=Path)
    args = parser.parse_args()

    try:
        payload = discover(args.root.resolve())
    except DiscoveryError as exc:
        parser.error(str(exc))
    args.manifest.write_text(
        json.dumps(
            {"schema_version": payload["schema_version"], "samples": payload["samples"], "validation": payload["validation"]},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    write_matrix(args.matrix, payload["matrix"])
    if args.build_readiness_matrix:
        write_matrix(
            args.build_readiness_matrix,
            [
                sample
                for sample in payload["matrix"]
                if not sample["live_service_validation_declared"]
            ],
        )
    if args.live_service_matrix:
        write_matrix(
            args.live_service_matrix,
            [
                sample
                for sample in payload["matrix"]
                if sample["live_service_validation_declared"]
            ],
        )
    print(json.dumps({"count": len(payload["matrix"]), "matrix": payload["matrix"]}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
