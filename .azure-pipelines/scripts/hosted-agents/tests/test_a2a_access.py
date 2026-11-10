"""Job-owned runtime role assignment lifecycle tests; no Azure operations."""

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

    def test_new_assignment_is_owned_then_deleted_by_exact_id(self):
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
            owned = json.loads(state.read_text())
            self.assertEqual(len(owned), 0 if existing else 1)
            module.manage("cleanup", state, "planner", command=command)
            deletes = [
                args
                for args in commands
                if args[:4] == ["az", "role", "assignment", "delete"]
            ]
            self.assertEqual(len(deletes), 0 if existing else 1)
            if not existing:
                self.assertEqual(deletes[0][-1], owned[0])
            self.assertEqual(json.loads(state.read_text()), [])
