"""Offline checks for Bicep CI selection and public-repository dependencies."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]
PIPELINE = ROOT / ".azure-pipelines/private-bicep-pr-ci.yml"
SAMPLE_ROOT = "infrastructure/infrastructure-setup-bicep"
EXCLUDED_SAMPLES = (
    "31-customer-managed-keys-standard-agent",
    "40-basic-agent-setup",
    "41-standard-agent-setup",
    "42-basic-agent-setup-with-customization",
    "43-standard-agent-setup-with-customization",
)


class BicepPipelineTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = yaml.safe_load(PIPELINE.read_text(encoding="utf-8"))

    def test_cloud_stages_require_non_fork_discovery(self):
        stages = self.pipeline["stages"]
        self.assertIn("eq(variables['System.PullRequest.IsFork'], 'False')", stages[0]["condition"])
        self.assertIn("ne(variables['Build.Reason'], 'PullRequest')", stages[0]["condition"])
        self.assertEqual("StaticValidation", stages[1]["dependsOn"])
        self.assertEqual("AzureConnectionValidation", stages[2]["dependsOn"])
        for stage in stages[1:]:
            self.assertNotIn("condition", stage)

    def test_trigger_and_diagnostic_paths_resolve_publicly(self):
        for trigger in ("trigger", "pr"):
            included = self.pipeline[trigger]["paths"]["include"]
            self.assertIn(PIPELINE.relative_to(ROOT).as_posix(), included)
            self.assertIn(".azure-pipelines/scripts/bicep/**", included)
            self.assertIn(
                "samples/python/hosted-agents/bring-your-own/invocations/diagnostic-agent/**",
                included,
            )
        diagnostic = ROOT / ".azure-pipelines/scripts/bicep/run-data-plane-diagnostics.sh"
        self.assertTrue(diagnostic.is_file())
        sample = ROOT / "samples/python/hosted-agents/bring-your-own/invocations/diagnostic-agent"
        self.assertTrue((sample / "azure.yaml").is_file())
        self.assertTrue((sample / "src/diagnostic-agent-python-invocations/main.py").is_file())
        self.assertNotIn("internal/tools/", PIPELINE.read_text(encoding="utf-8"))
        self.assertNotIn("internal/tools/", diagnostic.read_text(encoding="utf-8"))

    def test_push_and_helper_changes_select_templates_without_azure(self):
        bash = shutil.which("bash")
        self.assertIsNotNone(bash, "Bash is required for pipeline selection checks")
        script = self.pipeline["stages"][0]["jobs"][0]["steps"][1]["bash"]
        script = script.replace("${{ parameters.samplePath }}", "")
        script = script.replace("${{ parameters.validateAll }}", "false")
        script = script.replace("$(BICEP_ROOT)", SAMPLE_ROOT)
        stub = 'az() { printf "%s\\n" "$*" >> calls.txt; }\n'
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)

            def git(*args):
                return subprocess.run(
                    ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                    cwd=repo, check=True, capture_output=True, text=True,
                )

            git("init", "-q")
            git("config", "user.name", "CI")
            git("config", "user.email", "ci@example.com")
            for name in ("00-basic", "01-example", *EXCLUDED_SAMPLES):
                template = repo / SAMPLE_ROOT / name / "main.bicep"
                template.parent.mkdir(parents=True)
                template.write_text("param location string\n", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "base")
            for changed, expected in (
                (f"{SAMPLE_ROOT}/01-example/main.bicep", "01-example"),
                *((f"{SAMPLE_ROOT}/{name}/main.bicep", name) for name in EXCLUDED_SAMPLES),
                (".azure-pipelines/scripts/bicep/run-data-plane-diagnostics.sh", "00-basic"),
                (PIPELINE.relative_to(ROOT).as_posix(), "00-basic"),
            ):
                with self.subTest(changed=changed):
                    path = repo / changed
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("// changed\n", encoding="utf-8")
                    git("add", changed)
                    git("commit", "-qm", "change")
                    result = subprocess.run(
                        [bash, "-c", stub + script], cwd=repo,
                        env={**os.environ, "SYSTEM_PULLREQUEST_TARGETBRANCH": ""},
                        capture_output=True, text=True,
                    )
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    calls = (repo / "calls.txt").read_text(encoding="utf-8")
                    self.assertIn(f"bicep build --file {SAMPLE_ROOT}/{expected}/main.bicep", calls)
                    (repo / "calls.txt").unlink()

    def test_live_deployment_exclusion_is_sample_specific_and_preserves_failures(self):
        bash = shutil.which("bash")
        self.assertIsNotNone(bash, "Bash is required for pipeline deployment checks")
        script = self.pipeline["stages"][2]["jobs"][0]["steps"][1]["inputs"]["inlineScript"]
        loop = script[script.index('for deployment_file in "${deployment_files[@]}"; do'):]
        loop = loop.replace("$(BICEP_ROOT)", SAMPLE_ROOT)
        stub = """
set -euo pipefail
primary_location=westus
fallback_location=eastus
deployment_files=("$@")
deploy_with_location() {
    printf 'DEPLOY %s %s\\n' "$1" "$2"
    return "$DEPLOY_EXIT_CODE"
}
bicepparam_supports_location() { return 0; }
"""
        excluded_dirs = {f"{SAMPLE_ROOT}/{name}" for name in EXCLUDED_SAMPLES}
        excluded_files = [f"{SAMPLE_ROOT}/{name}/main.bicep" for name in EXCLUDED_SAMPLES]
        other = f"{SAMPLE_ROOT}/00-basic/main.bicep"
        lookalikes = [f"{SAMPLE_ROOT}/{name}-other/main.bicep" for name in EXCLUDED_SAMPLES]
        for files, deploy_exit_code, expected_exit_code in (
            *(([file], 0, 0) for file in excluded_files),
            *(([f"{directory}/main.bicepparam"], 0, 0) for directory in sorted(excluded_dirs)),
            (excluded_files, 0, 0),
            (excluded_files + [other], 0, 0),
            (lookalikes, 0, 0),
            (excluded_files + [other], 7, 1),
        ):
            with self.subTest(files=files, deploy_exit_code=deploy_exit_code):
                result = subprocess.run(
                    [bash, "-c", stub + loop, "bicep-ci", *files],
                    cwd=ROOT,
                    env={**os.environ, "DEPLOY_EXIT_CODE": str(deploy_exit_code)},
                    capture_output=True, text=True,
                )
                self.assertEqual(expected_exit_code, result.returncode, result.stdout + result.stderr)
                for file in files:
                    if file.rsplit("/", 1)[0] in excluded_dirs:
                        self.assertIn(f"Skipping live deployment of {file}", result.stdout)
                        self.assertIn("##vso[task.logissue type=warning]", result.stdout)
                        self.assertIn("live deployment is NOT validated", result.stdout)
                        self.assertNotIn(f"DEPLOY {file}", result.stdout)
                    else:
                        self.assertIn(f"DEPLOY {file} westus", result.stdout)
                if expected_exit_code:
                    self.assertIn("##vso[task.logissue type=error]", result.stdout)
                    self.assertIn(f"DEPLOY {other} eastus", result.stdout)


if __name__ == "__main__":
    unittest.main()
