"""Keep hosted-agent PR policy jobs credential-free, including for forks."""

from pathlib import Path
import unittest

import yaml


class PolicyWorkflowTests(unittest.TestCase):
    def test_both_policy_jobs_run_without_credentials(self):
        path = Path(__file__).resolve().parents[2] / "workflows/hosted-agent-policies.yml"
        workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        self.assertEqual(
            workflow["on"],
            {"pull_request": {"types": ["opened", "synchronize", "reopened", "ready_for_review"]}},
        )
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(set(workflow["jobs"]), {"contracts", "dependencies"})
        for name, job in workflow["jobs"].items():
            with self.subTest(job=name):
                self.assertEqual(job["runs-on"], "ubuntu-latest")
                for key in ("if", "environment", "permissions", "secrets", "continue-on-error"):
                    self.assertNotIn(key, job)
                checkout = job["steps"][0]["with"]
                self.assertEqual(checkout["ref"], "${{ github.event.pull_request.head.sha }}")
                self.assertEqual(checkout["fetch-depth"], "0")
                self.assertEqual(checkout["persist-credentials"], "false")
                for step in job["steps"]:
                    self.assertNotIn("continue-on-error", step)
                    self.assertNotIn("if", step)
                check = job["steps"][-1]
                self.assertEqual(check["env"]["BASE_SHA"], "${{ github.event.pull_request.base.sha }}")
                self.assertIn('git merge-base "$BASE_SHA" HEAD', check["run"])
                self.assertIn('--base "$base" --head HEAD', check["run"])
        dependency_job = workflow["jobs"]["dependencies"]
        install = next(
            step for step in dependency_job["steps"] if step.get("name") == "Install policy dependencies"
        )
        self.assertIn('"uv==0.11.7"', install["run"])
        self.assertIn("--resolve", dependency_job["steps"][-1]["run"])
        self.assertNotIn("secrets.", path.read_text(encoding="utf-8"))
        self.assertNotIn("id-token", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
