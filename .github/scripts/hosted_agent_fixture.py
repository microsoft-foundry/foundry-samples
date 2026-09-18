#!/usr/bin/env python3
"""Resolve one-to-one paths between hosted-agent samples and shared CI fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Iterable

FIXTURE_ROOT = PurePosixPath(".azure-pipelines/hosted-agent-tests")
CI_SKIPLIST = PurePosixPath(".azure-pipelines/scripts/hosted-agent-samples-ci-skiplist")
CODE_CI_SKIPLIST = PurePosixPath(".azure-pipelines/scripts/hosted-agent-samples-code-ci-skiplist")
SAMPLE_ROOTS = {
    "python": PurePosixPath("samples/python/hosted-agents"),
    "csharp": PurePosixPath("samples/csharp/hosted-agents"),
}


class FixturePathError(ValueError):
    """Raised when a sample or fixture path is outside the supported layout."""


def _relative_path(path: str, *, label: str) -> PurePosixPath:
    value = PurePosixPath(path)
    if (
        value.is_absolute()
        or not value.parts
        or any(part in ("", ".", "..") for part in value.parts)
    ):
        raise FixturePathError(
            f"{label} must be a normalized repository-relative path: {path}"
        )
    return value


def fixture_dir_for_sample(sample_dir: str) -> PurePosixPath:
    """Return the fixture directory preserving the complete hosted-agent path."""
    sample = _relative_path(sample_dir, label="sample directory")
    for language, root in SAMPLE_ROOTS.items():
        try:
            relative = sample.relative_to(root)
        except ValueError:
            continue
        if not relative.parts:
            break
        return FIXTURE_ROOT / language / relative
    raise FixturePathError(
        "sample directory must be below samples/python/hosted-agents or "
        f"samples/csharp/hosted-agents: {sample_dir}"
    )


def sample_dir_for_fixture(fixture_path: str) -> PurePosixPath:
    """Return the sample directory addressed by a shared CI fixture file."""
    fixture = _relative_path(fixture_path, label="fixture")
    if fixture.name not in {"test-spec.yml", "test-payload.txt"}:
        raise FixturePathError(
            "fixture must end with test-spec.yml or test-payload.txt: "
            f"{fixture_path}"
        )
    try:
        relative = fixture.parent.relative_to(FIXTURE_ROOT)
    except ValueError as error:
        raise FixturePathError(
            f"fixture must be below {FIXTURE_ROOT}: {fixture_path}"
        ) from error
    if len(relative.parts) < 2 or relative.parts[0] not in SAMPLE_ROOTS:
        raise FixturePathError(
            "fixture must include a supported language and sample path: "
            f"{fixture_path}"
        )
    language, *sample_parts = relative.parts
    return SAMPLE_ROOTS[language].joinpath(*sample_parts)


def load_skiplist(repo: Path, filename: PurePosixPath) -> set[PurePosixPath]:
    try:
        lines = (repo / filename).read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as error:
        raise FixturePathError(f"Could not read {filename}: {error}") from error
    samples: set[PurePosixPath] = set()
    for number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            fixture_dir_for_sample(line)
            sample = PurePosixPath(line)
            if sample.as_posix() != line or "\\" in line:
                raise FixturePathError("expected an exact normalized sample directory")
        except FixturePathError as error:
            raise FixturePathError(f"{filename}:{number}: {error}") from error
        samples.add(sample)
    return samples


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    fixture = subparsers.add_parser("fixture-dir")
    fixture.add_argument("--sample-dir", required=True)

    sample = subparsers.add_parser("sample-dir")
    sample.add_argument("--fixture", required=True)
    skiplists = subparsers.add_parser("skiplists")
    skiplists.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "fixture-dir":
            result = fixture_dir_for_sample(args.sample_dir)
        elif args.command == "sample-dir":
            result = sample_dir_for_fixture(args.fixture)
        else:
            result = json.dumps({
                "samples": sorted(map(str, load_skiplist(args.repo_root, CI_SKIPLIST))),
                "code": sorted(map(str, load_skiplist(args.repo_root, CODE_CI_SKIPLIST))),
            })
    except FixturePathError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
