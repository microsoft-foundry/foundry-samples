#!/usr/bin/env python3
from __future__ import annotations

import json
import html
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse


SCRIPT = Path(__file__).resolve().parents[1] / "render-validation-dashboard.py"
SAMPLE_A = "samples/python/quickstart/a"
SAMPLE_B = "samples/csharp/quickstart/b"


class DashboardTests(unittest.TestCase):
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
        self.output = self.root / "index.html"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_dashboard(
        self,
        job_links: dict[str, str] | None = None,
        artifact_links: dict[str, str] | None = None,
        codeowners: str | None = None,
        codeowners_bytes: bytes | None = None,
    ) -> subprocess.CompletedProcess[str]:
        args = [
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
        ]
        if job_links is not None:
            job_links_path = self.root / "job-links.json"
            job_links_path.write_text(json.dumps(job_links), encoding="utf-8")
            args.extend(["--job-links", str(job_links_path)])
        if artifact_links is not None:
            artifact_links_path = self.root / "artifact-links.json"
            artifact_links_path.write_text(json.dumps(artifact_links), encoding="utf-8")
            args.extend(["--artifact-links", str(artifact_links_path)])
        if codeowners is not None:
            codeowners_path = self.root / "CODEOWNERS"
            codeowners_path.write_text(codeowners, encoding="utf-8")
            args.extend(["--codeowners", str(codeowners_path)])
        if codeowners_bytes is not None:
            codeowners_path = self.root / "CODEOWNERS"
            codeowners_path.write_bytes(codeowners_bytes)
            args.extend(["--codeowners", str(codeowners_path)])
        return subprocess.run(args, capture_output=True, text=True)

    def write_result(
        self,
        sample: str,
        outcome: str = "passed",
        diagnostic_text: str = "diagnostic\n",
        completed_stage: str = "build readiness validation",
        run_overrides: dict[str, object] | None = None,
    ) -> None:
        manifest = json.loads(self.expected.read_text(encoding="utf-8"))
        sample_definition = next(
            value for value in manifest["samples"] if value["path"] == sample
        )
        sample_id = sample_definition["id"]
        sample_dir = self.results / sample_id
        sample_dir.mkdir()
        (sample_dir / "diagnostics.log").write_text(diagnostic_text, encoding="utf-8")
        run: dict[str, object] = {
            "repository": "example/repo",
            "workflow": "validation pilot",
            "run_id": "42",
            "run_attempt": "1",
            "sha": "abcdef0",
            "ref": "refs/heads/main",
            "started_at": "2026-08-10T19:22:00Z",
        }
        if run_overrides:
            run.update(run_overrides)
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
                    "run": run,
                }
            ),
            encoding="utf-8",
        )

    def test_renders_every_manifest_sample_with_no_banner_when_complete(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        self.write_result(SAMPLE_B, "sample failure")
        completed = self.run_dashboard()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("<html", body)
        self.assertIn(SAMPLE_A, body)
        self.assertIn(SAMPLE_B, body)
        self.assertIn('<table id="results">', body)
        # Only one table now -- no more per-outcome sections.
        self.assertEqual(body.count("<table"), 1)
        self.assertIn("✅ Passed (1)", body)
        self.assertIn("❌ Sample failure (1)", body)
        self.assertIn('<details class="filter-panel">', body)
        self.assertIn('<summary><strong>Filters</strong><span id="filter-summary">Showing all samples</span></summary>', body)
        self.assertIn('data-filter-outcome="all"', body)
        self.assertIn('data-filter-outcome="passed"', body)
        self.assertIn("Workflow run", body)
        self.assertNotIn("not authoritative", body)
        # Status badges link to the workflow run so a reader can jump
        # straight from a row to the run that produced it.
        self.assertIn('<a href="https://github.com/example/repo/actions/runs/42"><span class="badge', body)
        # Column headers are click-to-sort.
        self.assertIn('data-sort-index="0"', body)
        self.assertIn('data-sort-index="2"', body)
        self.assertIn("<script>", body)
        self.assertIn(">Validation<", body)
        self.assertIn(">Build check</td>", body)
        self.assertIn('title="build readiness validation"', body)
        self.assertIn('data-validation="build readiness validation"', body)

    def test_missing_result_is_shown_and_still_exits_zero_with_banner(self) -> None:
        # Sample "b" is in the manifest (i.e. discovery found its sample.yaml,
        # exactly like a newly added sample would be) but never produced a
        # result -- e.g. the fleet run failed to complete. The dashboard must
        # still publish (exit 0) so a broken run doesn't leave a stale page
        # looking like current status, and must flag itself as unauthoritative.
        self.write_result(SAMPLE_A, "passed")
        completed = self.run_dashboard()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("banner banner-incomplete", body)
        self.assertIn("most recent validation run", body)
        self.assertIn("not authoritative", body)
        self.assertIn(SAMPLE_B, body)

    def test_malformed_artifact_is_shown_and_still_exits_zero(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        sample_dir = self.results / "b"
        sample_dir.mkdir()
        (sample_dir / "sample-result.json").write_text("not json", encoding="utf-8")
        completed = self.run_dashboard()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("banner banner-incomplete", body)

    def test_multiple_orphaned_artifacts_render_as_distinct_rows(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        self.write_result(SAMPLE_B, "sample failure")
        for directory in ("bad-one", "bad-two"):
            bad = self.results / directory
            bad.mkdir()
            (bad / "sample-result.json").write_text("{", encoding="utf-8")

        completed = self.run_dashboard()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("invalid artifact: bad-one/sample-result.json", body)
        self.assertIn("invalid artifact: bad-two/sample-result.json", body)
        self.assertIn(
            'data-filter-language="reporting" class="filter-btn" aria-pressed="false">reporting (2)</button>',
            body,
        )

    def test_diagnostic_text_never_appears_on_the_public_page(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        self.write_result(
            SAMPLE_B,
            "sample failure",
            diagnostic_text="FAIL: super-secret-marker-should-not-be-published\n",
        )
        completed = self.run_dashboard()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertNotIn("super-secret-marker-should-not-be-published", body)

    def test_html_special_characters_in_sample_fields_are_escaped(self) -> None:
        manifest = json.loads(self.expected.read_text(encoding="utf-8"))
        manifest["samples"][1]["path"] = 'samples/csharp/quickstart/<script>alert(1)</script>'
        self.expected.write_text(json.dumps(manifest), encoding="utf-8")
        self.write_result(SAMPLE_A, "passed")
        self.write_result(
            'samples/csharp/quickstart/<script>alert(1)</script>',
            "sample failure",
            completed_stage='"><img src=x onerror=alert(1)>',
        )
        completed = self.run_dashboard()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertNotIn("<img src=x onerror=alert(1)>", body)
        self.assertIn("&lt;script&gt;", body)

    def test_sample_links_to_validated_commit(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        self.write_result(SAMPLE_B, "sample failure")
        completed = self.run_dashboard()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("https://github.com/example/repo/tree/abcdef0", body)
        self.assertIn("https://github.com/example/repo/commit/abcdef0", body)

    def test_status_links_to_per_sample_job_when_job_links_provided(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        self.write_result(SAMPLE_B, "sample failure")
        completed = self.run_dashboard(
            job_links={
                "b": "https://github.com/example/repo/actions/runs/42/job/999",
            }
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        # Sample "b" has a specific job link -- its badge should go straight
        # to that job page, not the generic run-overview link.
        self.assertIn(
            '<a href="https://github.com/example/repo/actions/runs/42/job/999">'
            '<span class="badge failed">',
            body,
        )
        # Sample "a" has no entry in the map, so it falls back to the run link.
        self.assertIn(
            '<a href="https://github.com/example/repo/actions/runs/42">'
            '<span class="badge passed">',
            body,
        )

    def test_job_links_with_wrong_repository_are_ignored(self) -> None:
        # A job-links entry that doesn't match this run's own repository
        # must never be trusted -- fall back to the run link instead of
        # linking off-run.
        self.write_result(SAMPLE_A, "passed")
        completed = self.run_dashboard(
            job_links={"a": "https://github.com/some-other/repo/actions/runs/1/job/1"}
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertNotIn("some-other/repo", body)
        self.assertIn(
            '<a href="https://github.com/example/repo/actions/runs/42">'
            '<span class="badge passed">',
            body,
        )

    def test_artifact_column_links_when_provided_and_shows_placeholder_otherwise(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        self.write_result(SAMPLE_B, "sample failure")
        completed = self.run_dashboard(
            artifact_links={"a": "https://github.com/example/repo/actions/runs/42/artifacts/555"}
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn(
            '<a href="https://github.com/example/repo/actions/runs/42/artifacts/555" class="artifact-link">',
            body,
        )
        self.assertIn('class="icon-download"', body)
        self.assertIn(">Diagnostics</a>", body)
        # Sample "b" has no artifact link -- shown as a plain placeholder, not a broken link.
        self.assertIn(">—</td>", body)
        self.assertIn(">Artifact<", body)

    def test_artifact_links_with_wrong_repository_are_ignored(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        completed = self.run_dashboard(
            artifact_links={"a": "https://github.com/some-other/repo/actions/runs/1/artifacts/1"}
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertNotIn("some-other/repo", body)
        self.assertNotIn("Diagnostics</a>", body)

    def test_result_with_non_string_run_repository_renders_as_error_row(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        self.write_result(SAMPLE_B, "sample failure", run_overrides={"repository": ["example/repo"]})
        completed = self.run_dashboard(
            job_links={"b": "https://github.com/example/repo/actions/runs/42/job/999"},
            artifact_links={"b": "https://github.com/example/repo/actions/runs/42/artifacts/555"},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn("banner banner-incomplete", body)
        self.assertIn("⚠️ Infrastructure/error", body)
        self.assertNotIn("Fix with Copilot", body)

    def test_failed_sample_offers_prefilled_copilot_issue(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        self.write_result(SAMPLE_B, "sample failure", completed_stage="live-service validation")
        completed = self.run_dashboard(
            job_links={"b": "https://github.com/example/repo/actions/runs/42/job/999"},
            artifact_links={"b": "https://github.com/example/repo/actions/runs/42/artifacts/555"},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        match = re.search(r'<a href="([^"]+)" class="copilot-link">Fix with Copilot ↗</a>', body)
        self.assertIsNotNone(match)
        issue_url = html.unescape(match.group(1))
        parsed = urlparse(issue_url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.path, "/example/repo/issues/new")
        self.assertEqual(query["assignees"], ["copilot-swe-agent[bot]"])
        self.assertEqual(query["title"], [f"Fix validation failure: {SAMPLE_B}"])
        self.assertIn(SAMPLE_B, query["body"][0])
        self.assertIn("Live run", query["body"][0])
        self.assertIn("https://github.com/example/repo/actions/runs/42/job/999", query["body"][0])
        self.assertIn("https://github.com/example/repo/actions/runs/42/artifacts/555", query["body"][0])

    def test_passed_sample_does_not_offer_copilot_issue(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        completed = self.run_dashboard()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertNotIn("Fix with Copilot", body)

    def test_language_filter_row_lists_each_distinct_language(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        self.write_result(SAMPLE_B, "sample failure")
        completed = self.run_dashboard()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn('<div id="language-filters" class="filters">', body)
        self.assertIn('data-filter-language="all" class="active" aria-pressed="true">All (2)</button>', body)
        self.assertIn('data-filter-language="python" class="filter-btn" aria-pressed="false">python (1)</button>', body)
        self.assertIn('data-filter-language="csharp" class="filter-btn" aria-pressed="false">csharp (1)</button>', body)
        # Rows carry a data-language attribute so the client-side filter can match on it.
        self.assertIn('data-language="python"', body)
        self.assertIn('data-language="csharp"', body)

    def test_validation_filter_row_lists_each_distinct_validation_label(self) -> None:
        self.write_result(SAMPLE_A, "passed", completed_stage="build readiness validation")
        self.write_result(SAMPLE_B, "sample failure", completed_stage="live-service validation")
        completed = self.run_dashboard()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn('<div class="filter-group"><strong>Validation</strong>', body)
        self.assertIn('data-filter-validation="all" class="active" aria-pressed="true">All (2)</button>', body)
        self.assertIn(
            'data-filter-validation="build readiness validation" class="filter-btn" aria-pressed="false">Build check (1)</button>',
            body,
        )
        self.assertIn(
            'data-filter-validation="live-service validation" class="filter-btn" aria-pressed="false">Live run (1)</button>',
            body,
        )
        self.assertIn('data-validation="build readiness validation"', body)
        self.assertIn('data-validation="live-service validation"', body)
        self.assertIn('data: "validation", label: "Validation"', body)
        self.assertIn('summary.textContent = "Showing " + visibleCount + " of " + total + " samples"', body)

    def test_codeowner_column_combines_directory_owner_and_nested_file_owner(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        self.write_result(SAMPLE_B, "sample failure")
        codeowners = (
            "# comment line, ignored\n"
            "\n"
            f"/{SAMPLE_A}/ @team-python\n"
            # A file-specific entry nested inside sample b's directory (e.g. a docs
            # team owning one file referenced from docs) is a real reviewer for
            # that sample too -- it should be unioned in, not discarded, even
            # though sample b has no directory-level CODEOWNERS entry of its own.
            f"/{SAMPLE_B}/inner_file.py @some-doc-owner\n"
        )
        completed = self.run_dashboard(codeowners=codeowners)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn(">Codeowner<", body)
        self.assertIn('data-codeowner="@team-python"', body)
        self.assertIn(">@team-python</td>", body)
        # Sample b has no directory-level entry, but does have a nested file
        # owner, so it shows that owner rather than falling back to "—".
        self.assertIn('data-codeowner="@some-doc-owner"', body)
        self.assertIn(">@some-doc-owner</td>", body)
        self.assertIn('data-filter-codeowner="all" class="active" aria-pressed="true">All (2)</button>', body)
        self.assertIn('data-filter-codeowner="@team-python" class="filter-btn" aria-pressed="false">@team-python (1)</button>', body)
        self.assertIn('data-filter-codeowner="@some-doc-owner" class="filter-btn" aria-pressed="false">@some-doc-owner (1)</button>', body)
        self.assertNotIn("Unowned (", body)

    def test_codeowner_directory_owner_and_nested_file_owner_are_deduplicated(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        codeowners = f"/{SAMPLE_A}/ @team-python\n/{SAMPLE_A}/inner_file.py @team-python\n"
        completed = self.run_dashboard(codeowners=codeowners)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn(">@team-python</td>", body)
        # The nested entry names the same owner as the directory -- it must not
        # be listed twice.
        self.assertNotIn("@team-python, @team-python", body)

    def test_repeated_primary_codeowner_is_deduplicated(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        codeowners = f"/{SAMPLE_A}/ @team-python @team-python\n"
        completed = self.run_dashboard(codeowners=codeowners)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn(">@team-python</td>", body)
        self.assertNotIn("@team-python, @team-python", body)
        self.assertIn('data-filter-codeowner="@team-python" class="filter-btn" aria-pressed="false">@team-python (1)</button>', body)

    def test_codeowners_last_matching_entry_wins(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        codeowners = f"/{SAMPLE_A}/ @team-general\n/{SAMPLE_A}/ @team-specific\n"
        completed = self.run_dashboard(codeowners=codeowners)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn(">@team-specific</td>", body)
        self.assertNotIn(">@team-general</td>", body)

    def test_missing_codeowners_file_falls_back_to_unowned(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        completed = self.run_dashboard()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn(">—</td>", body)

    def test_corrupt_codeowners_file_falls_back_to_unowned(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        completed = self.run_dashboard(codeowners_bytes=b"\xff\xfe\x00")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn(">—</td>", body)

    def test_sample_with_no_matching_codeowners_entry_counts_as_unowned(self) -> None:
        self.write_result(SAMPLE_A, "passed")
        self.write_result(SAMPLE_B, "sample failure")
        completed = self.run_dashboard(codeowners=f"/{SAMPLE_A}/ @team-python\n")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        body = self.output.read_text(encoding="utf-8")
        self.assertIn('data-codeowner=""', body)
        self.assertIn('data-filter-codeowner="" class="filter-btn" aria-pressed="false">Unowned (1)</button>', body)


if __name__ == "__main__":
    unittest.main()
