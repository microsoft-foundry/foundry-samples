#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "render-validation-report.py"
SAMPLE_A = "samples/python/quickstart/a"
SAMPLE_B = "samples/csharp/quickstart/b"


class ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.results = self.root / "results"
        self.results.mkdir()
        self.expected = self.root / "expected.json"
        self.expected.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "samples": [
                        {"id": "a", "path": SAMPLE_A, "language": "python", "shape": "quickstart"},
                        {"id": "b", "path": SAMPLE_B, "language": "csharp", "shape": "quickstart"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.output = self.root / "summary.md"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_report(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--results-dir",
                str(self.results),
                "--expected-samples",
                str(self.expected),
                "--output",
                str(self.output),
                "--run-url",
                "https://github.com/example/repo/actions/runs/42",
            ],
            capture_output=True,
            text=True,
        )

    def write_result(
        self,
        sample: str,
        outcome: str = "passed",
        diagnostic_text: str = "diagnostic\n",
        completed_stage: str = "build readiness validation",
    ) -> None:
        manifest = json.loads(self.expected.read_text(encoding="utf-8"))
        sample_definition = next(
            value for value in manifest["samples"] if value["path"] == sample
        )
        sample_id = sample_definition["id"]
        sample_dir = self.results / sample_id
        sample_dir.mkdir()
        (sample_dir / "diagnostics.log").write_text(diagnostic_text, encoding="utf-8")
        (sample_dir / "sample-result.json").write_text(
            json.dumps(
                {
                    "schema_version": manifest["schema_version"],
                    "sample": sample_definition,
                    "outcome": outcome,
                    "completed_stage": completed_stage,
                    "duration_seconds": 12.5,
                    "diagnostic_reference": "diagnostics.log",
                    "artifact_reference": f"validation-pilot-{sample_id}",
                    "completed_at": "2026-08-10T19:22:33Z",
                    "run": {
                        "repository": "example/repo",
                        "workflow": "validation pilot",
                        "run_id": "42",
                        "run_attempt": "1",
                        "sha": "abcdef0",
                        "ref": "refs/heads/main",
                        "started_at": "2026-08-10T19:22:00Z",
                    },
                }
            ),
            encoding="utf-8",
        )

    def test_renders_all_outcomes_and_run_freshness(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        self.write_result(SAMPLE_B, "sample failure")
        completed = self.run_report()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("✅ Passed", body)
        self.assertIn("❌ Sample failure", body)
        self.assertIn("Workflow run", body)
        self.assertIn("Sample failures (1)", body)
        self.assertIn("Passed (1)", body)
        self.assertIn("https://github.com/example/repo/tree/abcdef0", body)
        self.assertEqual(body.count("`samples/"), 2)

    def test_renders_skip_reason_and_sanitized_truncated_excerpt(self) -> None:
        self.expected.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "samples": [
                        {"id": "a", "path": SAMPLE_A, "language": "python", "shape": "quickstart"},
                        {"id": "b", "path": SAMPLE_B, "language": "csharp", "shape": "quickstart"},
                        {"id": "c", "path": "samples/rust/quickstart/c", "language": "rust", "shape": "quickstart"},
                        {"id": "d", "path": "samples/typescript/quickstart/d", "language": "typescript", "shape": "quickstart"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.write_result(SAMPLE_A, "passed")
        self.write_result(SAMPLE_B, "sample failure", "FAIL: password=secret " + ("x" * 300))
        self.write_result("samples/rust/quickstart/c", "skipped/not-completed", "skipped: unsupported language: rust\n")
        self.write_result("samples/typescript/quickstart/d", "infrastructure/error", "runner error: validator unavailable\n")
        completed = self.run_report()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("Sample failures (1)", body)
        self.assertIn("Infrastructure/errors (1)", body)
        self.assertIn("Skipped/not-completed (1)", body)
        self.assertIn("unsupported language: rust", body)
        self.assertIn("password=[redacted]", body)
        self.assertNotIn("password=secret", body)
        self.assertIn("…", body)

    def test_failure_excerpt_does_not_select_earlier_passing_verdict(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        self.write_result(
            SAMPLE_B,
            "sample failure",
            "\n".join(
                [
                    "PASS: L3 validation",
                    "verdict=pass",
                    "ModuleNotFoundError: No module named 'httpx'",
                    "FAIL: L4 command reported sample failure",
                    "verdict=fail",
                ]
            ),
        )
        completed = self.run_report()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("FAIL: L4 command reported sample failure", body)
        self.assertNotIn("`verdict=pass`", body)

    def test_missing_expected_artifact_publishes_partial_summary_and_fails(self) -> None:
        self.write_result(SAMPLE_A)
        completed = self.run_report()
        self.assertEqual(completed.returncode, 1)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("expected result artifact is missing", body)
        self.assertIn("⚠️ Infrastructure/error", body)

    def test_schema_one_stage_names_are_normalized_for_historical_artifacts(self) -> None:
        manifest = json.loads(self.expected.read_text(encoding="utf-8"))
        manifest["schema_version"] = 1
        self.expected.write_text(json.dumps(manifest), encoding="utf-8")
        self.write_result(SAMPLE_A, completed_stage="L3 validation")
        self.write_result(SAMPLE_B, completed_stage="L4 validation")
        completed = self.run_report()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("build readiness validation", body)
        self.assertIn("live-service validation", body)
        self.assertNotIn("L3 validation", body)
        self.assertNotIn("L4 validation", body)

    def test_malformed_artifact_publishes_error_row_and_fails(self) -> None:
        bad = self.results / "bad"
        bad.mkdir()
        (bad / "sample-result.json").write_text("{", encoding="utf-8")
        completed = self.run_report()
        self.assertEqual(completed.returncode, 1)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("invalid artifact: bad/sample-result.json", body)
        self.assertIn("⚠️ Infrastructure/error", body)

    def test_multiple_orphaned_artifacts_keep_unique_identities(self) -> None:
        for directory in ("bad-one", "bad-two"):
            bad = self.results / directory
            bad.mkdir()
            (bad / "sample-result.json").write_text("{", encoding="utf-8")

        completed = self.run_report()

        self.assertEqual(completed.returncode, 1)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("invalid artifact: bad-one/sample-result.json", body)
        self.assertIn("invalid artifact: bad-two/sample-result.json", body)

    def test_corrupt_utf8_artifact_publishes_error_row_and_fails(self) -> None:
        bad = self.results / "bad-utf8"
        bad.mkdir()
        (bad / "sample-result.json").write_bytes(b"\xff\xfe\x00")

        completed = self.run_report()

        self.assertEqual(completed.returncode, 1)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("invalid artifact: bad-utf8/sample-result.json", body)
        self.assertIn("not valid UTF-8", body)

    def test_orphaned_artifact_with_run_metadata_does_not_link_to_synthetic_path(self) -> None:
        (self.results / "run-metadata.json").write_text(
            json.dumps(
                {
                    "repository": "example/repo",
                    "workflow": "validation pilot",
                    "run_id": "42",
                    "run_attempt": "1",
                    "sha": "abcdef0",
                    "ref": "refs/heads/main",
                    "started_at": "2026-08-10T19:22:00Z",
                }
            ),
            encoding="utf-8",
        )
        bad = self.results / "bad"
        bad.mkdir()
        (bad / "sample-result.json").write_text("{", encoding="utf-8")

        completed = self.run_report()

        self.assertEqual(completed.returncode, 1)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("`<invalid artifact: bad/sample-result.json>`", body)
        self.assertNotIn("tree/abcdef0/%3Cinvalid%20artifact", body)

    def test_corrupt_run_metadata_falls_back_to_empty_metadata(self) -> None:
        (self.results / "run-metadata.json").write_bytes(b"\xff\xfe\x00")
        self.write_result(SAMPLE_A)

        completed = self.run_report()

        self.assertEqual(completed.returncode, 1)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("expected result artifact is missing for b", body)
        self.assertNotIn("UnicodeDecodeError", completed.stderr)

    def test_invalid_result_for_a_known_sample_does_not_also_report_it_missing(self) -> None:
        # A result artifact that identifies a real expected sample but fails
        # validation for some other reason (here, an unsupported outcome)
        # should produce exactly one error row for that sample -- not both an
        # "invalid artifact" row and a separate "missing" row for the same
        # sample.
        manifest = json.loads(self.expected.read_text(encoding="utf-8"))
        sample_definition = next(value for value in manifest["samples"] if value["path"] == SAMPLE_A)
        sample_dir = self.results / sample_definition["id"]
        sample_dir.mkdir()
        (sample_dir / "diagnostics.log").write_text("diagnostic\n", encoding="utf-8")
        (sample_dir / "sample-result.json").write_text(
            json.dumps(
                {
                    "schema_version": manifest["schema_version"],
                    "sample": sample_definition,
                    "outcome": "not-a-real-outcome",
                    "completed_stage": "build readiness validation",
                    "duration_seconds": 12.5,
                    "diagnostic_reference": "diagnostics.log",
                    "artifact_reference": f"validation-pilot-{sample_definition['id']}",
                    "completed_at": "2026-08-10T19:22:33Z",
                    "run": {
                        "repository": "example/repo",
                        "workflow": "validation pilot",
                        "run_id": "42",
                        "run_attempt": "1",
                        "sha": "abcdef0",
                        "ref": "refs/heads/main",
                        "started_at": "2026-08-10T19:22:00Z",
                    },
                }
            ),
            encoding="utf-8",
        )
        self.write_result(SAMPLE_B)
        completed = self.run_report()
        self.assertEqual(completed.returncode, 1)
        body = self.output.read_text(encoding="utf-8")
        self.assertEqual(body.count(SAMPLE_A), 1, body)
        self.assertNotIn("expected result artifact is missing for a", body)

    def test_outcome_of_wrong_json_type_is_reported_as_error_not_a_crash(self) -> None:
        # A malformed artifact whose outcome is e.g. a list rather than a
        # string must not crash normalization with an uncaught TypeError --
        # it should become an infrastructure/error row like any other
        # malformed artifact.
        manifest = json.loads(self.expected.read_text(encoding="utf-8"))
        sample_definition = next(value for value in manifest["samples"] if value["path"] == SAMPLE_A)
        sample_dir = self.results / sample_definition["id"]
        sample_dir.mkdir()
        (sample_dir / "diagnostics.log").write_text("diagnostic\n", encoding="utf-8")
        (sample_dir / "sample-result.json").write_text(
            json.dumps(
                {
                    "schema_version": manifest["schema_version"],
                    "sample": sample_definition,
                    "outcome": ["passed"],
                    "completed_stage": "build readiness validation",
                    "duration_seconds": 12.5,
                    "diagnostic_reference": "diagnostics.log",
                    "artifact_reference": f"validation-pilot-{sample_definition['id']}",
                    "completed_at": "2026-08-10T19:22:33Z",
                    "run": {
                        "repository": "example/repo",
                        "workflow": "validation pilot",
                        "run_id": "42",
                        "run_attempt": "1",
                        "sha": "abcdef0",
                        "ref": "refs/heads/main",
                        "started_at": "2026-08-10T19:22:00Z",
                    },
                }
            ),
            encoding="utf-8",
        )
        self.write_result(SAMPLE_B)
        completed = self.run_report()
        self.assertEqual(completed.returncode, 1)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("⚠️ Infrastructure/error", body)

    def test_non_finite_duration_is_reported_as_error_not_valid_result(self) -> None:
        manifest = json.loads(self.expected.read_text(encoding="utf-8"))
        sample_definition = next(value for value in manifest["samples"] if value["path"] == SAMPLE_A)
        sample_dir = self.results / sample_definition["id"]
        sample_dir.mkdir()
        (sample_dir / "diagnostics.log").write_text("diagnostic\n", encoding="utf-8")
        (sample_dir / "sample-result.json").write_text(
            json.dumps(
                {
                    "schema_version": manifest["schema_version"],
                    "sample": sample_definition,
                    "outcome": "passed",
                    "completed_stage": "build readiness validation",
                    "duration_seconds": float("nan"),
                    "diagnostic_reference": "diagnostics.log",
                    "artifact_reference": f"validation-pilot-{sample_definition['id']}",
                    "completed_at": "2026-08-10T19:22:33Z",
                    "run": {
                        "repository": "example/repo",
                        "workflow": "validation pilot",
                        "run_id": "42",
                        "run_attempt": "1",
                        "sha": "abcdef0",
                        "ref": "refs/heads/main",
                        "started_at": "2026-08-10T19:22:00Z",
                    },
                }
            ),
            encoding="utf-8",
        )
        self.write_result(SAMPLE_B)

        completed = self.run_report()

        self.assertEqual(completed.returncode, 1)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("duration_seconds must be a finite non-negative number", body)
        self.assertNotIn("nans", body)

    def test_result_schema_must_match_manifest_schema(self) -> None:
        self.write_result(SAMPLE_A)
        result_path = self.results / "a" / "sample-result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["schema_version"] = 1
        result_path.write_text(json.dumps(result), encoding="utf-8")
        self.write_result(SAMPLE_B)

        completed = self.run_report()

        self.assertEqual(completed.returncode, 1)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("result schema_version 1 does not match manifest schema_version 2", body)

    def test_manifest_schema_version_boolean_is_rejected(self) -> None:
        manifest = json.loads(self.expected.read_text(encoding="utf-8"))
        manifest["schema_version"] = True
        self.expected.write_text(json.dumps(manifest), encoding="utf-8")

        completed = self.run_report()

        self.assertEqual(completed.returncode, 1)
        self.assertIn("sample manifest must contain a non-empty samples array", completed.stderr)

    def test_result_schema_version_float_is_rejected(self) -> None:
        self.write_result(SAMPLE_A)
        self.write_result(SAMPLE_B)
        result_path = self.results / "a" / "sample-result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["schema_version"] = 2.0
        result_path.write_text(json.dumps(result), encoding="utf-8")

        completed = self.run_report()

        self.assertEqual(completed.returncode, 1)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("result must be a supported schema object", body)

    def test_all_samples_missing_still_links_validated_commit_from_run_metadata(self) -> None:
        # When every expected sample is missing, there is no per-sample `run`
        # block to draw the validated-commit link from -- but the
        # completeness job always persists a run-metadata.json alongside the
        # per-sample result directories, and that should be used as a
        # fallback so the report doesn't lose run/commit context entirely.
        (self.results / "run-metadata.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "repository": "example/repo",
                    "workflow": "validation pilot",
                    "run_id": "42",
                    "run_attempt": "1",
                    "sha": "abcdef0",
                    "ref": "refs/heads/main",
                    "completed_at": "2026-08-10T19:22:33Z",
                }
            ),
            encoding="utf-8",
        )
        completed = self.run_report()
        self.assertEqual(completed.returncode, 1)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("abcdef0", body)

    def test_run_shape_error_reports_missing_and_extra_fields(self) -> None:
        self.write_result(SAMPLE_A)
        result_path = self.results / "a" / "sample-result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        del result["run"]["ref"]
        result["run"]["unexpected"] = "value"
        result_path.write_text(json.dumps(result), encoding="utf-8")

        completed = self.run_report()

        self.assertEqual(completed.returncode, 1)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("missing fields: ['ref']", body)
        self.assertIn("extra fields: ['unexpected']", body)


if __name__ == "__main__":
    unittest.main()
