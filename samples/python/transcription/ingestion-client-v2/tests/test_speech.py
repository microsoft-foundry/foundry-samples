import io
import json
import os
import unittest
from unittest.mock import Mock, patch

from shared import speech


USER_AGENT = "IngestionClient/2.0 (Ingestion Client v2)"
ENDPOINT = "https://speech.example.test"
SUBMIT_URL = f"{ENDPOINT}/speechtotext/transcriptions:submit?api-version=2025-10-15"
TRANSCRIBE_URL = (
    f"{ENDPOINT}/speechtotext/transcriptions:transcribe?api-version=2025-10-15"
)


def response(status=200, body=None):
    result = Mock(status_code=status, headers={}, text="test response")
    result.json.return_value = body
    return result


class BatchPropertiesTests(unittest.TestCase):
    def test_diarization_uses_current_shape_for_two_and_multiple_speakers(self):
        for maximum in (2, 4, 35):
            with self.subTest(maximum=maximum):
                properties = speech._batch_properties(
                    {"diarization": {"enabled": True, "maxSpeakers": maximum}}, 12
                )
                self.assertEqual(
                    properties["diarization"],
                    {"enabled": True, "maxSpeakers": maximum},
                )
                self.assertNotIn("diarizationEnabled", properties)

    def test_diarization_defaults_to_two_speakers(self):
        properties = speech._batch_properties({"diarization": {"enabled": True}}, 12)
        self.assertEqual(
            properties["diarization"], {"enabled": True, "maxSpeakers": 2}
        )

    def test_disabled_or_omitted_diarization_stays_disabled(self):
        for diarization in ({}, {"enabled": False, "maxSpeakers": 4}):
            with self.subTest(diarization=diarization):
                properties = speech._batch_properties({"diarization": diarization}, 12)
                self.assertNotIn("diarization", properties)
                self.assertNotIn("diarizationEnabled", properties)

    def test_other_batch_properties_are_preserved(self):
        properties = speech._batch_properties(
            {
                "batch": {
                    "wordLevelTimestamps": False,
                    "displayFormWordLevelTimestamps": True,
                    "punctuationMode": "Automatic",
                },
                "profanityFilterMode": "Removed",
                "channels": [0, 1],
                "locales": ["en-US", "fr-FR"],
            },
            48,
        )
        self.assertEqual(
            properties,
            {
                "wordLevelTimestampsEnabled": False,
                "displayFormWordLevelTimestampsEnabled": True,
                "profanityFilterMode": "Removed",
                "punctuationMode": "Automatic",
                "timeToLiveHours": 48,
                "channels": [0, 1],
                "languageIdentification": {"candidateLocales": ["en-US", "fr-FR"]},
            },
        )


class SpeechRequestTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(
            patch.dict(
                os.environ,
                {"FOUNDRY_ENDPOINT": f"{ENDPOINT}/", "BATCH_JOBS_CONTAINER": "batch-jobs"},
            )
        )
        self.enterContext(patch.object(speech, "_token", return_value="test-token"))
        self.post = self.enterContext(patch.object(speech.requests, "post"))
        self.enterContext(patch.object(speech.time, "sleep"))
        self.headers = {"Authorization": "Bearer test-token", "User-Agent": USER_AGENT}

    def test_batch_submission_url_payload_and_versioned_job_record(self):
        job_url = f"{ENDPOINT}/speechtotext/transcriptions/job-123?api-version=2025-10-15"
        self.post.return_value = response(201, {"self": job_url})
        blobs = ["batch/first file.wav", "batch/second.wav"]
        model_url = f"{ENDPOINT}/speechtotext/models/model-123?api-version=2025-10-15"
        config = {
            "locales": ["en-US"],
            "diarization": {"enabled": True, "maxSpeakers": 4},
            "batch": {"timeToLiveHours": 12, "model": model_url},
        }
        with (
            patch.object(speech.storage, "account_name", return_value="inputaccount"),
            patch.object(
                speech.storage, "endpoint", return_value="https://input.example.test/"
            ),
            patch.object(speech.storage, "service"),
            patch.object(speech.storage, "write_json") as write_json,
            patch(
                "azure.storage.blob.generate_blob_sas",
                side_effect=["first-sas", "second-sas"],
            ),
        ):
            record = speech.submit_batch_group("audio-input", blobs, config)

        self.post.assert_called_once_with(
            SUBMIT_URL,
            headers={**self.headers, "Content-Type": "application/json"},
            json={
                "contentUrls": [
                    "https://input.example.test/audio-input/batch/first%20file.wav?first-sas",
                    "https://input.example.test/audio-input/batch/second.wav?second-sas",
                ],
                "locale": "en-US",
                "displayName": "ingestion-batch-2-files",
                "properties": {
                    "wordLevelTimestampsEnabled": True,
                    "displayFormWordLevelTimestampsEnabled": False,
                    "profanityFilterMode": "Masked",
                    "punctuationMode": "DictatedAndAutomatic",
                    "timeToLiveHours": 12,
                    "diarization": {"enabled": True, "maxSpeakers": 4},
                },
                "model": {"self": model_url},
            },
            timeout=120,
        )
        self.assertEqual(record["jobUrl"], job_url)
        self.assertEqual(record["sources"], blobs)
        write_json.assert_called_once_with(
            "batch-jobs", "job-123.json", record, account="output"
        )

    def test_batch_user_agent_and_auth_on_every_retry_including_exhaustion(self):
        for succeeds in (True, False):
            with self.subTest(succeeds=succeeds):
                self.post.reset_mock()
                self.post.side_effect = [response(429) for _ in range(5)] + [
                    response(201, {"self": "job"}) if succeeds else response(503)
                ]
                if succeeds:
                    self.assertEqual(
                        speech._post_json_with_retry(SUBMIT_URL, {}), {"self": "job"}
                    )
                else:
                    with self.assertRaises(speech.TransientTranscriptionError):
                        speech._post_json_with_retry(SUBMIT_URL, {})
                self.assertEqual(self.post.call_count, 6)
                for request in self.post.call_args_list:
                    self.assertEqual(request.args, (SUBMIT_URL,))
                    self.assertEqual(
                        request.kwargs["headers"],
                        {**self.headers, "Content-Type": "application/json"},
                    )

    def test_fast_and_llm_keep_current_api_and_definitions(self):
        cases = [
            (False, {}, {"phraseList": {"phrases": ["Contoso"]}}),
            (
                True,
                {"task": "transcribe", "prompt": "Preserve names"},
                {
                    "enhancedMode": {
                        "enabled": True,
                        "task": "transcribe",
                        "prompt": ["Preserve names"],
                    }
                },
            ),
            (
                True,
                {"task": "translate", "targetLanguage": "fr", "prompt": ["Use French"]},
                {
                    "enhancedMode": {
                        "enabled": True,
                        "task": "translate",
                        "targetLanguage": "fr",
                        "prompt": ["Use French"],
                    }
                },
            ),
        ]
        for llm, llm_config, extra_definition in cases:
            with self.subTest(llm=llm, llm_config=llm_config):
                self.post.reset_mock()
                transcript = {"combinedPhrases": [{"text": "test transcript"}]}
                self.post.return_value = response(200, transcript)
                config = {
                    "locales": ["en-US"],
                    "diarization": {"enabled": True, "maxSpeakers": 4},
                    "channels": [0],
                    "phraseList": ["Contoso"],
                    "llm": llm_config,
                }
                self.assertIs(
                    speech.transcribe_sync(b"audio", "call.wav", config, llm),
                    transcript,
                )
                self.post.assert_called_once()
                request = self.post.call_args
                self.assertEqual(request.args, (TRANSCRIBE_URL,))
                self.assertEqual(request.kwargs["headers"], self.headers)
                self.assertEqual(request.kwargs["timeout"], 1200)
                self.assertEqual(
                    request.kwargs["files"]["audio"],
                    ("call.wav", b"audio", "application/octet-stream"),
                )
                definition = request.kwargs["files"]["definition"]
                self.assertEqual((definition[0], definition[2]), (None, "application/json"))
                self.assertEqual(
                    json.loads(definition[1]),
                    {
                        "locales": ["en-US"],
                        "diarization": {"enabled": True, "maxSpeakers": 4},
                        "channels": [0],
                        "profanityFilterMode": "Masked",
                        **extra_definition,
                    },
                )

    def test_sync_user_agent_and_auth_on_every_retry_including_exhaustion(self):
        for llm in (False, True):
            for succeeds in (True, False):
                with self.subTest(llm=llm, succeeds=succeeds):
                    self.post.reset_mock()
                    self.post.side_effect = [response(429) for _ in range(4)] + [
                        response(200, {"text": "result"}) if succeeds else response(503)
                    ]
                    with io.BytesIO(b"audio") as audio:
                        if succeeds:
                            self.assertEqual(
                                speech.transcribe_sync(audio, "call.wav", {}, llm),
                                {"text": "result"},
                            )
                        else:
                            with self.assertRaises(speech.TransientTranscriptionError):
                                speech.transcribe_sync(audio, "call.wav", {}, llm)
                    self.assertEqual(self.post.call_count, 5)
                    for request in self.post.call_args_list:
                        self.assertEqual(request.args, (TRANSCRIBE_URL,))
                        self.assertEqual(request.kwargs["headers"], self.headers)


if __name__ == "__main__":
    unittest.main()
