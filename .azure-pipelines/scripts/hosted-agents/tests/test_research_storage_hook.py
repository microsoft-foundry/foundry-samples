"""Verify report Storage configuration and role ownership without Azure calls."""

import importlib.util
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
SAMPLE = ROOT / "samples/python/hosted-agents/langgraph/responses/11-deep-agents"
SPEC = importlib.util.spec_from_file_location(
    "report_storage_hook", SAMPLE / "hooks/configure-report-storage.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
SUBSCRIPTION = "11111111-1111-1111-1111-111111111111"
PRINCIPAL = "22222222-2222-2222-2222-222222222222"
ACCOUNT_ID = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/reports/providers/Microsoft.Storage/storageAccounts/reports"


class ResearchStorageHookTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        receipt = patch.object(module, "RECEIPT", Path(temporary.name) / "roles.json")
        receipt.start()
        self.addCleanup(receipt.stop)
        self.created = []
        self.deleted = []
        self.assigned = False
        self.failure = False
        self.principal = PRINCIPAL

    def cli(self, *arguments):
        if arguments == ("azd", "env", "get-values"):
            return f'AZURE_STORAGE_ACCOUNT_NAME="reports"\nAZURE_STORAGE_CONTAINER_NAME="reports"\nAZURE_SUBSCRIPTION_ID="{SUBSCRIPTION}"'
        if arguments[:3] == ("azd", "ai", "agent"):
            return json.dumps({"instance_identity": {"principal_id": self.principal}})
        if arguments[:4] == ("az", "storage", "account", "list"):
            return ACCOUNT_ID
        if arguments[:3] == ("az", "resource", "show"):
            return ""
        if arguments[:4] == ("az", "role", "definition", "list"):
            role = arguments[arguments.index("--name") + 1]
            return "/providers/Microsoft.Authorization/roleDefinitions/" + (
                "contributor" if "Contributor" in role else "delegator"
            )
        if arguments[:4] == ("az", "role", "assignment", "list"):
            if "--query" in arguments:
                return json.dumps({"principalId": self.principal})
            if self.assigned:
                return json.dumps(
                    [
                        {
                            "principalId": PRINCIPAL,
                            "roleDefinitionId": "/roleDefinitions/" + role,
                        }
                        for role in ["contributor", "delegator"]
                    ]
                )
            return "[]"
        if arguments[:4] == ("az", "role", "assignment", "create"):
            if self.failure:
                raise subprocess.CalledProcessError(1, "az")
            self.created.append(arguments)
            return ""
        if arguments[:4] == ("az", "role", "assignment", "delete"):
            self.deleted.append(arguments)
            return ""
        raise AssertionError(arguments)

    def test_standard_ci_storage_settings_map_to_upstream_runtime_names(self):
        manifest = (SAMPLE / "azure.yaml").read_text(encoding="utf-8")
        self.assertIn(
            "REPORT_STORAGE_ACCOUNT_URL: https://${AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
            manifest,
        )
        self.assertIn(
            "REPORT_STORAGE_CONTAINER: ${AZURE_STORAGE_CONTAINER_NAME}", manifest
        )
        runner = (
            ROOT / ".azure-pipelines/scripts/hosted-agents/run-hosted-agent.sh"
        ).read_text(encoding="utf-8")
        prefixes = (
            re.search(r'^PASSTHROUGH_PREFIXES="([^"]+)"', runner, re.MULTILINE)
            .group(1)
            .split()
        )
        for key in ["AZURE_STORAGE_ACCOUNT_NAME", "AZURE_STORAGE_CONTAINER_NAME"]:
            self.assertTrue(any(key.startswith(prefix) for prefix in prefixes))

    def test_roles_target_agent_instance_and_only_container_data_plus_account_delegation(
        self,
    ):
        with patch.object(module, "run_cli", side_effect=self.cli):
            module.configure()
        scopes = [
            arguments[arguments.index("--scope") + 1] for arguments in self.created
        ]
        self.assertEqual(
            scopes,
            [ACCOUNT_ID + "/blobServices/default/containers/reports", ACCOUNT_ID],
        )
        for arguments in self.created:
            self.assertEqual(
                arguments[arguments.index("--assignee-object-id") + 1], PRINCIPAL
            )
            self.assertEqual(
                arguments[arguments.index("--assignee-principal-type") + 1],
                "ServicePrincipal",
            )
        receipt = json.loads(module.RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(len(receipt["assignments"]), 2)

    def test_preexisting_grants_are_neither_recreated_nor_owned_for_cleanup(self):
        self.assigned = True
        with patch.object(module, "run_cli", side_effect=self.cli):
            module.configure()
            module.cleanup()
        self.assertEqual(self.created, [])
        self.assertEqual(self.deleted, [])

    def test_missing_identity_or_permission_fails_instead_of_skipping(self):
        self.principal = ""
        with patch.object(module, "run_cli", side_effect=self.cli), self.assertRaises(
            ValueError
        ):
            module.configure()
        self.assertEqual(self.created, [])
        self.principal = PRINCIPAL
        self.failure = True
        with patch.object(module, "run_cli", side_effect=self.cli), self.assertRaises(
            subprocess.CalledProcessError
        ):
            module.configure()

    def test_cleanup_removes_only_recorded_owned_assignments_and_is_idempotent(self):
        with patch.object(module, "run_cli", side_effect=self.cli):
            module.configure()
            module.cleanup()
            module.cleanup()
        self.assertEqual(len(self.deleted), 2)
        for arguments in self.deleted:
            self.assertTrue(
                arguments[arguments.index("--ids") + 1].startswith(ACCOUNT_ID + "/")
            )

    def test_cleanup_refuses_a_different_principal(self):
        with patch.object(module, "run_cli", side_effect=self.cli):
            module.configure()
            self.principal = "33333333-3333-3333-3333-333333333333"
            with self.assertRaises(ValueError):
                module.cleanup()
        self.assertEqual(self.deleted, [])

    def test_existing_owned_grants_must_be_cleaned_before_identity_changes(self):
        with patch.object(module, "run_cli", side_effect=self.cli):
            module.configure()
            self.principal = "33333333-3333-3333-3333-333333333333"
            with self.assertRaisesRegex(ValueError, "Clean up recorded grants"):
                module.configure()
        self.assertEqual(len(self.created), 2)

    def test_cleanup_cannot_escape_recorded_storage_account(self):
        with patch.object(module, "run_cli", side_effect=self.cli):
            module.configure()
            receipt = json.loads(module.RECEIPT.read_text(encoding="utf-8"))
            receipt["assignments"] = [
                "/subscriptions/another-account/roleAssignments/other"
            ]
            module.RECEIPT.write_text(json.dumps(receipt), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "escaped"):
                module.cleanup()
        self.assertEqual(self.deleted, [])

    def test_redeploy_preserves_ownership_without_duplicate_grants(self):
        with patch.object(module, "run_cli", side_effect=self.cli):
            module.configure()
            self.assigned = True
            module.configure()
            module.cleanup()
        self.assertEqual(len(self.created), 2)
        self.assertEqual(len(self.deleted), 2)


if __name__ == "__main__":
    unittest.main()
