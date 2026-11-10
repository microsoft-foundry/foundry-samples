"""Keep runtime regression execution isolated, frozen, and wired into GitHub CI."""

from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / ".github/scripts"
SPEC = importlib.util.spec_from_file_location(
    "hosted_agent_runtime_tests", SCRIPTS / "run_hosted_agent_runtime_tests.py"
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
                ".github/scripts/runtime-tests",
                "-p",
                "test_*.py",
            ],
        )
        for call in run.call_args_list:
            self.assertEqual(call.kwargs, {"cwd": ROOT, "check": True})
        self.assertFalse((SCRIPTS / "test/test_langgraph_sample_lifecycle.py").exists())
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

    def test_github_runs_the_entrypoint_without_skipping(self):
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
            "python .github/scripts/run_hosted_agent_runtime_tests.py",
        )
        self.assertIn(
            "python .github/scripts/test/test_hosted_agent_runtime_entrypoint.py",
            next(
                step["run"]
                for step in workflow["jobs"]["ado-pipelines-harness"]["steps"]
                if step.get("name") == "Test hosted-agent helpers and fixture contracts"
            ),
        )


if __name__ == "__main__":
    unittest.main()
