#!/usr/bin/env python3
"""Check phase boundaries without provisioning or invoking Azure resources."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import wave

import yaml


ROOT = Path(__file__).resolve().parents[4]
CI = ROOT / ".azure-pipelines" / "scripts" / "hosted-agents"
RUNNER = (CI / "run-hosted-agent.sh").read_text(encoding="utf-8")
PIPELINE = yaml.safe_load(
    (ROOT / ".azure-pipelines" / "hosted-agents-samples-ci.yml").read_text(
        encoding="utf-8"
    )
)
SHARDS = next(
    stage for stage in PIPELINE["stages"]
    if next(iter(stage)).startswith("${{ each shard")
)
JOB = next(iter(SHARDS.values()))[0]["jobs"][0]
BODIES = re.compile(
    r"(?m)(^.*bash /dev/fd/3 3<<'(?P<label>STEP_[A-Z0-9_]+)'\n)"
    r"(?P<body>[\s\S]*?)(?P=label)$"
)
BASH = os.environ.get("HOSTED_AGENT_TEST_BASH") or shutil.which("bash")


def action(step):
    if "bash" in step:
        return step["bash"].split()[-1]
    return step.get("inputs", {}).get("arguments")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.work = Path(self.directory.name)
        self.steps = {action(step): step for step in JOB["steps"] if action(step)}

    def run_phase(self, name, overrides=None, keep=(), env=None, shorten_timeout=False):
        overrides = overrides or {}

        def replace(match):
            label = match["label"]
            body = match["body"] if label in keep else (
                'test -z "${LEAKED-}" || exit 90\n'
                f"echo ran:{label}\n"
                + overrides.get(label, "")
                + "\n"
            )
            # Real result-writing behavior uses a private test directory, not /tmp.
            return match[1] + body.replace("/tmp/", "./") + label

        source = BODIES.sub(replace, RUNNER)
        if shorten_timeout:
            source = source.replace(
                "timeout --kill-after=30s 5m", "timeout --kill-after=1s 0.1s"
            )
        runner = self.work / "runner.sh"
        with runner.open("w", encoding="utf-8", newline="\n") as output:
            output.write(source)
        environment = {
            **os.environ,
            **{key: "test-value" for key in self.steps.get(name, {}).get("env", {})},
            "IS_TOOLBOX": "false",
            **(env or {}),
        }
        return subprocess.run(
            [BASH, str(runner), name],
            cwd=self.work,
            env=environment,
            input="caller-stdin\n",
            encoding="utf-8",
            capture_output=True,
            timeout=20,
        )

    def install_tls_mocks(self):
        bin_dir = self.work / "bin"
        bin_dir.mkdir()
        (bin_dir / "curl").write_text(
            """#!/usr/bin/env bash
set -euo pipefail
count=0
[ ! -f "$MOCK_CURL_COUNT" ] || count=$(cat "$MOCK_CURL_COUNT")
count=$((count + 1))
echo "$count" > "$MOCK_CURL_COUNT"
if [ "$count" -ge "$MOCK_CURL_SUCCEED_ON" ]; then
  printf '%s' "${MOCK_CURL_SUCCESS_CODE:-203}"
  exit 0
fi
printf '000'
echo 'curl: (60) simulated certificate mismatch' >&2
exit 60
""",
            encoding="utf-8",
            newline="\n",
        )
        (bin_dir / "sleep").write_text(
            "#!/usr/bin/env bash\necho \"$1\" >> \"$MOCK_SLEEP_LOG\"\n",
            encoding="utf-8",
            newline="\n",
        )
        for command in ("curl", "sleep"):
            (bin_dir / command).chmod(0o755)
        return bin_dir

    def test_step_contract(self):
        expected = [
            None, "ado-tls", None, "hydrate", "prepare", "scaffold", "provision",
            "prepare-deploy", "deploy", "verify-deploy", "diagnose-deploy",
            "session", "invoke", "guardrail", "voicelive", "status", "evidence",
            "delete-session", "delete-toolboxes", "results", None, "teardown",
        ]
        self.assertEqual([action(step) for step in JOB["steps"]], expected)
        for name, step in self.steps.items():
            with self.subTest(action=name):
                self.assertIn(f"  {name})", RUNNER)
                if "task" in step:
                    self.assertEqual(step["task"], "AzureCLI@2")
                    self.assertEqual(step["inputs"]["scriptLocation"], "scriptPath")
                    self.assertTrue(step["inputs"]["scriptPath"].endswith("/run-hosted-agent.sh"))
                else:
                    self.assertIn("run-hosted-agent.sh", step["bash"])
        self.assertEqual(len(BODIES.findall(RUNNER)), 29)
        self.assertEqual(JOB["timeoutInMinutes"], 120)
        self.assertGreaterEqual(JOB["cancelTimeoutInMinutes"], 35)
        self.assertEqual(self.steps["ado-tls"]["timeoutInMinutes"], 5)
        self.assertEqual(
            self.steps["ado-tls"]["env"]["ADO_COLLECTION_URL"],
            "$(System.CollectionUri)",
        )
        matrix_download = next(
            step for step in JOB["steps"]
            if step.get("displayName") == "Download sample matrix"
        )
        self.assertEqual(matrix_download["retryCountOnTaskFailure"], 3)
        self.assertEqual(
            matrix_download["patterns"],
            "HostedAgentSamplesMatrix-attempt-*/entries.json",
        )
        for name in ("status", "evidence", "delete-session", "delete-toolboxes", "results"):
            self.assertEqual(self.steps[name]["condition"], "always()")
        self.assertTrue(self.steps["delete-session"]["continueOnError"])
        self.assertFalse(self.steps["delete-toolboxes"].get("continueOnError", False))
        self.assertFalse(self.steps["evidence"].get("continueOnError", False))
        self.assertIn("bash", self.steps["results"])
        self.assertEqual(self.steps["results"]["env"]["JOB_STATUS"], "$(Agent.JobStatus)")
        self.assertEqual(JOB["steps"][-2]["condition"], "always()")
        self.assertEqual(
            JOB["steps"][-2]["artifact"],
            "cloud-e2e-results-$(comboId)-attempt-$(System.JobAttempt)",
        )
        self.assertEqual(
            self.steps["provision"]["condition"],
            "and(succeeded(), ne(variables['SKIP_PROVISION'], 'true'))",
        )
        self.assertEqual(
            self.steps["teardown"]["condition"],
            "and(always(), ne(variables['SKIP_PROVISION'], 'true'))",
        )
        self.assertEqual(self.steps["diagnose-deploy"]["condition"], "failed()")
        self.assertTrue(self.steps["diagnose-deploy"]["continueOnError"])
        self.assertEqual(
            self.steps["guardrail"]["condition"],
            "and(succeeded(), contains(variables['SAMPLE_PATH'], 'content-safety-guardrail'), eq(variables['PROTOCOL'], 'responses'))",
        )
        self.assertEqual(
            self.steps["voicelive"]["condition"],
            "and(succeeded(), eq(variables['VOICE_LIVE'], 'true'))",
        )
        for name, minutes in {
            "provision": 15, "deploy": 30, "diagnose-deploy": 3, "invoke": 15,
            "guardrail": 10, "voicelive": 20, "status": 3, "evidence": 8,
            "delete-session": 3, "delete-toolboxes": 5, "teardown": 10,
        }.items():
            self.assertEqual(self.steps[name]["timeoutInMinutes"], minutes)
        deadlines = re.findall(r"timeout --kill-after=30s (\d+m) bash /dev/fd/3", RUNNER)
        self.assertEqual(deadlines, ["5m", "3m", "3m", "3m", "15m"])
        for trigger in ("trigger", "pr"):
            self.assertIn(
                ".azure-pipelines/scripts/hosted-agents/**",
                PIPELINE[trigger]["paths"]["include"],
            )
        summary = next(
            stage for stage in PIPELINE["stages"]
            if stage.get("stage") == "Summary"
        )
        summary_script = next(
            step["bash"]
            for step in summary["jobs"][0]["steps"]
            if step.get("displayName") == "Generate sample status summary"
        )
        summary_download = next(
            step for step in summary["jobs"][0]["steps"]
            if step.get("displayName") == "Download result artifacts"
        )
        self.assertEqual(summary_download["retryCountOnTaskFailure"], 3)
        self.assertIn(
            "HostedAgentSamplesMatrix-attempt-*/entries.json",
            summary_download["patterns"],
        )
        status_publish = next(
            step for step in summary["jobs"][0]["steps"]
            if step.get("displayName") == "Upload status artifact"
        )
        self.assertEqual(
            status_publish["artifact"],
            "sample-status-attempt-$(System.JobAttempt)",
        )
        discover = next(
            stage for stage in PIPELINE["stages"]
            if stage.get("stage") == "Discover"
        )
        matrix_publish = next(
            step for step in discover["jobs"][0]["steps"]
            if step.get("displayName") == "Publish sample matrix"
        )
        self.assertEqual(
            matrix_publish["artifact"],
            "HostedAgentSamplesMatrix-attempt-$(System.JobAttempt)",
        )
        cleanup = next(
            stage for stage in PIPELINE["stages"]
            if stage.get("stage") == "CleanupOrphanedToolboxes"
        )
        orphan_publish = next(
            step for step in cleanup["jobs"][0]["steps"]
            if step.get("displayName") == "Upload orphan-cleanup results"
        )
        self.assertEqual(
            orphan_publish["artifact"],
            "cloud-e2e-toolbox-orphan-cleanup-attempt-$(System.JobAttempt)",
        )
        self.assertIn(
            "cloud-e2e-results-$combo_id-attempt-*/result.txt",
            summary_script,
        )
        self.assertIn(
            "HostedAgentSamplesMatrix-attempt-*/entries.json",
            summary_script,
        )
        self.assertIn("sort -V | tail -n 1", summary_script)
        discovery = (CI / "discover-samples.sh").read_text(encoding="utf-8")
        self.assertIn(
            "samples/python/hosted-agents/agent-framework/responses/07-teams-activity",
            discovery,
        )
        self.assertIn(
            "samples/csharp/hosted-agents/agent-framework/teams-activity",
            discovery,
        )
        self.assertIn('.label == "teams-tools"', discovery)
        self.assertIn('.label != "teams-tools"', discovery)
        sample_filter = next(
            parameter for parameter in PIPELINE["parameters"]
            if parameter["name"] == "sampleFilter"
        )
        self.assertEqual(sample_filter["default"], "*")

        self.assertIn('[ "$SAMPLE_FILTER" = "*" ] && SAMPLE_FILTER=""', discovery)
        shared_pattern = re.search(r'echo "\$changed_files" \| grep -qE \'([^\']+)\'', discovery)[1]
        for path in (
            ".azure-pipelines/hosted-agents-samples-ci.yml",
            ".azure-pipelines/scripts/hosted-agents/run-hosted-agent.sh",
            ".azure-pipelines/scripts/hosted-agents/tests/test_hosted_agent_pipeline.py",
            ".azure-pipelines/scripts/hosted-agents/voicelive/fixtures/voice-live-ci.wav",
            ".azure-pipelines/scripts/hosted-agent-samples-ci-skiplist",
            ".azure-pipelines/scripts/hosted-agent-samples-code-ci-skiplist",
            ".github/scripts/hosted_agent_fixture.py",
            ".github/scripts/hosted_agent_test_spec.py",
        ):
            with self.subTest(path=path):
                self.assertRegex(path, shared_pattern)
        self.assertNotRegex(
            ".azure-pipelines/hosted-agent-tests/python/example/test-spec.yml",
            shared_pattern,
        )
        for trigger in ("trigger", "pr"):
            paths = PIPELINE[trigger]["paths"]["include"]
            for path in (
                ".azure-pipelines/hosted-agent-tests/**",
                ".azure-pipelines/scripts/hosted-agent-samples-ci-skiplist",
                ".azure-pipelines/scripts/hosted-agent-samples-code-ci-skiplist",
                ".github/scripts/hosted_agent_fixture.py",
                ".github/scripts/hosted_agent_test_spec.py",
            ):
                self.assertIn(path, paths)

    def test_ado_tls_gate_retries_with_backoff(self):
        bin_dir = self.install_tls_mocks()
        count_file = self.work / "curl-count"
        sleep_file = self.work / "sleep-delays"

        result = self.run_phase(
            "ado-tls",
            keep=("STEP_WAIT_FOR_AZURE_DEVOPS_TLS",),
            env={
                "ADO_COLLECTION_URL": "https://msdata.visualstudio.com/",
                "ADO_TLS_MAX_ATTEMPTS": "3",
                "ADO_TLS_INITIAL_DELAY_SECONDS": "1",
                "ADO_TLS_MAX_DELAY_SECONDS": "10",
                "ADO_TLS_RETRY_JITTER_SECONDS": "0",
                "MOCK_CURL_COUNT": str(count_file),
                "MOCK_CURL_SUCCEED_ON": "3",
                "MOCK_SLEEP_LOG": str(sleep_file),
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(count_file.read_text(encoding="utf-8").strip(), "3")
        self.assertEqual(
            sleep_file.read_text(encoding="utf-8").splitlines(),
            ["1", "2"],
        )
        self.assertIn(
            "Azure DevOps TLS is healthy (HTTP 203) on attempt 3/3.",
            result.stdout,
        )

        count_file.unlink()
        sleep_file.unlink()
        exhausted = self.run_phase(
            "ado-tls",
            keep=("STEP_WAIT_FOR_AZURE_DEVOPS_TLS",),
            env={
                "ADO_COLLECTION_URL": "https://msdata.visualstudio.com/",
                "ADO_TLS_MAX_ATTEMPTS": "2",
                "ADO_TLS_INITIAL_DELAY_SECONDS": "0",
                "ADO_TLS_MAX_DELAY_SECONDS": "0",
                "ADO_TLS_RETRY_JITTER_SECONDS": "0",
                "MOCK_CURL_COUNT": str(count_file),
                "MOCK_CURL_SUCCEED_ON": "99",
                "MOCK_SLEEP_LOG": str(sleep_file),
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            },
        )

        self.assertEqual(exhausted.returncode, 1)
        self.assertEqual(count_file.read_text(encoding="utf-8").strip(), "2")
        self.assertIn(
            "Azure DevOps TLS health check failed after 2 attempts",
            exhausted.stdout,
        )

    def test_hydrate_prefers_latest_matrix_attempt(self):
        workspace = self.work / "workspace"
        for attempt, sample_name in ((2, "older"), (10, "latest")):
            artifact = workspace / f"HostedAgentSamplesMatrix-attempt-{attempt}"
            artifact.mkdir(parents=True)
            (artifact / "entries.json").write_text(
                json.dumps([{
                    "comboId": "combo",
                    "sampleId": "sample-id",
                    "samplePath": "samples/python/hosted-agents/example",
                    "sampleName": sample_name,
                    "sampleLanguage": "python",
                    "protocol": "responses",
                    "protocolVersion": "1.0.0",
                    "isToolbox": "false",
                    "toolboxLabel": "",
                    "toolboxUrl": "",
                    "toolboxQuery": "",
                    "useWestus2": "false",
                    "voiceLive": "false",
                    "deployMode": "container",
                    "runtime": "python_3_13",
                    "entryPoint": "main.py",
                    "depResolution": "",
                }]),
                encoding="utf-8",
            )

        result = self.run_phase(
            "hydrate",
            keep=("STEP_HYDRATE_COMBO_RECORD",),
            env={
                "COMBO_ID": "combo",
                "PIPELINE_WORKSPACE": str(workspace),
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("variable=SAMPLE_NAME]latest", result.stdout)
        self.assertNotIn("variable=SAMPLE_NAME]older", result.stdout)

    def test_summary_prefers_latest_job_attempt(self):
        workspace = self.work / "workspace"
        for attempt in (2, 10):
            result_dir = workspace / f"cloud-e2e-results-combo-attempt-{attempt}"
            result_dir.mkdir(parents=True)
            (result_dir / "result.txt").write_text("success\n", encoding="utf-8")

        result = subprocess.run(
            [
                BASH,
                "-c",
                """
                combo_id=combo
                find "$PIPELINE_WORKSPACE" -maxdepth 2 -type f \
                  -path "$PIPELINE_WORKSPACE/cloud-e2e-results-$combo_id-attempt-*/result.txt" \
                  -print | sort -V | tail -n 1
                """,
            ],
            env={**os.environ, "PIPELINE_WORKSPACE": str(workspace)},
            encoding="utf-8",
            capture_output=True,
            check=True,
        )
        self.assertTrue(
            result.stdout.strip().endswith(
                "cloud-e2e-results-combo-attempt-10/result.txt"
            )
        )

    def test_discovery_uses_shared_exact_skiplist_matching(self):
        discovery = (CI / "discover-samples.sh").read_text(encoding="utf-8")
        self.assertIn("python3 .github/scripts/hosted_agent_fixture.py skiplists", discovery)
        self.assertEqual(discovery.count('grep -Fxq -- "$sample_dir" <<< "$skipped_samples"'), 2)
        self.assertIn('grep -Fxq -- "$sample_dir" <<< "$code_skipped_samples"', discovery)
        self.assertNotIn('/.ci-skip', discovery)
        self.assertNotIn('/.code-ci-skip', discovery)

    def test_discovery_allows_approved_fork_pr(self):
        discover = next(
            stage for stage in PIPELINE["stages"] if stage.get("stage") == "Discover"
        )
        condition = re.sub(r"\s+", "", discover["condition"])
        self.assertEqual(
            condition,
            "ne(variables['CLOUD_E2E_ENABLED'],'false')",
        )
        self.assertNotIn("System.PullRequest.IsFork", condition)
        cloud_stage = next(iter(SHARDS.values()))[0]
        self.assertIn("Discover", cloud_stage["dependsOn"])
        self.assertIn("succeeded('Discover')", cloud_stage["condition"])
        for name in ("CleanupOrphanedToolboxes", "Summary", "NoSamples"):
            stage = next(
                stage for stage in PIPELINE["stages"] if stage.get("stage") == name
            )
            self.assertIn("Discover", stage["dependsOn"])
            self.assertRegex(stage["condition"], r"succeeded\((?:'Discover')?\)")

    def test_public_local_dependencies(self):
        for path in re.findall(r'\$REPO_ROOT/([^"\s]+)', RUNNER):
            if path.startswith("$"):
                continue
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file(), path)
        for filename in ("hosted_agent_fixture.py", "hosted_agent_test_spec.py"):
            self.assertTrue((ROOT / ".github" / "scripts" / filename).is_file())
            self.assertFalse((CI / "scripts" / filename).exists())
            self.assertIn(f"$REPO_ROOT/.github/scripts/{filename}", RUNNER)
        for step in JOB["steps"]:
            if step.get("task") == "AzureCLI@2":
                self.assertEqual(
                    step["inputs"]["scriptPath"],
                    "$(Build.SourcesDirectory)/.azure-pipelines/scripts/hosted-agents/run-hosted-agent.sh",
                )

    def test_voice_fixture_format(self):
        with wave.open(str(CI / "voicelive/fixtures/voice-live-ci.wav"), "rb") as audio:
            self.assertEqual(audio.getnchannels(), 1)
            self.assertEqual(audio.getsampwidth(), 2)
            self.assertEqual(audio.getframerate(), 24000)
            self.assertEqual(audio.getcomptype(), "NONE")
            self.assertGreater(audio.getnframes(), 0)

    def test_diagnostics_do_not_dump_configuration_values(self):
        self.assertNotIn("cat azure.yaml", RUNNER)
        self.assertNotIn('jq . <<< "$DEPLOYED_ENV"', RUNNER)
        self.assertIn("azd env get-values | cut -d= -f1", RUNNER)
        self.assertIn("jq '{id, name, version, status, agent_endpoints}'", RUNNER)
        self.assertNotIn("|| cat /tmp/agent", RUNNER)

    def test_shared_toolbox_preparation_wiring(self):
        self.assertIn('"$COMBO_ID" \\\n    "${TOOLBOX_URL:-}"', RUNNER)
        prepare = (CI / "scripts/prepare-hosted-agent-ci-toolboxes.sh").read_text()
        self.assertIn("shared_endpoint=${6:-}", prepare)
        self.assertIn("REMOVED_SERVICES", prepare)
        self.assertIn("SHARED_ENDPOINT", prepare)
        self.assertIn('state=\'[]\'', prepare)

    def test_log_presentation(self):
        cleanup = next(
            stage for stage in PIPELINE["stages"]
            if stage.get("stage") == "CleanupOrphanedToolboxes"
        )
        for step in [*JOB["steps"], *cleanup["jobs"][0]["steps"]]:
            if step.get("task") == "AzureCLI@2":
                with self.subTest(step=step["displayName"]):
                    self.assertIs(step["inputs"].get("visibleAzLogin"), False)
        wrappers = BODIES.sub("", RUNNER)
        self.assertNotIn("##[group]", wrappers)
        self.assertNotIn("##[endgroup]", wrappers)
        self.assertEqual(wrappers.count("##[section]"), 29)

    def test_prepare_preserves_stdin_and_isolates_shell_state(self):
        result = self.run_phase("prepare", {
            "STEP_INSTALL_AZD_FOUNDRY_EXTENSION_AND_YQ": (
                'read -r value\n'
                "[ \"${value%$'\\r'}\" = caller-stdin ] || exit 81\n"
                'export LEAKED=true\ncd /\ntrap "echo child-exit" EXIT\nexit 0'
            ),
            "STEP_VALIDATE_REQUIRED_VARIABLES": '[ "$PWD" != / ] || exit 82',
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("child-exit", result.stdout)
        self.assertEqual(result.stdout.count("ran:"), 5)

    def test_failure_stops_only_its_phase(self):
        for name, failed, skipped in [
            ("prepare", "STEP_VALIDATE_REQUIRED_VARIABLES", "STEP_VALIDATE_SAMPLE_STRUCTURE"),
            ("scaffold", "STEP_SCAFFOLD_AGENT_PROJECT", "STEP_CONFIGURE_AZD_ENVIRONMENT"),
            ("verify-deploy", "STEP_VERIFY_TEMPORARY_TOOLBOX_DEPLOYMENT", "STEP_VERIFY_DEPLOYED_AGENT_ENVIRONMENT"),
            ("session", "STEP_WAIT_FOR_AGENT_TO_BE_ACTIVE", "STEP_CREATE_AGENT_SESSION"),
        ]:
            with self.subTest(action=name):
                result = self.run_phase(name, {failed: "exit 7"})
                self.assertEqual(result.returncode, 7, result.stderr)
                self.assertNotIn("ran:" + skipped, result.stdout)
        for name in ("status", "evidence", "delete-session", "delete-toolboxes", "results"):
            result = self.run_phase(name)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_optional_toolbox_operation_does_not_skip_other_preparation(self):
        for flag, expected in (("true", 3), ("false", 2)):
            result = self.run_phase("prepare-deploy", env={"IS_TOOLBOX": flag})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.count("ran:"), expected)
            self.assertIn("ran:STEP_PRE_PULL_DOCKER_BASE_IMAGES", result.stdout)
        result = self.run_phase(
            "prepare-deploy", {"STEP_OVERRIDE_TOOLBOX_ENV_IN_AZURE_YAML": "exit 7"},
            env={"IS_TOOLBOX": "true"},
        )
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertNotIn("ran:STEP_PRE_PULL_DOCKER_BASE_IMAGES", result.stdout)

    def test_successful_early_exit_does_not_skip_next_operation(self):
        for name, early, following in [
            ("verify-deploy", "STEP_VERIFY_TEMPORARY_TOOLBOX_DEPLOYMENT", "STEP_VERIFY_DEPLOYED_AGENT_ENVIRONMENT"),
            ("session", "STEP_WAIT_FOR_AGENT_TO_BE_ACTIVE", "STEP_CREATE_AGENT_SESSION"),
        ]:
            result = self.run_phase(name, {early: "exit 0"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ran:" + following, result.stdout)

    def test_operation_timeout_prevents_configuration(self):
        result = self.run_phase(
            "scaffold", {"STEP_SCAFFOLD_AGENT_PROJECT": "sleep 2"}, shorten_timeout=True
        )
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertNotIn("ran:STEP_CONFIGURE_AZD_ENVIRONMENT", result.stdout)

    def test_scaffold_inputs_do_not_leak_into_configuration(self):
        result = self.run_phase("scaffold", {
            "STEP_VERIFY_AZURE_AUTH": 'test "$GH_PAT" = ambient || exit 81',
            "STEP_SCAFFOLD_AGENT_PROJECT": (
                'test "$GH_PAT" = credential && test "$github_pat" = credential && '
                'test "$PLAYWRIGHT_SERVICE_ACCESS_TOKEN" = browser && '
                'test "$SKIP_ACR_CREATION" = true || exit 82'
            ),
            "STEP_CONFIGURE_AZD_ENVIRONMENT": (
                'test "$GH_PAT" = credential && '
                'test "$PLAYWRIGHT_SERVICE_ACCESS_TOKEN" = ambient && '
                'test "$SKIP_ACR_CREATION" = ambient || exit 83'
            ),
        }, env={
            "GH_PAT": "ambient", "PLAYWRIGHT_SERVICE_ACCESS_TOKEN": "ambient",
            "SKIP_ACR_CREATION": "ambient", "PHASE_GH_PAT": "credential",
            "PHASE_github_pat": "credential",
            "PHASE_PLAYWRIGHT_SERVICE_ACCESS_TOKEN": "browser",
            "PHASE_SKIP_ACR_CREATION": "true",
        })
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_results_remain_available_without_azure_authentication(self):
        for status, expected in (
            ("Succeeded", "success"), ("SucceededWithIssues", "success"),
            ("Failed", "failure"), ("Canceled", "failure"),
        ):
            with self.subTest(status=status):
                result = self.run_phase(
                    "results", keep={"STEP_WRITE_STATUS_FILE_AND_STAGE_ARTIFACTS"},
                    env={
                        "JOB_STATUS": status, "SAMPLE_NAME": "sample",
                        "TOOLBOX_LABEL": "", "COMBO_ID": "combo", "SAMPLE_PATH": "sample",
                        "ARTIFACT_STAGING": "artifacts", "CI_TOOLBOX_STATE_FILE": "absent",
                        "CI_TOOLBOX_DEPLOY_RESULT": "absent", "CI_TOOLBOX_CLEANUP_RESULT": "absent",
                    },
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                report = self.work / "artifacts" / "cloud-e2e-results-combo" / "result.txt"
                self.assertEqual(report.read_text().splitlines()[0], expected)

    def test_unknown_action_fails(self):
        result = self.run_phase("not-an-action")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unknown hosted-agent action", result.stderr)


if __name__ == "__main__":
    unittest.main()
