#!/usr/bin/env python3
"""Ensure stable CI planner access without revoking concurrent builds' grants."""

import json
import subprocess
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROLE = "eed3b665-ab3a-47b6-8f48-c9382fb1dad6"


def run(arguments):
    result = subprocess.run(arguments, check=False, capture_output=True, text=True)
    if result.returncode:
        print(result.stderr, file=sys.stderr, end="")
        result.check_returncode()
    return json.loads(result.stdout) if result.stdout.strip() else None


def manage(action: str, state: Path, agent: str, *, command=run) -> None:
    if action == "cleanup":
        # Agent identities are reused by overlapping builds; access must outlive jobs.
        return
    if action != "grant":
        raise ValueError("Expected grant or cleanup")
    metadata = command(
        ["azd", "ai", "agent", "show", agent, "--output", "json", "--no-prompt"]
    )
    principal = metadata["instance_identity"]["principal_id"]
    scope_result = subprocess.run(
        ["azd", "env", "get-value", "AZURE_AI_PROJECT_ID"],
        check=True,
        capture_output=True,
        text=True,
    )
    scope = scope_result.stdout.strip()
    if (
        not scope.lower().startswith("/subscriptions/")
        or "/projects/" not in scope.lower()
    ):
        raise ValueError("Expected a Foundry project ARM scope")
    existing = command(
        [
            "az",
            "role",
            "assignment",
            "list",
            "--assignee",
            principal,
            "--scope",
            scope,
            "--include-inherited",
            "--output",
            "json",
        ]
    )
    state.parent.mkdir(parents=True, exist_ok=True)
    if any(item["roleDefinitionId"].lower().endswith("/" + ROLE) for item in existing):
        state.write_text(
            json.dumps({"lifecycle": "persistent", "created": False}), encoding="utf-8"
        )
        return
    name = str(uuid5(NAMESPACE_URL, f"{scope.lower()}:{principal.lower()}:{ROLE}"))
    assignment = scope + "/providers/Microsoft.Authorization/roleAssignments/" + name
    command(
        [
            "az",
            "role",
            "assignment",
            "create",
            "--name",
            name,
            "--assignee-object-id",
            principal,
            "--assignee-principal-type",
            "ServicePrincipal",
            "--role",
            ROLE,
            "--scope",
            scope,
            "--output",
            "json",
        ]
    )
    state.write_text(
        json.dumps(
            {"lifecycle": "persistent", "assignment": assignment, "created": True}
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    manage(sys.argv[1], Path(sys.argv[2]), sys.argv[3])
