"""Offline regressions; simulated Blob calls do not verify Azure permissions."""

from __future__ import annotations

import copy
import hashlib
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

from azure.core.exceptions import (
    HttpResponseError,
    ServiceRequestError,
    ServiceResponseError,
)
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import report_export

REPORT = "# Original report\nEvidence [1].\n\n[1] https://example.org/source"
REVISED = REPORT + "\n\n## Recovery limitations\nSaved state is not in-flight work."


class ReportExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(
            os.environ,
            {
                "REPORT_STORAGE_ACCOUNT_URL": "https://reports.blob.core.windows.net",
                "REPORT_STORAGE_CONTAINER": "reports",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.storage = MagicMock()
        self.storage.__enter__.return_value = self.storage
        self.storage.account_name = "reports"
        self.blobs: list[MagicMock] = []

        def create_blob(container: str, name: str) -> MagicMock:
            blob = MagicMock(
                url=f"https://reports.blob.core.windows.net/{container}/{name}"
            )
            self.blobs.append(blob)
            return blob

        self.storage.get_blob_client.side_effect = create_blob
        storage_patch = patch.object(
            report_export, "BlobServiceClient", return_value=self.storage
        )
        self.storage_factory = storage_patch.start()
        self.addCleanup(storage_patch.stop)
        signature_patch = patch.object(
            report_export,
            "generate_blob_sas",
            return_value="sp=r&spr=https&sr=b&sig=test",
        )
        self.sign = signature_patch.start()
        self.addCleanup(signature_patch.stop)
        self.files: dict[str, dict[str, Any]] = {
            "/report-v1.md": {"content": REPORT, "encoding": "utf-8"},
            "/report-v2.md": {"content": REVISED, "encoding": "utf-8"},
            "/final_report.md": {"content": REPORT, "encoding": "utf-8"},
        }
        self.tool = report_export.create_report_export_tool(MagicMock())

    def publish(self, report_name: str = "report-v1.md") -> ToolMessage:
        runtime = ToolRuntime(
            state={"files": self.files},
            context=None,
            config={},
            stream_writer=lambda value: None,
            tool_call_id="export-test",
            store=None,
        )
        return self.tool.invoke(
            {
                "type": "tool_call",
                "name": "publish_report",
                "id": "export-test",
                "args": {"report_name": report_name, "runtime": runtime},
            }
        )

    def test_publish_selects_named_saved_versions_without_editing_them(self) -> None:
        import json

        original_files = copy.deepcopy(self.files)
        first = json.loads(str(self.publish().content))
        second = json.loads(str(self.publish("report-v2.md").content))
        self.assertEqual(self.files, original_files)
        self.assertEqual(first["file_path"], "/report-v1.md")
        self.assertEqual(second["file_path"], "/report-v2.md")
        self.assertNotEqual(first["download_url"], second["download_url"])
        self.assertEqual(second["sha256"], hashlib.sha256(REVISED.encode()).hexdigest())
        self.assertTrue(first["download_url"].split("?")[0].endswith("/report-v1.md"))
        self.assertTrue(second["download_url"].split("?")[0].endswith("/report-v2.md"))
        self.assertEqual(self.blobs[0].upload_blob.call_args.args, (REPORT.encode(),))
        self.assertEqual(self.blobs[1].upload_blob.call_args.args, (REVISED.encode(),))
        for blob, name in zip(self.blobs, ("report-v1.md", "report-v2.md")):
            options = blob.upload_blob.call_args.kwargs
            self.assertFalse(options["overwrite"])
            self.assertEqual(
                options["content_settings"].content_disposition,
                f'attachment; filename="{name}"',
            )
        self.assertEqual(self.storage.get_blob_client.call_count, 2)
        self.assertEqual(self.sign.call_args.kwargs["permission"].read, True)
        self.assertEqual(self.sign.call_args.kwargs["protocol"], "https")
        self.assertLessEqual(
            datetime.fromisoformat(second["expires_at"]),
            datetime.now(timezone.utc) + timedelta(hours=1),
        )

    def test_schema_exposes_only_required_report_name(self) -> None:
        schema = cast(type[BaseModel], self.tool.tool_call_schema).model_json_schema()
        self.assertEqual(set(schema["properties"]), {"report_name"})
        self.assertEqual(schema["required"], ["report_name"])

    def test_legacy_saved_content_remains_publishable(self) -> None:
        self.files["/report-v1.md"]["content"] = REPORT.split("\n")
        self.assertEqual(self.publish().status, "success")
        self.assertEqual(self.blobs[0].upload_blob.call_args.args, (REPORT.encode(),))

    def test_expected_blob_failures_are_explicit_handled_tool_errors(self) -> None:
        for operation in ("key", "upload"):
            for error_type in (
                HttpResponseError,
                ServiceRequestError,
                ServiceResponseError,
            ):
                with self.subTest(operation=operation, error=error_type.__name__):
                    self.storage.get_user_delegation_key.side_effect = None
                    blob = MagicMock(
                        url="https://reports.blob.core.windows.net/reports/test.md"
                    )
                    self.storage.get_blob_client.side_effect = None
                    self.storage.get_blob_client.return_value = blob
                    target = (
                        self.storage.get_user_delegation_key
                        if operation == "key"
                        else blob.upload_blob
                    )
                    target.side_effect = error_type(
                        "sensitive-token-must-not-be-echoed"
                    )
                    before = copy.deepcopy(self.files)
                    result = self.publish()
                    self.assertEqual(result.status, "error")
                    self.assertIn("/report-v1.md", result.content)
                    self.assertIn("remains available for editing", result.content)
                    self.assertIn("No download link", result.content)
                    self.assertNotIn("sensitive-token", result.content)
                    self.assertNotIn("sig=", result.content)
                    self.assertEqual(self.files, before)

    def test_invalid_names_do_not_access_blob_storage(self) -> None:
        for report_name in (
            "../report.md",
            "/report.md",
            "folder/report.md",
            "report.txt",
            "report.md\n",
            "report.md?sig=x",
            "report\\v1.md",
            ".hidden.md",
        ):
            with self.subTest(report_name=report_name):
                result = self.publish(report_name)
                self.assertEqual(result.status, "error")
        self.storage_factory.assert_not_called()

    def test_missing_or_empty_file_is_a_handled_error(self) -> None:
        self.files = {}
        self.assertEqual(self.publish().status, "error")
        self.files = {"/report-v1.md": {"content": ""}}
        self.assertEqual(self.publish().status, "error")
        self.storage_factory.assert_not_called()

    def test_programming_errors_are_not_silently_handled(self) -> None:
        self.storage.get_user_delegation_key.side_effect = TypeError("unexpected bug")
        with self.assertRaisesRegex(TypeError, "unexpected bug"):
            self.publish()


if __name__ == "__main__":
    unittest.main()
