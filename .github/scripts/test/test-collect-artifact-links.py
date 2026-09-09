#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "collect-artifact-links.py"


class CollectArtifactLinksTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_script(
        self,
        artifacts: list[dict[str, object]],
        repository: str = "example/repo",
        run_id: str = "42",
        run_attempt: str = "1",
    ) -> dict[str, str]:
        artifacts_file = self.root / "artifacts.ndjson"
        artifacts_file.write_text("\n".join(json.dumps(artifact) for artifact in artifacts) + "\n", encoding="utf-8")
        output = self.root / "artifact-links.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--artifacts-file",
                str(artifacts_file),
                "--repository",
                repository,
                "--run-id",
                run_id,
                "--run-attempt",
                run_attempt,
                "--output",
                str(output),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(output.read_text(encoding="utf-8"))

    def test_maps_per_sample_artifact_name_to_artifact_page_url(self) -> None:
        links = self.run_script(
            [
                {"name": "validation-pilot-python-quickstart-a", "id": 100},
                {"name": "validation-pilot-csharp-quickstart-b", "id": 101},
            ]
        )
        self.assertEqual(
            links,
            {
                "python-quickstart-a": "https://github.com/example/repo/actions/runs/42/artifacts/100",
                "csharp-quickstart-b": "https://github.com/example/repo/actions/runs/42/artifacts/101",
            },
        )

    def test_excludes_manifest_and_combined_run_artifacts(self) -> None:
        links = self.run_script(
            [
                {"name": "validation-pilot-manifest", "id": 1},
                {"name": "validation-pilot-run-42-1", "id": 2},
                {"name": "validation-pilot-python-quickstart-a", "id": 100},
            ]
        )
        self.assertEqual(links, {"python-quickstart-a": "https://github.com/example/repo/actions/runs/42/artifacts/100"})

    def test_ignores_unrelated_artifacts(self) -> None:
        links = self.run_script([{"name": "some-other-artifact", "id": 5}])
        self.assertEqual(links, {})

    def test_ignores_malformed_lines(self) -> None:
        artifacts_file = self.root / "artifacts.ndjson"
        artifacts_file.write_text(
            json.dumps({"name": "validation-pilot-python-quickstart-a", "id": 100}) + "\nnot json\n{}\n",
            encoding="utf-8",
        )
        output = self.root / "artifact-links.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--artifacts-file",
                str(artifacts_file),
                "--repository",
                "example/repo",
                "--run-id",
                "42",
                "--run-attempt",
                "1",
                "--output",
                str(output),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads(output.read_text(encoding="utf-8")),
            {"python-quickstart-a": "https://github.com/example/repo/actions/runs/42/artifacts/100"},
        )


if __name__ == "__main__":
    unittest.main()
