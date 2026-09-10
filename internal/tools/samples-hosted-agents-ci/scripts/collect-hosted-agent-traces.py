#!/usr/bin/env python3
"""Collect session-correlated hosted-agent spans from Application Insights."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _run_json(command: list[str]) -> Any:
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def _quote_kusto(value: str) -> str:
    return value.replace("'", "''")


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _table_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    tables = response.get("tables", [])
    if not tables:
        return []
    table = tables[0]
    names = [column["name"] for column in table.get("columns", [])]
    return [dict(zip(names, row)) for row in table.get("rows", [])]


def _attributes(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"raw.customDimensions": value}
        return parsed if isinstance(parsed, dict) else {"raw.customDimensions": parsed}
    return {}


def collect(resource_group: str, agent_name: str, session_id: str) -> dict[str, Any]:
    component_ids = _run_json(
        [
            "az",
            "resource",
            "list",
            "--resource-group",
            resource_group,
            "--resource-type",
            "microsoft.insights/components",
            "--query",
            "[].id",
            "--output",
            "json",
        ]
    )
    components = []
    for component_id in component_ids:
        component = _run_json(
            [
                "az",
                "resource",
                "show",
                "--ids",
                component_id,
                "--query",
                "{id:id,appId:properties.AppId,name:name}",
                "--output",
                "json",
            ]
        )
        if component.get("appId"):
            components.append(component)
    if not components:
        return {
            "available": False,
            "error": f"no queryable Application Insights component exists in {resource_group!r}",
            "spans": [],
        }

    query = f"""
union dependencies, requests
| where timestamp >= ago(45m)
| where cloud_RoleName == '{_quote_kusto(agent_name)}'
| where tostring(customDimensions) contains '{_quote_kusto(session_id)}'
| project timestamp, itemType, name, success, customDimensions, operation_Id, id
| order by timestamp asc
""".strip()
    spans = []
    queried_components = []
    for component in components:
        response = _run_json(
            [
                "az",
                "rest",
                "--method",
                "post",
                "--resource",
                "https://api.applicationinsights.io",
                "--url",
                f"https://api.applicationinsights.io/v1/apps/{component['appId']}/query",
                "--body",
                json.dumps({"query": query}),
                "--output",
                "json",
            ]
        )
        queried_components.append(component)
        for row in _table_rows(response):
            attributes = _attributes(row.get("customDimensions"))
            attributes.setdefault("application_insights.item_type", row.get("itemType"))
            attributes.setdefault(
                "application_insights.operation_id", row.get("operation_Id")
            )
            success = row.get("success")
            status = (
                "ok" if success is True or str(success).lower() == "true" else "error"
            )
            if success is None or str(success).lower() in {"", "none", "null"}:
                status = "unset"
            spans.append(
                {
                    "name": row.get("name"),
                    "status": status,
                    "attributes": attributes,
                    "timestamp": row.get("timestamp"),
                    "span_id": row.get("id"),
                    "application_insights": component["name"],
                }
            )
    if not spans:
        return {
            "available": False,
            "error": "no session-correlated spans are available yet",
            "application_insights": queried_components,
            "query": query,
            "spans": [],
        }
    return {
        "available": True,
        "application_insights": queried_components,
        "query": query,
        "spans": spans,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--agent-name", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = collect(args.resource_group, args.agent_name, args.session_id)
    except (subprocess.CalledProcessError, json.JSONDecodeError, OSError) as exc:
        result = {"available": False, "error": str(exc), "spans": []}
    _write(args.output, result)
    if not result["available"]:
        print(f"Trace evidence unavailable: {result['error']}")
        return 1
    print(f"Collected {len(result['spans'])} correlated span(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
