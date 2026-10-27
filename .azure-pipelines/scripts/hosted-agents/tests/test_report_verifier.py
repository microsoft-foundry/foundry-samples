"""Exercise the Deep Research cloud verifier with external I/O simulated."""

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[4]
SOURCE = (
    ROOT
    / ".azure-pipelines/hosted-agent-tests/python/langgraph/responses/11-deep-agents/verify_reports.py"
)
SPEC = importlib.util.spec_from_file_location("research_report_verifier", SOURCE)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
ORIGINAL = (
    "# LangGraph Checkpoints\nOriginal evidence.\n" + module.SOURCE_URL
).encode()
REVISED = (
    ORIGINAL + b"\n## Recovery Limitations\nSaved state is not in-flight recovery."
)


class ReportVerifierTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(
            os.environ,
            {
                "AZURE_STORAGE_ACCOUNT_NAME": "reports",
                "AZURE_STORAGE_CONTAINER_NAME": "reports",
                "TF_BUILD": "false",
            },
        )
        environment.start()
        self.addCleanup(environment.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.publications = []
        self.bodies = {}
        for turn, name, content in [
            (1, "report-v1.md", ORIGINAL),
            (2, "report-v2.md", REVISED),
            (3, "report-v1.md", ORIGINAL),
        ]:
            publication = {
                "file_path": "/" + name,
                "download_url": f"https://reports.blob.core.windows.net/reports/{turn:032x}/{name}?sp=r&spr=https&sig=test",
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            self.publications.append(publication)
            self.bodies[publication["download_url"]] = content
            self.write_turn(turn, publication)

    def write_turn(self, turn, publication):
        name = "report-v2.md" if turn == 2 else "report-v1.md"
        response = {
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "name": "publish_report",
                    "call_id": "publication",
                    "arguments": json.dumps({"report_name": name}),
                },
                {
                    "type": "function_call_output",
                    "call_id": "publication",
                    "output": json.dumps(publication)
                    if isinstance(publication, dict)
                    else publication,
                },
            ],
        }
        (self.root / f"turn-{turn}-raw.txt").write_text(
            json.dumps(response), encoding="utf-8"
        )

    def verify(self, downloader=None, remover=None, role_remover=None):
        return module.verify_reports(
            self.root,
            [1, 2, 3],
            downloader=downloader
            or (lambda publication: self.bodies[publication["download_url"]]),
            remover=remover or MagicMock(),
            role_remover=role_remover or MagicMock(),
        )

    def test_success_checks_three_versions_rechecks_original_and_cleans_only_observed_exports(
        self,
    ):
        downloader = MagicMock(
            side_effect=lambda publication: self.bodies[publication["download_url"]]
        )
        remover = MagicMock()
        role_remover = MagicMock()
        self.verify(downloader, remover, role_remover)
        self.assertEqual(downloader.call_count, 4)
        self.assertEqual(remover.call_count, 3)
        self.assertEqual(
            [call.args for call in remover.call_args_list],
            [
                (
                    "reports",
                    "reports",
                    f"{turn:032x}/report-v{2 if turn == 2 else 1}.md",
                )
                for turn in [1, 2, 3]
            ],
        )
        role_remover.assert_called_once_with()

    def test_handled_publication_errors_cannot_pass(self):
        for turn in [1, 2, 3]:
            self.write_turn(turn, "Publishing failed. No download link was created.")
        with self.assertRaisesRegex(module.VerificationError, "publication_missing"):
            self.verify()

    def test_changed_original_and_changed_old_snapshot_fail(self):
        self.bodies[self.publications[2]["download_url"]] = ORIGINAL + b"changed"
        with self.assertRaisesRegex(
            module.VerificationError, "original_report_changed"
        ):
            self.verify()
        self.bodies[self.publications[2]["download_url"]] = ORIGINAL
        downloader = MagicMock(
            side_effect=[ORIGINAL, REVISED, ORIGINAL, ORIGINAL + b"changed"]
        )
        with self.assertRaisesRegex(
            module.VerificationError, "original_snapshot_changed"
        ):
            self.verify(downloader)

    def test_missing_revision_or_sources_fail(self):
        for content, reason in [
            (ORIGINAL, "revision_missing"),
            (b"## Recovery Limitations\nNo sources", "source_citation_missing"),
        ]:
            with self.subTest(reason=reason):
                self.bodies[self.publications[1]["download_url"]] = content
                with self.assertRaisesRegex(module.VerificationError, reason):
                    self.verify()

    def test_untrusted_or_write_capable_urls_are_rejected_before_download_or_cleanup(
        self,
    ):
        original_url = self.publications[0]["download_url"]
        for url in [
            original_url.replace("reports.blob.core.windows.net", "attacker.invalid"),
            original_url.replace("https://", "http://"),
            original_url.replace("sp=r&", "sp=rw&"),
            original_url.replace("/reports/", "/another-container/"),
            original_url.replace(
                "reports.blob.core.windows.net", "reports.blob.core.windows.net:8443"
            ),
        ]:
            with self.subTest(url=url):
                publication = dict(self.publications[0], download_url=url)
                self.write_turn(1, publication)
                downloader = MagicMock()
                remover = MagicMock()
                with self.assertRaisesRegex(
                    module.VerificationError, "unsafe_publication"
                ):
                    self.verify(downloader, remover)
                downloader.assert_not_called()
                remover.assert_not_called()

    def test_partial_turn_evidence_still_cleans_observed_exports(self):
        (self.root / "turn-2-raw.txt").unlink()
        (self.root / "turn-3-raw.txt").unlink()
        remover = MagicMock()
        with self.assertRaisesRegex(module.VerificationError, "incomplete_turns"):
            self.verify(remover=remover)
        remover.assert_called_once_with("reports", "reports", f"{1:032x}/report-v1.md")

    def test_cleanup_failure_is_not_reported_as_success_and_other_cleanup_continues(
        self,
    ):
        remover = MagicMock(side_effect=[OSError("denied"), None, None])
        roles = MagicMock()
        with self.assertRaisesRegex(module.VerificationError, "cleanup_failed"):
            self.verify(remover=remover, role_remover=roles)
        self.assertEqual(remover.call_count, 3)
        roles.assert_called_once_with()

    def test_real_download_boundary_checks_digest_attachment_and_size(self):
        publication = self.publications[0]
        response = MagicMock()
        response.headers = {
            "Content-Disposition": 'attachment; filename="report-v1.md"'
        }
        response.read.return_value = ORIGINAL
        response.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = response
        with patch.object(module, "build_opener", return_value=opener):
            self.assertEqual(module.download_report(publication), ORIGINAL)
            response.read.return_value = ORIGINAL + b"tampered"
            with self.assertRaisesRegex(
                module.VerificationError, "report_digest_mismatch"
            ):
                module.download_report(publication)
            response.headers = {
                "Content-Disposition": 'attachment; filename="other.md"'
            }
            with self.assertRaisesRegex(
                module.VerificationError, "attachment_name_mismatch"
            ):
                module.download_report(publication)
            response.headers = {
                "Content-Disposition": 'attachment; filename="report-v1.md"'
            }
            response.read.return_value = b"x" * (module.MAX_REPORT_BYTES + 1)
            with self.assertRaisesRegex(module.VerificationError, "report_too_large"):
                module.download_report(publication)

    def test_repeated_evaluation_is_cached_but_changed_evidence_is_reverified(self):
        arguments = [
            "verify_reports.py",
            "--evidence-dir",
            str(self.root),
            "--turns",
            "1",
            "2",
            "3",
        ]
        with patch.object(sys, "argv", arguments), patch.object(
            module, "verify_reports"
        ) as verify:
            self.assertEqual(module.main(), 0)
            self.assertEqual(module.main(), 0)
            self.assertEqual(verify.call_count, 1)
            self.write_turn(3, "Publishing failed")
            self.assertEqual(module.main(), 0)
            self.assertEqual(verify.call_count, 2)


if __name__ == "__main__":
    unittest.main()
