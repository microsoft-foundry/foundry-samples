import json
import os
import unittest
from unittest.mock import Mock, call, patch

from shared import batch_poller


USER_AGENT = "IngestionClient/2.0 (Ingestion Client v2)"
JOB_URL = (
    "https://speech.example.test/speechtotext/transcriptions/job-123"
    "?api-version=2025-10-15"
)
LEGACY_JOB_URL = "https://speech.example.test/speechtotext/v3.2/transcriptions/job-123"


def response(body, status=200):
    result = Mock(status_code=status, content=json.dumps(body).encode("utf-8"))
    result.json.return_value = body
    return result


class BatchPollerTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(
            patch.dict(
                os.environ,
                {"OUTPUT_CONTAINER": "transcriptions", "BATCH_JOBS_CONTAINER": "batch-jobs"},
            )
        )
        self.get = self.enterContext(patch.object(batch_poller.requests, "get"))
        self.storage = self.enterContext(patch.object(batch_poller, "storage"))
        self.enterContext(
            patch.object(
                batch_poller.speech, "token_for_speech", return_value="test-token"
            )
        )
        self.headers = {"Authorization": "Bearer test-token", "User-Agent": USER_AGENT}

    def test_files_fallback_preserves_query_and_legacy_urls(self):
        cases = [
            (
                JOB_URL,
                "https://speech.example.test/speechtotext/transcriptions/job-123/files"
                "?api-version=2025-10-15",
            ),
            (
                f"{JOB_URL}&extra=a%2Bb",
                "https://speech.example.test/speechtotext/transcriptions/job-123/files"
                "?api-version=2025-10-15&extra=a%2Bb",
            ),
            (LEGACY_JOB_URL, f"{LEGACY_JOB_URL}/files"),
            (f"{LEGACY_JOB_URL}/", f"{LEGACY_JOB_URL}/files"),
        ]
        for job_url, files_url in cases:
            with self.subTest(job_url=job_url):
                self.get.reset_mock()
                self.get.return_value = response({"values": []})
                self.assertTrue(
                    batch_poller._collect_succeeded(job_url, {}, [], "test-token", 10)
                )
                self.get.assert_called_once_with(
                    files_url, headers=self.headers, timeout=60
                )

    def test_service_returned_files_link_is_used_unchanged(self):
        files_url = (
            "https://speech.example.test/speechtotext/transcriptions/job-123/files"
            "?api-version=2025-10-15&top=17"
        )
        self.get.return_value = response({"values": []})
        self.assertTrue(
            batch_poller._collect_succeeded(
                JOB_URL, {"links": {"files": files_url}}, [], "test-token", 10
            )
        )
        self.get.assert_called_once_with(files_url, headers=self.headers, timeout=60)

    def test_content_download_has_user_agent_but_no_speech_authorization(self):
        files_url = "https://speech.example.test/files?api-version=2025-10-15"
        content_url = "https://results.example.test/transcript.json?sig=test-sas"
        transcript = response(
            {"source": "https://input.example.test/audio-input/batch/call.wav?sig=test-sas"}
        )
        self.get.side_effect = [
            response(
                {
                    "values": [
                        {"kind": "Transcription", "links": {"contentUrl": content_url}}
                    ]
                }
            ),
            transcript,
        ]
        self.assertTrue(
            batch_poller._collect_succeeded(
                JOB_URL,
                {"links": {"files": files_url}},
                ["batch/call.wav"],
                "test-token",
                10,
            )
        )
        self.assertEqual(
            self.get.call_args_list,
            [
                call(files_url, headers=self.headers, timeout=60),
                call(content_url, headers={"User-Agent": USER_AGENT}, timeout=600),
            ],
        )
        self.storage.upload.assert_called_once_with(
            "transcriptions",
            "batch/call.wav.json",
            transcript.content,
            account="output",
            content_type="application/json",
        )
        self.storage.write_error.assert_not_called()

    def test_files_listing_keeps_headers_on_next_cycle_after_transient_failure(self):
        self.get.side_effect = [
            response({}, status=503),
            response({"values": []}),
        ]
        self.assertFalse(
            batch_poller._collect_succeeded(JOB_URL, {}, [], "test-token", 10)
        )
        self.assertTrue(
            batch_poller._collect_succeeded(JOB_URL, {}, [], "test-token", 10)
        )
        self.assertEqual(self.get.call_count, 2)
        for request in self.get.call_args_list:
            self.assertEqual(request.kwargs["headers"], self.headers)

    def test_polling_preserves_current_and_legacy_job_urls(self):
        self.storage.list_blobs.return_value = ["job-123.json"]
        with patch.object(batch_poller, "_collect_succeeded", return_value=True) as collect:
            for job_url in (JOB_URL, LEGACY_JOB_URL):
                with self.subTest(job_url=job_url):
                    self.get.reset_mock()
                    collect.reset_mock()
                    self.storage.delete_blob.reset_mock()
                    self.storage.download.return_value = json.dumps(
                        {"jobUrl": job_url, "sources": ["batch/call.wav"]}
                    ).encode("utf-8")
                    job = {"status": "Succeeded"}
                    self.get.return_value = response(job)
                    batch_poller.poll_batch_jobs()
                    self.get.assert_called_once_with(
                        job_url, headers=self.headers, timeout=60
                    )
                    collect.assert_called_once_with(
                        job_url, job, ["batch/call.wav"], "test-token", 0
                    )
                    self.storage.delete_blob.assert_called_once_with(
                        "batch-jobs", "job-123.json", account="output"
                    )

    def test_polling_keeps_headers_on_next_cycle_after_transient_failure(self):
        self.storage.list_blobs.return_value = ["job-123.json"]
        self.storage.download.return_value = json.dumps(
            {"jobUrl": JOB_URL, "sources": ["batch/call.wav"]}
        ).encode("utf-8")
        self.get.side_effect = [
            response({}, status=503),
            response({"status": "Running"}),
        ]
        batch_poller.poll_batch_jobs()
        batch_poller.poll_batch_jobs()
        self.assertEqual(
            self.get.call_args_list,
            [call(JOB_URL, headers=self.headers, timeout=60)] * 2,
        )
        self.storage.delete_blob.assert_not_called()


if __name__ == "__main__":
    unittest.main()
