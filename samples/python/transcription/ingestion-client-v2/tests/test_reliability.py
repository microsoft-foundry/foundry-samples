import io
import os
import unittest
from unittest.mock import Mock, patch

import requests

from shared import batch_aggregator, config, processing, speech, storage


class BatchSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {"AUDIO_INPUT_CONTAINER": "audio-input"}))
        self.storage = self.enterContext(patch.object(batch_aggregator, "storage"))
        self.submit = self.enterContext(patch.object(batch_aggregator.speech, "submit_batch_group"))
        self.enterContext(patch.object(batch_aggregator, "load_config", return_value={}))
        self.enterContext(patch.object(batch_aggregator, "validate_config", return_value={}))
        self.storage.list_blobs.return_value = ["batch/file.wav.json"]
        self.storage.download.return_value = b'{"source":"batch/file.wav"}'

    def test_temporary_submission_failure_preserves_pending_marker(self):
        self.submit.side_effect = speech.TransientTranscriptionError("temporary")
        batch_aggregator.flush_pending()
        self.storage.delete_blob.assert_not_called()
        self.storage.write_error.assert_not_called()

    def test_tracking_record_storage_failure_preserves_pending_marker(self):
        self.submit.side_effect = OSError("storage unavailable after submission")
        with self.assertRaises(OSError):
            batch_aggregator.flush_pending()
        self.storage.delete_blob.assert_not_called()
        self.storage.write_error.assert_not_called()

    def test_permanent_submission_failure_records_error_and_removes_marker(self):
        self.submit.side_effect = speech.PermanentTranscriptionError("bad request")
        batch_aggregator.flush_pending()
        self.storage.write_error.assert_called_once()
        self.storage.delete_blob.assert_called_once_with(
            "batch-pending", "batch/file.wav.json", account="output"
        )


class ProcessingTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(
            patch.dict(os.environ, {"AUDIO_INPUT_CONTAINER": "audio-input", "BATCH_PENDING_CONTAINER": "batch-pending"})
        )
        self.storage = self.enterContext(patch.object(processing, "storage"))
        self.storage.get_blob_size.return_value = 5
        self.enterContext(patch.object(processing, "load_config", return_value={}))
        self.enterContext(patch.object(processing, "validate_config", return_value={}))

    def test_batch_marker_write_failure_propagates_for_service_bus_retry(self):
        self.storage.write_json.side_effect = OSError("storage unavailable")
        with self.assertRaises(OSError):
            processing.process_blob_event({"data": {"url": "https://input.test/audio-input/batch/file.wav"}})
        self.storage.write_error.assert_not_called()

    def test_fast_blob_download_failure_propagates_for_service_bus_retry(self):
        self.storage.download_to_spooled.side_effect = OSError("storage unavailable")
        with self.assertRaises(OSError):
            processing.process_blob_event({"data": {"url": "https://input.test/audio-input/fast/file.wav"}})
        self.storage.write_error.assert_not_called()

    def test_permanent_speech_failure_records_error(self):
        self.storage.download_to_spooled.return_value = io.BytesIO(b"audio")
        with patch.object(processing.speech, "transcribe_sync", side_effect=speech.PermanentTranscriptionError("bad input")):
            processing.process_blob_event({"data": {"url": "https://input.test/audio-input/fast/file.wav"}})
        self.storage.write_error.assert_called_once()


class StorageAndConfigTests(unittest.TestCase):
    def test_quarantine_streams_chunks_instead_of_reading_blob(self):
        with (
            patch.dict(os.environ, {"QUARANTINE_CONTAINER": "quarantine"}),
            patch.object(storage, "service") as service,
            patch.object(storage, "upload") as upload,
            patch.object(storage, "download") as download,
        ):
            source = Mock()
            target = Mock()
            service.return_value.get_blob_client.side_effect = [source, target]
            chunks = iter([b"first", b"second"])
            source.download_blob.return_value.chunks.return_value = chunks
            storage.quarantine("audio-input", "fast/file.wav", "too large")
            data = target.upload_blob.call_args.args[0]
            self.assertIs(data, chunks)
            self.assertEqual(list(data), [b"first", b"second"])
            upload.assert_called_once()
            download.assert_not_called()

    def test_invalid_diarization_defaults_without_throwing(self):
        for diarization in (None, {"maxSpeakers": "not-a-number"}, {"maxSpeakers": float("inf")}):
            with self.subTest(diarization=diarization):
                settings = config.validate_config({"diarization": diarization}, "batch")
                self.assertEqual(settings["diarization"]["maxSpeakers"], 4)


if __name__ == "__main__":
    unittest.main()
