#!/usr/bin/env python3
"""Native A2A contract, deployment preparation and transport regressions."""

import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".github" / "scripts"))
from hosted_agent_test_spec import SpecError, build_plan, evaluate_plan, load_spec

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


invoke = load("invoke_hosted_agent_a2a")
prepare = load("prepare_hosted_agent_a2a")
SAMPLE = "samples/python/hosted-agents/bring-your-own/a2a"
FIXTURE = ".azure-pipelines/hosted-agent-tests/python/bring-your-own/a2a"


def completed(request_id):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "task": {
                "id": "echo-task",
                "status": {"state": "TASK_STATE_COMPLETED"},
                "artifacts": [{"parts": [{"text": "Echo: hello"}]}],
            }
        },
    }


class A2AInvocationTests(unittest.TestCase):
    def test_failed_task_transient_diagnostics_are_retryable_not_successful(self):
        for message in (
            "Model deployment rate limit exceeded",
            "Error calling model: Error code: 503 - server_error",
            "The model is currently experiencing high demand that exceeds the maximum usage size allowed during peak load.",
            "session_not_ready",
        ):
            with self.subTest(message=message):

                def change(response, message=message):
                    response["result"]["task"]["status"] = {
                        "state": "TASK_STATE_FAILED",
                        "message": {"parts": [{"text": message}]},
                    }
                    return response

                outcome, text, raw = self.run_turn(change)
                self.assertEqual(outcome["turn_exit"], 1)
                self.assertFalse(outcome["approval_terminal_error"])
                self.assertEqual(text, "")
                self.assertIn(message, raw)

    def test_nonretryable_and_malformed_failed_tasks_stay_terminal(self):
        for message in (
            {"parts": [{"text": "No cited search results"}]},
            {"parts": [{"text": "Invalid trip requirements"}]},
            {"parts": [{"text": 503}]},
            {"parts": "Model deployment rate limit exceeded"},
            {"parts": [{"text": "Model deployment rate limit exceeded"}, None]},
        ):
            with self.subTest(message=message):

                def change(response, message=message):
                    response["result"]["task"]["status"] = {
                        "state": "TASK_STATE_FAILED",
                        "message": message,
                    }
                    return response

                outcome, text, _ = self.run_turn(change)
                self.assertEqual(outcome["turn_exit"], 1)
                self.assertTrue(outcome["approval_terminal_error"])
                self.assertEqual(text, "")

    def test_http_success_retryable_jsonrpc_errors_reach_retry_classifiers(self):
        for message in (
            "session_not_ready",
            "session_quota_exceeded",
            "Model rate limit exceeded",
        ):
            outcome, _, _ = self.run_turn(
                lambda response: {
                    "jsonrpc": "2.0",
                    "id": response["id"],
                    "error": {"code": -32603, "message": message},
                }
            )
            self.assertEqual(outcome["turn_exit"], 1)
            self.assertFalse(outcome["approval_terminal_error"])

    def run_turn(
        self, change=None, *, status=200, cli_exit=0, raw_json=False, stderr=""
    ):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "input").write_text("hello\n", encoding="utf-8")
            (work / "turn.json").write_text("{}", encoding="utf-8")

            def transport(arguments):
                self.assertIn("--a2a-version", arguments)
                self.assertEqual(arguments[arguments.index("--a2a-version") + 1], "1.0")
                self.assertEqual(
                    arguments[arguments.index("--session-id") + 1], "cell-session"
                )
                self.assertEqual(arguments[4], "cell-agent")
                request = json.loads(
                    Path(arguments[arguments.index("--input-file") + 1]).read_text()
                )
                self.assertEqual(request["method"], "SendMessage")
                self.assertEqual(request["params"]["message"]["role"], "ROLE_USER")
                self.assertFalse(
                    request["params"]["configuration"]["returnImmediately"]
                )
                response = completed(request["id"])
                if change:
                    response = change(response)
                body = response if isinstance(response, str) else json.dumps(response)
                raw = (
                    body
                    if raw_json
                    else f"HTTP/2.0 {status} OK\r\nContent-Type: application/json\r\n\r\n{body}"
                )
                return subprocess.CompletedProcess(arguments, cli_exit, raw, stderr)

            outcome = invoke.invoke_turn(
                1,
                work / "input",
                work / "turn.json",
                work / "evidence",
                1,
                environment={
                    "CI_AGENT_SESSION_ID": "cell-session",
                    "FOUNDRY_AGENT_NAME": "cell-agent",
                },
                transport=transport,
                temp_dir=work,
            )
            text = (work / "invoke-response-1.txt").read_text()
            raw = (work / "invoke-raw-1.json").read_text()
            if cli_exit and stderr:
                self.assertIn(stderr, (work / "invoke-out-1.txt").read_text())
                self.assertNotIn(stderr, raw)
            self.assertTrue(
                (work / "evidence/turn-1-attempt-1-a2a-request.json").is_file()
            )
            self.assertEqual(
                json.loads((work / "invoke-result-1.json").read_text()), outcome
            )
            return outcome, text, raw

    def test_stderr_only_retry_diagnostics_are_retained_separately(self):
        for error in ("session_not_ready", "session_quota_exceeded", "HTTP 429"):
            outcome, _, _ = self.run_turn(cli_exit=1, stderr=error)
            self.assertEqual(outcome["turn_exit"], 1)
            self.assertFalse(outcome["approval_terminal_error"])

    def test_completed_task_produces_artifact_text_and_raw_evidence(self):
        for raw_json in (False, True):
            with self.subTest(raw_json=raw_json):
                outcome, text, raw = self.run_turn(raw_json=raw_json)
                self.assertEqual(outcome["turn_exit"], 0)
                self.assertEqual(text, "Echo: hello")
                self.assertIn("echo-task", raw)

    def test_http_success_with_jsonrpc_error_is_failure(self):
        outcome, text, _ = self.run_turn(
            lambda response: {
                "jsonrpc": "2.0",
                "id": response["id"],
                "error": {"code": -32603, "message": "Specialist failed"},
            }
        )
        self.assertEqual(outcome["turn_exit"], 1)
        self.assertTrue(outcome["approval_terminal_error"])
        self.assertIn("Specialist failed", outcome["approval_error"])
        self.assertEqual(text, "")

    def test_known_azd_update_footer_is_not_part_of_the_server_json(self):
        footer = (
            "WARNING: A new version of extension 'Foundry agents (Beta)' is available: "
            "1.0.0-beta.23 -> 1.0.0\n"
            "  \u2022 To update: azd extension update azure.ai.agents\n"
            "  \u2022 To update all: azd extension update --all\n"
        )
        outcome, text, raw = self.run_turn(
            lambda response: json.dumps(response) + footer
        )
        self.assertEqual(outcome["turn_exit"], 0)
        self.assertEqual(text, "Echo: hello")
        self.assertNotIn("WARNING", raw)

    def test_unrecognized_trailing_output_is_rejected(self):
        outcome, text, _ = self.run_turn(
            lambda response: json.dumps(response) + "unexpected error output"
        )
        self.assertEqual(outcome["turn_exit"], 1)
        self.assertEqual(text, "")

    def test_failed_pending_and_input_required_tasks_are_rejected(self):
        for state in (
            "TASK_STATE_FAILED",
            "TASK_STATE_WORKING",
            "TASK_STATE_INPUT_REQUIRED",
        ):
            with self.subTest(state=state):

                def change(response):
                    response["result"]["task"]["status"]["state"] = state
                    return response

                outcome, text, _ = self.run_turn(change)
                self.assertEqual(outcome["turn_exit"], 1)
                self.assertEqual(text, "")

    def test_malformed_missing_artifact_or_mismatched_response_fails(self):
        for change in (
            lambda response: "not JSON",
            lambda response: {**response, "id": "other-request"},
            lambda response: {**response, "result": {"message": {}}},
            lambda response: {
                **response,
                "result": {
                    "task": {
                        "id": "no-evidence",
                        "status": {"state": "TASK_STATE_COMPLETED"},
                    }
                },
            },
            lambda response: {
                **response,
                "result": {
                    "task": {"id": "", "status": {"state": "TASK_STATE_COMPLETED"}}
                },
            },
        ):
            with self.subTest(change=change):
                outcome, _, _ = self.run_turn(change)
                self.assertEqual(outcome["turn_exit"], 1)
                self.assertTrue(outcome["approval_terminal_error"])

    def test_cli_or_http_failure_cannot_pass_with_completed_body(self):
        for kwargs in ({"cli_exit": 7}, {"status": 401}, {"status": 500}):
            with self.subTest(kwargs=kwargs):
                outcome, text, _ = self.run_turn(**kwargs)
                self.assertEqual(outcome["turn_exit"], 1)
                self.assertEqual(text, "")


class A2APreparationTests(unittest.TestCase):
    def test_each_planner_keeps_its_own_specialist_version_bindings(self):
        root = ROOT / SAMPLE / "travel-planner-web-search"
        original = yaml.safe_load((root / "azure.yaml").read_text())
        spec = load_spec(ROOT / FIXTURE / "travel-planner-web-search/test-spec.yml")
        observed = []
        with tempfile.TemporaryDirectory() as directory:
            for build, version in (("a", "3"), ("b", "4")):
                path = Path(directory) / f"{build}.yaml"
                path.write_text(
                    yaml.safe_dump(
                        prepare.prepare(original, spec["sample"], root, "ci-travel")
                    )
                )

                def command(args, **kwargs):
                    observed.append(args)
                    return subprocess.CompletedProcess(
                        args, 0, json.dumps({"version": version}), ""
                    )

                prepare.deploy_dependencies(path, "ci-travel", command=command)
            first = yaml.safe_load((Path(directory) / "a.yaml").read_text())[
                "services"
            ]["ci-travel"]["env"]
            second = yaml.safe_load((Path(directory) / "b.yaml").read_text())[
                "services"
            ]["ci-travel"]["env"]
            for key in ("FLIGHT_AGENT_VERSION", "HOTEL_AGENT_VERSION"):
                self.assertEqual(first[key], "3")
                self.assertEqual(second[key], "4")
            self.assertFalse(
                any(args[:3] == ["azd", "deploy", "ci-travel"] for args in observed)
            )

    def test_travel_preserves_three_agents_and_binds_their_own_endpoints(self):
        root = ROOT / SAMPLE / "travel-planner-web-search"
        original = yaml.safe_load((root / "azure.yaml").read_text())
        spec = load_spec(ROOT / FIXTURE / "travel-planner-web-search/test-spec.yml")
        before = copy.deepcopy(original)
        manifest = prepare.prepare(original, spec["sample"], root, "ci-travel-code")
        self.assertEqual(original, before)
        agents = {
            key: value
            for key, value in manifest["services"].items()
            if value["host"] == "azure.ai.agent"
        }
        self.assertEqual(
            set(agents),
            {"ci-travel-code", "ci-travel-code-flights", "ci-travel-code-hotels"},
        )
        planner = agents["ci-travel-code"]
        self.assertEqual(planner["project"], "src/travel-agent")
        for key, variable in (
            ("flights", "FLIGHT_AGENT_ENDPOINT"),
            ("hotels", "HOTEL_AGENT_ENDPOINT"),
        ):
            name = f"ci-travel-code-{key}"
            self.assertIn(name, planner["uses"])
            self.assertEqual(
                planner["env"][variable],
                "${AZURE_AI_PROJECT_ENDPOINT}/agents/"
                + name
                + "/endpoint/protocols/a2a?api-version=v1",
            )
            self.assertEqual(
                agents[name]["env"]["TOOLBOX_ENDPOINT"],
                "${TOOLBOX_CI_A2A_TOOLBOX_MCP_ENDPOINT}",
            )
        self.assertEqual(
            manifest["services"]["ci-a2a-toolbox"]["tools"],
            [{"type": "web_search", "name": "web_search"}],
        )

    def test_echo_auto_selects_its_single_service_without_toolbox(self):
        root = ROOT / SAMPLE / "echo"
        document = yaml.safe_load((root / "azure.yaml").read_text())
        spec = load_spec(ROOT / FIXTURE / "echo/test-spec.yml")
        manifest = prepare.prepare(document, spec["sample"], root, "ci-echo-code")
        self.assertEqual(set(manifest["services"]), {"ai-project", "ci-echo-code"})
        self.assertEqual(
            manifest["services"]["ci-echo-code"]["project"], "src/echo-a2a"
        )

    def test_missing_target_and_unknown_endpoint_services_fail(self):
        root = ROOT / SAMPLE / "travel-planner-web-search"
        document = yaml.safe_load((root / "azure.yaml").read_text())
        for sample in (
            {},
            {"service": "missing"},
            {"service": "planner", "endpoints": {"FLIGHT_AGENT_ENDPOINT": "missing"}},
        ):
            with self.subTest(sample=sample), self.assertRaises(ValueError):
                prepare.prepare(document, sample, root, "ci-travel-code")

    def test_both_published_contracts_plan_with_a2a(self):
        for name in ("echo", "travel-planner-web-search"):
            document = load_spec(ROOT / FIXTURE / name / "test-spec.yml")
            plan = build_plan(document, protocol="a2a")
            self.assertEqual(plan["tests"][0]["status"], "applicable")
            self.assertEqual(len(plan["tests"][0]["turns"]), 1)

    def test_a2a_rejects_responses_only_features(self):
        document = load_spec(ROOT / FIXTURE / "echo/test-spec.yml")
        for field in ({"approvals": {"mcp": []}}, {"previous_turn": 1}):
            altered = copy.deepcopy(document)
            altered["tests"][0]["turns"][0].update(field)
            with self.subTest(field=field), self.assertRaises(SpecError):
                build_plan(altered, protocol="a2a")


@unittest.skipUnless(
    os.name == "posix" and shutil.which("bash") and shutil.which("jq"),
    "Linux runner integration",
)
class A2ARunnerTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("yq"), "Structure validation needs yq")
    def test_structure_checks_every_agent_project(self):
        runner = (SCRIPTS.parent / "run-hosted-agent.sh").read_text()
        body = re.search(
            r"3<<'STEP_VALIDATE_SAMPLE_STRUCTURE'\n(.*?)\nSTEP_VALIDATE_SAMPLE_STRUCTURE",
            runner,
            re.DOTALL,
        )[1]
        for name in ("echo", "travel-planner-web-search"):
            manifest = yaml.safe_load((ROOT / SAMPLE / name / "azure.yaml").read_text())
            projects = [
                service["project"]
                for service in manifest["services"].values()
                if service.get("host") == "azure.ai.agent"
            ]
            empty_project = copy.deepcopy(manifest)
            agents = [
                service
                for service in empty_project["services"].values()
                if service.get("host") == "azure.ai.agent"
            ]
            agents[-1]["project"] = ""
            no_agents = {"services": {}}
            for case, document, missing in (
                ("valid", manifest, None),
                ("missing-directory", manifest, projects[-1]),
                ("empty-project", empty_project, None),
                ("no-agents", no_agents, None),
            ):
                with self.subTest(
                    sample=name, case=case
                ), tempfile.TemporaryDirectory() as directory:
                    work = Path(directory)
                    (work / "azure.yaml").write_text(yaml.safe_dump(document))
                    for project in projects:
                        if project != missing:
                            (work / project).mkdir(parents=True)
                    result = subprocess.run(
                        ["bash", "-c", body],
                        check=False,
                        capture_output=True,
                        text=True,
                        env={**os.environ, "SAMPLE_PATH": str(work)},
                        timeout=10,
                    )
                    self.assertEqual(
                        result.returncode,
                        int(case != "valid"),
                        result.stdout + result.stderr,
                    )
                    if missing:
                        self.assertIn(
                            f"missing source directory '{missing}'", result.stdout
                        )

    @unittest.skipUnless(shutil.which("yq"), "Toolbox preparation needs yq")
    def test_native_setup_uses_existing_toolbox_isolation_lifecycle(self):
        root = ROOT / SAMPLE / "travel-planner-web-search"
        document = yaml.safe_load((root / "azure.yaml").read_text())
        spec = load_spec(ROOT / FIXTURE / "travel-planner-web-search/test-spec.yml")
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            path = work / "azure.yaml"
            path.write_text(
                yaml.safe_dump(
                    prepare.prepare(document, spec["sample"], root, "ci-travel-code")
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "bash",
                    str(SCRIPTS / "prepare-hosted-agent-ci-toolboxes.sh"),
                    str(path),
                    str(work / "state.json"),
                    "123",
                    "1",
                    "native-code",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            toolbox = json.loads((work / "state.json").read_text())["toolboxes"][0]
            isolated = yaml.safe_load(path.read_text())
            self.assertNotIn("ci-a2a-toolbox", isolated["services"])
            self.assertIn(toolbox["name"], isolated["services"])
            for name in ("ci-travel-code-flights", "ci-travel-code-hotels"):
                agent = isolated["services"][name]
                self.assertIn(toolbox["name"], agent["uses"])
                self.assertEqual(
                    agent["env"]["TOOLBOX_ENDPOINT"],
                    "${" + toolbox["endpoint_key"] + "}",
                )
            self.assertEqual(
                len(
                    [
                        s
                        for s in isolated["services"].values()
                        if s["host"] == "azure.ai.agent"
                    ]
                ),
                3,
            )

    def test_real_runner_dispatch_collects_and_evaluates_native_task_artifacts(self):
        self.run_invoke(False)

    def test_real_runner_rejects_failed_task_even_when_cli_exits_zero(self):
        self.run_invoke(True)

    def test_real_runner_does_not_retry_permanent_failed_task_diagnostics(self):
        self.run_invoke(True, diagnostic="No cited search results")

    def test_real_runner_retries_transient_failed_task_and_keeps_evidence(self):
        for diagnostic in (
            "Model deployment rate limit exceeded",
            "Error calling model: Error code: 503 - server_error",
            "The model is currently experiencing high demand that exceeds the maximum usage size allowed during peak load.",
        ):
            with self.subTest(diagnostic=diagnostic):
                self.run_invoke(False, diagnostic=diagnostic)

    def run_invoke(self, fail, *, diagnostic=None):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            azd = work / "azd"
            azd.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "args = sys.argv[1:]\n"
                "if args[:3] == ['ai', 'agent', 'show']:\n"
                "    assert args[-1] == 'cell-agent'\n"
                "    print(json.dumps({'version': '2'}))\n"
                "elif args[:3] == ['ai', 'agent', 'invoke']:\n"
                "    assert args[3] == 'cell-agent'\n"
                "    assert os.environ['AZD_ALPHA_ENABLE_AGENTS_A2A'] == 'true'\n"
                "    req = json.loads(Path(args[args.index('--input-file') + 1]).read_text())\n"
                "    counter = Path('invoke-count')\n"
                "    attempt = int(counter.read_text()) + 1 if counter.exists() else 1\n"
                "    counter.write_text(str(attempt))\n"
                f"    state = {'TASK_STATE_FAILED' if fail else 'TASK_STATE_COMPLETED'!r}\n"
                "    body = {'jsonrpc':'2.0','id':req['id'],'result':{'task':{'id':'task-1','status':{'state':state},'artifacts':[{'parts':[{'text':'Echo: hello'}]}]}}}\n"
                f"    diagnostic = {diagnostic!r}\n"
                "    if diagnostic and attempt == 1:\n"
                "        body['result']['task']['status'] = {'state':'TASK_STATE_FAILED','message':{'parts':[{'text':diagnostic}]}}\n"
                "    print('HTTP/2.0 200 OK\\nContent-Type: application/json\\n\\n' + json.dumps(body))\n"
                "else:\n"
                "    raise AssertionError(args)\n",
                encoding="utf-8",
            )
            azd.chmod(0o700)
            sleep = work / "sleep"
            sleep.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            sleep.chmod(0o700)
            combo = work.name + "-a2a"
            evidence = Path("/tmp") / f"agent-test-evidence-{combo}"
            self.addCleanup(shutil.rmtree, evidence, True)
            for prefix, suffix in (
                ("agent-test-plan", ".json"),
                ("agent-turn-plan", ".jsonl"),
            ):
                self.addCleanup(
                    (Path("/tmp") / f"{prefix}-{combo}{suffix}").unlink, missing_ok=True
                )
            result = subprocess.run(
                ["bash", str(SCRIPTS.parent / "run-hosted-agent.sh"), "invoke"],
                capture_output=True,
                text=True,
                timeout=30,
                env={
                    **os.environ,
                    "PATH": str(work) + os.pathsep + os.environ["PATH"],
                    "WORK_DIR": str(work),
                    "REPO_ROOT": str(ROOT),
                    "SAMPLE_PATH": SAMPLE + "/echo",
                    "COMBO_ID": combo,
                    "SAMPLE_NAME": "a2a-echo",
                    "PROTOCOL": "a2a",
                    "TOOLBOX_LABEL": "",
                    "TOOLBOX_QUERY": "",
                    "IS_TOOLBOX": "false",
                    "CI_AGENT_SESSION_ID": "cell-session",
                    "FOUNDRY_AGENT_NAME": "cell-agent",
                },
            )
            self.assertEqual(
                result.returncode, int(fail), result.stdout + result.stderr
            )
            status = json.loads((evidence / "turn-1-status.json").read_text())
            self.assertEqual(status["exit_code"], int(fail))
            self.assertEqual(status["protocol"], "a2a")
            self.assertEqual(
                status["final_attempt"], 2 if diagnostic and not fail else 1
            )
            if diagnostic:
                first = (evidence / "turn-1-attempt-1-a2a-response.txt").read_text()
                self.assertIn("TASK_STATE_FAILED", first)
                self.assertIn(diagnostic, first)
            plan = build_plan(
                load_spec(ROOT / FIXTURE / "echo/test-spec.yml"), protocol="a2a"
            )
            report = evaluate_plan(
                plan, evidence, work / "console.txt", work / "trace.json"
            )
            self.assertEqual(report["status"], "error" if fail else "passed", report)


if __name__ == "__main__":
    unittest.main()
