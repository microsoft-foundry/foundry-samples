"""Offline validation for prompt-agent ownership and evidence helpers."""

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import yaml


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
        document["services"]["agent"].pop("toolbox")
        document["services"]["agent"].update(
            toolboxes=["toolbox"],
            tools=[
                {"type": "microsoft_copilot_toolset_preview", "defaultConfig": {"enabled": False}},
                {"type": "mcp", "server_label": "toolbox", "require_approval": "never"},
            ],
        )
        self.assertEqual(helpers.validate_manifest(document, "agent"), "project")
        for bad_harness in ("", {"type": ""}, {"type": "bad name"}, {"type": "ok", "extra": True}):
            document["services"]["agent"]["harness"] = bad_harness
            with self.assertRaisesRegex(helpers.LifecycleError, "managed harness.type must be a nonempty identifier"):
                helpers.validate_manifest(document, "agent")
        document["services"]["agent"]["harness"] = {"type": "microsoft_copilot_preview"}
        document["services"]["toolbox"]["tools"] = [{"type": "mcp"}]
        with self.assertRaisesRegex(helpers.LifecycleError, "only web_search"):
            helpers.validate_manifest(document, "agent")
        skill_doc = {"services": {
            "project": {"host": "azure.ai.project"},
            "travel-guide": {"host": "azure.ai.skill", "uses": ["project"], "archive": "./skills/travel-guide"},
            "agent": {
                "host": "azure.ai.agent", "kind": "prompt", "project": ".",
                "uses": ["project", "travel-guide"], "harness": {"type": "microsoft_copilot_preview"},
                "skills": ["travel-guide"], "tools": [{"type": "web_search"}],
            },
        }}
        self.assertEqual(helpers.validate_manifest(skill_doc, "agent"), "project")
        skill_doc["services"]["travel-guide"]["archive"] = "../outside"
        with self.assertRaisesRegex(helpers.LifecycleError, "skill archive"):
            helpers.validate_manifest(skill_doc, "agent")

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

    def test_toolbox_skill_and_connection_absence_are_pinned(self):
        nonce = "a" * 32
        context = {
            "execution_profile": "managed", "agent_name": "ci-prompt-" + nonce,
            "toolbox_name": "ci-e2e-tb-" + nonce, "skill_name": "ci-e2e-sk-" + nonce,
            "project_endpoint": "https://project.invalid/api/projects/project",
        }
        endpoint = context["project_endpoint"] + f"/toolboxes/{context['toolbox_name']}/versions/3/mcp?api-version=v1"
        context["toolbox_endpoint"] = endpoint
        context["connection_name"] = helpers.toolbox_connection_name(context["toolbox_name"], "3", endpoint)
        metadata = {
            "toolbox": {"name": context["toolbox_name"]},
            "version": {"name": context["toolbox_name"], "version": "3", "tools": [{"type": "web_search"}]},
            "endpoint": endpoint,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.json"
            path.write_text(json.dumps(metadata), encoding="utf-8")
            self.assertEqual(helpers.verify_toolbox(path, context, endpoint), "3")
            with self.assertRaisesRegex(helpers.LifecycleError, "MCP endpoint"):
                helpers.verify_toolbox(path, context, endpoint.replace("versions/3", "versions/4"))
            path.write_text(json.dumps({"toolboxes": [{"name": context["toolbox_name"].upper()}]}), encoding="utf-8")
            self.assertFalse(helpers.toolbox_absent(path, context))
            path.write_text('{"toolboxes": [{}]}', encoding="utf-8")
            with self.assertRaisesRegex(helpers.LifecycleError, "nonempty toolbox names"):
                helpers.toolbox_absent(path, context)
            path.write_text(json.dumps({"name": context["skill_name"], "default_version": "1", "latest_version": "1"}), encoding="utf-8")
            self.assertEqual(helpers.verify_skill(path, context, "1"), "1")
            with self.assertRaisesRegex(helpers.LifecycleError, "skill show returned"):
                helpers.verify_skill(path, context, "2")
            path.write_text(json.dumps([{"name": context["skill_name"].upper()}]), encoding="utf-8")
            self.assertFalse(helpers.skill_absent(path, context))
            conn_doc = {
                "name": context["connection_name"], "target": endpoint,
                "kind": "RemoteTool", "authType": "UserEntraToken",
            }
            path.write_text(json.dumps(conn_doc), encoding="utf-8")
            helpers.verify_connection(path, context)
            for field, bad_val in (("name", "wrong"), ("target", "https://other.invalid"), ("kind", "ApiKey"), ("authType", "ApiKey")):
                path.write_text(json.dumps({**conn_doc, field: bad_val}), encoding="utf-8")
                with self.assertRaisesRegex(helpers.LifecycleError, "connection show returned"):
                    helpers.verify_connection(path, context)
            tb_path = Path(directory) / "toolbox.json"
            tb_path.write_text(json.dumps(metadata), encoding="utf-8")
            conn_path = Path(directory) / "connection.json"
            conn_path.write_text(json.dumps(conn_doc), encoding="utf-8")
            agent_path = Path(directory) / "agent.json"
            agent_doc = {
                "name": context["agent_name"],
                "versions": {"latest": {"version": "1", "definition": {
                    "kind": "prompt", "model": "gpt-4o",
                    "harness": {"type": "microsoft_copilot_preview"},
                    "tools": [{
                        "type": "mcp", "server_label": context["toolbox_name"],
                        "server_url": endpoint, "project_connection_id": context["connection_name"],
                    }],
                }}},
            }
            agent_path.write_text(json.dumps(agent_doc), encoding="utf-8")
            tb_only_ctx = {**context, "skill_name": ""}
            helpers.verify_deployed(agent_path, tb_only_ctx, "gpt-4o", tb_path, None, conn_path)
            with self.assertRaisesRegex(helpers.LifecycleError, "toolbox and connection metadata"):
                helpers.verify_deployed(agent_path, tb_only_ctx, "gpt-4o", tb_path, None, None)
            no_conn_agent = json.loads(json.dumps(agent_doc))
            no_conn_agent["versions"]["latest"]["definition"]["tools"][0].pop("project_connection_id")
            agent_path.write_text(json.dumps(no_conn_agent), encoding="utf-8")
            with self.assertRaisesRegex(helpers.LifecycleError, "connection ID"):
                helpers.verify_deployed(agent_path, tb_only_ctx, "gpt-4o", tb_path, None, conn_path)
            path.write_text(json.dumps([{"name": context["connection_name"].upper()}]), encoding="utf-8")
            self.assertFalse(helpers.connection_absent(path, context))
            path.write_text("null", encoding="utf-8")
            self.assertTrue(helpers.connection_absent(path, context))
            with self.assertRaisesRegex(helpers.LifecycleError, "owned toolbox connection"):
                helpers.connection_absent(path, {**context, "connection_name": "ci-e2e-tb-aaaaaaaaaa-00000000-mcp"})

    def test_verify_adopted_enforces_exclusive_toolbox_and_skill_topology(self):
        nonce = "b" * 32
        agent_name = "ci-prompt-" + nonce
        tb_name = "ci-e2e-tb-" + nonce
        sk_name = "ci-e2e-sk-" + nonce
        tb_context = {
            "execution_profile": "managed", "agent_name": agent_name, "agent_service": "agent",
            "toolbox_name": tb_name, "skill_name": "", "connection_name": "", "toolbox_endpoint": "",
            "project_endpoint": "https://project.invalid/api/projects/project",
        }
        sk_context = {**tb_context, "toolbox_name": "", "skill_name": sk_name}
        tb_doc = {"services": {
            "project": {"host": "azure.ai.project"},
            tb_name: {"host": "azure.ai.toolbox", "uses": ["project"], "tools": [{"type": "web_search"}]},
            "agent": {
                "host": "azure.ai.agent", "kind": "prompt", "project": ".",
                "name": agent_name, "model": "gpt-4o", "uses": ["project", tb_name],
                "harness": {"type": "microsoft_copilot_preview"}, "toolboxes": [tb_name],
            },
        }}
        sk_doc = {"services": {
            "project": {"host": "azure.ai.project"},
            sk_name: {"host": "azure.ai.skill", "uses": ["project"], "archive": f"./skills/{sk_name}"},
            "agent": {
                "host": "azure.ai.agent", "kind": "prompt", "project": ".",
                "name": agent_name, "model": "gpt-4o", "uses": ["project", sk_name],
                "harness": {"type": "microsoft_copilot_preview"}, "skills": [sk_name],
            },
        }}
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "azure.yaml"
            manifest.write_text(yaml.safe_dump(tb_doc), encoding="utf-8")
            helpers.verify_adopted(manifest, tb_context, "gpt-4o")
            with self.assertRaisesRegex(helpers.LifecycleError, "owned skill service"):
                helpers.verify_adopted(manifest, sk_context, "gpt-4o")
            with self.assertRaisesRegex(helpers.LifecycleError, "owned toolbox or skill"):
                helpers.verify_adopted(manifest, {**tb_context, "skill_name": sk_name}, "gpt-4o")
            no_tb = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            no_tb["services"]["agent"].pop("toolboxes")
            manifest.write_text(yaml.safe_dump(no_tb), encoding="utf-8")
            with self.assertRaisesRegex(helpers.LifecycleError, "toolboxes or legacy toolbox"):
                helpers.verify_adopted(manifest, tb_context, "gpt-4o")
            manifest.write_text(yaml.safe_dump(sk_doc), encoding="utf-8")
            helpers.verify_adopted(manifest, sk_context, "gpt-4o")
            with self.assertRaisesRegex(helpers.LifecycleError, "owned toolbox service"):
                helpers.verify_adopted(manifest, tb_context, "gpt-4o")

    def test_source_skill_bundle_rejects_symlinks_before_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            sample = Path(directory) / "sample"
            skill_dir = sample / "skills/travel-guide"
            skill_dir.mkdir(parents=True)
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text(
                "---\nname: travel-guide\ndescription: Guide\n---\nFollow instructions.\n",
                encoding="utf-8",
            )
            aux = skill_dir / "notes.txt"
            aux.write_text("helper notes\n", encoding="utf-8")
            helpers._validate_source_skill_bundle(sample, "travel-guide")
            for target in (sample / "skills", skill_dir, skill_md, aux):
                with self.subTest(target=target.name):
                    orig_is_symlink = Path.is_symlink
                    with mock.patch.object(
                        Path, "is_symlink", autospec=True,
                        side_effect=lambda p, t=target: True if p == t else orig_is_symlink(p),
                    ):
                        with self.assertRaisesRegex(helpers.LifecycleError, "symlink"):
                            helpers._validate_source_skill_bundle(sample, "travel-guide")
            outside = Path(directory) / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")
            link = skill_dir / "linked.txt"
            try:
                os.symlink(outside, link)
            except OSError:
                pass
            else:
                with self.assertRaisesRegex(helpers.LifecycleError, "symlink"):
                    helpers._validate_source_skill_bundle(sample, "travel-guide")


if __name__ == "__main__":
    unittest.main()
