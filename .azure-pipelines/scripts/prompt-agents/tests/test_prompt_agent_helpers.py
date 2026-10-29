"""Offline validation for prompt-agent ownership and evidence helpers."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "prompt_agent_helpers.py"
SPEC = importlib.util.spec_from_file_location("prompt_helpers", SCRIPT)
helpers = importlib.util.module_from_spec(SPEC)
with mock.patch.object(sys, "path", [str(SCRIPT.parent), *sys.path]):
    SPEC.loader.exec_module(helpers)


class HelperTests(unittest.TestCase):
    def test_prompt_and_managed_manifest_restrictions(self):
        document = {"services": {
            "project": {"host": "azure.ai.project"},
            "agent": {"host": "azure.ai.agent", "kind": "prompt", "project": ".", "uses": ["project"]},
        }}
        self.assertEqual(helpers.validate_manifest(document, "agent"), "project")
        document["services"]["agent"].update(
            harness={"type": "github_copilot_preview"},
            uses=["project", "toolbox"], toolbox={"name": "toolbox"},
        )
        with self.assertRaisesRegex(helpers.LifecycleError, "exactly one"):
            helpers.validate_manifest(document, "agent")
        document["services"]["toolbox"] = {
            "host": "azure.ai.toolbox", "uses": ["project"], "tools": [{"type": "web_search"}],
        }
        for harness_type in ("github_copilot_preview", "microsoft_copilot_preview"):
            document["services"]["agent"]["harness"] = {"type": harness_type}
            self.assertEqual(helpers.validate_manifest(document, "agent"), "project")
        for bad_harness in ("", {"type": ""}, {"type": "bad name"}, {"type": "ok", "extra": True}):
            document["services"]["agent"]["harness"] = bad_harness
            with self.assertRaisesRegex(helpers.LifecycleError, "managed harness.type must be a nonempty identifier"):
                helpers.validate_manifest(document, "agent")
        document["services"]["agent"]["harness"] = {"type": "microsoft_copilot_preview"}
        document["services"]["toolbox"]["tools"] = [{"type": "mcp"}]
        with self.assertRaisesRegex(helpers.LifecycleError, "only web_search"):
            helpers.validate_manifest(document, "agent")

    def test_absence_requires_exact_owned_target(self):
        name = "ci-prompt-owned"
        endpoint = "https://project.invalid/api/projects/project"
        message = (f'failed to get prompt agent "{name}": GET {endpoint}/agents/{name}?api-version=v1\n'
                   "RESPONSE 404: 404 Not Found\n")
        self.assertTrue(helpers.agent_absent(message, 1, name, endpoint))
        self.assertFalse(helpers.agent_absent(message, 0, name, endpoint))
        self.assertFalse(helpers.agent_absent(message, 124, name, endpoint))
        self.assertFalse(helpers.agent_absent(message, 137, name, endpoint))
        self.assertFalse(helpers.agent_absent(message, 1, "ci-prompt-other", endpoint))
        self.assertFalse(helpers.agent_absent(message.replace("404: 404", "403: 403"), 1, name, endpoint))

    def test_toolbox_endpoint_and_absence_are_pinned(self):
        context = {
            "execution_profile": "managed", "agent_name": "ci-prompt-owned",
            "toolbox_name": "ci-e2e-tb-owned", "project_endpoint": "https://project.invalid/api/projects/project",
        }
        endpoint = context["project_endpoint"] + "/toolboxes/ci-e2e-tb-owned/versions/3/mcp?api-version=v1"
        metadata = {
            "toolbox": {"name": context["toolbox_name"]},
            "version": {"name": context["toolbox_name"], "version": "3", "tools": [{"type": "web_search"}]},
            "endpoint": endpoint,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.json"
            path.write_text(json.dumps(metadata), encoding="utf-8")
            helpers.verify_toolbox(path, context, endpoint)
            with self.assertRaisesRegex(helpers.LifecycleError, "MCP endpoint"):
                helpers.verify_toolbox(path, context, endpoint.replace("versions/3", "versions/4"))
            path.write_text(json.dumps({"toolboxes": [{"name": context["toolbox_name"].upper()}]}), encoding="utf-8")
            self.assertFalse(helpers.toolbox_absent(path, context))
            path.write_text('{"toolboxes": [{}]}', encoding="utf-8")
            with self.assertRaisesRegex(helpers.LifecycleError, "nonempty toolbox names"):
                helpers.toolbox_absent(path, context)


if __name__ == "__main__":
    unittest.main()
