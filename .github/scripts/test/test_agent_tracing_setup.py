"""Offline tests for ownership-safe, existing-project tracing setup."""

import contextlib
from concurrent.futures import ThreadPoolExecutor
import errno
import io
import json
from pathlib import Path
import subprocess
import sys
from threading import Barrier, Lock
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_tracing_setup as setup

PROJECT = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/account/projects/project"
APPI = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Insights/components/appi"
IDENTITY = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.ManagedIdentity/userAssignedIdentities/agent"
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
    def setUp(self):
        lock = mock.patch.object(setup, "project_setup_lock", return_value=contextlib.nullcontext())
        self.setup_lock = lock.start()
        self.addCleanup(lock.stop)

    def cli(self, project_id=PROJECT):
        cli = mock.Mock()
        cli.list.return_value = []
        cli.rest.side_effect = lambda method, resource, version, *body: (
            {"location": "westus3", "identity": {"principalId": "principal"}}
            if method == "get" and resource == project_id else {}
        )
        return cli

    @mock.patch.object(setup, "connection", side_effect=[None, None, None])
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
    @mock.patch.object(setup, "wait_ready", return_value={"properties": {"ConnectionString": "placeholder"}})
    def test_resource_group_named_providers_preserves_resource_scope(self, _ready, _connection):
        for group in ("providers", "Providers"):
            project = PROJECT.replace("/resourceGroups/rg/", f"/resourceGroups/{group}/")
            scope = f"/subscriptions/sub/resourceGroups/{group}"
            cli = self.cli(project)
            with self.subTest(group=group):
                result = setup.prepare(cli, project)
                self.assertEqual("configured", result["status"])
                cli.list.assert_any_call(f"{scope}/resources", "2021-04-01")
                resources = [call.args[1] for call in cli.rest.call_args_list
                             if call.args[0] == "put" and "tags" in call.args[3]]
                self.assertEqual(2, len(resources))
                self.assertTrue(all(resource.startswith(f"{scope}/providers/") for resource in resources))

    @mock.patch.object(setup, "connection", return_value=None)
    @mock.patch.object(setup, "wait_ready", return_value={"properties": {"ConnectionString": "placeholder"}})
    def test_long_project_ids_have_bounded_stable_tags_and_full_output(self, _ready, _connection):
        project = (
            "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/"
            + "r" * 90 + "/providers/Microsoft.CognitiveServices/accounts/" + "a" * 64 + "/projects/project"
        )
        self.assertGreater(len(project), 256)
        project_tags = []
        for project_id in (project, project.upper(), project + "-other"):
            cli = self.cli(project_id)
            with self.subTest(project=project_id):
                result = setup.prepare(cli, project_id)
                tags = [call.args[3]["tags"] for call in cli.rest.call_args_list
                        if call.args[0] == "put" and "tags" in call.args[3]]
                self.assertEqual(2, len(tags))
                self.assertEqual(tags[0], tags[1])
                project_tags.append(tags[0]["foundry-tracing-project"])
                self.assertTrue(all(len(value) <= 256 for resource in tags for value in resource.values()))
                self.assertEqual(project_id, result["project_id"])
        self.assertEqual(project_tags[0], project_tags[1])
        self.assertNotEqual(project_tags[0], project_tags[2])

    def test_request_filesystem_error_rolls_back_created_resources_and_returns_exit_two(self):
        cli = setup.AzureCLI()
        resources = {}
        deleted = []
        write_text = Path.write_text

        def write(path, text, *args, **kwargs):
            properties = json.loads(text).get("properties", {})
            if properties.get("roleDefinitionId", "").endswith(setup.READER):
                self.assertEqual(3, len(resources))
                raise OSError(errno.ENOSPC, "Disk full")
            return write_text(path, text, *args, **kwargs)

        def run(*arguments):
            method = arguments[arguments.index("--method") + 1]
            resource = arguments[arguments.index("--url") + 1].removeprefix(setup.ARM).split("?", 1)[0]
            if method == "get":
                if resource == PROJECT:
                    return {"location": "westus3", "identity": {"principalId": "principal"}}
                if resource.endswith(("/resources", "/roleAssignments")):
                    return {"value": []}
                if resource in resources:
                    return resources[resource]
                raise setup.AzureError("Not found", "ResourceNotFound")
            if method == "put":
                body = json.loads(Path(arguments[arguments.index("--body") + 1][1:]).read_text())
                if "/components/" in resource:
                    body["properties"]["ConnectionString"] = "placeholder"
                resources[resource] = body
                return {}
            if method == "delete":
                del resources[resource]
                deleted.append(resource)
                return {}
            self.fail(f"Unexpected request: {method} {resource}")

        with mock.patch.object(setup, "connection", return_value=None), \
                mock.patch.object(cli, "run", side_effect=run), \
                mock.patch.object(setup, "AzureCLI", return_value=cli), \
                mock.patch.object(Path, "write_text", new=write), \
                mock.patch.object(sys, "argv", ["setup", "--project-id", PROJECT]), \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(2, setup.main())
        self.assertEqual({}, resources)
        self.assertEqual(3, len(deleted))
        self.assertIn("Disk full", stderr.getvalue())

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
        with mock.patch.object(setup, "connection", side_effect=[None, None, None, None]):
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
        with mock.patch.object(setup, "connection", side_effect=[None, None, None, link]), \
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

    def test_waiting_setup_reuses_winner_without_provisioning(self):
        cli = self.cli()
        with mock.patch.object(setup, "connection", side_effect=[None, LINK]):
            result = setup.prepare(cli, PROJECT)
        self.assertEqual("reused", result["status"])
        self.setup_lock.assert_called_once()
        cli.rest.assert_not_called()

    @mock.patch.object(setup, "connection", side_effect=[None, None, None])
    @mock.patch.object(setup, "wait_ready")
    def test_user_assigned_project_grants_roles_to_its_principal(self, ready, _connection):
        ready.side_effect = [{}, {"properties": {"ConnectionString": "placeholder"}}, {}]
        cli = self.cli()
        original = cli.rest.side_effect

        def rest(method, resource, version, *body):
            if method == "get" and resource == PROJECT:
                return {"location": "westus3", "identity": {
                    "type": "UserAssigned", "userAssignedIdentities": {IDENTITY: {"principalId": "uai-principal"}},
                }}
            return original(method, resource, version, *body)

        cli.rest.side_effect = rest
        result = setup.prepare(cli, PROJECT)
        roles = [call.args[3]["properties"]["principalId"] for call in cli.rest.call_args_list
                 if call.args[0] == "put" and "/roleAssignments/" in call.args[1]]
        self.assertEqual(["uai-principal"] * 3, roles)
        self.assertEqual("uai-principal", result["principal_id"])

    def test_failure_cleanup_finishes_before_releasing_lock(self):
        active = False

        @contextlib.contextmanager
        def lock(*args):
            nonlocal active
            active = True
            try:
                yield
            finally:
                active = False

        cli = self.cli()
        original = cli.rest.side_effect

        def rest(method, resource, version, *body):
            self.assertTrue(active)
            if method == "put":
                raise setup.AzureError("Policy denied", "PolicyDenied")
            return original(method, resource, version, *body)

        cli.rest.side_effect = rest
        self.setup_lock.side_effect = lock
        with mock.patch.object(setup, "connection", return_value=None), \
                mock.patch.object(setup, "delete_owned", side_effect=lambda *args: self.assertTrue(active)) as cleanup:
            with self.assertRaisesRegex(setup.AzureError, "Policy denied"):
                setup.prepare(cli, PROJECT)
        cleanup.assert_called_once()
        self.assertFalse(active)


class ProjectIdentityTests(unittest.TestCase):
    def test_system_identity_is_preserved_as_default(self):
        cli = mock.Mock()
        project = {"identity": {"principalId": "system", "userAssignedIdentities": {
            IDENTITY: {"principalId": "user"},
        }}}
        self.assertEqual("system", setup.project_principal(cli, project))
        cli.rest.assert_not_called()

    def test_single_user_identity_is_selected(self):
        cli = mock.Mock()
        project = {"identity": {"type": "UserAssigned", "userAssignedIdentities": {
            IDENTITY: {"principalId": "user"},
        }}}
        self.assertEqual("user", setup.project_principal(cli, project))
        cli.rest.assert_not_called()

    def test_missing_principal_is_resolved_from_attached_identity_resource(self):
        cli = mock.Mock()
        cli.rest.return_value = {"properties": {"principalId": "resolved"}}
        self.assertEqual("resolved", setup.project_principal(cli, {"identity": {
            "userAssignedIdentities": {IDENTITY: {}},
        }}))
        cli.rest.assert_called_once_with("get", IDENTITY, "2023-01-31")

    def test_multiple_user_identities_require_explicit_selection(self):
        project = {"identity": {"userAssignedIdentities": {
            IDENTITY: {"principalId": "first"}, IDENTITY + "-other": {"principalId": "second"},
        }}}
        with self.assertRaisesRegex(setup.AzureError, "Multiple"):
            setup.project_principal(mock.Mock(), project)
        self.assertEqual("second", setup.project_principal(mock.Mock(), project, (IDENTITY + "-other").upper()))

    def test_unattached_identity_is_rejected_without_reading_it(self):
        cli = mock.Mock()
        with self.assertRaisesRegex(setup.AzureError, "attached"):
            setup.project_principal(cli, {"identity": {"userAssignedIdentities": {
                IDENTITY: {"principalId": "first"},
            }}}, IDENTITY + "-unattached")
        cli.rest.assert_not_called()

    def test_unresolved_identity_is_an_explicit_error(self):
        cli = mock.Mock()
        cli.rest.return_value = {"properties": {}}
        with self.assertRaisesRegex(setup.AzureError, "no principal ID"):
            setup.project_principal(cli, {"identity": {"userAssignedIdentities": {IDENTITY: {}}}})


class ProjectLockTests(unittest.TestCase):
    def test_concurrent_clients_are_serialized_by_project_etags(self):
        mutex = Lock()
        initial_reads = Barrier(2)
        state = {"tags": {"existing": "keep"}, "version": 0, "reads": 0, "conflicts": 0,
                 "active": 0, "maximum_active": 0}

        def rest(method, resource, version, body=None, *, headers=None):
            self.assertEqual(PROJECT, resource)
            with mutex:
                if method == "get":
                    state["reads"] += 1
                    synchronize = state["reads"] <= 2
                    result = {"etag": str(state["version"]), "tags": dict(state["tags"])}
                else:
                    self.assertEqual("patch", method)
                    if headers != {"If-Match": str(state["version"])}:
                        state["conflicts"] += 1
                        raise setup.AzureError("ETag changed", "IfMatchPreconditionFailed")
                    state["tags"] = dict(body["tags"])
                    state["version"] += 1
                    return {}
            if synchronize:
                initial_reads.wait(timeout=5)
            return result

        def configure(_):
            cli = mock.Mock()
            cli.rest.side_effect = rest
            cli.deadline = time.monotonic() + 10
            with setup.project_setup_lock(cli, PROJECT, cli.deadline):
                with mutex:
                    state["active"] += 1
                    state["maximum_active"] = max(state["maximum_active"], state["active"])
                time.sleep(0.02)
                with mutex:
                    state["active"] -= 1

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(configure, range(2)))
        self.assertEqual(1, state["maximum_active"])
        self.assertGreaterEqual(state["conflicts"], 1)
        self.assertEqual({"existing": "keep"}, state["tags"])

    def test_missing_etag_fails_closed_without_mutations(self):
        cli = mock.Mock()
        cli.rest.return_value = {"tags": {}}
        with self.assertRaisesRegex(setup.AzureError, "no ETag"):
            with setup.project_setup_lock(cli, PROJECT, time.monotonic() + 10):
                self.fail("Unprotected setup must not run")
        self.assertEqual(1, cli.rest.call_count)

    def test_owned_lock_is_released_after_setup_failure(self):
        cli = mock.Mock()
        cli.deadline = time.monotonic() + 10
        state = {"tags": {"existing": "keep"}}

        def rest(method, resource, version, body=None, *, headers=None):
            if method == "get":
                return {"etag": "etag", "tags": dict(state["tags"])}
            state["tags"] = dict(body["tags"])
            return {}

        cli.rest.side_effect = rest
        for error in (setup.AzureError("Setup denied"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__), self.assertRaises(type(error)):
                with setup.project_setup_lock(cli, PROJECT, cli.deadline):
                    raise error
            self.assertEqual({"existing": "keep"}, state["tags"])

    def test_unrelated_or_replaced_lock_is_never_removed(self):
        cli = mock.Mock()
        cli.rest.return_value = {"etag": "etag", "tags": {setup.SETUP_LOCK_TAG: "another-run"}}
        setup._release_project_lock(cli, PROJECT, "my-run")
        self.assertEqual(1, cli.rest.call_count)

    @mock.patch.object(setup.time, "sleep")
    def test_release_retries_etag_conflict_and_preserves_new_tags(self, _sleep):
        cli = mock.Mock()
        cli.deadline = time.monotonic() + 10
        cli.rest.side_effect = [
            {"etag": "old", "tags": {setup.SETUP_LOCK_TAG.upper(): "owner"}},
            setup.AzureError("ETag changed", "IfMatchPreconditionFailed"),
            {"etag": "new", "tags": {setup.SETUP_LOCK_TAG: "owner", "new-tag": "keep"}},
            {},
        ]
        setup._release_project_lock(cli, PROJECT, "owner")
        self.assertEqual({"tags": {"new-tag": "keep"}}, cli.rest.call_args.args[3])
        self.assertEqual({"If-Match": "new"}, cli.rest.call_args.kwargs["headers"])

    def test_uncertain_claim_is_reconciled_and_released(self):
        cli = mock.Mock()
        cli.deadline = time.monotonic() + 10
        with mock.patch.object(setup.uuid, "uuid4", return_value=mock.Mock(hex="owner")):
            cli.rest.side_effect = [
                {"etag": "old", "tags": {}},
                setup.AzureError("Claim timed out"),
                {"etag": "new", "tags": {setup.SETUP_LOCK_TAG: "owner"}},
                {},
            ]
            with self.assertRaisesRegex(setup.AzureError, "Claim timed out"):
                with setup.project_setup_lock(cli, PROJECT, cli.deadline):
                    self.fail("An uncertain claim must not start setup")
        self.assertEqual({"tags": {}}, cli.rest.call_args.args[3])

    def test_release_failure_after_success_is_not_a_successful_result(self):
        cli = mock.Mock()
        cli.deadline = time.monotonic() + 10
        cli.rest.side_effect = [{"etag": "etag", "tags": {}}, {}, setup.AzureError("Release denied")]
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaisesRegex(setup.AzureError, "Release denied"):
            with setup.project_setup_lock(cli, PROJECT, cli.deadline):
                pass

    @mock.patch.object(setup.time, "sleep")
    @mock.patch.object(setup.time, "monotonic", side_effect=[0, 1, 2])
    def test_held_lock_wait_is_bounded_and_does_not_steal(self, _clock, _sleep):
        cli = mock.Mock()
        cli.rest.return_value = {"etag": "etag", "tags": {setup.SETUP_LOCK_TAG: "another-run"}}
        with self.assertRaisesRegex(setup.AzureError, "Timed out"):
            with setup.project_setup_lock(cli, PROJECT, 1):
                self.fail("Must not steal an active or abandoned lock")
        self.assertTrue(all(call.args[0] == "get" for call in cli.rest.call_args_list))

    def test_release_failure_does_not_mask_original_error(self):
        cli = mock.Mock()
        cli.deadline = time.monotonic() + 10
        cli.rest.side_effect = [{"etag": "etag", "tags": {}}, {}, setup.AzureError("Release denied")]
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaisesRegex(setup.AzureError, "Original"):
                with setup.project_setup_lock(cli, PROJECT, cli.deadline):
                    raise setup.AzureError("Original")
        self.assertIn("release unverified", stderr.getvalue())


class AzureCLITests(unittest.TestCase):
    def test_request_filesystem_failures_are_converted_to_azure_errors(self):
        for stage in ("directory", "headers", "body"):
            failure = OSError(errno.ENOSPC, "Disk full")
            patch = (
                mock.patch.object(setup.tempfile, "TemporaryDirectory", side_effect=failure)
                if stage == "directory" else mock.patch.object(Path, "write_text", side_effect=failure)
            )
            cli = setup.AzureCLI()
            with self.subTest(stage=stage), patch, mock.patch.object(cli, "run") as run:
                with self.assertRaises(setup.AzureError) as raised:
                    cli.rest("patch", PROJECT, setup.FOUNDRY_VERSION, {},
                             headers={"If-Match": "etag"} if stage == "headers" else None)
                self.assertIs(failure, raised.exception.__cause__)
                run.assert_not_called()

    def test_conditional_headers_are_preserved_via_json_file(self):
        cli = setup.AzureCLI()
        etag = '"quoted-etag"'

        def run(*arguments):
            headers_path = Path(arguments[arguments.index("--headers") + 1][1:])
            body_path = Path(arguments[arguments.index("--body") + 1][1:])
            self.assertEqual({"If-Match": etag}, json.loads(headers_path.read_text()))
            self.assertEqual({"tags": {"existing": "keep"}}, json.loads(body_path.read_text()))
            return {}

        with mock.patch.object(cli, "run", side_effect=run):
            cli.rest("patch", PROJECT, setup.FOUNDRY_VERSION, {"tags": {"existing": "keep"}},
                     headers={"If-Match": etag})

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
