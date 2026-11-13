"""Exercise the Entra-only downloader without contacting Azure."""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from azure.core.exceptions import HttpResponseError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import download_report


class DownloadReportTests(unittest.TestCase):
    def test_download_uses_caller_credential_and_verifies_bytes(self) -> None:
        content = b"# Report\nVerified content"
        digest = hashlib.sha256(content).hexdigest()
        url = "https://reports.blob.core.windows.net/reports/snapshot/report-v1.md"
        credential_scope = MagicMock()
        credential = credential_scope.__enter__.return_value
        blob_scope = MagicMock()
        blob = blob_scope.__enter__.return_value
        blob.download_blob.return_value.readall.return_value = content
        with (
            TemporaryDirectory() as directory,
            patch.object(
                download_report, "DefaultAzureCredential", return_value=credential_scope
            ),
            patch.object(
                download_report.BlobClient, "from_blob_url", return_value=blob_scope
            ) as create_blob,
        ):
            destination = Path(directory) / "report-v1.md"
            self.assertEqual(
                download_report.download_report(url, digest, destination), destination
            )
            self.assertEqual(destination.read_bytes(), content)
            create_blob.assert_called_once_with(url, credential=credential)
        credential_scope.__exit__.assert_called_once()
        blob_scope.__exit__.assert_called_once()

    def test_denied_download_does_not_create_a_file_or_fall_back_to_sas(self) -> None:
        with (
            TemporaryDirectory() as directory,
            patch.object(download_report, "DefaultAzureCredential"),
            patch.object(download_report.BlobClient, "from_blob_url") as create_blob,
        ):
            create_blob.return_value.__enter__.return_value.download_blob.side_effect = HttpResponseError(
                "denied"
            )
            destination = Path(directory) / "report.md"
            with self.assertRaises(HttpResponseError):
                download_report.download_report(
                    "https://reports.blob.core.windows.net/reports/snapshot/report.md",
                    "0" * 64,
                    destination,
                )
            self.assertFalse(destination.exists())

    def test_digest_mismatch_preserves_existing_destination(self) -> None:
        with (
            TemporaryDirectory() as directory,
            patch.object(download_report, "DefaultAzureCredential"),
            patch.object(download_report.BlobClient, "from_blob_url") as create_blob,
        ):
            create_blob.return_value.__enter__.return_value.download_blob.return_value.readall.return_value = b"changed"
            destination = Path(directory) / "report.md"
            destination.write_bytes(b"original")
            with self.assertRaisesRegex(ValueError, "SHA256"):
                download_report.download_report(
                    "https://reports.blob.core.windows.net/reports/snapshot/report.md",
                    "0" * 64,
                    destination,
                )
            self.assertEqual(destination.read_bytes(), b"original")

    def test_sas_urls_and_invalid_digests_are_rejected_before_authentication(
        self,
    ) -> None:
        for url, digest in (
            ("https://attacker.example/reports/report.md", "0" * 64),
            (
                "https://reports.blob.core.windows.net.attacker.example/reports/report.md",
                "0" * 64,
            ),
            (
                "https://reports.blob.core.windows.net/reports/report.md?sig=secret",
                "0" * 64,
            ),
            ("http://reports.blob.core.windows.net/reports/report.md", "0" * 64),
            (
                "https://user:password@reports.blob.core.windows.net/reports/report.md",
                "0" * 64,
            ),
            ("https://reports.blob.core.windows.net/reports/report.md", "invalid"),
        ):
            with (
                self.subTest(url=url),
                patch.object(download_report, "DefaultAzureCredential") as credential,
            ):
                with self.assertRaises(ValueError):
                    download_report.download_report(url, digest, Path("unused.md"))
                credential.assert_not_called()


if __name__ == "__main__":
    unittest.main()
