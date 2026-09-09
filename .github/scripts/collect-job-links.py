#!/usr/bin/env python3
"""Map each matrixed validation-pilot job in a workflow run to its sample id.

render-validation-dashboard.py links every row's Status badge to the exact
job that produced it (where the failing step is visible), rather than the
generic run-overview page. This script builds that sample-id -> job-URL
mapping from the run's job list.

Matrix job display names GitHub Actions generates look like:
  "build-readiness (sample-id, samples/.../path, language, shape)"
  "live-service (sample-id, samples/.../path, language, shape)"
GitHub truncates the display name to roughly 100 characters, but the sample
id -- the matrix's first field -- always appears in full before the first
comma, so it can be recovered even when the rest of the name is cut off.
This depends on sample ids never containing a comma or parenthesis;
discover-validation-samples.py enforces a `[A-Za-z0-9_-]+` id alphabet at
discovery time specifically so that guarantee holds here.

Input is NDJSON (one job object per line) with at least `name` and
`html_url` fields, e.g. produced by:
  gh api repos/OWNER/REPO/actions/runs/RUN_ID/jobs --paginate -q '.jobs[] | {name, html_url}'
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

JOB_NAME_PATTERN = re.compile(r"^(?:build-readiness|live-service) \(([^,()]+),")


def collect_links(lines: list[str]) -> dict[str, str]:
    links: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
        except ValueError:
            continue
        if not isinstance(job, dict):
            continue
        name = job.get("name")
        html_url = job.get("html_url")
        if not isinstance(name, str) or not isinstance(html_url, str):
            continue
        match = JOB_NAME_PATTERN.match(name)
        if not match:
            continue
        sample_id = match.group(1).strip()
        if sample_id:
            links[sample_id] = html_url
    return links


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs-file", type=Path, required=True, help="NDJSON of {name, html_url} job objects")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        lines = args.jobs_file.read_text(encoding="utf-8").splitlines()
        links = collect_links(lines)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(links, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"collect-job-links: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
