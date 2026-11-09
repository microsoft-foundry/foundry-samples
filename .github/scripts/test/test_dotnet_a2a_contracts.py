"""Native A2A planning retains Responses and Invocations approval boundaries."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hosted_agent_test_spec as spec
from check_hosted_agent_contracts import _selected_protocol

ROOT = Path(__file__).resolve().parents[3]


class NativeA2ATests(unittest.TestCase):
    def test_both_dotnet_samples_plan_as_native_a2a(self):
        for sample in ("echo", "travel-planner-web-search"):
            with self.subTest(sample=sample):
                manifest = ROOT / "samples/csharp/hosted-agents/bring-your-own/a2a" / sample / "azure.yaml"
                fixture = ROOT / ".azure-pipelines/hosted-agent-tests/csharp/bring-your-own/a2a" / sample / "test-spec.yml"
                self.assertEqual("a2a", _selected_protocol(manifest))
                plan = spec.build_plan(spec.load_spec(fixture), protocol="a2a")
                self.assertEqual(1 if sample == "echo" else 2, len(plan["tests"]))

    def test_a2a_does_not_accept_responses_approval_contracts(self):
        document = {
            "tests": [{
                "name": "not-responses",
                "turns": [{"input": "hello", "approvals": {"mcp": []}}],
            }]
        }
        with self.assertRaises(spec.SpecError):
            spec.build_plan(document, protocol="a2a")

    def test_a2a_does_not_accept_responses_previous_turn(self):
        document = {
            "tests": [{
                "name": "not-a-responses-chain",
                "turns": [{"input": "first"}, {"input": "second", "previous_turn": 1}],
            }]
        }
        with self.assertRaises(spec.SpecError):
            spec.build_plan(document, protocol="a2a")
