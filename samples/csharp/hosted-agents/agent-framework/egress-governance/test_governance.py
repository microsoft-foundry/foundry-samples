# Copyright (c) Microsoft. All rights reserved.

import argparse
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import governance as g


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.args = argparse.Namespace(state=Path(self.temporary.name) / "state.json")
        self.state = {
            "account": "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/test/providers/Microsoft.CognitiveServices/accounts/sample",
            "endpoint": "https://sample.services.ai.azure.com/api/projects/test",
            "run": "egov-123456789abc",
            "owned": [],
            "parameters": {
                "permittedDestinations": {"value": ["httpbin.org/get"]},
                "deniedDestinations": {"value": ["unapproved.example.com"]},
                "allowedActionTypes": {
                    "value": ["Allow", "Deny", "Transform", "Rewrite"]
                },
            },
        }

    def test_agent_cli_accepts_the_unapproved_source_guardrail_fixture(self):
        with patch.object(g, "load", return_value=self.state), patch.object(
            g, "agent"
        ) as create:
            g.main(
                [
                    "agent",
                    "--fixture",
                    "bad-source",
                    "--expect",
                    "denied",
                    "--image",
                    "registry.azurecr.io/probe@sha256:" + "a" * 64,
                ]
            )
        self.assertEqual(create.call_args.args[0].fixture, "bad-source")

    def test_denial_requires_intended_assignment_definition_and_error(self):
        assignment = (
            self.state["account"]
            + "/providers/Microsoft.Authorization/policyAssignments/"
            + self.state["run"]
            + "-agent"
        )
        body = {
            "error": {
                "code": "agent_policy_denied",
                "additionalInfo": {
                    "policy_assignment_id": assignment,
                    "policy_definition_id": g.PREFIX + g.DEFINITIONS["agent"],
                },
            }
        }
        g.assert_result(403, body, "denied", self.state, "agent", "agent_policy_denied")
        for field in ("policy_assignment_id", "policy_definition_id"):
            wrong = copy.deepcopy(body)
            wrong["error"]["additionalInfo"][field] = "unrelated"
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                g.assert_result(
                    403, wrong, "denied", self.state, "agent", "agent_policy_denied"
                )
        with self.assertRaises(RuntimeError):
            g.assert_result(
                200, {}, "denied", self.state, "agent", "agent_policy_denied"
            )
        with self.assertRaises(RuntimeError):
            g.assert_result(
                403,
                {"error": {"code": "Forbidden"}},
                "denied",
                self.state,
                "agent",
                "agent_policy_denied",
            )
        split = {
            "error": {
                "code": "agent_policy_denied",
                "details": [
                    {"policy_assignment_id": assignment},
                    {"policy_definition_id": g.PREFIX + g.DEFINITIONS["agent"]},
                ],
            }
        }
        with self.assertRaises(RuntimeError):
            g.assert_result(
                403, split, "denied", self.state, "agent", "agent_policy_denied"
            )

    def test_full_assignments_share_destinations_with_member_specific_parameters(self):
        self.args.confirm_account = self.state["account"]
        self.args.profile = "full"
        self.args.effect = "Audit"
        saved = {}

        def fake_request(method, url, body=None):
            if method == "PUT":
                saved[url] = body
                return 201, body
            return (200, saved[url]) if url in saved else (404, {})

        with patch.object(g, "request", side_effect=fake_request):
            g.assign(self.args, self.state)
        self.assertEqual(len(saved), 4)
        for body in saved.values():
            params = body["properties"]["parameters"]
            if (
                body["properties"]["policyDefinitionId"]
                == g.PREFIX + g.DEFINITIONS["headers"]
            ):
                self.assertEqual(set(params), {"effect"})
            else:
                self.assertEqual(
                    params["permittedDestinations"],
                    self.state["parameters"]["permittedDestinations"],
                )
                self.assertEqual(
                    params["deniedDestinations"],
                    self.state["parameters"]["deniedDestinations"],
                )
                if (
                    body["properties"]["policyDefinitionId"]
                    == g.PREFIX + g.DEFINITIONS["rewrite"]
                ):
                    self.assertNotIn("allowedActionTypes", params)
        self.args.profile = "baseline"
        with patch.object(g, "request", side_effect=fake_request):
            g.assign(self.args, self.state)
        for body in saved.values():
            member = body["properties"]["policyDefinitionId"]
            if member in (
                g.PREFIX + g.DEFINITIONS["rewrite"],
                g.PREFIX + g.DEFINITIONS["headers"],
            ):
                self.assertEqual(
                    body["properties"]["parameters"]["effect"]["value"], "Disabled"
                )

    def test_denied_fresh_agent_cannot_have_a_stored_version(self):
        self.args.fixture = "none"
        self.args.image = "registry.azurecr.io/probe@sha256:" + "a" * 64
        self.args.python_runtime = True
        self.args.expect = "denied"
        denied = {
            "error": {
                "code": "agent_policy_denied",
                "additionalInfo": {
                    "policy_assignment_id": self.state["account"]
                    + "/providers/Microsoft.Authorization/policyAssignments/"
                    + self.state["run"]
                    + "-agent",
                    "policy_definition_id": g.PREFIX + g.DEFINITIONS["agent"],
                },
            }
        }
        with patch.object(
            g,
            "request",
            side_effect=[
                (404, {}),
                (403, denied),
                (200, {"data": []}),
            ],
        ) as network:
            g.agent(self.args, self.state)
        self.assertNotIn("rai_config", network.call_args_list[1].args[2]["definition"])
        with patch.object(
            g,
            "request",
            side_effect=[
                (403, denied),
                (200, {"data": [{"version": "1"}]}),
            ],
        ), self.assertRaisesRegex(RuntimeError, "stored versions"):
            # Reuse the owned agent name to isolate the absence check.
            with patch.object(g.uuid, "uuid4") as identifier:
                identifier.return_value.hex = (
                    self.state["owned"][0]["url"].split("-agent-")[1].split("?")[0]
                )
                g.agent(self.args, self.state)

    def test_denied_update_must_preserve_previous_guardrail(self):
        self.args.fixture = "bad-source"
        self.args.member = "baseline"
        self.args.expect = "denied"
        url = (
            "https://management.azure.com"
            + self.state["account"]
            + "/raiPolicies/"
            + self.state["run"]
            + "-bad-source?api-version=2026-09-01"
        )
        self.state["owned"] = [{"kind": "guardrail", "url": url}]
        before = g.fixture("good")
        assignment = (
            self.state["account"]
            + "/providers/Microsoft.Authorization/policyAssignments/"
            + self.state["run"]
            + "-baseline"
        )
        denied = {
            "error": {
                "code": "RequestDisallowedByPolicy",
                "additionalInfo": [
                    {
                        "info": {
                            "policyAssignmentId": assignment,
                            "policyDefinitionId": g.PREFIX + g.DEFINITIONS["baseline"],
                        }
                    }
                ],
            }
        }
        with patch.object(
            g, "request", side_effect=[(200, before), (403, denied), (200, before)]
        ):
            g.guardrail(self.args, self.state)
        with patch.object(
            g,
            "request",
            side_effect=[
                (200, before),
                (403, denied),
                (200, g.fixture("bad-source")),
            ],
        ), self.assertRaisesRegex(RuntimeError, "changed"):
            g.guardrail(self.args, self.state)

    def test_cleanup_rejects_unowned_resources_and_deletes_assignments_first(self):
        base = "https://management.azure.com" + self.state["account"]
        self.state["owned"] = [
            {
                "kind": "guardrail",
                "url": base + "/raiPolicies/shared?api-version=2026-09-01",
            }
        ]
        with patch.object(g, "request") as network, self.assertRaises(ValueError):
            g.cleanup(self.args, self.state)
        network.assert_not_called()
        self.state["owned"] = [
            {
                "kind": "guardrail",
                "url": base
                + "/raiPolicies/"
                + self.state["run"]
                + "-good?api-version=2026-09-01",
            },
            {
                "kind": "assignment",
                "url": base
                + "/providers/Microsoft.Authorization/policyAssignments/"
                + self.state["run"]
                + "-agent?api-version=2024-04-01",
            },
        ]
        with patch.object(
            g, "request", side_effect=[(204, {}), (404, {}), (204, {}), (404, {})]
        ) as network:
            g.cleanup(self.args, self.state)
        self.assertIn("/policyAssignments/", network.call_args_list[0].args[1])

    def test_cleanup_waits_for_async_deletion_and_persists_only_verified_absence(self):
        url = (
            "https://management.azure.com"
            + self.state["account"]
            + "/raiPolicies/"
            + self.state["run"]
            + "-good?api-version=2026-09-01"
        )
        self.state["owned"] = [{"kind": "guardrail", "url": url}]
        with patch.object(
            g,
            "request",
            side_effect=[
                (202, {}),
                (200, {"properties": {"provisioningState": "Deleting"}}),
                (404, {}),
            ],
        ) as network, patch("time.sleep"), patch("time.monotonic", return_value=0):
            g.cleanup(self.args, self.state)
        self.assertEqual(
            [call.args[0] for call in network.call_args_list], ["DELETE", "GET", "GET"]
        )
        self.assertTrue(g.load(self.args.state)["owned"][0]["deleted"])

    def test_cleanup_timeout_keeps_the_resource_pending(self):
        url = (
            "https://management.azure.com"
            + self.state["account"]
            + "/raiPolicies/"
            + self.state["run"]
            + "-good?api-version=2026-09-01"
        )
        self.state["owned"] = [{"kind": "guardrail", "url": url}]
        with patch.object(g, "request", side_effect=[(202, {}), (200, {})]), patch(
            "time.sleep"
        ), patch("time.monotonic", side_effect=[0, 301]), self.assertRaisesRegex(
            RuntimeError, "deletion"
        ):
            g.cleanup(self.args, self.state)
        self.assertFalse(self.state["owned"][0].get("deleted", False))

    def test_recreated_assignments_and_guardrails_are_owned_before_write_and_cleaned(
        self,
    ):
        for kind in ("assignment", "guardrail"):
            with self.subTest(kind=kind):
                state = copy.deepcopy(self.state)
                remote = {}
                args = argparse.Namespace(
                    state=self.args.state,
                    confirm_account=state["account"],
                    profile="baseline",
                    effect="Audit",
                    fixture="good",
                    member="baseline",
                    expect="allowed",
                )

                def network(method, url, body=None):
                    if method == "GET":
                        return (
                            (200, copy.deepcopy(remote[url]))
                            if url in remote
                            else (404, {})
                        )
                    if method == "PUT":
                        persisted = next(
                            item
                            for item in g.load(args.state)["owned"]
                            if item["url"] == url
                        )
                        self.assertFalse(persisted.get("deleted", False))
                        remote[url] = copy.deepcopy(body)
                        return 201, copy.deepcopy(body)
                    if method == "DELETE":
                        remote.pop(url, None)
                        return 204, {}
                    self.fail("Unexpected method: " + method)

                write = g.assign if kind == "assignment" else g.guardrail
                with patch.object(g, "request", side_effect=network):
                    write(args, state)
                    g.cleanup(args, state)
                    self.assertFalse(remote)
                    args.effect = "Deny"
                    write(args, state)
                    self.assertTrue(remote)
                    if kind == "assignment":
                        self.assertTrue(
                            all(
                                body["properties"]["parameters"]["effect"]["value"]
                                == "Deny"
                                for body in remote.values()
                            )
                        )
                    g.cleanup(args, state)
                self.assertFalse(remote)
                self.assertTrue(
                    all(item.get("deleted") for item in g.load(args.state)["owned"])
                )

    def test_deleted_ownership_entry_cannot_reclaim_an_existing_resource(self):
        for kind, suffix in (
            ("assignment", "/providers/Microsoft.Authorization/policyAssignments/"),
            ("guardrail", "/raiPolicies/"),
        ):
            with self.subTest(kind=kind):
                state = copy.deepcopy(self.state)
                url = (
                    "https://management.azure.com"
                    + state["account"]
                    + suffix
                    + state["run"]
                    + "-good"
                )
                state["owned"] = [{"kind": kind, "url": url, "deleted": True}]
                g.save(self.args.state, state)
                with patch.object(g, "request", return_value=(200, {})) as network:
                    with self.assertRaises(RuntimeError):
                        g.own(self.args, state, kind, url)
                network.assert_called_once_with("GET", url)
                self.assertTrue(g.load(self.args.state)["owned"][0]["deleted"])

    def test_target_must_be_https_project_on_same_account(self):
        g.validate_target(self.state["account"], self.state["endpoint"])
        for endpoint in (
            "http://sample.services.ai.azure.com/api/projects/test",
            "https://other.services.ai.azure.com/api/projects/test",
            self.state["endpoint"] + "?redirect=other",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                g.validate_target(self.state["account"], endpoint)


if __name__ == "__main__":
    unittest.main()
