#!/usr/bin/env python3
"""Unit tests for the hosted-agent E2E test-spec framework."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location(
    "hosted_agent_test_spec", SCRIPTS / "hosted_agent_test_spec.py"
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)

TRACE_SPEC = importlib.util.spec_from_file_location(
    "collect_hosted_agent_traces", SCRIPTS / "collect-hosted-agent-traces.py"
)
assert TRACE_SPEC and TRACE_SPEC.loader
trace_module = importlib.util.module_from_spec(TRACE_SPEC)
sys.modules[TRACE_SPEC.name] = trace_module
TRACE_SPEC.loader.exec_module(trace_module)

INVOKE_SPEC = importlib.util.spec_from_file_location(
    "invoke_hosted_agent_responses", SCRIPTS / "invoke_hosted_agent_responses.py"
)
assert INVOKE_SPEC and INVOKE_SPEC.loader
invoke_module = importlib.util.module_from_spec(INVOKE_SPEC)
sys.modules[INVOKE_SPEC.name] = invoke_module
INVOKE_SPEC.loader.exec_module(invoke_module)


BASE = """\
version: 1
sample:
  owner: wemeng
  experiences: [azd, vscode]
tests:
  - name: basic
    turns:
      - input: hello
        assertions:
          - source: assistant_text
            type: contains
            value: world
"""


class SpecSchemaTests(unittest.TestCase):
    def load(self, text: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test-spec.yml"
            path.write_text(text, encoding="utf-8")
            return module.load_spec(path)

    def test_owner_is_required(self):
        with self.assertRaisesRegex(module.SpecError, "missing key.*owner"):
            self.load(BASE.replace("  owner: wemeng\n", ""))

    def test_verified_alias_is_allowed(self):
        document = self.load(BASE.replace("owner: wemeng", "owner: zhuoqunli"))
        self.assertEqual(document["sample"]["owner"], "zhuoqunli")

    def test_email_owner_is_rejected(self):
        with self.assertRaisesRegex(module.SpecError, "without @microsoft.com"):
            self.load(BASE.replace("owner: wemeng", "owner: x@microsoft.com"))

    def test_duplicate_key_is_rejected(self):
        with self.assertRaisesRegex(module.SpecError, "duplicate key 'version'"):
            self.load("version: 1\nversion: 1\nsample: {}\ntests: []\n")

    def test_unknown_key_is_rejected(self):
        with self.assertRaisesRegex(module.SpecError, "unknown key"):
            self.load(BASE.replace("sample:\n", "sample:\n  mystery: true\n"))

    def test_duplicate_test_name_is_rejected(self):
        duplicate = (
            BASE
            + """\
  - name: basic
    turns:
      - input: again
"""
        )
        with self.assertRaisesRegex(module.SpecError, "duplicates test name"):
            self.load(duplicate)

    def test_wrong_scope_is_rejected(self):
        invalid = BASE.replace("source: assistant_text", "source: console_log")
        with self.assertRaisesRegex(module.SpecError, "not valid at turn scope"):
            self.load(invalid)

    def test_ambiguous_legacy_sources_are_rejected(self):
        for source in ("response", "protocol"):
            with self.subTest(source=source), self.assertRaisesRegex(
                module.SpecError, "source is unsupported"
            ):
                self.load(BASE.replace("source: assistant_text", f"source: {source}"))

    def test_invalid_absence_bounds_are_rejected(self):
        invalid = BASE.replace(
            "value: world",
            "value: world\n            min_matches: 1\n            max_matches: 0",
        )
        with self.assertRaisesRegex(module.SpecError, "greater than or equal"):
            self.load(invalid)

    def test_empty_contains_is_rejected_but_empty_equals_is_allowed(self):
        empty = BASE.replace("value: world", 'value: ""')
        with self.assertRaisesRegex(module.SpecError, "non-empty string"):
            self.load(empty)
        document = self.load(empty.replace("type: contains", "type: equals"))
        self.assertEqual(document["tests"][0]["turns"][0]["assertions"][0]["value"], "")

    def test_nested_json_compatible_input_is_allowed(self):
        document = module.validate_spec(
            {
                "version": 1,
                "sample": {"owner": "wemeng", "experiences": ["azd"]},
                "tests": [
                    {
                        "name": "structured",
                        "turns": [
                            {
                                "input": {
                                    "values": ["text", 1, 1.5, True, None],
                                    "nested": {"ok": False},
                                }
                            }
                        ],
                    }
                ],
            }
        )
        self.assertIn(
            '"nested":{"ok":false}',
            module.build_plan(document)["tests"][0]["turns"][0]["serialized_input"],
        )

    def test_non_json_compatible_nested_inputs_are_rejected(self):
        invalid_values = [
            {"value": {1, 2}},
            {"value": b"bytes"},
            {"value": (1, 2)},
            {1: "non-string key"},
            {"value": float("nan")},
            {"value": float("inf")},
        ]
        for turn_input in invalid_values:
            document = {
                "version": 1,
                "sample": {"owner": "wemeng", "experiences": ["azd"]},
                "tests": [{"name": "bad", "turns": [{"input": turn_input}]}],
            }
            with self.subTest(turn_input=turn_input), self.assertRaises(
                module.SpecError
            ):
                module.validate_spec(document)

    def test_recursive_input_is_rejected(self):
        turn_input = []
        turn_input.append(turn_input)
        document = {
            "version": 1,
            "sample": {"owner": "wemeng", "experiences": ["azd"]},
            "tests": [{"name": "recursive", "turns": [{"input": turn_input}]}],
        }
        with self.assertRaisesRegex(module.SpecError, "recursive value"):
            module.validate_spec(document)

    def test_yaml_timestamp_input_is_rejected_as_invalid_spec(self):
        invalid = BASE.replace("input: hello", "input:\n          date: 2026-01-01")
        with self.assertRaisesRegex(module.SpecError, "JSON-compatible"):
            self.load(invalid)

    def test_json_path_is_not_supported(self):
        assertion = """\
          - source: raw
            type: json_path
            path: $.status
            operator: exists
"""
        invalid = BASE.replace(
            "          - source: assistant_text\n            type: contains\n            value: world\n",
            assertion,
        )
        with self.assertRaisesRegex(module.SpecError, "type is unsupported"):
            self.load(invalid)

    def test_unsafe_session_path_is_rejected(self):
        assertion = """\
          - source: session_files
            type: exists
            path: /generated/../secret
"""
        invalid = BASE.replace(
            "          - source: assistant_text\n            type: contains\n            value: world\n",
            assertion,
        )
        with self.assertRaisesRegex(module.SpecError, "must not contain"):
            self.load(invalid)

    def test_trace_requires_predicate(self):
        invalid = BASE.replace(
            "    turns:\n",
            "    assertions:\n      - source: trace\n        type: span\n    turns:\n",
        )
        with self.assertRaisesRegex(module.SpecError, "at least one"):
            self.load(invalid)

    def test_valid_turn_approval_sequence(self):
        document = self.load(
            BASE.replace(
                "      - input: hello\n",
                """      - input: hello
        approvals:
          mcp:
            - server_label: agent_framework
              name: load_skill
            - server_label: agent_framework
              name: run_skill_script
""",
            )
        )
        sequence = document["tests"][0]["turns"][0]["approvals"]["mcp"]
        self.assertEqual(
            [step["name"] for step in sequence], ["load_skill", "run_skill_script"]
        )

    def test_repeated_approval_sequence_steps_are_allowed(self):
        document = self.load(
            BASE.replace(
                "      - input: hello\n",
                """      - input: hello
        approvals:
          mcp:
            - server_label: agent_framework
              name: run_query
            - server_label: agent_framework
              name: run_query
""",
            )
        )
        self.assertEqual(len(document["tests"][0]["turns"][0]["approvals"]["mcp"]), 2)

    def test_invalid_turn_approval_sequences(self):
        base_policy = {
            "mcp": [
                {"server_label": "agent_framework", "name": "load_skill"},
                {"server_label": "agent_framework", "name": "run_skill_script"},
            ]
        }
        invalid_cases = [
            ({**base_policy, "unknown": True}, "unknown key"),
            ({"mcp": []}, "non-empty sequence"),
            ({"mcp": [{"server_label": "label"}]}, "missing key.*name"),
            ({"mcp": [{"name": "tool"}]}, "missing key.*server_label"),
            (
                {"mcp": [{"server_label": "label", "name": "tool", "extra": True}]},
                "unknown key",
            ),
            ({"mcp": [{"server_label": "*", "name": "tool"}]}, "wildcards"),
            ({"mcp": [{"server_label": "label", "name": "tool?"}]}, "wildcards"),
        ]
        for policy, message in invalid_cases:
            document = {
                "version": 1,
                "sample": {"owner": "wemeng", "experiences": ["azd"]},
                "tests": [
                    {"name": "bad", "turns": [{"input": "go", "approvals": policy}]}
                ],
            }
            with self.subTest(policy=policy), self.assertRaisesRegex(
                module.SpecError, message
            ):
                module.validate_spec(document)


class PlanningTests(unittest.TestCase):
    def document(self):
        return module.validate_spec(
            {
                "version": 1,
                "sample": {"owner": "wemeng", "experiences": ["azd"]},
                "tests": [
                    {"name": "always", "turns": [{"input": {"query": "one"}}]},
                    {
                        "name": "toolbox",
                        "when": {"toolbox_label": "code-interpreter"},
                        "turns": [{"input": "declared"}],
                    },
                ],
            }
        )

    def test_structured_input_is_compact_json(self):
        plan = module.build_plan(self.document())
        self.assertEqual(
            plan["tests"][0]["turns"][0]["serialized_input"], '{"query":"one"}'
        )

    def test_nonmatching_condition_is_not_applicable(self):
        plan = module.build_plan(self.document(), "web-search")
        self.assertEqual(plan["tests"][1]["status"], "not_applicable")

    def test_toolbox_query_explicitly_replaces_conditioned_test(self):
        plan = module.build_plan(self.document(), "code-interpreter", "42 * 17")
        test = plan["tests"][1]
        self.assertEqual(test["input_source"], "toolbox_query")
        self.assertEqual(test["turns"][0]["serialized_input"], "42 * 17")

    def test_invocations_toolbox_query_retains_structured_payload(self):
        plan = module.build_plan(
            self.document(), "code-interpreter", "42 * 17", protocol="invocations"
        )
        self.assertEqual(
            plan["tests"][1]["turns"][0]["serialized_input"],
            '{"query":"42 * 17"}',
        )

    def test_approval_sequence_survives_toolbox_override(self):
        document = self.document()
        document["tests"][1]["turns"][0]["approvals"] = {
            "mcp": [{"server_label": "agent_framework", "name": "load_skill"}]
        }
        plan = module.build_plan(document, "code-interpreter", "question")
        self.assertEqual(
            plan["tests"][1]["turns"][0]["approvals"],
            document["tests"][1]["turns"][0]["approvals"],
        )

    def test_approval_policy_is_rejected_for_invocations(self):
        document = self.document()
        document["tests"][0]["turns"][0]["approvals"] = {
            "mcp": [{"server_label": "agent_framework", "name": "load_skill"}]
        }
        with self.assertRaisesRegex(module.SpecError, "Responses protocol"):
            module.build_plan(document, protocol="invocations")

    def test_assistant_text_is_rejected_for_invocations(self):
        document = self.document()
        document["tests"][0]["turns"][0]["assertions"] = [
            {"source": "assistant_text", "type": "contains", "value": "hello"}
        ]
        with self.assertRaisesRegex(module.SpecError, "assistant_text.*Responses"):
            module.build_plan(document, protocol="invocations")


class ApprovalDecisionTests(unittest.TestCase):
    def turn(self, policy=True):
        turn = {"input": "go"}
        if policy:
            turn["approvals"] = {
                "mcp": [
                    {"server_label": "agent_framework", "name": "load_skill"},
                    {"server_label": "agent_framework", "name": "run_skill_script"},
                ]
            }
        return turn

    def response(self, *requests):
        return {
            "output": [
                {"type": "mcp_approval_request", **request} for request in requests
            ]
        }

    def test_absent_policy_leaves_request_pending(self):
        decision = module.decide_mcp_approvals(
            self.turn(False),
            self.response(
                {"id": "one", "server_label": "agent_framework", "name": "load_skill"}
            ),
            set(),
        )
        self.assertEqual(decision["status"], "pending")
        self.assertEqual(decision["approval_responses"], [])

    def test_expected_sequence_is_approved_one_step_at_a_time(self):
        first = module.decide_mcp_approvals(
            self.turn(),
            self.response(
                {"id": "one", "server_label": "agent_framework", "name": "load_skill"}
            ),
            set(),
        )
        self.assertEqual(first["status"], "approved")
        self.assertEqual(first["step"], 1)
        self.assertEqual(first["new_ids"], ["one"])

        second = module.decide_mcp_approvals(
            self.turn(),
            self.response(
                {
                    "id": "two",
                    "server_label": "agent_framework",
                    "name": "run_skill_script",
                }
            ),
            {"one"},
        )
        self.assertEqual(second["status"], "approved")
        self.assertEqual(second["step"], 2)

        completed = module.decide_mcp_approvals(
            self.turn(), self.response(), {"one", "two"}
        )
        self.assertEqual(completed["status"], "none")
        self.assertTrue(completed["sequence_complete"])

    def test_missing_reordered_extra_and_multiple_steps_fail(self):
        cases = [
            (self.response(), set()),
            (
                self.response(
                    {
                        "id": "one",
                        "server_label": "agent_framework",
                        "name": "run_skill_script",
                    }
                ),
                set(),
            ),
            (
                self.response(
                    {"id": "three", "server_label": "browser", "name": "click"}
                ),
                {"one", "two"},
            ),
            (
                self.response(
                    {
                        "id": "one",
                        "server_label": "agent_framework",
                        "name": "load_skill",
                    },
                    {
                        "id": "two",
                        "server_label": "agent_framework",
                        "name": "run_skill_script",
                    },
                ),
                set(),
            ),
        ]
        for response, approved in cases:
            with self.subTest(response=response, approved=approved):
                decision = module.decide_mcp_approvals(self.turn(), response, approved)
                self.assertEqual(decision["status"], "error")
                self.assertEqual(decision["approval_responses"], [])

    def test_malformed_response_shapes_are_errors(self):
        for response in ([], "text", {"output": "not-an-array"}, {"output": None}):
            with self.subTest(response=response):
                decision = module.decide_mcp_approvals(self.turn(), response, set())
                self.assertEqual(decision["status"], "error")

    def test_malformed_duplicate_and_repeated_ids_are_errors(self):
        cases = [
            (
                self.response(
                    {"id": "", "server_label": "agent_framework", "name": "load_skill"}
                ),
                set(),
            ),
            (
                self.response(
                    {
                        "id": "same",
                        "server_label": "agent_framework",
                        "name": "load_skill",
                    },
                    {
                        "id": "same",
                        "server_label": "agent_framework",
                        "name": "load_skill",
                    },
                ),
                set(),
            ),
            (
                self.response(
                    {
                        "id": "old",
                        "server_label": "agent_framework",
                        "name": "load_skill",
                    }
                ),
                {"old"},
            ),
        ]
        for response, approved in cases:
            with self.subTest(response=response, approved=approved):
                self.assertEqual(
                    module.decide_mcp_approvals(self.turn(), response, approved)[
                        "status"
                    ],
                    "error",
                )


class ResponsesInvocationTests(unittest.TestCase):
    ENVIRONMENT = {
        "AGENT_RESPONSES_URL": "https://example.test/responses",
        "AAD_TOKEN": "token",
        "DEPLOYED_AGENT_VERSION": "version",
        "CI_AGENT_SESSION_ID": "session",
    }

    @staticmethod
    def response(response_id, *, status="completed", output=None, error=None):
        value = {"id": response_id, "status": status, "output": output or []}
        if error is not None:
            value["error"] = error
        return value

    def invoke(self, responses, turn_record=None):
        root_context = tempfile.TemporaryDirectory()
        self.addCleanup(root_context.cleanup)
        root = Path(root_context.name)
        evidence = root / "evidence"
        evidence.mkdir()
        turn_file = root / "turn.txt"
        turn_file.write_text("do the work\n", encoding="utf-8")
        record_file = root / "turn.json"
        record_file.write_text(
            json.dumps(turn_record or {"input": "do the work"}), encoding="utf-8"
        )
        queued = list(responses)

        def transport(request_file, headers_file, raw_file, environment):
            self.assertEqual(environment["CI_AGENT_SESSION_ID"], "session")
            response = queued.pop(0)
            headers_file.write_text("HTTP/2 200\n", encoding="utf-8")
            raw_file.write_text(json.dumps(response), encoding="utf-8")
            return 0, "200"

        result = invoke_module.invoke_turn(
            77,
            turn_file,
            record_file,
            evidence,
            1,
            environment=self.ENVIRONMENT,
            transport=transport,
            temp_dir=root,
        )
        self.assertFalse(queued)
        return root, result

    def test_completed_response_succeeds(self):
        root, result = self.invoke(
            [
                self.response(
                    "response-1",
                    output=[
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "done"}],
                        }
                    ],
                )
            ]
        )
        self.assertEqual(result["turn_exit"], 0)
        self.assertEqual(
            (root / "invoke-response-77.txt").read_text(encoding="utf-8"), "done\n"
        )

    def test_failed_final_continuation_cannot_be_hidden_by_earlier_text(self):
        request = {
            "type": "mcp_approval_request",
            "id": "approval-1",
            "server_label": "agent_framework",
            "name": "run_tool",
        }
        initial_output = [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "Starting work"}],
            },
            request,
        ]
        root, result = self.invoke(
            [
                self.response("response-1", output=initial_output),
                self.response(
                    "response-2",
                    status="failed",
                    error={"code": "server_error"},
                ),
            ],
            {
                "input": "do the work",
                "approvals": {
                    "mcp": [{"server_label": "agent_framework", "name": "run_tool"}]
                },
            },
        )
        self.assertEqual(result["turn_exit"], 1)
        output = (root / "invoke-out-77.txt").read_text(encoding="utf-8")
        self.assertIn('"status": "failed"', output)
        self.assertIn('"code": "server_error"', output)
        self.assertEqual(
            (root / "invoke-response-77.txt").read_text(encoding="utf-8"),
            "Starting work\n",
        )


class TraceCollectorTests(unittest.TestCase):
    def test_resolves_component_properties_and_normalizes_spans(self):
        query_response = {
            "tables": [
                {
                    "columns": [
                        {"name": "timestamp"},
                        {"name": "itemType"},
                        {"name": "name"},
                        {"name": "success"},
                        {"name": "customDimensions"},
                        {"name": "operation_Id"},
                        {"name": "id"},
                    ],
                    "rows": [
                        [
                            "2026-01-01T00:00:00Z",
                            "dependency",
                            "execute_tool",
                            True,
                            {"gen_ai.tool.name": "GetWeather", "session": "ci-123"},
                            "trace-1",
                            "span-1",
                        ]
                    ],
                }
            ]
        }
        with mock.patch.object(
            trace_module,
            "_run_json",
            side_effect=[
                [
                    "/subscriptions/s/resourceGroups/rg/providers/microsoft.insights/components/app"
                ],
                {"id": "component", "appId": "app-id", "name": "app"},
                query_response,
            ],
        ):
            result = trace_module.collect("rg", "agent", "ci-123")
        self.assertTrue(result["available"])
        self.assertEqual(result["spans"][0]["name"], "execute_tool")
        self.assertEqual(result["spans"][0]["status"], "ok")
        self.assertEqual(
            result["spans"][0]["attributes"]["gen_ai.tool.name"], "GetWeather"
        )


class EvaluationTests(unittest.TestCase):
    def test_all_assertion_sources_and_absence(self):
        document = module.validate_spec(
            {
                "version": 1,
                "sample": {"owner": "wemeng", "experiences": ["azd"]},
                "tests": [
                    {
                        "name": "evidence",
                        "turns": [
                            {
                                "input": "go",
                                "assertions": [
                                    {
                                        "source": "assistant_text",
                                        "type": "contains",
                                        "value": "714",
                                    },
                                    {
                                        "source": "assistant_text",
                                        "type": "regex",
                                        "value": "traceback",
                                        "min_matches": 0,
                                        "max_matches": 0,
                                    },
                                    {
                                        "source": "raw",
                                        "type": "regex",
                                        "value": '"status"\\s*:\\s*"completed"',
                                    },
                                    {
                                        "source": "session_files",
                                        "type": "exists",
                                        "path": "/generated/guide.pdf",
                                    },
                                ],
                            }
                        ],
                        "assertions": [
                            {
                                "source": "console_log",
                                "type": "regex",
                                "value": "uncaught",
                                "min_matches": 0,
                                "max_matches": 0,
                            },
                            {
                                "source": "trace",
                                "type": "span",
                                "name": "execute_tool",
                                "attributes": {
                                    "gen_ai.tool.name": {"equals": "calculator"}
                                },
                                "status": "ok",
                            },
                        ],
                    }
                ],
            }
        )
        plan = module.build_plan(document)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "turn-1-assistant-text.txt").write_text(
                "The answer is 714", encoding="utf-8"
            )
            (root / "turn-1-raw.txt").write_text(
                json.dumps({"status": "completed"}), encoding="utf-8"
            )
            (root / "turn-1-session-files-4.json").write_text(
                json.dumps([{"name": "guide.pdf"}]), encoding="utf-8"
            )
            console = root / "console.txt"
            console.write_text("all good", encoding="utf-8")
            (root / "turn-1-status.json").write_text(
                json.dumps(
                    {
                        "exit_code": 0,
                        "mcp_approvals": {
                            "automatic": False,
                            "pending": 0,
                            "error": None,
                            "steps": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            trace = root / "trace.json"
            trace.write_text(
                json.dumps(
                    {
                        "available": True,
                        "spans": [
                            {
                                "name": "execute_tool",
                                "status": "ok",
                                "attributes": {"gen_ai.tool.name": "calculator"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report = module.evaluate_plan(plan, root, console, trace)
        self.assertEqual(report["status"], "passed")

    def test_approval_execution_error_marks_report_error(self):
        document = module.validate_spec(
            {
                "version": 1,
                "sample": {"owner": "wemeng", "experiences": ["azd"]},
                "tests": [{"name": "approval", "turns": [{"input": "go"}]}],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "turn-1-status.json").write_text(
                json.dumps(
                    {
                        "exit_code": 1,
                        "mcp_approvals": {
                            "automatic": True,
                            "pending": 1,
                            "error": "approval sequence mismatch",
                            "steps": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            report = module.evaluate_plan(
                module.build_plan(document), root, root / "console", root / "trace"
            )
        self.assertEqual(report["status"], "error")
        self.assertEqual(
            report["tests"][0]["turns"][0]["execution"]["mcp_approvals"]["error"],
            "approval sequence mismatch",
        )

    def test_malformed_turn_status_is_reported_as_error(self):
        document = module.validate_spec(
            {
                "version": 1,
                "sample": {"owner": "wemeng", "experiences": ["azd"]},
                "tests": [{"name": "status", "turns": [{"input": "go"}]}],
            }
        )
        for status in (
            None,
            [],
            {},
            {"exit_code": None},
            {"exit_code": False},
            {"exit_code": "0"},
            {"exit_code": 0},
            {"exit_code": 0, "mcp_approvals": None},
            {
                "exit_code": 0,
                "mcp_approvals": {
                    "automatic": "false",
                    "pending": 0,
                    "error": None,
                    "steps": [],
                },
            },
        ):
            with self.subTest(
                status=status
            ), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "turn-1-status.json").write_text(
                    json.dumps(status), encoding="utf-8"
                )
                report = module.evaluate_plan(
                    module.build_plan(document), root, root / "console", root / "trace"
                )
                self.assertEqual(report["status"], "error")

    def test_missing_required_evidence_is_error(self):
        document = module.validate_spec(
            {
                "version": 1,
                "sample": {"owner": "wemeng", "experiences": ["azd"]},
                "tests": [
                    {
                        "name": "missing",
                        "turns": [
                            {
                                "input": "go",
                                "assertions": [
                                    {
                                        "source": "assistant_text",
                                        "type": "contains",
                                        "value": "ok",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = module.evaluate_plan(
                module.build_plan(document), root, root / "console", root / "trace"
            )
        self.assertEqual(report["status"], "error")


if __name__ == "__main__":
    unittest.main()
