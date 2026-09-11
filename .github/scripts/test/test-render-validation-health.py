#!/usr/bin/env python3
"""Fixture tests for render-validation-health.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "render-validation-health.py"
SHA = "0123456789abcdef0123456789abcdef01234567"
GENERATED_AT = "2026-08-07T20:30:00Z"
C_SHARP = "samples/csharp/quickstart/chat-with-agent"
PYTHON = "samples/python/quickstart/chat-with-agent"


class RendererTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for sample in (C_SHARP, PYTHON):
            (self.root / sample).mkdir(parents=True)
        self.config = self.root / "config.json"
        self.config.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "repository": "microsoft-foundry/foundry-samples",
                    "samples": [C_SHARP, PYTHON],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_renderer(
        self,
        results: dict | str | None = None,
        *,
        config: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        output = self.root / "dashboard.md"
        command = [
            sys.executable,
            str(SCRIPT),
            "--config",
            str(config or self.config),
            "--repo-root",
            str(self.root),
            "--output",
            str(output),
            "--source-sha",
            SHA,
            "--generated-at",
            GENERATED_AT,
        ]
        if results is not None:
            results_path = self.root / "results.json"
            if isinstance(results, str):
                results_path.write_text(results, encoding="utf-8")
            else:
                results_path.write_text(json.dumps(results), encoding="utf-8")
            command.extend(["--results", str(results_path)])
        completed = subprocess.run(command, capture_output=True, text=True)
        completed.output_path = output  # type: ignore[attr-defined]
        return completed

    def test_never_run_view_has_two_linked_rows(self) -> None:
        completed = self.run_renderer()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        markdown = completed.output_path.read_text(encoding="utf-8")
        self.assertEqual(markdown.count("| [`samples/"), 2)
        self.assertEqual(markdown.count("⚪ Never run"), 4)
        self.assertIn(
            f"https://github.com/microsoft-foundry/foundry-samples/tree/main/{C_SHARP}",
            markdown,
        )
        self.assertIn(
            f"https://github.com/microsoft-foundry/foundry-samples/tree/main/{PYTHON}",
            markdown,
        )
        self.assertLess(markdown.index(C_SHARP), markdown.index(PYTHON))

    def test_status_mapping_dates_and_evidence(self) -> None:
        results = {
            "schema_version": 1,
            "source_sha": SHA,
            "results": {
                C_SHARP: {
                    "l3": {
                        "status": "pass",
                        "run_at": "2026-08-06T01:02:03Z",
                        "evidence_url": (
                            "https://github.com/example/actions/runs/1"
                            "?name=a|b&label=<details open>"
                        ),
                    },
                    "l4": {
                        "status": "failure",
                        "run_at": "2026-08-06T02:03:04Z",
                    },
                },
                PYTHON: {
                    "l3": {
                        "status": "error",
                        "run_at": "2026-08-06T03:04:05Z",
                    }
                },
            },
        }
        completed = self.run_renderer(results)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        markdown = completed.output_path.read_text(encoding="utf-8")
        self.assertIn(
            (
                "[✅ Pass](https://github.com/example/actions/runs/1"
                "?name=a%7Cb&label=%3Cdetails%20open%3E)"
            ),
            markdown,
        )
        self.assertIn("❌ Failed", markdown)
        self.assertIn("⚠️ Warning", markdown)
        self.assertIn("⚪ Never run", markdown)
        self.assertIn("2026-08-06 01:02 UTC", markdown)
        self.assertIn("2026-08-06 02:03 UTC", markdown)
        self.assertIn("2026-08-06 03:04 UTC", markdown)

    def test_invalid_selected_status_fails(self) -> None:
        results = {
            "schema_version": 1,
            "source_sha": SHA,
            "results": {
                PYTHON: {
                    "l3": {
                        "status": "pending",
                        "run_at": "2026-08-06T03:04:05Z",
                    }
                }
            },
        }
        completed = self.run_renderer(results)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("status must be one of", completed.stderr)

    def test_non_string_selected_status_fails_cleanly(self) -> None:
        results = {
            "schema_version": 1,
            "source_sha": SHA,
            "results": {
                PYTHON: {
                    "l3": {
                        "status": [],
                        "run_at": "2026-08-06T03:04:05Z",
                    }
                }
            },
        }
        completed = self.run_renderer(results)
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertIn("status must be one of", completed.stderr)

    def test_malformed_evidence_url_fails_cleanly(self) -> None:
        results = {
            "schema_version": 1,
            "source_sha": SHA,
            "results": {
                PYTHON: {
                    "l3": {
                        "status": "pass",
                        "run_at": "2026-08-06T03:04:05Z",
                        "evidence_url": "http://[",
                    }
                }
            },
        }
        completed = self.run_renderer(results)
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertIn("absolute HTTP(S) URL", completed.stderr)

    def test_invalid_selected_timestamp_fails(self) -> None:
        results = {
            "schema_version": 1,
            "source_sha": SHA,
            "results": {
                PYTHON: {
                    "l3": {
                        "status": "pass",
                        "run_at": "yesterday",
                    }
                }
            },
        }
        completed = self.run_renderer(results)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("ISO-8601 UTC", completed.stderr)

    def test_unselected_results_are_ignored(self) -> None:
        results = {
            "schema_version": 1,
            "source_sha": SHA,
            "results": {
                "samples/rust/not-in-pilot": {
                    "l3": {"status": "not-a-real-status", "run_at": "not-a-date"}
                }
            },
        }
        completed = self.run_renderer(results)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_missing_configured_sample_fails(self) -> None:
        missing = self.root / PYTHON
        missing.rmdir()
        completed = self.run_renderer()
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("configured sample directory does not exist", completed.stderr)

    def test_malformed_results_json_fails(self) -> None:
        completed = self.run_renderer("{")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("results is not valid JSON", completed.stderr)


if __name__ == "__main__":
    unittest.main()
