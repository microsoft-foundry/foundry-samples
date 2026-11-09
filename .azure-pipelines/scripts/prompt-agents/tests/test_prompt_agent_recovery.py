"""Exercise the real recovery shell with isolated azd/git stubs, never Azure."""

import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "cleanup-prompt-agent.sh"
PROJECT_ID = "/subscriptions/test/resourceGroups/test/providers/Microsoft.CognitiveServices/accounts/borrowed/projects/test"
ENDPOINT = "https://test.invalid/api/projects/test"
MODEL = "borrowed-model"
NAME = "ci-prompt-" + "a" * 32
TOOLBOX = "ci-e2e-tb-" + "a" * 32
TOOLBOX_ENDPOINT = f"{ENDPOINT}/toolboxes/{TOOLBOX}/versions/3/mcp?api-version=v1"
SKILL = "ci-e2e-sk-" + "a" * 32
CONN = f"ci-e2e-tb-aaaaaaaaaa-{hashlib.sha256(TOOLBOX_ENDPOINT.encode('utf-8')).hexdigest()[:8]}-mcp"
SERVICE = "chat-agent"

FAKE_CLI = r'''
import json
import os
from pathlib import Path
import sys

path = Path(os.environ["RECOVERY_TEST_STATE"])
state = json.loads(path.read_text(encoding="utf-8"))
argv = sys.argv[1:]
state["commands"].append(argv)
path.write_text(json.dumps(state), encoding="utf-8")
assert argv[:2] == ["azd", "-C"], argv
assert Path(argv[2]) == Path(state["project"]), argv
assert (Path(argv[2]) / ".azure" / state["name"] / ".env").is_file()
assert os.environ.get("AZD_ALPHA_ENABLE_AGENTS_MANAGED_HARNESS") == "true"
expected = {"FOUNDRY_PROJECT_ENDPOINT": state["endpoint"],
            "AZURE_AI_PROJECT_ENDPOINT": state["endpoint"],
            "AZURE_AI_PROJECT_ID": state["project_id"],
            "AGENT_CHAT_AGENT_NAME": state["name"]}
for key, value in {**expected, "AZURE_ENV_NAME": state["name"]}.items():
    assert os.environ[key] == value, (key, os.environ.get(key))
args = argv[3:]
if args[:2] == ["env", "set"]:
    key = args[2]
    assert args == ["env", "set", key, expected[key], "--environment", state["name"], "--no-prompt"], args
    state["pinned"][key] = args[3]
else:
    assert state["pinned"] == expected, state["pinned"]
    if args[:3] == ["ai", "agent", "show"]:
        assert args == ["ai", "agent", "show", "chat-agent", "--output", "json", "--no-prompt"], args
        if state["auth_failure"]:
            print("403 Forbidden", file=sys.stderr)
            sys.exit(1)
        if state["agent_deleted"]:
            print(f'failed to get prompt agent "{state["name"]}": GET {state["endpoint"]}/agents/{state["name"]}\nRESPONSE 404: 404 Not Found', file=sys.stderr)
            sys.exit(1)
        print(json.dumps({"name": state["name"]}))
    elif args[:3] == ["ai", "agent", "delete"]:
        assert args == ["ai", "agent", "delete", "chat-agent", "--force", "--no-prompt", "--output", "json"], args
        state["agent_deleted"] = True
    elif args[:3] == ["ai", "toolbox", "list"]:
        assert args == ["ai", "toolbox", "list", "--project-endpoint", state["endpoint"], "--output", "json", "--no-prompt"], args
        names = ["unowned-toolbox"] + ([] if state["toolbox_deleted"] else [state["toolbox"]])
        print(json.dumps({"toolboxes": [{"name": name} for name in names]}))
    elif args[:3] == ["ai", "toolbox", "delete"]:
        assert args == ["ai", "toolbox", "delete", state["toolbox"], "--project-endpoint", state["endpoint"],
                        "--force", "--no-prompt", "--output", "json"], args
        state["toolbox_deleted"] = True
    elif args[:3] == ["ai", "skill", "list"]:
        assert args == ["ai", "skill", "list", "--project-endpoint", state["endpoint"], "--output", "json", "--no-prompt"], args
        names = ["unowned-skill"] + ([] if state["skill_deleted"] else [state["skill"]])
        print(json.dumps([{"name": name} for name in names]))
    elif args[:3] == ["ai", "skill", "delete"]:
        assert args == ["ai", "skill", "delete", state["skill"], "--project-endpoint", state["endpoint"],
                        "--force", "--no-prompt", "--output", "json"], args
        state["skill_deleted"] = True
    elif args[:3] == ["ai", "connection", "list"]:
        assert args == ["ai", "connection", "list", "--project-endpoint", state["endpoint"], "--output", "json", "--no-prompt"], args
        if state["connection_deleted"] and state.get("connection_null"):
            print("null")
        else:
            names = ["unowned-conn"] + ([] if state["connection_deleted"] else [state["connection"]])
            print(json.dumps([{"name": name} for name in names]))
    elif args[:3] == ["ai", "connection", "show"]:
        assert args == ["ai", "connection", "show", state["connection"], "--project-endpoint", state["endpoint"],
                        "--output", "json", "--no-prompt"], args
        print(json.dumps({
            "name": state["connection"], "target": state["toolbox_endpoint"],
            "kind": "RemoteTool", "authType": "UserEntraToken",
            **state.get("connection_changes", {}),
        }))
    elif args[:3] == ["ai", "connection", "delete"]:
        assert args == ["ai", "connection", "delete", state["connection"], "--project-endpoint", state["endpoint"],
                        "--force", "--no-prompt"], args
        state["connection_deleted"] = True
    else:
        raise AssertionError(args)
path.write_text(json.dumps(state), encoding="utf-8")
'''


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bash = os.environ.get("PROMPT_AGENT_TEST_BASH") or (
            "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash"))
        cls.tool_path = os.environ.get("PROMPT_AGENT_TEST_PATH", os.environ.get("PATH", ""))
        env = {**os.environ, "PATH": cls.tool_path}
        env.pop("BASH_ENV", None)
        try:
            probe = subprocess.run([cls.bash or "bash", "--noprofile", "--norc", "-c",
                                    'for tool in jq timeout realpath mktemp dirname cp mv cmp sleep; do '
                                    'command -v "$tool" >/dev/null || { echo "missing $tool"; exit 1; }; done; '
                                    'case "$OSTYPE" in msys*|cygwin*) command -v cygpath ;; esac'],
                                   env=env, capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise unittest.SkipTest(f"recovery tests require Bash and local tools: {error}")
        if probe.returncode:
            raise unittest.SkipTest(f"shell tools unavailable: {probe.stdout}{probe.stderr}")

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="prompt recovery test ")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        fake = self.root / "fake_cli.py"
        fake.write_text(FAKE_CLI, encoding="utf-8", newline="\n")
        for cli in ("az", "azd", "git"):
            stub = self.bin / cli
            stub.write_text("#!/bin/bash\nexec " + shlex.quote(Path(sys.executable).as_posix()) + " "
                            + shlex.quote(fake.as_posix()) + f' {cli} "$@"\n', encoding="utf-8", newline="\n")
            stub.chmod(0o755)
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()
        self.work = self.root / "retained work"
        self.project = self.work / "project"
        environment = self.project / ".azure" / NAME
        environment.mkdir(parents=True)
        (environment / ".env").write_text("", encoding="utf-8")
        manifest = {"name": "recovery", "services": {
            "project": {"host": "azure.ai.project"},
            TOOLBOX: {"host": "azure.ai.toolbox", "uses": ["project"], "tools": [{"type": "web_search"}]},
            SERVICE: {"host": "azure.ai.agent", "kind": "prompt", "project": ".",
                      "name": NAME, "model": MODEL, "uses": ["project", TOOLBOX],
                      "harness": {"type": "github_copilot_preview"}, "toolbox": {"name": TOOLBOX}},
        }}
        for parent in (self.project, self.artifacts):
            (parent / "azure.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8", newline="\n")
        self.ownership = {"project_id": PROJECT_ID, "project_endpoint": ENDPOINT,
                          "agent_name": NAME, "agent_service": SERVICE, "toolbox_name": TOOLBOX,
                          "deployment_attempted": True, "toolbox_deployment_attempted": True,
                          "working_directory": str(self.work), "cleanup": {}}
        self.context = {"project_endpoint": ENDPOINT, "agent_name": NAME, "agent_service": SERVICE,
                        "service_env_key": "CHAT_AGENT", "toolbox_name": TOOLBOX, "execution_profile": "managed"}
        self.state_path = self.root / "state.json"

    def read_json(self, name):
        return json.loads((self.artifacts / name).read_text(encoding="utf-8"))

    def run_recovery(self, *, code=0, ledger=True, auth_failure=False, connection_null=False, connection_changes=None):
        if ledger:
            (self.artifacts / "ownership.json").write_text(json.dumps(self.ownership), encoding="utf-8")
        (self.artifacts / "context.json").write_text(json.dumps(self.context), encoding="utf-8")
        self.state_path.write_text(json.dumps({"project": str(self.project), "project_id": PROJECT_ID,
            "endpoint": ENDPOINT, "name": NAME, "toolbox": TOOLBOX, "toolbox_endpoint": TOOLBOX_ENDPOINT,
            "skill": SKILL, "connection": CONN,
            "commands": [], "pinned": {},
            "agent_deleted": False, "toolbox_deleted": False, "skill_deleted": False,
            "connection_deleted": False, "auth_failure": auth_failure,
            "connection_null": connection_null, "connection_changes": connection_changes or {}}), encoding="utf-8")
        env = {**os.environ, "PATH": str(self.bin) + os.pathsep + self.tool_path,
               "PYTHON": Path(sys.executable).as_posix(), "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1",
               "RECOVERY_TEST_STATE": self.state_path.as_posix(), "TEST_BIN": self.bin.as_posix(),
               "TEST_TMP": self.root.as_posix(), "TMP": str(self.root), "TEMP": str(self.root)}
        env.pop("BASH_ENV", None)
        launcher = ('case "$OSTYPE" in msys*|cygwin*) TEST_BIN="$(cygpath -u "$TEST_BIN")"; '
                    'export TMPDIR="$(cygpath -u "$TEST_TMP")" ;; *) export TMPDIR="$TEST_TMP" ;; esac; '
                    'export PATH="$TEST_BIN:$PATH"; for cli in az azd git; do '
                    '[[ "$(command -v "$cli")" -ef "$TEST_BIN/$cli" ]] || { echo "unsafe CLI: $cli" >&2; exit 98; }; done; '
                    'exec bash "$@"')
        process = subprocess.run([self.bash, "--noprofile", "--norc", "-c", launcher, "recovery-test", SCRIPT.as_posix(),
                                  "--artifacts", self.artifacts.as_posix(), "--project-id", PROJECT_ID,
                                  "--project-endpoint", ENDPOINT, "--model-deployment", MODEL],
                                 cwd=self.root, env=env, capture_output=True, text=True, encoding="utf-8", timeout=90)
        self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
        diagnostics = "\n".join(path.read_text(encoding="utf-8") for path in self.artifacts.rglob("*-stderr.txt"))
        self.assertNotIn("Traceback", diagnostics)
        self.assertEqual(process.returncode, code, process.stdout + process.stderr + diagnostics)
        return process

    def test_missing_ownership_does_not_run_commands(self):
        self.run_recovery(ledger=False)
        self.assertEqual(self.state["commands"], [])
        self.assertFalse((self.artifacts / "recovery-result.json").exists())

    def test_already_absent_needs_no_workspace(self):
        self.ownership["cleanup"] = {NAME: "absent", TOOLBOX: "absent"}
        shutil.rmtree(self.work)
        self.run_recovery()
        self.assertEqual(self.state["commands"], [])
        self.assertEqual(self.read_json("recovery-result.json")["cleanup_status"], "complete")

    def test_pending_resources_clean_in_order_without_upgrading_result(self):
        self.ownership.update(toolbox_endpoint=TOOLBOX_ENDPOINT, connection_name=CONN, connection_deployment_attempted=True)
        self.context.update(toolbox_endpoint=TOOLBOX_ENDPOINT, connection_name=CONN)
        (self.artifacts / "result.json").write_text('{"status":"failed","evaluation_exit_code":1}', encoding="utf-8")
        before = (self.project / "azure.yaml").read_bytes()
        self.run_recovery(connection_null=True)
        operations = [cmd[3:6] for cmd in self.state["commands"] if cmd[3] == "ai"]
        self.assertEqual(operations, [["ai", "agent", "show"], ["ai", "agent", "delete"],
                                      ["ai", "agent", "show"], ["ai", "connection", "list"],
                                      ["ai", "connection", "show"], ["ai", "connection", "delete"],
                                      ["ai", "connection", "list"],
                                      ["ai", "toolbox", "list"], ["ai", "toolbox", "delete"],
                                      ["ai", "toolbox", "list"]])
        self.assertEqual(self.read_json("ownership.json")["cleanup"], {NAME: "absent", CONN: "absent", TOOLBOX: "absent"})
        self.assertEqual(self.read_json("result.json")["status"], "failed")
        self.assertEqual(self.read_json("result.json")["evaluation_exit_code"], 1)
        self.assertEqual((self.project / "azure.yaml").read_bytes(), before)

    def test_unowned_connection_digest_or_target_refuses_deletion(self):
        self.ownership.update(
            deployment_attempted=False, toolbox_endpoint="", connection_name="",
            connection_deployment_attempted=False, cleanup={TOOLBOX: "unverified"},
        )
        self.context.update(toolbox_endpoint="", connection_name="")
        self.run_recovery()
        self.assertEqual(
            [cmd[3:6] for cmd in self.state["commands"] if cmd[3] == "ai"],
            [["ai", "toolbox", "list"], ["ai", "toolbox", "delete"], ["ai", "toolbox", "list"]],
        )
        self.assertEqual(self.read_json("ownership.json")["cleanup"], {TOOLBOX: "absent"})
        bad_conn = "ci-e2e-tb-aaaaaaaaaa-00000000-mcp"
        self.ownership.update(
            deployment_attempted=True, toolbox_endpoint=TOOLBOX_ENDPOINT,
            connection_name=bad_conn, connection_deployment_attempted=True, cleanup={},
        )
        self.context.update(toolbox_endpoint=TOOLBOX_ENDPOINT, connection_name=bad_conn)
        self.run_recovery(code=1)
        self.assertEqual(self.state["commands"], [])
        self.assertFalse(self.read_json("recovery-result.json")["ownership_validated"])
        self.ownership.update(connection_name=CONN)
        self.context.update(connection_name=CONN)
        self.run_recovery(code=1, connection_changes={"target": "https://other.invalid/mcp"})
        self.assertFalse(self.state["connection_deleted"])
        self.assertEqual(self.read_json("ownership.json")["cleanup"], {NAME: "absent", CONN: "unverified", TOOLBOX: "absent"})

    def test_pending_skill_cleans_in_order(self):
        manifest = {"name": "recovery-skill", "services": {
            "project": {"host": "azure.ai.project"},
            SKILL: {"host": "azure.ai.skill", "uses": ["project"], "archive": f"./skills/{SKILL}"},
            SERVICE: {"host": "azure.ai.agent", "kind": "prompt", "project": ".",
                      "name": NAME, "model": MODEL, "uses": ["project", SKILL],
                      "harness": {"type": "microsoft_copilot_preview"}, "skills": [SKILL]},
        }}
        for parent in (self.project, self.artifacts):
            (parent / "azure.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8", newline="\n")
        self.ownership.update(toolbox_name="", toolbox_deployment_attempted=False,
                              skill_name=SKILL, skill_deployment_attempted=True)
        self.context.update(toolbox_name="", skill_name=SKILL)
        self.run_recovery()
        operations = [cmd[3:6] for cmd in self.state["commands"] if cmd[3] == "ai"]
        self.assertEqual(operations, [["ai", "agent", "show"], ["ai", "agent", "delete"],
                                      ["ai", "agent", "show"], ["ai", "skill", "list"],
                                      ["ai", "skill", "delete"], ["ai", "skill", "list"]])
        self.assertEqual(self.read_json("ownership.json")["cleanup"], {NAME: "absent", SKILL: "absent"})

    def test_agent_auth_error_still_cleans_toolbox_and_fails_result(self):
        (self.artifacts / "result.json").write_text('{"status":"passed"}', encoding="utf-8")
        self.run_recovery(code=1, auth_failure=True)
        self.assertFalse(self.state["agent_deleted"])
        self.assertTrue(self.state["toolbox_deleted"])
        self.assertEqual(self.read_json("ownership.json")["cleanup"], {NAME: "unverified", TOOLBOX: "absent"})
        self.assertEqual(self.read_json("result.json")["status"], "failed")

    def test_missing_workspace_refuses_commands(self):
        shutil.rmtree(self.work)
        self.assertIn("working directory/project is missing", self.run_recovery(code=1).stderr)
        self.assertEqual(self.state["commands"], [])

    def test_project_mismatch_refuses_all_commands(self):
        for document, key, value in ((self.ownership, "project_id", PROJECT_ID + "-other"),
                                     (self.ownership, "project_endpoint", ENDPOINT + "-other"),
                                     (self.context, "project_endpoint", ENDPOINT + "-other")):
            with self.subTest(key=key, value=value):
                original = document[key]
                document[key] = value
                try:
                    process = self.run_recovery(code=1)
                finally:
                    document[key] = original
                self.assertIn("trusted project mismatch", process.stderr)
                self.assertEqual(self.state["commands"], [])
                self.assertFalse(self.read_json("recovery-result.json")["ownership_validated"])

    def test_successful_recovery_does_not_create_missing_e2e_result(self):
        self.run_recovery()
        self.assertEqual(self.read_json("recovery-result.json")["cleanup_status"], "complete")
        self.assertFalse((self.artifacts / "result.json").exists())


if __name__ == "__main__":
    unittest.main()
