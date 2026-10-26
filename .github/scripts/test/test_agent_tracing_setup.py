"""Offline tests for ownership-safe, existing-project tracing setup."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_tracing_setup as setup

PROJECT = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/account/projects/project"
APPI = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Insights/components/appi"
LINK = {"connection_id": PROJECT + "/connections/traces", "application_insights_resource_id": APPI, "auth_type": "ApiKey"}


class ConnectionTests(unittest.TestCase):
    def test_reuses_project_connection_without_writes(self):
        cli = mock.Mock()
        cli.list.return_value = [{"id": LINK["connection_id"], "properties": {
            "category": "AppInsights", "authType": "ApiKey", "target": APPI,
        }}]
        result = setup.prepare(cli, PROJECT)
        self.assertEqual("reused", result["status"])
        self.assertEqual("ApiKey", result["auth_type"])
        cli.rest.assert_not_called()

    def test_shared_account_connection_is_reused(self):
        cli = mock.Mock()
        cli.list.side_effect = [[], [{"id": "account-connection", "properties": {
            "category": "AppInsights", "authType": "ProjectManagedIdentity",
            "isSharedToAll": True, "metadata": {"ResourceId": APPI},
        }}]]
        result = setup.connection(cli, PROJECT)
        self.assertEqual(APPI, result["application_insights_resource_id"])
        self.assertIn("/accounts/account/connections", cli.list.call_args.args[0])

    def test_nonshared_account_connection_is_not_adopted(self):
        cli = mock.Mock()
        cli.list.side_effect = [[], [{"properties": {
            "category": "AppInsights", "target": APPI, "isSharedToAll": False,
        }}]]
        self.assertIsNone(setup.connection(cli, PROJECT))

    def test_opt_out_does_not_call_azure(self):
        cli = mock.Mock()
        self.assertEqual("disabled", setup.prepare(cli, PROJECT, disabled=True)["status"])
        self.assertEqual([], cli.mock_calls)

    def test_existing_connection_conflict_is_not_replaced(self):
        with mock.patch.object(setup, "connection", return_value=LINK):
            cli = mock.Mock()
            with self.assertRaisesRegex(setup.AzureError, "will not be replaced"):
                setup.prepare(cli, PROJECT, application_insights=APPI + "-other")
            cli.rest.assert_not_called()

    def test_multiple_connections_fail_explicitly(self):
        cli = mock.Mock()
        cli.list.return_value = [{"properties": {"category": "AppInsights"}}] * 2
        with self.assertRaisesRegex(setup.AzureError, "Multiple"):
            setup.connection(cli, PROJECT)

    def test_invalid_project_id_fails_before_azure(self):
        cli = mock.Mock()
        with self.assertRaises(setup.AzureError):
            setup.prepare(cli, "https://not-an-arm-id")
        self.assertEqual([], cli.mock_calls)


class ProvisioningTests(unittest.TestCase):
    def cli(self):
        cli = mock.Mock()
        cli.list.return_value = []
        cli.rest.side_effect = lambda method, resource, version, *body: (
            {"location": "westus3", "identity": {"principalId": "principal"}}
            if method == "get" and resource == PROJECT else {}
        )
        return cli

    @mock.patch.object(setup, "connection", side_effect=[None, None])
    @mock.patch.object(setup, "wait_ready")
    def test_new_setup_is_workspace_based_and_uses_project_identity(self, ready, _connection):
        ready.side_effect = [{}, {"properties": {"ConnectionString": "placeholder"}}, {}]
        cli = self.cli()
        result = setup.prepare(cli, PROJECT)
        self.assertEqual("configured", result["status"])
        bodies = [call.args[3] for call in cli.rest.call_args_list if call.args[0] == "put"]
        components = [body for body in bodies if body.get("kind") == "web"]
        self.assertEqual(1, len(components))
        self.assertTrue(components[0]["properties"]["DisableLocalAuth"])
        self.assertIn("WorkspaceResourceId", components[0]["properties"])
        self.assertEqual("ProjectManagedIdentity", bodies[-1]["properties"]["authType"])
        self.assertNotIn("credentials", bodies[-1]["properties"])
        self.assertNotIn("placeholder", json.dumps(result))

    @mock.patch.object(setup, "connection", return_value=None)
    def test_missing_identity_is_explicit(self, _connection):
        cli = mock.Mock()
        cli.rest.return_value = {"location": "westus3"}
        with self.assertRaisesRegex(setup.AzureError, "managed identity"):
            setup.prepare(cli, PROJECT)
        self.assertEqual(1, cli.rest.call_count)

    @mock.patch.object(setup.uuid, "uuid4")
    @mock.patch.object(setup, "connection", return_value=None)
    def test_name_collision_is_not_overwritten(self, _connection, uuid4):
        cli = self.cli()
        uuid4.return_value.hex = "fixedtestowner"
        suffix = "fixedtestown"
        workspace = PROJECT.split("/providers/")[0] + "/providers/Microsoft.OperationalInsights/workspaces/agent-traces-" + suffix
        cli.list.return_value = [{"id": workspace}]
        with self.assertRaisesRegex(setup.AzureError, "already exists"):
            setup.prepare(cli, PROJECT)
        self.assertFalse(any(call.args[0] == "put" for call in cli.rest.call_args_list))

    @mock.patch.object(setup, "connection", return_value=None)
    def test_byo_policy_is_not_changed(self, _connection):
        cli = self.cli()
        cli.rest.side_effect = [
            {"location": "westus3", "identity": {"principalId": "principal"}},
            {"properties": {"WorkspaceResourceId": "workspace", "DisableLocalAuth": False}},
        ]
        with self.assertRaisesRegex(setup.AzureError, "will not be changed"):
            setup.prepare(cli, PROJECT, application_insights=APPI)
        self.assertFalse(any(call.args[0] in ("put", "delete") for call in cli.rest.call_args_list))

    def test_role_assignment_id_is_stable(self):
        cli = mock.Mock()
        cli.list.return_value = []
        setup.assign_role(cli, APPI, "principal", setup.PUBLISHER)
        first = cli.rest.call_args
        setup.assign_role(cli, APPI, "principal", setup.PUBLISHER)
        self.assertEqual(first, cli.rest.call_args)

    def test_existing_role_with_another_assignment_name_is_reused(self):
        cli = mock.Mock()
        cli.list.return_value = [{"properties": {
            "principalId": "principal",
            "roleDefinitionId": "/subscriptions/sub/providers/Microsoft.Authorization/roleDefinitions/" + setup.PUBLISHER,
        }}]
        setup.assign_role(cli, APPI, "principal", setup.PUBLISHER)
        cli.rest.assert_not_called()

    def test_cleanup_confirms_ownership_and_waits_for_deletion(self):
        cli = mock.Mock()
        cli.rest.side_effect = [
            {"tags": {"foundry-tracing-owner": "owned"}}, {},
            setup.AzureError("ResourceNotFound", "ResourceNotFound"),
        ]
        setup.delete_owned(cli, APPI, "version", "owned", 30)
        self.assertEqual(["get", "delete", "get"], [call.args[0] for call in cli.rest.call_args_list])

    def test_cleanup_never_deletes_unowned_resource(self):
        cli = mock.Mock()
        cli.rest.return_value = {"tags": {"foundry-tracing-owner": "somebody-else"}}
        with self.assertRaisesRegex(setup.AzureError, "ownership"):
            setup.delete_owned(cli, APPI, "version", "owned", 30)
        self.assertEqual(1, cli.rest.call_count)

    def test_owned_role_assignments_are_removed_on_byo_attach_failure(self):
        cli = self.cli()
        assignments = {}
        deleted = []

        def rest(method, resource, version, *body):
            if method == "get" and resource == PROJECT:
                return {"location": "westus3", "identity": {"principalId": "principal"}}
            if method == "get" and resource == APPI:
                return {"properties": {
                    "ConnectionString": "placeholder", "WorkspaceResourceId": "workspace", "DisableLocalAuth": True,
                }}
            if "/roleAssignments/" in resource:
                if method == "put":
                    assignments[resource] = body[0]
                    return body[0]
                if method == "delete":
                    deleted.append(resource)
                    del assignments[resource]
                    return {}
                if resource in assignments:
                    return assignments[resource]
                raise setup.AzureError("Not found", "RoleAssignmentNotFound")
            if method == "put" and "/connections/" in resource:
                raise setup.AzureError("PolicyDenied")
            self.fail(f"Unexpected request: {method} {resource}")

        cli.rest.side_effect = rest
        with mock.patch.object(setup, "connection", side_effect=[None, None, None]):
            with self.assertRaisesRegex(setup.AzureError, "PolicyDenied"):
                setup.prepare(cli, PROJECT, application_insights=APPI)
        self.assertEqual(3, len(deleted))
        self.assertEqual({}, assignments)
        self.assertTrue(all("/roleAssignments/" in resource for resource in deleted))

    def test_uncertain_connection_put_preserves_attached_destination(self):
        cli = self.cli()
        original = cli.rest.side_effect

        def rest(method, resource, version, *body):
            if method == "put" and "/connections/" in resource:
                raise setup.AzureError("Timed out")
            if method == "get" and resource == APPI:
                return {"properties": {
                    "ConnectionString": "placeholder", "WorkspaceResourceId": "workspace", "DisableLocalAuth": True,
                }}
            return original(method, resource, version, *body)

        cli.rest.side_effect = rest
        link = {"application_insights_resource_id": APPI}
        with mock.patch.object(setup, "connection", side_effect=[None, None, link]), \
                mock.patch.object(setup, "wait_ready", return_value={"properties": {
                    "ConnectionString": "placeholder", "WorkspaceResourceId": "workspace", "DisableLocalAuth": True,
                }}):
            with self.assertRaisesRegex(setup.AzureError, "Timed out"):
                setup.prepare(cli, PROJECT, application_insights=APPI)
        self.assertFalse(any(call.args[0] == "delete" for call in cli.rest.call_args_list))

    def test_provisioning_deadline_is_bounded(self):
        cli = mock.Mock()
        cli.rest.return_value = {"properties": {"provisioningState": "Creating"}}
        with self.assertRaisesRegex(setup.AzureError, "Timed out"):
            setup.wait_ready(cli, APPI, "version", 0)

    @mock.patch.object(setup, "connection", return_value=None)
    @mock.patch.object(setup, "wait_ready", side_effect=setup.AzureError("PolicyDenied"))
    def test_original_error_survives_cleanup_failure(self, _ready, _connection):
        cli = self.cli()
        original = cli.rest.side_effect
        cli.rest.side_effect = lambda method, *args: (
            (_ for _ in ()).throw(setup.AzureError("CleanupDenied"))
            if method == "delete" else original(method, *args)
        )
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaisesRegex(setup.AzureError, "PolicyDenied"):
                setup.prepare(cli, PROJECT)
        self.assertIn("Cleanup unverified", stderr.getvalue())


class AzureCLITests(unittest.TestCase):
    @mock.patch.object(setup.subprocess, "run")
    def test_plain_arm_not_found_is_recognized_during_cleanup(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, "", "ERROR: Not Found\n")
        with self.assertRaises(setup.AzureError) as raised:
            setup.AzureCLI().run("rest")
        self.assertEqual("NotFound", raised.exception.code)

    def test_repeated_pagination_link_is_rejected(self):
        cli = setup.AzureCLI()
        page = {"value": [], "nextLink": setup.ARM + "/next"}
        with mock.patch.object(cli, "rest", return_value=page), \
                mock.patch.object(cli, "run", return_value=page) as run:
            with self.assertRaisesRegex(setup.AzureError, "repeated"):
                cli.list("/resource", "version")
        run.assert_called_once()

    @mock.patch.object(setup.subprocess, "run")
    def test_failure_does_not_echo_connection_credentials(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, "", "(PolicyDenied) credentials=secret-value")
        with self.assertRaises(setup.AzureError) as raised:
            setup.AzureCLI().run("rest")
        self.assertIn("PolicyDenied", str(raised.exception))
        self.assertNotIn("secret-value", str(raised.exception))

    @mock.patch.object(setup.subprocess, "run")
    def test_invalid_json_is_an_error(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "not-json", "")
        with self.assertRaisesRegex(setup.AzureError, "malformed JSON"):
            setup.AzureCLI().run("rest")


if __name__ == "__main__":
    unittest.main()
