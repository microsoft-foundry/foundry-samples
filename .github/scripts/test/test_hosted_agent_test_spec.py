"""Regression tests for serializable contracts and fail-closed approval evidence."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hosted_agent_test_spec as spec


TRACE_CONTRACT = """\
version: 1
sample:
  owner: sampleowner
  experiences: [azd]
tests:
  - name: trace-evidence
    turns: [{input: hello}]
    assertions:
      - source: trace
        type: span
        attributes:
          observed:
            equals: VALUE
"""


class TraceValueTests(unittest.TestCase):
    def test_non_json_yaml_values_fail_before_writing_plan(self):
        for value in (
            "2026-09-18",
            "!!set {item: null}",
            "!!binary aGVsbG8=",
            ".nan",
            ".inf",
            "{1: value}",
            "{nested: [2026-09-18]}",
            "&cycle [*cycle]",
        ):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "test-spec.yml"
                output = Path(directory) / "plan.json"
                source.write_text(TRACE_CONTRACT.replace("VALUE", value), encoding="utf-8")
                messages = io.StringIO()
                with contextlib.redirect_stdout(messages):
                    result = spec.main(
                        ["plan", "--spec", str(source), "--output", str(output)]
                    )
                self.assertEqual(2, result)
                self.assertIn("equals", messages.getvalue())
                self.assertFalse(output.exists())

    def test_json_equals_values_remain_valid(self):
        values = (None, "", False, 0, 1.5, [], {}, {"nested": [True, None, 42, "text"]})
        for value in values:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "test-spec.yml"
                source.write_text(
                    TRACE_CONTRACT.replace("VALUE", json.dumps(value)), encoding="utf-8"
                )
                plan = spec.build_plan(spec.load_spec(source))
                serialized = json.loads(json.dumps(plan, allow_nan=False))
                self.assertEqual(
                    value, serialized["tests"][0]["assertions"][0]["attributes"]["observed"]["equals"]
                )


class ApprovalEvidenceTests(unittest.TestCase):
    def test_non_array_output_fails_even_after_all_approvals(self):
        policy = {"approvals": {"mcp": [{"server_label": "agent", "name": "tool"}]}}
        for output in ({}, "", 0, False, None, {"unexpected": True}, "text"):
            for turn, approved in (({}, set()), (policy, {"already-approved"})):
                with self.subTest(output=output, turn=turn):
                    decision = spec.decide_mcp_approvals(turn, {"output": output}, approved)
                    self.assertEqual("error", decision["status"])
                    self.assertEqual([], decision["approval_responses"])
                    self.assertNotIn("sequence_complete", decision)

    def test_missing_or_empty_output_keeps_valid_no_approval_behavior(self):
        for response in ({}, {"output": []}):
            with self.subTest(response=response):
                decision = spec.decide_mcp_approvals({}, response, set())
                self.assertEqual("none", decision["status"])


if __name__ == "__main__":
    unittest.main()
