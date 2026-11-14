"""Stable runtime role assignment lifecycle tests; no Azure operations."""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "a2a_access",
    Path(__file__).resolve().parents[1] / "scripts" / "hosted_agent_a2a_access.py",
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
SCOPE = "/subscriptions/test/resourceGroups/test/providers/Microsoft.CognitiveServices/accounts/test/projects/test"


class AccessTests(unittest.TestCase):
    def test_existing_assignment_is_never_owned_or_deleted(self):
        self.lifecycle(True)

    def test_new_assignment_survives_job_cleanup(self):
        self.lifecycle(False)

    def lifecycle(self, existing):
        commands = []

        def command(args):
            commands.append(args)
            if args[:4] == ["azd", "ai", "agent", "show"]:
                return {"instance_identity": {"principal_id": "planner-principal"}}
            if args[3] == "list":
                return (
                    [{"roleDefinitionId": "/roles/" + module.ROLE}] if existing else []
                )
            return {}

        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "access.json"
            with patch.object(
                module.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, SCOPE, ""),
            ):
                module.manage("grant", state, "planner", command=command)
            saved = json.loads(state.read_text())
            self.assertEqual(saved["lifecycle"], "persistent")
            self.assertEqual(saved["created"], not existing)
            module.manage("cleanup", state, "planner", command=command)
            deletes = [
                args
                for args in commands
                if args[:4] == ["az", "role", "assignment", "delete"]
            ]
            self.assertEqual(deletes, [])
            self.assertEqual(json.loads(state.read_text()), saved)

    def test_overlapping_builds_converge_without_revoking_access(self):
        creates = []
        present = False

        def command(args):
            if args[:4] == ["azd", "ai", "agent", "show"]:
                return {"instance_identity": {"principal_id": "planner-principal"}}
            if args[3] == "list":
                return (
                    [{"roleDefinitionId": "/roles/" + module.ROLE}] if present else []
                )
            self.assertEqual(args[3], "create")
            creates.append(args[args.index("--name") + 1])
            return {}

        with tempfile.TemporaryDirectory() as directory, patch.object(
            module.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, SCOPE, ""),
        ):
            first = Path(directory) / "job-a.json"
            second = Path(directory) / "job-b.json"
            module.manage("grant", first, "planner", command=command)
            module.manage("grant", second, "planner", command=command)
            self.assertEqual(creates[0], creates[1])
            present = True
            module.manage("cleanup", first, "planner", command=command)
            module.manage("grant", second, "planner", command=command)
            self.assertFalse(json.loads(second.read_text())["created"])
            self.assertEqual(len(creates), 2)
