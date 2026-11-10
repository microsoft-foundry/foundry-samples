#!/usr/bin/env python3
"""Grant only the CI planner runtime access; remove only job-owned assignments."""

import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROLE = "eed3b665-ab3a-47b6-8f48-c9382fb1dad6"


def run(arguments):
    result = subprocess.run(arguments, check=False, capture_output=True, text=True)
    if result.returncode:
        print(result.stderr, file=sys.stderr, end="")
        result.check_returncode()
    return json.loads(result.stdout) if result.stdout.strip() else None


def manage(action: str, state: Path, agent: str, *, command=run) -> None:
    if action == "cleanup":
        if not state.exists():
            return
        owned = json.loads(state.read_text(encoding="utf-8"))
        for assignment in list(owned):
            command(["az", "role", "assignment", "delete", "--ids", assignment])
            owned.remove(assignment)
            state.write_text(json.dumps(owned), encoding="utf-8")
        return
    if action != "grant":
        raise ValueError("Expected grant or cleanup")
    if state.exists():
        raise ValueError("Access ownership state already exists; refusing to overwrite")
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
    state.write_text("[]", encoding="utf-8")
    if any(item["roleDefinitionId"].lower().endswith("/" + ROLE) for item in existing):
        return
    name = str(uuid4())
    assignment = scope + "/providers/Microsoft.Authorization/roleAssignments/" + name
    # Persist ownership before creating so interrupted requests remain cleanable.
    state.write_text(json.dumps([assignment]), encoding="utf-8")
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


if __name__ == "__main__":
    manage(sys.argv[1], Path(sys.argv[2]), sys.argv[3])
