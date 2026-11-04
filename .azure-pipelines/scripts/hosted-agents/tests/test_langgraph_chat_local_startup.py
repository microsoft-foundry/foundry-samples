"""Keep the LangGraph chat sample's local and hosted entrypoints aligned."""

from pathlib import Path
import shlex
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[4]
SAMPLE = ROOT / "samples/python/hosted-agents/langgraph/responses/01-langgraph-chat"


class LangGraphChatLocalStartupTests(unittest.TestCase):
    def setUp(self):
        manifest = yaml.safe_load((SAMPLE / "azure.yaml").read_text(encoding="utf-8"))
        self.service = manifest["services"]["langgraph-chat-responses"]

    def test_local_command_matches_hosted_entrypoint(self):
        expected = [
            "uv", "run", "--no-sync", "python",
            *shlex.split(self.service["codeConfiguration"]["entryPoint"]),
        ]
        self.assertEqual(shlex.split(self.service.get("startupCommand", "")), expected)

    def test_local_command_declares_responses_protocol(self):
        self.assertIn("--protocol responses", self.service.get("startupCommand", ""))
        self.assertEqual(
            self.service["protocols"],
            [{"protocol": "responses", "version": "2.0.0"}],
        )


if __name__ == "__main__":
    unittest.main()
