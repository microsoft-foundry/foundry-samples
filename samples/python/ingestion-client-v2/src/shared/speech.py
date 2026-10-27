"""Speech-to-text engines: fast + llm (synchronous) and batch (async submit).

All calls authenticate to the Foundry resource with the function's managed identity
(no keys). The active engine is chosen by the `mode` field in the runtime config.
"""
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from urllib.parse import quote, urlparse

import requests

from shared import storage

_SCOPE = "https://cognitiveservices.azure.com/.default"
_FAST_API_VERSION = "2025-10-15"
_BATCH_API_PATH = "speechtotext/v3.2/transcriptions"
_RETRY_STATUS = {429, 500, 502, 503, 504}
_SYNC_TIMEOUT_SECONDS = 1200  # allow long fast/llm sync files (up to ~20 min audio)


class TransientTranscriptionError(Exception):
    """Raised when retries are exhausted so the Service Bus message is retried later."""


def _token() -> str:
    return storage.credential().get_token(_SCOPE).token


def token_for_speech() -> str:
    """Public accessor for a Speech/Foundry bearer token (used by the batch poller)."""
    return _token()


def _endpoint() -> str:
    return os.environ["FOUNDRY_ENDPOINT"].rstrip("/")


def _retry_after_seconds(resp: "requests.Response", fallback: int) -> int:
    """Honor the server's Retry-After header (seconds) on 429/503; else use the fallback."""
    header = resp.headers.get("Retry-After")
    if header:
        try:
            return max(1, min(int(float(header)), 60))
        except ValueError:
            return fallback
    return fallback


def _post_json_with_retry(url: str, body: Dict[str, Any], timeout: int = 60, max_attempts: int = 6) -> Dict[str, Any]:
    """POST JSON with exponential backoff that honors Retry-After.

    Raises TransientTranscriptionError when retries are exhausted (so the caller can
    reschedule) and RuntimeError for non-retryable failures.
    """
    backoff = 2
    last_status = None
    for attempt in range(max_attempts):
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
            json=body,
            timeout=timeout,
        )
        if resp.status_code in (200, 201):
            return resp.json()
        last_status = resp.status_code
        if resp.status_code in _RETRY_STATUS:
            delay = _retry_after_seconds(resp, backoff)
            logging.warning("POST attempt %d -> HTTP %d; retrying in %ss", attempt + 1, resp.status_code, delay)
            time.sleep(delay)
            backoff = min(backoff * 2, 60)
            continue
        raise RuntimeError(f"Request failed: HTTP {resp.status_code} {resp.text[:1000]}")
    raise TransientTranscriptionError(f"Exhausted retries (last status {last_status})")


def _build_definition(cfg: Dict[str, Any], llm: bool) -> Dict[str, Any]:
    definition: Dict[str, Any] = {}

    # locales guide recognition; empty/omitted => automatic language detection (multilingual)
    locales = cfg.get("locales") or []
    if locales:
        definition["locales"] = locales

    diar = cfg.get("diarization", {})
    if diar.get("enabled"):
        definition["diarization"] = {"enabled": True, "maxSpeakers": diar.get("maxSpeakers", 4)}

    channels = cfg.get("channels") or []
    if channels:
        definition["channels"] = channels

    definition["profanityFilterMode"] = cfg.get("profanityFilterMode", "Masked")

    if llm:
        # LLM Speech is enabled via the enhancedMode object (transcribe/translate + prompt list).
        llm_cfg = cfg.get("llm", {})
        enhanced: Dict[str, Any] = {"enabled": True, "task": llm_cfg.get("task", "transcribe")}
        if enhanced["task"] == "translate" and llm_cfg.get("targetLanguage"):
            enhanced["targetLanguage"] = llm_cfg["targetLanguage"]
        prompt = llm_cfg.get("prompt")
        if prompt:
            enhanced["prompt"] = prompt if isinstance(prompt, list) else [prompt]
        definition["enhancedMode"] = enhanced
    else:
        # phraseList is supported by fast transcription (and batch), but not by LLM Speech.
        phrases = cfg.get("phraseList") or []
        if phrases:
            definition["phraseList"] = {"phrases": phrases}

    return definition


def transcribe_sync(audio, filename: str, cfg: Dict[str, Any], llm: bool) -> Dict[str, Any]:
    """Fast / LLM Speech: synchronous transcription via the transcribe endpoint.

    `audio` may be raw bytes or a seekable file-like object (used for long audio so
    it doesn't all sit in memory).
    """
    url = f"{_endpoint()}/speechtotext/transcriptions:transcribe?api-version={_FAST_API_VERSION}"
    definition = _build_definition(cfg, llm)
    backoff = 2
    last_status = None
    for attempt in range(5):
        if hasattr(audio, "seek"):
            audio.seek(0)
        files = {
            "audio": (os.path.basename(filename), audio, "application/octet-stream"),
            "definition": (None, json.dumps(definition), "application/json"),
        }
        resp = requests.post(url, headers={"Authorization": f"Bearer {_token()}"}, files=files, timeout=_SYNC_TIMEOUT_SECONDS)
        if resp.status_code == 200:
            return resp.json()
        last_status = resp.status_code
        if resp.status_code in _RETRY_STATUS:
            delay = _retry_after_seconds(resp, backoff)
            logging.warning("transcribe attempt %d -> HTTP %d; retrying in %ss", attempt + 1, resp.status_code, delay)
            time.sleep(delay)
            backoff = min(backoff * 2, 32)
            continue
        raise RuntimeError(f"Transcription failed: HTTP {resp.status_code} {resp.text[:1000]}")
    raise TransientTranscriptionError(f"Exhausted retries (last status {last_status})")


def _batch_properties(cfg: Dict[str, Any], ttl_hours: int) -> Dict[str, Any]:
    """Build the batch job `properties` object shared by every file in a job."""
    batch_cfg = cfg.get("batch", {})
    diar = cfg.get("diarization", {})

    properties: Dict[str, Any] = {
        "wordLevelTimestampsEnabled": bool(batch_cfg.get("wordLevelTimestamps", True)),
        "displayFormWordLevelTimestampsEnabled": bool(batch_cfg.get("displayFormWordLevelTimestamps", False)),
        "profanityFilterMode": cfg.get("profanityFilterMode", "Masked"),
        "punctuationMode": batch_cfg.get("punctuationMode", "DictatedAndAutomatic"),
        "timeToLiveHours": ttl_hours,
    }

    if diar.get("enabled"):
        properties["diarizationEnabled"] = True
        max_speakers = int(diar.get("maxSpeakers", 2) or 2)
        if max_speakers > 2:  # richer diarization is required for 3+ speakers
            properties["diarization"] = {"speakers": {"minCount": 1, "maxCount": max_speakers}}

    channels = cfg.get("channels") or []
    if channels:
        properties["channels"] = channels

    # Multiple candidate locales => language identification (base models only).
    locales = cfg.get("locales") or ["en-US"]
    if len(locales) > 1:
        properties["languageIdentification"] = {"candidateLocales": locales}

    return properties


def submit_batch_group(container: str, blobs: List[str], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Submit MANY audio files as ONE batch transcription job (contentUrls array).

    Each file gets its own keyless user-delegation SAS. Bundling files into a single
    job is the batch API's recommended pattern - it avoids the create-rate limit that a
    job-per-file design hits under load, and cuts the number of API calls and poll work.
    The poller fetches each file's transcript and mirrors it to transcriptions/<path>.json.
    """
    from azure.storage.blob import BlobSasPermissions, generate_blob_sas

    ttl_hours = int(cfg.get("batch", {}).get("timeToLiveHours", 12) or 12)
    start = datetime.now(timezone.utc) - timedelta(minutes=5)
    expiry = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

    account = storage.account_name("input")
    base = storage.endpoint("input").rstrip("/")
    input_udk = storage.service("input").get_user_delegation_key(start, expiry)

    content_urls: List[str] = []
    for blob in blobs:
        sas = generate_blob_sas(
            account_name=account,
            container_name=container,
            blob_name=blob,
            user_delegation_key=input_udk,
            permission=BlobSasPermissions(read=True),
            start=start,
            expiry=expiry,
        )
        content_urls.append(f"{base}/{container}/{quote(blob)}?{sas}")

    locales = cfg.get("locales") or ["en-US"]
    body: Dict[str, Any] = {
        "contentUrls": content_urls,
        "locale": locales[0],
        "displayName": f"ingestion-batch-{len(content_urls)}-files",
        "properties": _batch_properties(cfg, ttl_hours),
    }

    # Optional custom / Whisper model (its `self` URI); omit to use the latest base model.
    model_uri = cfg.get("batch", {}).get("model") or cfg.get("batch", {}).get("customModelEndpointId")
    if model_uri:
        body["model"] = {"self": model_uri}

    url = f"{_endpoint()}/{_BATCH_API_PATH}"
    job = _post_json_with_retry(url, body, timeout=120)
    job_url = job.get("self")
    job_id = (
        urlparse(job_url).path.rstrip("/").split("/")[-1]
        if job_url
        else datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    )
    record = {"jobUrl": job_url, "sources": blobs, "submittedAt": datetime.now(timezone.utc).isoformat()}
    storage.write_json(
        os.environ.get("BATCH_JOBS_CONTAINER", "batch-jobs"),
        f"{job_id}.json",
        record,
        account="output",
    )
    logging.info("Batch job %s submitted with %d file(s)", job_id, len(blobs))
    return record
