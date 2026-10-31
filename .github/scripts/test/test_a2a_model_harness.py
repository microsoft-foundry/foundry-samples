"""Credential-free native A2A model-output contract regressions."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
import hosted_agent_test_spec as spec

HELPER = (
    ROOT / ".azure-pipelines/scripts/hosted-agents/scripts/invoke_hosted_agent_a2a.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location("a2a_helper", HELPER)
helper = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(helper)
CARD = {
    "name": "test",
    "supportedInterfaces": [{"protocolBinding": "JSONRPC", "protocolVersion": "1.0"}],
}
TASK = {
    "id": "task-1",
    "contextId": "context-1",
    "status": {"state": "TASK_STATE_COMPLETED"},
    "artifacts": [{"parts": [{"text": "test answer"}]}],
}


class NativeContractTests(unittest.TestCase):
    def test_exact_output_still_requires_exact_match(self):
        for expected, passes in (("test answer", True), ("wrong answer", False)):
            with self.subTest(expected=expected), patch.object(
                helper.A2AClient, "discover", return_value=CARD
            ), patch.object(
                helper.A2AClient, "rpc", side_effect=[{"task": TASK}, TASK]
            ):
                client = helper.A2AClient("https://example.test/a2a")
                scenario = {"message": "test", "expected_text": expected}
                if passes:
                    self.assertEqual(
                        TASK, helper.run_scenario(client, scenario)["task"]
                    )
                else:
                    with self.assertRaisesRegex(ValueError, "Expected artifact"):
                        helper.run_scenario(client, scenario)

    def test_pattern_requires_full_match(self):
        for pattern, passes in ((r"test .+", True), (r"answer", False)):
            with self.subTest(pattern=pattern), patch.object(
                helper.A2AClient, "discover", return_value=CARD
            ), patch.object(
                helper.A2AClient, "rpc", side_effect=[{"task": TASK}, TASK]
            ):
                client = helper.A2AClient("https://example.test/a2a")
                scenario = {"message": "test", "expected_pattern": pattern}
                if passes:
                    helper.run_scenario(client, scenario)
                else:
                    with self.assertRaisesRegex(ValueError, "required output pattern"):
                        helper.run_scenario(client, scenario)

    def test_matcher_and_timeout_validation(self):
        for scenario in (
            {"message": "test"},
            {"message": "test", "expected_text": "x", "expected_pattern": ".*"},
            {"message": "test", "expected_pattern": "["},
            {"message": "test", "expected_pattern": ""},
        ):
            with self.subTest(scenario=scenario), self.assertRaises(spec.SpecError):
                spec.validate_a2a_input(scenario)
        for timeout in (0, -1, True, 601, float("inf"), "180"):
            with self.subTest(timeout=timeout), self.assertRaises(spec.SpecError):
                spec.validate_a2a_input(
                    {
                        "message": "test",
                        "expected_text": "test answer",
                        "timeout_seconds": timeout,
                    }
                )
        client = helper.A2AClient("https://example.test/a2a")
        with patch.object(client, "discover", return_value=CARD), patch.object(
            client, "rpc", side_effect=[{"task": TASK}, TASK]
        ):
            helper.run_scenario(
                client,
                {
                    "message": "test",
                    "expected_text": "test answer",
                    "timeout_seconds": 240,
                },
            )
        self.assertEqual(240, client.timeout)

    def test_rpc_errors_and_mismatched_response_ids_fail(self):
        client = helper.A2AClient("https://example.test/a2a")
        for response in (
            {"jsonrpc": "2.0", "id": "wrong", "result": TASK},
            {"jsonrpc": "2.0", "id": "wrong", "error": {"code": -32000}},
        ):
            with self.subTest(response=response), patch.object(
                client, "_request", return_value=response
            ), self.assertRaises((ValueError, RuntimeError)):
                client.rpc("GetTask", {"id": "task-1"})

    def test_discovery_uses_public_and_local_card_routes(self):
        for endpoint, expected in (
            ("http://localhost:8088/a2a", "/a2a/.well-known/agent-card.json"),
            (
                "https://example.test/agents/test/endpoint/protocols/a2a",
                "/agents/test/endpoint/protocols/a2a/agentCard/v1.0",
            ),
        ):
            client = helper.A2AClient(endpoint)
            with patch.object(client, "_request", return_value=CARD) as request:
                client.discover()
                self.assertTrue(request.call_args.args[0].endswith(expected))

    def test_cloud_failure_records_failure_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.json"
            source.write_text(json.dumps({"message": "test", "expected_pattern": ".+"}))
            environment = {
                "AGENT_A2A_URL": "https://example.test/endpoint/protocols/a2a",
                "AAD_TOKEN": "fixture-token",
                "DEPLOYED_AGENT_VERSION": "1",
                "CI_AGENT_SESSION_ID": "fixture-session",
            }
            with patch.object(
                helper.A2AClient, "discover", side_effect=ValueError("bad Card")
            ):
                result = helper.invoke_turn(
                    1, source, root, 1, environment=environment, temp_dir=root
                )
            self.assertEqual(1, result["turn_exit"])
            for path in root.glob("*"):
                self.assertNotIn("fixture-token", path.read_text())


if __name__ == "__main__":
    unittest.main()
