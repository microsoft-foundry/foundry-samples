"""Offline checks for named downloads and latest-response/session chaining."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import httpx
from openai import OpenAI, omit
from openai.types.responses import Response

SAMPLE_DIR = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "deep_research_demo_client", SAMPLE_DIR / "client.py"
)
assert SPEC is not None and SPEC.loader is not None
demo = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = demo
SPEC.loader.exec_module(demo)

REPORT = b"# Report v1\nEvidence https://example.org/source"
REVISED = REPORT + b"\n\n## Recovery limitations\nOnly saved state is restored."


def response(
    identifier: str, report_name: str | None = None, content: bytes = REPORT
) -> Any:
    result = MagicMock(spec=Response)
    result.id = identifier
    result.status = "completed"
    result.error = None
    result.model_extra = {"agent_session_id": "session-test"}
    result.output_text = content.decode()
    output = []
    if report_name:
        output = [
            {
                "type": "function_call",
                "name": "publish_report",
                "call_id": "export",
                "arguments": json.dumps({"report_name": report_name}),
            },
            {
                "type": "function_call_output",
                "call_id": "export",
                "output": json.dumps(
                    {
                        "file_path": f"/{report_name}",
                        "download_url": f"https://reports.blob.core.windows.net/reports/{'a' * 32}/{report_name}?sig=test",
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                ),
            },
        ]
    result.model_dump.return_value = {"output": output}
    return result


class ClientTests(unittest.TestCase):
    def setUp(self) -> None:
        environment = patch.dict(
            os.environ,
            {
                "REPORT_STORAGE_ACCOUNT_URL": "https://reports.blob.core.windows.net",
                "REPORT_STORAGE_CONTAINER": "reports",
            },
        )
        environment.start()
        self.addCleanup(environment.stop)

    def test_demo_chains_latest_ids_and_downloads_both_names(self) -> None:
        client = MagicMock()
        client.responses.create.side_effect = [
            response("first", "report-v1.md"),
            response("read"),
            response("revised", "report-v2.md", REVISED),
            response("reread", content=REVISED),
        ]

        def get(url: str, **kwargs: Any) -> httpx.Response:
            body = REVISED if "report-v2.md" in url else REPORT
            return httpx.Response(200, content=body, request=httpx.Request("GET", url))

        sessions: set[str] = set()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(demo.httpx, "get", side_effect=get),
            patch("builtins.print"),
        ):
            demo.run_demo(client, Path(directory), sessions)
            self.assertEqual((Path(directory) / "report-v1.md").read_bytes(), REPORT)
            self.assertEqual((Path(directory) / "report-v2.md").read_bytes(), REVISED)
        requests = [
            invocation.kwargs for invocation in client.responses.create.call_args_list
        ]
        self.assertEqual(
            [request["previous_response_id"] for request in requests],
            [omit, "first", "read", "revised"],
        )
        self.assertEqual(requests[0]["extra_body"], {})
        self.assertTrue(
            all(
                request["extra_body"] == {"agent_session_id": "session-test"}
                for request in requests[1:]
            )
        )
        self.assertEqual(sessions, {"session-test"})
        for request in requests:
            for internal_name in (
                "research-agent",
                "read_file",
                "write_file",
                "edit_file",
                "publish_report",
            ):
                self.assertNotIn(internal_name, request["input"])
        self.assertIn("primary sources", requests[0]["input"])
        self.assertIn("report-v1.md", requests[0]["input"])
        self.assertIn("download link", requests[0]["input"])
        self.assertIn("Recovery limitations", requests[2]["input"])
        self.assertIn("report-v2.md", requests[2]["input"])
        self.assertIn("citations", requests[2]["input"])
        self.assertIn("without changing", requests[2]["input"])

    def test_handled_failure_creates_no_local_download(self) -> None:
        result = response("failed-publication")
        result.model_dump.return_value = {
            "output": [
                {
                    "type": "function_call",
                    "name": "publish_report",
                    "call_id": "publish",
                    "arguments": '{"report_name":"report-v1.md"}',
                },
                {
                    "type": "function_call_output",
                    "call_id": "publish",
                    "output": "Publishing failed. The saved report remains available for editing. No download link was created.",
                },
            ]
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(demo.httpx, "get") as download,
        ):
            with self.assertRaisesRegex(RuntimeError, "failed-publication"):
                demo.download_report(result, "report-v1.md", Path(directory))
            download.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_first_wire_request_omits_null_previous_response_id(self) -> None:
        requests = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "id": "first",
                    "object": "response",
                    "status": "completed",
                    "output": [],
                },
            )

        with (
            httpx.Client(transport=httpx.MockTransport(respond)) as transport,
            OpenAI(
                base_url="https://example.invalid",
                api_key="test",
                http_client=cast(Any, transport),
            ) as client,
            tempfile.TemporaryDirectory() as directory,
            patch("builtins.print"),
            self.assertRaisesRegex(RuntimeError, "No download link"),
        ):
            demo.run_demo(client, Path(directory), set())
        self.assertEqual(len(requests), 1)
        self.assertNotIn("previous_response_id", requests[0])

    def test_download_mismatch_creates_no_file(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(
                demo.httpx,
                "get",
                return_value=httpx.Response(
                    200,
                    content=b"truncated",
                    request=httpx.Request(
                        "GET", "https://reports.blob.core.windows.net"
                    ),
                ),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "digest"):
                demo.download_report(
                    response("original", "report-v1.md"),
                    "report-v1.md",
                    Path(directory),
                )
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_changed_session_is_rejected_but_both_are_remembered(self) -> None:
        client = MagicMock()
        first, second = response("first"), response("second")
        second.model_extra = {"agent_session_id": "different-session"}
        client.responses.create.side_effect = [first, second]
        sessions: set[str] = set()
        with (
            patch.object(demo, "download_report"),
            patch("builtins.print"),
            self.assertRaisesRegex(RuntimeError, "hosted session"),
        ):
            demo.run_demo(client, Path("unused"), sessions)
        self.assertEqual(sessions, {"session-test", "different-session"})


if __name__ == "__main__":
    unittest.main()
