#!/usr/bin/env python3
"""Require behavior contracts for newly added hosted-agent samples."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path, PurePosixPath
from typing import Iterable

import yaml

from hosted_agent_fixture import fixture_dir_for_sample
from hosted_agent_test_spec import SpecError, build_plan, load_spec

SAMPLE_ROOTS = (
    "samples/python/hosted-agents",
    "samples/csharp/hosted-agents",
)
DOCUMENTATION_PATH = ".azure-pipelines/hosted-agent-tests/README.md"
DOCUMENTATION_URL = (
    "https://github.com/microsoft-foundry/foundry-samples/blob/main/"
    f"{DOCUMENTATION_PATH}#resolving-contract-policy-failures"
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def manifest_paths_at(repo: Path, revision: str) -> set[PurePosixPath]:
    output = _git(repo, "ls-tree", "-r", "--name-only", revision, "--", *SAMPLE_ROOTS)
    return {
        PurePosixPath(line)
        for line in output.splitlines()
        if line.endswith("/azure.yaml")
    }


def renamed_manifest_destinations(
    repo: Path, base: str, head: str
) -> set[PurePosixPath]:
    """Return manifest destinations Git identifies as renames rather than additions."""
    output = _git(
        repo,
        "diff",
        "--name-status",
        "-z",
        "--find-renames",
        base,
        head,
        "--",
        *SAMPLE_ROOTS,
    )
    tokens = iter(output.rstrip("\0").split("\0")) if output else iter(())
    destinations: set[PurePosixPath] = set()
    for status in tokens:
        if status.startswith(("R", "C")):
            next(tokens)
            destination = PurePosixPath(next(tokens))
            if status.startswith("R") and destination.name == "azure.yaml":
                destinations.add(destination)
        else:
            next(tokens)
    return destinations


def new_sample_dirs(
    base_manifests: set[PurePosixPath],
    head_manifests: set[PurePosixPath],
    renamed_destinations: set[PurePosixPath] | None = None,
) -> list[PurePosixPath]:
    """Return genuinely added sample roots; updates and detected moves are ignored."""
    added = head_manifests - base_manifests - (renamed_destinations or set())
    return sorted(path.parent for path in added)


def _selected_protocol(manifest_path: Path) -> str:
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"could not read hosted-agent protocols: {error}") from error
    if not isinstance(manifest, dict) or not isinstance(manifest.get("services"), dict):
        raise ValueError("services must be a mapping")

    protocols: set[str] = set()
    for service in manifest["services"].values():
        if not isinstance(service, dict) or service.get("host") != "azure.ai.agent":
            continue
        entries = service.get("protocols", [])
        if not isinstance(entries, list):
            raise ValueError("azure.ai.agent protocols must be a sequence")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("each azure.ai.agent protocol must be a mapping")
            protocol = entry.get("protocol")
            if protocol in {"responses", "invocations"}:
                protocols.add(protocol)
    if len(protocols) != 1:
        raise ValueError(
            "expected exactly one supported protocol: responses or invocations"
        )
    return protocols.pop()


def _validation_commands(spec_path: PurePosixPath, protocol: str) -> str:
    return (
        "Validate:\n"
        "  python3 .github/scripts/hosted_agent_test_spec.py validate \\\n"
        f"    --spec {spec_path}\n\n"
        "Plan:\n"
        "  python3 .github/scripts/hosted_agent_test_spec.py plan \\\n"
        f"    --spec {spec_path} \\\n"
        f"    --protocol {protocol} \\\n"
        "    --output /tmp/hosted-agent-test-plan.json"
    )


def _missing_contract_error(
    sample: PurePosixPath, spec_path: PurePosixPath, protocol: str
) -> str:
    return (
        "Missing hosted-agent behavior contract\n\n"
        f"New sample:\n  {sample}\n\n"
        f"Required contract:\n  {spec_path}\n\n"
        f"Detected protocol:\n  {protocol}\n\n"
        "How to fix:\n"
        "  1. Create test-spec.yml at the required path above.\n"
        "  2. Set sample.owner and sample.experiences.\n"
        "  3. Add deterministic turns and assertions for the sample's defining behavior.\n"
        "  4. Run both commands below before pushing.\n\n"
        f"{_validation_commands(spec_path, protocol)}\n\n"
        f"Documentation:\n  {DOCUMENTATION_URL}"
    )


def _invalid_contract_error(
    spec_path: PurePosixPath, protocol: str, error: SpecError
) -> str:
    return (
        "Invalid hosted-agent behavior contract\n\n"
        f"Contract:\n  {spec_path}\n\n"
        f"Problem:\n  {error}\n\n"
        f"{_validation_commands(spec_path, protocol)}\n\n"
        f"Documentation:\n  {DOCUMENTATION_URL}"
    )


def check_new_samples(repo: Path, samples: Iterable[PurePosixPath]) -> list[str]:
    errors: list[str] = []
    for sample in samples:
        manifest_path = repo / sample / "azure.yaml"
        if (repo / sample / ".ci-skip").is_file():
            continue
        try:
            fixture_dir = fixture_dir_for_sample(str(sample))
        except ValueError as error:
            errors.append(f"{sample}: {error}\n\nDocumentation:\n  {DOCUMENTATION_URL}")
            continue
        try:
            protocol = _selected_protocol(manifest_path)
        except ValueError as error:
            errors.append(
                "Invalid hosted-agent protocol declaration\n\n"
                f"Manifest:\n  {manifest_path.relative_to(repo).as_posix()}\n\n"
                f"Problem:\n  {error}\n\n"
                f"Documentation:\n  {DOCUMENTATION_URL}"
            )
            continue
        relative_spec = fixture_dir / "test-spec.yml"
        spec_path = repo / relative_spec
        if not spec_path.is_file():
            errors.append(_missing_contract_error(sample, relative_spec, protocol))
            continue
        try:
            document = load_spec(spec_path)
            build_plan(document, protocol=protocol)
        except SpecError as error:
            errors.append(_invalid_contract_error(relative_spec, protocol, error))
    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="base revision or merge base")
    parser.add_argument("--head", default="HEAD", help="head revision (default: HEAD)")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    repo = args.repo_root.resolve()
    try:
        base_manifests = manifest_paths_at(repo, args.base)
        head_manifests = manifest_paths_at(repo, args.head)
        renamed = renamed_manifest_destinations(repo, args.base, args.head)
        samples = new_sample_dirs(base_manifests, head_manifests, renamed)
        errors = check_new_samples(repo, samples)
    except (RuntimeError, ValueError) as error:
        print(f"::error::Could not evaluate hosted-agent contract coverage: {error}")
        return 2

    if errors:
        for error in errors:
            print(f"::error::{error}")
        print(
            f"{len(errors)} new hosted-agent sample(s) are missing a valid behavior contract."
        )
        return 1

    if samples:
        print(
            f"Validated behavior contracts for {len(samples)} new hosted-agent sample(s)."
        )
    else:
        print(
            "No new hosted-agent samples detected; existing sample updates are not evaluated."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
