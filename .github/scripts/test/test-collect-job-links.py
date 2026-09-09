#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "collect-job-links.py"


class CollectJobLinksTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_script(self, jobs: list[dict[str, str]]) -> dict[str, str]:
        jobs_file = self.root / "jobs.ndjson"
        jobs_file.write_text("\n".join(json.dumps(job) for job in jobs) + "\n", encoding="utf-8")
        output = self.root / "job-links.json"
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--jobs-file", str(jobs_file), "--output", str(output)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(output.read_text(encoding="utf-8"))

    def test_matches_build_readiness_and_live_service_job_names(self) -> None:
        links = self.run_script(
            [
                {
                    "name": "build-readiness (python-quickstart-a, samples/python/quickstart/a, python, full-fleet)",
                    "html_url": "https://github.com/example/repo/actions/runs/1/job/10",
                },
                {
                    "name": "live-service (csharp-quickstart-b, samples/csharp/quickstart/b, csharp, full-fleet)",
                    "html_url": "https://github.com/example/repo/actions/runs/1/job/11",
                },
            ]
        )
        self.assertEqual(
            links,
            {
                "python-quickstart-a": "https://github.com/example/repo/actions/runs/1/job/10",
                "csharp-quickstart-b": "https://github.com/example/repo/actions/runs/1/job/11",
            },
        )

    def test_recovers_sample_id_from_truncated_job_name(self) -> None:
        # GitHub truncates long matrix job display names, but the sample id
        # (the matrix's first field) is always intact before the first comma.
        links = self.run_script(
            [
                {
                    "name": "build-readiness (python-hosted-agents-agent-framework-a2a-01, samples/python/hosted-agen...",
                    "html_url": "https://github.com/example/repo/actions/runs/1/job/12",
                },
            ]
        )
        self.assertEqual(
            links,
            {"python-hosted-agents-agent-framework-a2a-01": "https://github.com/example/repo/actions/runs/1/job/12"},
        )

    def test_ignores_unrelated_jobs(self) -> None:
        links = self.run_script(
            [
                {"name": "discover", "html_url": "https://github.com/example/repo/actions/runs/1/job/1"},
                {"name": "completeness", "html_url": "https://github.com/example/repo/actions/runs/1/job/2"},
                {"name": "publish-dashboard", "html_url": "https://github.com/example/repo/actions/runs/1/job/3"},
            ]
        )
        self.assertEqual(links, {})

    def test_ignores_malformed_lines(self) -> None:
        links = self.run_script([{"name": "build-readiness (a, samples/a, python, full-fleet)", "html_url": "https://github.com/example/repo/actions/runs/1/job/1"}])
        jobs_file = self.root / "jobs.ndjson"
        jobs_file.write_text(jobs_file.read_text(encoding="utf-8") + "not json\n{}\n", encoding="utf-8")
        output = self.root / "job-links.json"
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--jobs-file", str(jobs_file), "--output", str(output)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), links)


if __name__ == "__main__":
    unittest.main()
