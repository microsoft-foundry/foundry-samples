"""Run the real Bash lifecycle with isolated az/azd stubs, never Azure.

Set PROMPT_AGENT_TEST_BASH and PROMPT_AGENT_TEST_PATH to select shell tools.
"""

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


SCRIPT = Path(__file__).resolve().parents[1] / "run-prompt-agent.sh"
PROJECT_ID = "/subscriptions/test/resourceGroups/test/providers/Microsoft.CognitiveServices/accounts/borrowed-account/projects/test"
ENDPOINT = "https://test.invalid/api/projects/test"
MODEL = "borrowed-model"
SERVICE = "chat-agent"

# State is outside the disposable azd workspace so cleanup remains observable.
FAKE_CLI = r'''
import json
import os
from pathlib import Path
import shutil
import sys
import time
import yaml

path = Path(os.environ["FAKE_CLI_STATE"])
state = json.loads(path.read_text(encoding="utf-8"))
config = state["config"]
argv = sys.argv[1:]
state["commands"].append(argv)
state["workspaces"].append(str(Path.cwd()))

def save():
    path.write_text(json.dumps(state), encoding="utf-8")

def absent():
    name = state["name"]
    return (f'failed to get prompt agent "{name}": GET {config["endpoint"]}/agents/{name}?api-version=v1\n'
            'RESPONSE 404: 404 Not Found\n')

save()
stdout, stderr, code = "", "", 0
is_toolbox = argv[1:3] == ["ai", "toolbox"]
operation = argv[3] if argv[1:2] == ["ai"] else argv[1]
failure = "toolbox_" + operation if is_toolbox else operation
if argv[0] == "az":
    assert argv == ["az", "resource", "show", "--ids", config["project_id"],
                    "--query", 'properties.endpoints."AI Foundry API"', "-o", "tsv"], argv
    stdout = config.get("resolved_endpoint", config["endpoint"]) + "/\n"
elif operation == "version":
    assert argv == ["azd", "version"], argv
    stdout = "azd version 1.99.0 (offline)\n"
elif operation == "extension":
    assert argv == ["azd", "extension", "list", "--installed", "--output", "json"], argv
    stdout = '[{"id":"microsoft.foundry"}]\n'
elif operation == "init":
    source = Path(argv[argv.index("-m") + 1])
    assert source == Path.cwd().parent / "input/azure.yaml", argv
    assert not list(Path.cwd().iterdir())
    state["name"] = argv[argv.index("--agent-name") + 1]
    assert argv == ["azd", "ai", "agent", "init", "-m", source.as_posix(),
                    "--project-id", config["project_id"], "--model-deployment", config["model"],
                    "--agent-name", state["name"], "--src", ".", "--no-prompt",
                    "--environment", state["name"]], argv
    shutil.copyfile(source, "azure.yaml")
    document = yaml.safe_load(Path("azure.yaml").read_text(encoding="utf-8"))
    if config["managed"]:
        state["toolbox"] = document["services"][config["service"]]["toolbox"]["name"]
        assert state["toolbox"] == "ci-e2e-tb-" + state["name"].removeprefix("ci-prompt-")
        state["toolbox_endpoint"] = (config["endpoint"] + "/toolboxes/" + state["toolbox"]
                                     + "/versions/3/mcp?api-version=v1")
    environment = Path(".azure") / state["name"]
    environment.mkdir(parents=True)
    (environment / ".env").write_text("", encoding="utf-8")
    if config.get("adopted_changes"):
        document["services"][config["service"]].update(config["adopted_changes"])
        Path("azure.yaml").write_text(yaml.safe_dump(document), encoding="utf-8")
elif operation == "env":
    if argv[2] == "get-value":
        assert argv == ["azd", "env", "get-value", "TOOLBOX_" + state["toolbox"].replace("-", "_").upper() + "_MCP_ENDPOINT"]
        assert state["toolbox_deployed"] and not state["deployed"]
        stdout = config.get("toolbox_endpoint", state["toolbox_endpoint"]) + "\n"
    else:
        assert argv[1:3] == ["env", "set"] and len(argv) == 5, argv
        state["environment"][argv[3]] = argv[4]
elif is_toolbox:
    expected = ["azd", "ai", "toolbox", operation]
    if operation != "list":
        expected.append(state["toolbox"])
    expected += ["--project-endpoint", config["endpoint"]]
    expected += (["--force", "--no-prompt", "--output", "json"] if operation == "delete"
                 else ["--output", "json", "--no-prompt"])
    assert argv == expected, argv
    if operation == "list":
        mode = config.get("toolbox_cleanup" if state["toolbox_deleted"] else "toolbox_preflight", "absent")
        names = ["unowned-toolbox"]
        if mode == "collision" or state["toolbox_deployed"] and not state["toolbox_deleted"]:
            names.append(state["toolbox"].upper())
        stdout = json.dumps({"toolboxes": [{"name": name} for name in names]})
        if mode == "auth":
            code, stderr = 1, "403 Forbidden listing toolboxes\n"
        elif mode == "malformed":
            stdout = '{"toolboxes":[{}]}'
    elif operation == "show":
        assert state["toolbox_deployed"] and not state["deployed"]
        stdout = json.dumps({"toolbox": {"name": state["toolbox"]},
                             "version": {"name": state["toolbox"], "version": "3", "tools": [{"type": "web_search"}]},
                             "endpoint": state["toolbox_endpoint"]})
    elif operation == "delete":
        assert state["toolbox_deployed"]
        assert not state["deployed"] or state["deleted"]
        state["toolbox_deleted"] = True
elif operation == "deploy":
    assert state["environment"]["AGENT_CHAT_AGENT_NAME"] == state["name"]
    target = state["toolbox"] if config["managed"] and argv[2] == state["toolbox"] else config["service"]
    assert argv == ["azd", "deploy", target, "--no-prompt", "--timeout", "20"], argv
    if target == config["service"]:
        assert not config["managed"] or state["toolbox_deployed"]
        state["deployed"] = True
    else:
        state["toolbox_deployed"] = True
        failure = "toolbox_deploy"
elif operation == "show":
    assert argv == ["azd", "ai", "agent", "show", config["service"], "--output", "json", "--no-prompt"], argv
    mode = config.get("cleanup" if state["deleted"] else "preflight", "absent")
    if state["deployed"] and not state["deleted"] or mode == "collision":
        definition = {"kind": "prompt", "model": config["model"]}
        if config["managed"]:
            definition.update(harness={"type": "github_copilot_preview"}, tools=[{
                "type": "mcp", "server_label": state["toolbox"],
                "server_url": state["toolbox_endpoint"], "require_approval": "never"}])
            definition["tools"][0].update(config.get("mcp_changes", {}))
        definition.update(config.get("definition_changes", {}))
        metadata = {"name": state["name"], "versions": {"latest": {"version": "7", "definition": definition}}}
        metadata.update(config.get("metadata_changes", {}))
        stdout = json.dumps(metadata)
    else:
        message = absent()
        if mode in ("auth", "mixed404"):
            message = message.replace("404: 404 Not Found", "403: 403 Forbidden")
        if mode == "mixed404":
            message += "GET https://other.invalid/agents/other\nRESPONSE 404: 404 Not Found\n"
        text = json.dumps({"type": "consoleMessage", "data": {"message": message}}) + "\n"
        if config.get("show_error_stdout"):
            stdout = text
        else:
            stderr = text
        code = 1
elif operation == "invoke":
    filename = argv[argv.index("--input-file") + 1]
    expected = ["azd", "ai", "agent", "invoke", config["service"], "--input-file", filename,
                "--protocol", "responses", "--no-prompt"]
    assert argv in (expected, expected + ["--new-conversation"]), argv
    state["inputs"].append(Path(filename).read_text(encoding="utf-8"))
    if config.get("invoke_timeout"):
        save()
        print("partial", flush=True)
        time.sleep(3)
        sys.exit(0)
    stdout = config.get("invoke_stdout", "Hello\n")
    if config.get("early_stream_error"):
        code, stderr, stdout = 1, "Error: response.failed: stream ended early\n", ""
elif operation == "delete":
    assert argv == ["azd", "ai", "agent", "delete", config["service"], "--force", "--no-prompt", "--output", "json"], argv
    assert state["deployed"] and state["environment"]["AGENT_CHAT_AGENT_NAME"] == state["name"]
    state["deleted"] = True
else:
    raise AssertionError(argv)
if config.get("fail_operation") == failure:
    code, stderr = 1, f"injected {failure} failure\n"
save()
sys.stdout.write(stdout)
sys.stderr.write(stderr)
sys.exit(code)
'''


class PromptShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bash = os.environ.get("PROMPT_AGENT_TEST_BASH") or (
            "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash"))
        cls.tool_path = os.environ.get("PROMPT_AGENT_TEST_PATH", os.environ.get("PATH", ""))
        env = {**os.environ, "PATH": cls.tool_path}
        env.pop("BASH_ENV", None)
        try:
            probe = subprocess.run([cls.bash or "bash", "--noprofile", "--norc", "-c",
                                    'for tool in jq timeout realpath mktemp dirname cp rm tr cat sleep; do '
                                    'command -v "$tool" >/dev/null || { echo "missing $tool"; exit 1; }; done; '
                                    'case "$OSTYPE" in msys*|cygwin*) command -v cygpath ;; esac'],
                                   env=env, capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise unittest.SkipTest(f"shell tests require Bash and local tools: {error}")
        if probe.returncode:
            raise unittest.SkipTest(f"shell tools unavailable: {probe.stdout}{probe.stderr}")

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="prompt shell test ")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        fake = self.root / "fake_cli.py"
        fake.write_text(FAKE_CLI, encoding="utf-8", newline="\n")
        for cli in ("az", "azd"):
            stub = self.bin / cli
            stub.write_text("#!/bin/bash\nexec " + shlex.quote(Path(sys.executable).as_posix()) + " "
                            + shlex.quote(fake.as_posix()) + f' {cli} "$@"\n', encoding="utf-8", newline="\n")
            stub.chmod(0o755)
        self.number = 0
        self.configure()

    def configure(self, *, managed=False):
        self.number += 1
        self.repo = self.root / f"repo {self.number}"
        evaluator = self.repo / ".github/scripts/hosted_agent_test_spec.py"
        evaluator.parent.mkdir(parents=True)
        shutil.copyfile(SCRIPT.parents[3] / ".github/scripts/hosted_agent_test_spec.py", evaluator)
        self.sample = self.repo / "samples/cli/prompt-agents/basic"
        self.sample.mkdir(parents=True)
        self.fixture = self.repo / ".azure-pipelines/prompt-agent-tests/cli/basic/test-spec.yml"
        self.fixture.parent.mkdir(parents=True)
        self.artifacts = self.repo / "artifacts output"
        self.state_path = self.root / f"state-{self.number}.json"
        agent = {"host": "azure.ai.agent", "kind": "prompt", "name": "source-agent",
                 "model": "source-model", "project": ".", "uses": ["project"]}
        services = {"project": {"host": "azure.ai.project", "deployments": [{"name": "source-model"}]}}
        if managed:
            agent.update(harness={"type": "github_copilot_preview"}, uses=["project", "sample-toolbox"],
                         toolbox={"name": "sample-toolbox"})
            services["sample-toolbox"] = {"host": "azure.ai.toolbox", "uses": ["project"],
                                          "tools": [{"type": "web_search"}]}
        services[SERVICE] = agent
        self.document = {"name": "basic", "services": services}
        self.contract = {"version": 1, "sample": {"owner": "tester", "experiences": ["azd"]},
                         "tests": [{"name": "answer", "turns": [{"input": "Say hello", "assertions": [
                             {"source": "assistant_text", "type": "equals", "value": "Hello"}]}]}]}
        self.config = {"endpoint": ENDPOINT, "project_id": PROJECT_ID, "model": MODEL,
                       "service": SERVICE, "managed": managed}

    def read_json(self, name):
        return json.loads((self.artifacts / name).read_text(encoding="utf-8"))

    def operations(self, operation, resource="agent"):
        return [cmd for cmd in self.commands if cmd[1:4] == ["ai", resource, operation]]

    def run_agent(self, *, passed=True, prepared=True):
        (self.sample / "azure.yaml").write_text(yaml.safe_dump(self.document, sort_keys=False), encoding="utf-8")
        self.fixture.write_text(yaml.safe_dump(self.contract), encoding="utf-8")
        self.state_path.write_text(json.dumps({"config": self.config, "commands": [], "workspaces": [],
            "environment": {}, "inputs": [], "deployed": False, "deleted": False,
            "toolbox_deployed": False, "toolbox_deleted": False}), encoding="utf-8")
        before = {p.relative_to(self.sample): p.read_bytes() for p in self.sample.rglob("*") if p.is_file()}
        env = {**os.environ, "PATH": str(self.bin) + os.pathsep + self.tool_path,
               "PYTHON": Path(sys.executable).as_posix(), "PYTHONUTF8": "1",
               "FAKE_CLI_STATE": self.state_path.as_posix(), "TMPDIR": self.root.as_posix(),
               "TMP": str(self.root), "TEMP": str(self.root), "TEST_BIN": self.bin.as_posix(),
               "TEST_TMP": self.root.as_posix()}
        env.pop("BASH_ENV", None)
        launcher = ('case "$OSTYPE" in msys*|cygwin*) export TMPDIR="$(cygpath -u "$TEST_TMP")" ;; '
                    '*) export TMPDIR="$TEST_TMP" ;; esac; '
                    'for cli in az azd; do '
                    '[[ "$(command -v "$cli")" -ef "$TEST_BIN/$cli" ]] || exit 98; done; exec bash "$@"')
        result = subprocess.run([self.bash, "--noprofile", "--norc", "-c", launcher, "prompt-test", SCRIPT.as_posix(),
                                 "--repo", self.repo.as_posix(), "--sample", self.sample.relative_to(self.repo).as_posix(),
                                 "--project-id", PROJECT_ID, "--project-endpoint", ENDPOINT,
                                 "--model-deployment", MODEL, "--artifacts", self.artifacts.as_posix(),
                                 "--command-timeout", "20", "--turn-timeout", "1" if self.config.get("invoke_timeout") else "20"],
                                cwd=self.repo, env=env, capture_output=True, text=True, encoding="utf-8", timeout=90)
        self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.commands = self.state["commands"]
        self.assertEqual({p.relative_to(self.sample): p.read_bytes() for p in self.sample.rglob("*") if p.is_file()}, before)
        self.assertEqual(result.returncode, 0 if passed else 1, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        if prepared:
            self.result = self.read_json("result.json")
            self.assertEqual(self.result["status"], "passed" if passed else "failed")
            self.assertEqual(json.loads(result.stdout), self.result)
            ownership = self.read_json("ownership.json")
            self.assertFalse(Path(ownership["working_directory"]).exists())
            self.assertTrue(all(Path(p) == Path(ownership["working_directory"]) / "project" for p in self.state["workspaces"]))
            logs = sorted(self.artifacts.glob("command-*.json"), key=lambda p: int(p.stem.split("-")[1]))
            self.assertEqual([json.loads(p.read_text(encoding="utf-8"))["command"] for p in logs], self.commands)
        else:
            self.assertEqual(self.commands, [])
            self.assertFalse(self.artifacts.exists())
        return result

    def assert_cleaned(self):
        ownership = self.read_json("ownership.json")
        expected = {self.state["name"]: "absent"}
        if self.config["managed"]:
            expected[self.state["toolbox"]] = "absent"
            self.assertTrue(self.state["toolbox_deleted"])
            self.assertEqual(len(self.operations("delete", "toolbox")), 1)
            self.assertLess(self.commands.index(self.operations("delete")[0]),
                            self.commands.index(self.operations("delete", "toolbox")[0]))
        self.assertEqual(ownership["cleanup"], expected)
        self.assertEqual(self.result["cleanup"], expected)
        self.assertEqual(len(self.operations("delete")), 1)
        self.assertTrue(self.state["deleted"])

    def assert_not_owned(self):
        ownership = self.read_json("ownership.json")
        self.assertFalse(ownership["deployment_attempted"])
        self.assertFalse(ownership["toolbox_deployment_attempted"])
        self.assertEqual(ownership["cleanup"], {})
        self.assertEqual(self.operations("delete") + self.operations("delete", "toolbox"), [])

    def test_success_adopts_manifest_records_evidence_and_cleans(self):
        self.document["services"][SERVICE]["tools"] = [{"type": "mcp", "server_label": "public",
            "server_url": "https://mcp.invalid", "require_approval": "never"}]
        self.run_agent()
        self.assert_cleaned()
        self.assertRegex(self.state["name"], r"^ci-prompt-[0-9a-f]{32}$")
        adopted = yaml.safe_load((self.artifacts / "azure.yaml").read_text(encoding="utf-8"))
        self.assertNotIn("deployments", adopted["services"]["project"])
        self.assertEqual(adopted["services"][SERVICE]["model"], MODEL)
        self.assertEqual(adopted["services"][SERVICE]["tools"], self.document["services"][SERVICE]["tools"])
        self.assertEqual(self.state["inputs"], ["Say hello"])
        self.assertIn("--new-conversation", self.operations("invoke")[0])
        self.assertEqual((self.artifacts / "evidence/turn-1-assistant-text.txt").read_text(encoding="utf-8"), "Hello")
        self.assertFalse(self.read_json("evidence/turn-1-status.json")["mcp_approvals"]["observed"])
        self.assertEqual(self.read_json("report.json")["status"], "passed")
        self.assertIn("not verified", self.result["response_retention"])

    def test_multiturn_keeps_exact_inputs_and_conversation_boundaries(self):
        inputs = ['  Remember "one"\nnext line\n', "Recall it", "--new-conversation; $HOME `exit 9`", "Continue  "]
        self.contract["tests"] = [{"name": "first", "turns": [{"input": text} for text in inputs[:2]]},
                                  {"name": "second", "turns": [{"input": text} for text in inputs[2:]]}]
        self.contract["tests"][0]["turns"][0]["assertions"] = [
            {"source": "assistant_text", "type": "contains", "value": "Hello"}]
        self.config["invoke_stdout"] = "  Hello  \n\n"
        self.run_agent()
        self.assertEqual(self.state["inputs"], inputs)
        self.assertEqual(["--new-conversation" in cmd for cmd in self.operations("invoke")], [True, False, True, False])
        self.assert_cleaned()

    def test_unsupported_contract_and_dependencies_fail_before_cli(self):
        for change, message in (({"skills": ["skill"]}, "dependencies"),
                                ({"uses": ["project", "other"]}, "borrowed project"),
                                ({"hooks": {}}, "hooks"),
                                ({"tools": [{"type": "mcp", "require_approval": "always"}]}, "public")):
            with self.subTest(change=change):
                self.configure()
                self.document["services"][SERVICE].update(change)
                self.assertIn(message, self.run_agent(passed=False, prepared=False).stderr)
        for managed in (False, True):
            for kind, message in (("raw", "does not expose raw"), ("structured", "only string input")):
                with self.subTest(managed=managed, kind=kind):
                    self.configure(managed=managed)
                    turn = {"input": "hello"}
                    if kind == "raw":
                        turn["assertions"] = [{"source": "raw", "type": "contains", "value": "hello"}]
                    else:
                        turn["input"] = [{"role": "user", "content": "hello"}]
                    self.contract["tests"].append({"name": "filtered", "when": {"toolbox_label": "not-selected"}, "turns": [turn]})
                    self.assertIn(message, self.run_agent(passed=False, prepared=False).stderr)

    def test_preflight_refuses_collision_auth_and_unrelated_404(self):
        for mode in ("auth", "collision", "mixed404"):
            with self.subTest(mode=mode):
                self.configure()
                self.config["preflight"] = mode
                self.assertIn("refusing deployment", self.run_agent(passed=False).stderr)
                self.assertEqual(len(self.operations("show")), 1)
                self.assert_not_owned()

    def test_endpoint_and_adopted_identity_mismatch_refuse_deployment(self):
        self.config["resolved_endpoint"] = "https://other.invalid/api/projects/test"
        self.assertIn("project endpoint does not match", self.run_agent(passed=False).stderr)
        self.assertEqual(len(self.commands), 1)
        self.assert_not_owned()
        self.configure()
        self.config["adopted_changes"] = {"name": "unowned"}
        self.assertIn("init changed", self.run_agent(passed=False).stderr)
        self.assert_not_owned()

    def test_partial_deploy_and_failed_invoke_still_clean(self):
        for operation in ("deploy", "invoke"):
            with self.subTest(operation=operation):
                self.configure()
                self.config["fail_operation"] = operation
                self.run_agent(passed=False)
                self.assert_cleaned()
                self.assertEqual(len(self.operations("invoke")), 0 if operation == "deploy" else 1)

    def test_real_invoke_timeout_does_not_retry_and_cleans(self):
        self.config["invoke_timeout"] = True
        self.contract["tests"][0]["turns"].append({"input": "Must not run"})
        self.assertIn("azd invoke failed", self.run_agent(passed=False).stderr)
        self.assertEqual(len(self.operations("invoke")), 1)
        self.assertEqual(self.read_json("evidence/turn-1-status.json")["exit_code"], 124)
        self.assertFalse((self.artifacts / "evidence/turn-2-status.json").exists())
        self.assert_cleaned()

    def test_cleanup_auth_failure_does_not_claim_absence(self):
        self.config["cleanup"] = "auth"
        self.run_agent(passed=False)
        self.assertEqual(self.read_json("report.json")["status"], "passed")
        self.assertEqual(self.result["cleanup"], {self.state["name"]: "unverified"})

    def test_wrong_deployed_metadata_skips_invoke_and_cleans(self):
        self.config["definition_changes"] = {"model": "wrong"}
        self.assertIn("unexpected agent identity", self.run_agent(passed=False).stderr)
        self.assertEqual(self.operations("invoke"), [])
        self.assert_cleaned()

    def test_managed_success_orders_and_cleans_both_resources(self):
        self.configure(managed=True)
        self.run_agent()
        self.assert_cleaned()
        toolbox = self.state["toolbox"]
        adopted = yaml.safe_load((self.artifacts / "azure.yaml").read_text(encoding="utf-8"))
        self.assertEqual(list(adopted["services"]), ["project", toolbox, SERVICE])
        self.assertEqual(adopted["services"][SERVICE]["uses"], ["project", toolbox])
        self.assertEqual(self.read_json("toolbox.json")["endpoint"], self.state["toolbox_endpoint"])
        self.assertEqual(self.read_json("context.json")["execution_profile"], "managed")
        self.assertLess(self.commands.index(["azd", "deploy", toolbox, "--no-prompt", "--timeout", "20"]),
                        self.commands.index(["azd", "deploy", SERVICE, "--no-prompt", "--timeout", "20"]))

    def test_managed_preflight_never_deletes_unowned_resources(self):
        for mode in ("auth", "collision", "malformed"):
            with self.subTest(mode=mode):
                self.configure(managed=True)
                self.config["toolbox_preflight"] = mode
                self.run_agent(passed=False)
                self.assertEqual(len(self.operations("list", "toolbox")), 1)
                self.assert_not_owned()

    def test_managed_toolbox_deploy_failure_cleans_only_toolbox(self):
        self.configure(managed=True)
        self.config["fail_operation"] = "toolbox_deploy"
        self.run_agent(passed=False)
        self.assertFalse(self.state["deployed"])
        self.assertEqual(self.operations("delete"), [])
        self.assertTrue(self.state["toolbox_deleted"])
        self.assertEqual(self.result["cleanup"], {self.state["toolbox"]: "absent"})

    def test_managed_wrong_attachment_cleans_without_invoking(self):
        self.configure(managed=True)
        self.config["mcp_changes"] = {"server_url": "https://other.invalid/mcp"}
        self.assertIn("MCP endpoint", self.run_agent(passed=False).stderr)
        self.assertEqual(self.operations("invoke"), [])
        self.assert_cleaned()


if __name__ == "__main__":
    unittest.main()
