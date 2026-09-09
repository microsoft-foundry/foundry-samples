#!/usr/bin/env python3
"""Map each per-sample validation-pilot artifact in a workflow run to its sample id.

render-validation-dashboard.py links an Artifact column per row to the exact
artifact (validation-pilot-{sample_id}, uploaded by the build-readiness/
live-service job for that sample) containing that sample's sample-result.json
and diagnostics.log -- so a reader can download the full diagnostic log
without needing repo write access to browse job logs.

Input is NDJSON (one artifact object per line) with at least `name` and `id`
fields, e.g. produced by:
  gh api repos/OWNER/REPO/actions/runs/RUN_ID/artifacts --paginate -q '.artifacts[] | {name, id}'

Artifacts that aren't a per-sample result (the combined manifest artifact, or
the combined run artifact this very script's output feeds into) are skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ARTIFACT_NAME_PREFIX = "validation-pilot-"


def collect_links(
    lines: list[str], repository: str, run_id: str, reserved_names: set[str]
) -> dict[str, str]:
    links: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            artifact = json.loads(line)
        except ValueError:
            continue
        if not isinstance(artifact, dict):
            continue
        name = artifact.get("name")
        artifact_id = artifact.get("id")
        if not isinstance(name, str) or not isinstance(artifact_id, int):
            continue
        if name in reserved_names or not name.startswith(ARTIFACT_NAME_PREFIX):
            continue
        sample_id = name[len(ARTIFACT_NAME_PREFIX):]
        links[sample_id] = f"https://github.com/{repository}/actions/runs/{run_id}/artifacts/{artifact_id}"
    return links


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-file", type=Path, required=True, help="NDJSON of {name, id} artifact objects")
    parser.add_argument("--repository", required=True, help="owner/repo, used to build the artifact page URL")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True, help="Used to exclude this workflow's own combined-run artifact by its exact name")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reserved_names = {
        "validation-pilot-manifest",
        f"validation-pilot-run-{args.run_id}-{args.run_attempt}",
    }
    try:
        lines = args.artifacts_file.read_text(encoding="utf-8").splitlines()
        links = collect_links(lines, args.repository, args.run_id, reserved_names)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(links, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"collect-artifact-links: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
