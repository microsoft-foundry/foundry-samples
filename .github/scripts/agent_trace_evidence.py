#!/usr/bin/env python3
"""Verify that a sample's agent responses reached its connected App Insights."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_tracing_setup import AzureCLI, AzureError, connection, validate_project

RESPONSE_PATTERN = re.compile(r"^Agent response ID: ([A-Za-z0-9_-]+)\s*$", re.MULTILINE)


def table_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    # Match the hosted-agent collector's table normalization, but reject partial evidence.
    if response.get("error"):
        raise AzureError("App Insights returned an error or partial query result")
    tables = response.get("tables")
    if not isinstance(tables, list) or not tables:
        raise AzureError("App Insights query returned no tables")
    table = tables[0]
    columns = table.get("columns")
    rows = table.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise AzureError("App Insights query returned a malformed table")
    names = [column["name"] for column in columns]
    if not names or any(not isinstance(row, list) or len(row) != len(names) for row in rows):
        raise AzureError("App Insights query returned malformed rows")
    return [dict(zip(names, row)) for row in rows]


def trace_query(response_ids: list[str], started_at: str) -> str:
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AzureError("--started-at must be an ISO UTC timestamp") from exc
    if started.tzinfo is None:
        raise AzureError("--started-at must include a timezone")
    timestamp = started.astimezone(timezone.utc).isoformat()
    return f"""
union dependencies, requests
| where timestamp >= datetime({timestamp})
| extend response_id = tostring(customDimensions["gen_ai.response.id"])
| where response_id in ({", ".join(json.dumps(value) for value in response_ids)})
| where name startswith "invoke_agent " and isnotempty(customDimensions["gen_ai.agent.id"])
| project timestamp, name, response_id, operation_Id, id,
          agent_name=tostring(customDimensions["gen_ai.agent.name"]),
          agent_id=tostring(customDimensions["gen_ai.agent.id"])
| order by timestamp asc
""".strip()


def verify(
    cli: AzureCLI, project_id: str, response_ids: list[str], started_at: str,
    *, timeout: float = 300, interval: float = 10,
) -> dict[str, Any]:
    validate_project(project_id)
    if not response_ids or any(not re.fullmatch(r"[A-Za-z0-9_-]+", value) for value in response_ids):
        raise AzureError("At least one valid agent response ID is required")
    deadline = time.monotonic() + timeout
    cli.deadline = deadline
    linked = connection(cli, project_id)
    if not linked:
        raise AzureError("Project has no App Insights connection; run agent_tracing_setup.py first")
    component = cli.rest("get", linked["application_insights_resource_id"], "2020-02-02")
    app_id = component.get("properties", {}).get("AppId")
    if not app_id or not re.fullmatch(r"[A-Za-z0-9-]+", app_id):
        raise AzureError("Connected App Insights resource has no valid application ID")
    query = trace_query(response_ids, started_at)
    spans: list[dict[str, Any]] = []
    first_query = True
    while first_query or time.monotonic() < deadline:
        first_query = False
        with tempfile.TemporaryDirectory() as directory:
            body = Path(directory) / "query.json"
            body.write_text(json.dumps({"query": query}), encoding="utf-8")
            result = cli.run(
                "rest", "--method", "post", "--resource", "https://api.applicationinsights.io",
                "--url", f"https://api.applicationinsights.io/v1/apps/{app_id}/query",
                "--body", f"@{body}",
            )
        spans = table_rows(result)
        expected = set(response_ids)
        found = {span.get("response_id") for span in spans}
        if spans and expected.issubset(found):
            return {
                "status": "verified", "project_id": project_id,
                "application_insights_resource_id": linked["application_insights_resource_id"],
                "response_ids": response_ids, "started_at": started_at, "spans": spans,
            }
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))
    return {
        "status": "missing_traces", "project_id": project_id,
        "application_insights_resource_id": linked["application_insights_resource_id"],
        "response_ids": response_ids,
        "missing_response_ids": sorted(set(response_ids) - {span.get("response_id") for span in spans}),
        "started_at": started_at, "spans": spans,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", default=os.environ.get("FOUNDRY_PROJECT_RESOURCE_ID"))
    parser.add_argument("--sample-log", type=Path, required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--expected-responses", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.project_id:
        parser.error("--project-id or FOUNDRY_PROJECT_RESOURCE_ID is required")
    if not math.isfinite(args.timeout) or args.timeout <= 0 or args.expected_responses <= 0:
        parser.error("--timeout must be finite and positive; --expected-responses must be positive")
    try:
        response_ids = RESPONSE_PATTERN.findall(args.sample_log.read_text(encoding="utf-8"))
        if len(response_ids) != args.expected_responses or len(set(response_ids)) != len(response_ids):
            print("FAIL: sample did not record the expected distinct successful agent responses", file=sys.stderr)
            return 1
        result = verify(
            AzureCLI(min(args.timeout, 60)), args.project_id, response_ids,
            args.started_at, timeout=args.timeout,
        )
    except (AzureError, OSError, KeyError, TypeError) as exc:
        print(f"Trace verification could not complete: {exc}", file=sys.stderr)
        return 2
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "verified" else 1


if __name__ == "__main__":
    sys.exit(main())
