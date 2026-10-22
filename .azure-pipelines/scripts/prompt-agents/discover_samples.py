#!/usr/bin/env python3
"""Discover prompt-agent E2E records without provisioning Azure resources."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".github" / "scripts"))
from hosted_agent_fixture import fixture_dir_for_sample, sample_dir_for_fixture

# Add sample roots here and their matching layout in hosted_agent_fixture.py.
SAMPLE_ROOTS = ("samples/cli/prompt-agents",)
FULL_RUN_PATHS = {
    ".azure-pipelines/prompt-agents-samples-ci.yml",
    ".github/scripts/hosted_agent_fixture.py",
    ".github/scripts/hosted_agent_test_spec.py",
}
CI_ROOT = ".azure-pipelines/scripts/prompt-agents"
FIXTURE_ROOT = ".azure-pipelines/prompt-agent-tests"
BLACKLIST_PATH = CI_ROOT + "/blacklist.json"


class DiscoveryError(ValueError):
    pass


class ManifestLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise DiscoveryError("manifest mapping keys must be strings")
        if key in result:
            raise DiscoveryError(f"duplicate manifest key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


ManifestLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping
)


def matrix_key(combo_id: str) -> str:
    readable = re.sub(r"[^A-Za-z0-9]+", "_", combo_id).strip("_")[:72]
    digest = hashlib.sha256(combo_id.encode("utf-8")).hexdigest()[:7]
    return f"{readable}_{digest}"


def sample_record(repo: Path, manifest: Path) -> dict:
    try:
        document = yaml.load(manifest.read_text(encoding="utf-8"), Loader=ManifestLoader)
        if not isinstance(document, dict) or not isinstance(document.get("services"), dict):
            raise DiscoveryError("services must be a mapping")
        if any(not isinstance(service, dict) for service in document["services"].values()):
            raise DiscoveryError("each service must be a mapping")
        agents = [
            (key, service) for key, service in document["services"].items()
            if service.get("host") == "azure.ai.agent"
        ]
        if len(agents) != 1:
            raise DiscoveryError("exactly one azure.ai.agent service is required")
        service_key, agent = agents[0]
        if agent.get("kind") != "prompt":
            raise DiscoveryError("agent kind must be prompt")
        harness_type = ""
        if "harness" in agent:
            harness = agent["harness"]
            if (
                not isinstance(harness, dict)
                or set(harness) != {"type"}
                or not isinstance(harness.get("type"), str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", harness["type"])
            ):
                raise DiscoveryError("harness.type must be a nonempty identifier when harness is present")
            harness_type = harness["type"]
        protocol_version = "1.0.0"
        if "protocols" in agent:
            protocols = agent["protocols"]
            if (
                not isinstance(protocols, list) or len(protocols) != 1
                or not isinstance(protocols[0], dict)
                or protocols[0].get("protocol") != "responses"
                or str(protocols[0].get("version", "1.0.0")) != "1.0.0"
            ):
                raise DiscoveryError("only one Responses 1.0.0 protocol is supported")
        name = document.get("name")
        if not isinstance(name, str) or not name.strip() or any(c in name for c in "\r\n"):
            raise DiscoveryError("name must be a nonempty single-line string")
        sample_path = manifest.parent.relative_to(repo).as_posix()
        sample_id = sample_path.removeprefix("samples/").replace("/", "-")
        return {
            "sampleId": sample_id,
            "samplePath": sample_path,
            "sampleName": name,
            "sampleLanguage": manifest.relative_to(repo).parts[1],
            "agentService": service_key,
            "agentKind": "prompt",
            "executionProfile": "managed" if harness_type else "prompt",
            "harnessType": harness_type,
            "protocol": "responses",
            "protocolVersion": protocol_version,
            "comboId": sample_id,
            "matrixKey": matrix_key(sample_id),
        }
    except (OSError, yaml.YAMLError, DiscoveryError) as error:
        raise DiscoveryError(f"{manifest.relative_to(repo).as_posix()}: {error}") from error


def load_blacklist(repo: Path) -> dict[str, str]:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise DiscoveryError(f"duplicate blacklist path: {key}")
            result[key] = value
        return result

    blacklist = json.loads((repo / BLACKLIST_PATH).read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
    if not isinstance(blacklist, dict):
        raise DiscoveryError("blacklist must map sample paths to exclusion reasons")
    for path, reason in blacklist.items():
        if (not any(path.startswith(root + "/") for root in SAMPLE_ROOTS)
                or "\\" in path or any(part in ("", ".", "..") for part in path.split("/"))):
            raise DiscoveryError(f"invalid blacklist sample path: {path}")
        fixture_dir_for_sample(path)
        if not (repo / path).resolve().is_relative_to(repo.resolve()):
            raise DiscoveryError(f"blacklist sample resolves outside the repository: {path}")
        if not isinstance(reason, str) or not reason.strip():
            raise DiscoveryError(f"blacklist reason must be a nonempty string: {path}")
    return blacklist


def discover(repo: Path, changed_paths: list[str] | None = None, sample_filter: str = "") -> dict:
    blacklist = load_blacklist(repo)
    manifests = []
    for sample_root in SAMPLE_ROOTS:
        root = repo / sample_root
        if not root.is_dir():
            raise DiscoveryError(f"sample root does not exist: {root}")
        manifests.extend(root.rglob("azure.yaml"))
    full_run = changed_paths is None or any(
        path in FULL_RUN_PATHS or path.startswith(CI_ROOT + "/")
        for path in changed_paths
    )
    tokens = [] if sample_filter.strip() == "*" else [
        token.strip().casefold() for token in sample_filter.split(",") if token.strip()
    ]
    entries = []
    combo_ids = set()
    matrix_keys = set()
    for manifest in sorted(manifests):
        sample_path = manifest.parent.relative_to(repo).as_posix()
        if sample_path in blacklist:
            continue
        fixture_path = fixture_dir_for_sample(sample_path).as_posix()
        if not full_run and not any(
            path.startswith(sample_path + "/") or path.startswith(fixture_path + "/")
            for path in changed_paths
        ):
            continue
        record = sample_record(repo, manifest)
        if record["comboId"] in combo_ids or record["matrixKey"] in matrix_keys:
            raise DiscoveryError(f"duplicate combo ID or matrix key: {sample_path}")
        combo_ids.add(record["comboId"])
        matrix_keys.add(record["matrixKey"])
        haystack = " ".join(record[key] for key in ("comboId", "samplePath", "sampleName")).casefold()
        if tokens and not any(token in haystack for token in tokens):
            continue
        entries.append(record)
    result = {"count": len(entries), "entries": entries}
    for profile in ("all", "prompt", "managed"):
        selected = [entry for entry in entries if profile == "all" or entry["executionProfile"] == profile]
        result[f"matrix_{profile}"] = {
            entry["matrixKey"]: {"comboId": entry["comboId"]} for entry in selected
        }
        if profile != "all":
            result[f"count_{profile}"] = len(selected)
    return result


def validate_contracts(repo: Path) -> None:
    from prompt_agent_helpers import plan_contract, validate_manifest

    blacklist = load_blacklist(repo)
    candidates = {record["samplePath"] for record in discover(repo)["entries"]}
    fixtures = {}
    for spec in sorted((repo / FIXTURE_ROOT).rglob("test-spec.yml")):
        relative = sample_dir_for_fixture(spec.relative_to(repo).as_posix()).as_posix()
        fixtures[relative] = spec
    for path in sorted(candidates | set(fixtures)):
        if not any(path.startswith(root + "/") for root in SAMPLE_ROOTS):
            raise DiscoveryError(f"unsupported fixture sample root: {path}")
        # The shared resolver rejects traversal and unsupported layouts.
        expected = repo / fixture_dir_for_sample(path) / "test-spec.yml"
        if not (repo / path).resolve().is_relative_to(repo.resolve()):
            raise DiscoveryError(f"sample resolves outside the repository: {path}")
        if not (repo / path / "azure.yaml").is_file():
            raise DiscoveryError(f"fixture has no sample manifest: {path}/azure.yaml")
        if path in blacklist:
            continue
        if path not in fixtures:
            raise DiscoveryError(f"non-skipped sample requires a contract: {expected}")
        record = sample_record(repo, repo / path / "azure.yaml")
        document = yaml.load((repo / path / "azure.yaml").read_text(encoding="utf-8"), Loader=ManifestLoader)
        validate_manifest(document, record["agentService"])
        plan_contract(fixtures[path], record["executionProfile"])


def hydrate(entries: list, combo_id: str) -> dict:
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise DiscoveryError("entries artifact must contain an array of records")
    matches = [entry for entry in entries if entry.get("comboId") == combo_id]
    if len(matches) != 1:
        raise DiscoveryError(f"expected exactly one discovery record for {combo_id}; found {len(matches)}")
    return matches[0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    discovery = commands.add_parser("discover")
    discovery.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    discovery.add_argument("--mode", choices=("all", "changed"), default="all")
    discovery.add_argument("--base-ref", default="origin/main")
    discovery.add_argument("--sample-filter", default="")
    discovery.add_argument("--validate-contracts", action="store_true", help="check fixture mappings and contracts for every non-skipped sample before filtering")
    hydration = commands.add_parser("hydrate")
    hydration.add_argument("--entries", type=Path, required=True)
    hydration.add_argument("--combo-id", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "hydrate":
            result = hydrate(json.loads(args.entries.read_text(encoding="utf-8")), args.combo_id)
        else:
            repo = args.repo.resolve()
            if args.validate_contracts:
                validate_contracts(repo)
            changed = None
            if args.mode == "changed":
                # Disable rename detection so both sides select their owning sample.
                diff = subprocess.run(
                    ["git", "diff", "--name-only", "--no-renames", "-z", f"{args.base_ref}...HEAD", "--"],
                    cwd=repo, check=True, capture_output=True, encoding="utf-8",
                )
                changed = [path for path in diff.stdout.split("\0") if path]
            result = discover(repo, changed, args.sample_filter)
            if any(result[f"count_{profile}"] > 256 for profile in ("prompt", "managed")):
                raise DiscoveryError("profile matrix exceeds the 256-job limit; split the matrix before execution")
        print(json.dumps(result, indent=2))
        return 0
    except (DiscoveryError, OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
