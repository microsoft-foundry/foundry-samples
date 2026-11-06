"""Keep runtime regression execution isolated, frozen, and wired into both CIs."""

from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / ".azure-pipelines/scripts/hosted-agents"
SPEC = importlib.util.spec_from_file_location(
    "hosted_agent_runtime_tests", SCRIPTS / "run_runtime_tests.py"
)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class RuntimeTestEntrypointTests(unittest.TestCase):
    def test_syncs_frozen_sample_before_running_separate_discovery(self):
        project = str(
            ROOT
            / "samples/python/hosted-agents/langgraph/responses/07-human-in-the-loop"
            / "src/langgraph-human-in-the-loop-responses"
        )
        with patch.object(runner.subprocess, "run") as run:
            runner.main()
        self.assertEqual(run.call_count, 2)
        self.assertEqual(
            run.call_args_list[0].args[0],
            ["uv", "sync", "--frozen", "--python", "3.13", "--project", project],
        )
        self.assertEqual(
            run.call_args_list[1].args[0],
            [
                "uv",
                "run",
                "--no-sync",
                "--project",
                project,
                "python",
                "-m",
                "unittest",
                "discover",
                "-s",
                ".azure-pipelines/scripts/hosted-agents/runtime-tests",
                "-p",
                "test_*.py",
            ],
        )
        for call in run.call_args_list:
            self.assertEqual(call.kwargs, {"cwd": ROOT, "check": True})
        self.assertFalse(
            (SCRIPTS / "tests/test_langgraph_sample_lifecycle.py").exists()
        )
        self.assertTrue(
            (SCRIPTS / "runtime-tests/test_langgraph_sample_lifecycle.py").is_file()
        )

    def test_sync_failure_prevents_test_execution(self):
        with (
            patch.object(
                runner.subprocess,
                "run",
                side_effect=subprocess.CalledProcessError(1, "uv"),
            ) as run,
            self.assertRaises(subprocess.CalledProcessError),
        ):
            runner.main()
        self.assertEqual(run.call_count, 1)

    def test_runtime_failure_propagates(self):
        with (
            patch.object(
                runner.subprocess,
                "run",
                side_effect=[None, subprocess.CalledProcessError(1, "unittest")],
            ),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            runner.main()

    def test_github_and_ado_run_the_entrypoint_without_skipping(self):
        workflow = yaml.load(
            (ROOT / ".github/workflows/scripts-selftest.yml").read_text(
                encoding="utf-8"
            ),
            Loader=yaml.BaseLoader,
        )
        job = workflow["jobs"]["hosted-agent-runtime-regressions"]
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertIn(
            "samples/python/hosted-agents/langgraph/responses/07-human-in-the-loop/**",
            workflow["on"]["pull_request"]["paths"],
        )
        self.assertEqual(job["steps"][0]["with"]["persist-credentials"], "false")
        for step in job["steps"]:
            self.assertNotIn("if", step)
            self.assertNotIn("continue-on-error", step)
        self.assertIn('"uv==0.11.7"', job["steps"][-2]["run"])
        self.assertEqual(
            job["steps"][-1]["run"],
            "python .azure-pipelines/scripts/hosted-agents/run_runtime_tests.py",
        )
        pipeline = yaml.safe_load(
            (ROOT / ".azure-pipelines/hosted-agents-samples-ci.yml").read_text(
                encoding="utf-8"
            )
        )
        discover = next(
            stage for stage in pipeline["stages"] if stage.get("stage") == "Discover"
        )
        steps = discover["jobs"][0]["steps"]
        runtime = next(
            step
            for step in steps
            if step.get("displayName") == "Run frozen hosted-agent runtime regressions"
        )
        self.assertIn('"uv==0.11.7"', runtime["bash"])
        self.assertIn("set -euo pipefail", runtime["bash"])
        self.assertIn(
            "python3 .azure-pipelines/scripts/hosted-agents/run_runtime_tests.py",
            runtime["bash"],
        )
        self.assertNotIn("condition", runtime)
        self.assertNotIn("continueOnError", runtime)


if __name__ == "__main__":
    unittest.main()
