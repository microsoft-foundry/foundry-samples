"""Offline checks for prompt pipeline wiring and result summaries."""

import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import yaml


REPO = Path(__file__).resolve().parents[4]
SCRIPT = Path(__file__).resolve().parents[1] / "summarize_results.py"
SPEC = importlib.util.spec_from_file_location("prompt_pipeline_summary", SCRIPT)
summary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(summary)


def mappings(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from mappings(child)


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = yaml.safe_load((REPO / ".azure-pipelines/prompt-agents-samples-ci.yml").read_text(encoding="utf-8"))
        cls.nodes = list(mappings(cls.pipeline))
        cls.stages = {node["stage"]: node for node in cls.nodes if "stage" in node}
        cls.discovery = cls.stages["Discover"]
        cls.execution = cls.stages["E2E_${{ profile }}"]
        cls.job = next(node for node in mappings(cls.execution) if node.get("job") == "Validate")
        cls.invoke = next(node for node in mappings(cls.job) if "run-prompt-agent.sh" in node.get("inputs", {}).get("inlineScript", ""))
        cls.recovery = next(node for node in mappings(cls.job) if "cleanup-prompt-agent.sh" in node.get("inputs", {}).get("inlineScript", ""))

    def test_automatic_triggers_and_provision_modes(self):
        paths = {
            "samples/cli/prompt-agents/**",
            ".azure-pipelines/prompt-agents-samples-ci.yml",
            ".azure-pipelines/scripts/prompt-agents/**",
            ".azure-pipelines/prompt-agent-tests/**",
            ".github/scripts/hosted_agent_fixture.py",
            ".github/scripts/hosted_agent_test_spec.py",
        }
        self.assertIs(self.pipeline["trigger"]["batch"], True)
        self.assertIs(self.pipeline["pr"]["autoCancel"], True)
        for event in ("trigger", "pr"):
            self.assertEqual(self.pipeline[event]["branches"]["include"], ["main"])
            self.assertEqual(set(self.pipeline[event]["paths"]["include"]), paths)
        self.assertEqual(self.pipeline["schedules"][0]["cron"], "0 9 * * *")
        self.assertEqual(self.pipeline["schedules"][0]["branches"]["include"], ["main"])
        self.assertIs(self.pipeline["schedules"][0]["always"], True)
        params = {item["name"]: item for item in self.pipeline["parameters"]}
        self.assertEqual(params["sampleFilter"]["default"], "*")
        self.assertEqual(params["discoveryMode"]["default"], "auto")
        self.assertIn({"group": "samples-prompt-agents-ci"}, self.pipeline["variables"])
        profiles = next(item["value"] for item in self.pipeline["variables"] if item.get("name") == "profiles")
        self.assertEqual(profiles.split(","), ["prompt", "managed"])
        discover_script = next(node for node in mappings(self.discovery) if node.get("name") == "matrix")
        self.assertIn('SKIP_PROVISION" != true', discover_script["bash"])
        self.assertIn('is_unset "$SERVICE_CONNECTION"', discover_script["bash"])
        self.assertIn('for key in PROJECT_ID PROJECT_ENDPOINT MODEL_DEPLOYMENT', discover_script["bash"])
        self.assertIn('for key in SUBSCRIPTION_ID LOCATION', discover_script["bash"])
        self.assertIn('python -m unittest discover -s .azure-pipelines/scripts/prompt-agents/tests', discover_script["bash"])
        self.assertEqual(discover_script["env"]["SKIP_PROVISION"], "$(SKIP_PROVISION)")
        steps = self.job["steps"]
        provision = next(node for node in steps if "provision-prompt-agent.sh" in node.get("inputs", {}).get("inlineScript", ""))
        teardown = next(node for node in steps if "teardown-prompt-agent.sh" in node.get("inputs", {}).get("inlineScript", ""))
        self.assertEqual(provision["condition"], "and(succeeded(), eq(variables['SKIP_PROVISION'], 'false'))")
        self.assertEqual(teardown["condition"], "and(always(), eq(variables['SKIP_PROVISION'], 'false'))")
        self.assertLess(steps.index(provision), steps.index(self.invoke))
        self.assertLess(steps.index(self.recovery), steps.index(teardown))
        self.assertLess(steps.index(teardown), steps.index(next(node for node in steps if node.get("task") == "PublishPipelineArtifact@1")))
        self.assertIn('jq -er .project_id "$CELL_DIR/provision-ledger.json"', self.invoke["inputs"]["inlineScript"])
        self.assertIn('jq -r .project_id "$CELL_DIR/provision-ledger.json"', self.recovery["inputs"]["inlineScript"])

    def test_changed_mode_validates_ref_before_discovery(self):
        checkout = next(node for node in mappings(self.discovery) if node.get("checkout") == "self")
        self.assertEqual(checkout["fetchDepth"], 0)
        self.assertIs(checkout["persistCredentials"], True)
        step = next(node for node in mappings(self.discovery) if node.get("name") == "matrix")
        script = step["bash"]
        self.assertIn('if [ "$BUILD_REASON" = PullRequest ]; then', script)
        self.assertIn('DISCOVERY_MODE=changed', script)
        self.assertIn('DISCOVERY_MODE=all', script)
        self.assertIn('BASE_REF="origin/$target_branch"', script)
        self.assertLess(script.index('BASE_REF="origin/$target_branch"'), script.index('git fetch'))
        self.assertEqual(step["env"]["BUILD_REASON"], "$(Build.Reason)")
        self.assertEqual(step["env"]["PR_TARGET_BRANCH"], "$(System.PullRequest.TargetBranch)")
        self.assertIn('git check-ref-format "refs/heads/$branch"', script)
        self.assertIn('git fetch --no-tags origin "+refs/heads/$branch:refs/remotes/origin/$branch"', script)
        self.assertIn('git rev-parse --verify "$BASE_REF^{commit}"', script)
        self.assertLess(script.index("git check-ref-format"), script.index("git fetch"))
        self.assertLess(script.index("git fetch"), script.index("git rev-parse"))
        self.assertLess(script.index("git rev-parse"), script.index("discover_samples.py"))
        self.assertIn("--validate-contracts", script)

    def test_recovery_is_authenticated_always_task_after_runner(self):
        self.assertEqual(self.invoke["task"], "AzureCLI@2")
        self.assertEqual(self.recovery["task"], "AzureCLI@2")
        self.assertEqual(self.recovery["condition"], "always()")
        self.assertEqual(self.invoke["env"]["PROMPT_AGENT_KEEP_WORKSPACE"], "true")
        for key in ("azureSubscription", "visibleAzLogin", "scriptType", "scriptLocation"):
            self.assertEqual(self.recovery["inputs"][key], self.invoke["inputs"][key])
        for key in ("PYTHON", "CELL_DIR", "PROJECT_ID", "PROJECT_ENDPOINT", "MODEL_DEPLOYMENT"):
            self.assertEqual(self.recovery["env"][key], self.invoke["env"][key])
        steps = self.job["steps"]
        publisher = next(node for node in steps if node.get("task") == "PublishPipelineArtifact@1")
        self.assertLess(steps.index(self.invoke), steps.index(self.recovery))
        self.assertLess(steps.index(self.recovery), steps.index(publisher))
        self.assertGreater(self.job["cancelTimeoutInMinutes"], self.recovery["timeoutInMinutes"])
        self.assertEqual(self.job["strategy"]["maxParallel"], 1)
        match = re.search(r"--command-timeout\s+(\d+)", self.invoke["inputs"]["inlineScript"])
        self.assertIsNotNone(match)
        runner = (REPO / ".azure-pipelines/scripts/prompt-agents/run-prompt-agent.sh").read_text(encoding="utf-8")
        cleanup_timeout = int(re.search(r"local cleanup_timeout=(\d+)", runner)[1])
        self.assertGreater(
            self.job["cancelTimeoutInMinutes"] * 60,
            600 + 10 + 9 * (cleanup_timeout + 10) + 20 +
            (self.recovery["timeoutInMinutes"] + 30) * 60,
        )

    def test_compact_matrix_hydrates_artifacts_and_publishes_failures(self):
        step = next(node for node in mappings(self.discovery) if node.get("name") == "matrix")
        self.assertIn("jq '.entries'", step["bash"])
        self.assertIn("matrix.matrix_${{ profile }}", self.job["strategy"]["matrix"])
        download = next(node for node in self.job["steps"] if node.get("download") == "current")
        self.assertIn(f"/{download['artifact']}/entries.json", self.invoke["env"]["ENTRIES"])
        script = self.invoke["inputs"]["inlineScript"]
        self.assertLess(script.index(" hydrate"), script.index("run-prompt-agent.sh"))
        self.assertIn('--sample "$sample"', script)
        for stage in (self.discovery, self.execution, self.stages["Summary"]):
            publishers = [node for node in mappings(stage) if node.get("task") == "PublishPipelineArtifact@1"]
            self.assertTrue(publishers)
            self.assertTrue(all(node["condition"] == "always()" for node in publishers))
        self.assertIn("always()", self.stages["Summary"]["condition"])


class SummaryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.entries = [{"comboId": "cli-prompt-agents-basic", "samplePath": "samples/cli/prompt-agents/basic",
                         "executionProfile": "prompt"}]

    def test_cli_fails_closed_for_missing_and_invalid_results(self):
        entries = self.root / "entries.json"
        entries.write_text(json.dumps(self.entries), encoding="utf-8")
        result = self.root / f"PromptAgentResult-{self.entries[0]['comboId']}" / "run/result.json"
        result.parent.mkdir(parents=True)
        output = self.root / "summary/summary.md"
        for content, status, code in ((None, "missing/invalid result", 1), ("{", "missing/invalid result", 1),
                                       ("[]", "missing/invalid result", 1), ("{}", "missing/invalid result", 1),
                                       ('{"status":"failed"}', "failed", 1), ('{"status":"passed"}', "failed recovery", 1)):
            with self.subTest(content=content):
                if content is not None:
                    result.write_text(content, encoding="utf-8")
                process = subprocess.run([sys.executable, "-B", str(SCRIPT), "--entries", str(entries),
                                          "--artifacts", str(self.root), "--output", str(output)],
                                         capture_output=True, text=True, timeout=30)
                self.assertEqual(process.returncode, code, process.stderr)
                text = output.read_text(encoding="utf-8")
                self.assertIn(f"| {self.entries[0]['samplePath']} | prompt | {status} |", text)

    def test_failed_recovery_overrides_passed_e2e(self):
        run = self.root / f"PromptAgentResult-{self.entries[0]['comboId']}" / "run"
        run.mkdir(parents=True)
        (run / "result.json").write_text('{"status":"passed"}', encoding="utf-8")
        for recovery in ('{"status":"cleanup-only","exit_code":1,"cleanup_status":"failed","ownership_validated":false}',
                         "{}", "{"):
            with self.subTest(recovery=recovery):
                (run / "recovery-result.json").write_text(recovery, encoding="utf-8")
                text, failed = summary.summarize(self.entries, self.root)
                self.assertTrue(failed)
                self.assertIn("failed recovery", text)

    def test_provisioned_cell_requires_verified_teardown(self):
        cell = self.root / f"PromptAgentResult-{self.entries[0]['comboId']}"
        (cell / "run").mkdir(parents=True)
        (cell / "run/result.json").write_text('{"status":"passed"}', encoding="utf-8")
        (cell / "run/recovery-result.json").write_text(
            '{"status":"cleanup-only","exit_code":0,"cleanup_status":"complete"}', encoding="utf-8"
        )
        (cell / "provision-ledger.json").write_text('{}', encoding="utf-8")
        text, failed = summary.summarize(self.entries, self.root)
        self.assertTrue(failed)
        self.assertIn("failed teardown", text)
        (cell / "teardown-result.json").write_text('{"status":"passed"}', encoding="utf-8")
        text, failed = summary.summarize(self.entries, self.root)
        self.assertFalse(failed)

    def test_passed_cell_requires_recovery_result(self):
        run = self.root / f"PromptAgentResult-{self.entries[0]['comboId']}" / "run"
        run.mkdir(parents=True)
        (run / "result.json").write_text('{"status":"passed"}', encoding="utf-8")
        text, failed = summary.summarize(self.entries, self.root)
        self.assertTrue(failed)
        self.assertIn("failed recovery", text)
        (run / "recovery-result.json").write_text(
            '{"status":"cleanup-only","exit_code":0,"cleanup_status":"complete"}', encoding="utf-8"
        )
        text, failed = summary.summarize(self.entries, self.root)
        self.assertFalse(failed)

    def test_only_expected_cells_are_reported_and_paths_escaped(self):
        entries = [{"comboId": name, "samplePath": f"samples/{name}", "executionProfile": profile}
                   for name, profile in (("failed", "managed"), ("missing", "prompt"), ("passed", "prompt"))]
        for name in ("failed", "passed", "unrelated"):
            path = self.root / f"PromptAgentResult-{name}/run/result.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"status": "failed" if name == "failed" else "passed"}), encoding="utf-8")
            (path.parent / "recovery-result.json").write_text(
                '{"status":"cleanup-only","exit_code":0,"cleanup_status":"complete"}', encoding="utf-8"
            )
        text, failed = summary.summarize(entries, self.root)
        self.assertTrue(failed)
        self.assertIn("| samples/missing | prompt | missing/invalid result |", text)
        self.assertNotIn("unrelated", text)
        escaped, _ = summary.summarize([{**entries[0], "samplePath": "sample|name\nnext"}], self.root)
        self.assertIn("sample\\|name next", escaped)

    def test_unsafe_combo_ids_are_rejected(self):
        for combo in ("../outside", "/absolute", "a/b", "a\\b", "", None):
            with self.subTest(combo=combo):
                with self.assertRaisesRegex(ValueError, "unsafe combo ID"):
                    summary.summarize([{**self.entries[0], "comboId": combo}], self.root)


if __name__ == "__main__":
    unittest.main()
