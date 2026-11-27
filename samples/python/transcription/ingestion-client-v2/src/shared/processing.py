"""Orchestration: route a blob-created event to the right engine by its input folder.

The first path segment under audio-input/ selects the engine:
    audio-input/fast/...   -> fast transcription
    audio-input/llm/...    -> LLM Speech
    audio-input/batch/...  -> batch transcription
Anything else (or a file dropped in the container root) is quarantined.
Output mirrors the full input path, e.g. transcriptions/fast/<...>.json.
"""
import logging
import os
import time
from datetime import datetime, timezone
from urllib.parse import unquote, urlparse
from typing import Optional, Tuple

from shared import speech, storage
from shared.config import ENGINES, load_config, validate_config

# Fast / LLM synchronous engines accept files up to 500 MB.
MAX_SYNC_BYTES = 500 * 1024 * 1024


def _parse_blob_url(url: str) -> Tuple[str, str]:
    path = unquote(urlparse(url).path.lstrip("/"))
    container, _, blob = path.partition("/")
    return container, blob


def process_blob_event(event: dict) -> None:
    start = time.monotonic()
    url: Optional[str] = event.get("data", {}).get("url")
    if not url:
        logging.warning("BlobCreated event has no data.url; skipping")
        return

    container, blob_name = _parse_blob_url(url)
    audio_container = os.environ["AUDIO_INPUT_CONTAINER"]
    if container != audio_container:
        logging.info("Blob %s is not in %s; skipping", blob_name, audio_container)
        return

    # Engine is the top-level folder; the remainder is the mirrored relative path.
    engine, _, remainder = blob_name.partition("/")
    if engine not in ENGINES or not remainder:
        storage.quarantine(audio_container, blob_name, reason=f"unrecognized-engine-folder:'{engine}'")
        logging.info("INGEST status=quarantined engine=unknown ms=0 blob=%s", blob_name)
        return

    cfg = validate_config(load_config(engine), engine)
    logging.info("Processing '%s' with engine=%s", blob_name, engine)

    if engine in ("fast", "llm"):
        size = storage.get_blob_size(audio_container, blob_name)
        if size is not None and size > MAX_SYNC_BYTES:
            storage.quarantine(audio_container, blob_name, reason="exceeds-500MB-sync-limit")
            logging.info("INGEST status=quarantined engine=%s ms=0 blob=%s", engine, blob_name)
            return

    try:
        if engine == "batch":
            # Batch is async and aggregated: just record the file as pending. A timer
            # groups pending files into a single multi-file job (efficient + avoids the
            # create-rate limit). The poller then mirrors each transcript to the output.
            pending = os.environ.get("BATCH_PENDING_CONTAINER", "batch-pending")
            storage.write_json(
                pending,
                f"{blob_name}.json",
                {"source": blob_name, "queuedAt": datetime.now(timezone.utc).isoformat()},
                account="output",
            )
            logging.info("INGEST status=submitted engine=batch ms=0 blob=%s", blob_name)
            return
        audio = storage.download_to_spooled(audio_container, blob_name)
        try:
            result = speech.transcribe_sync(audio, blob_name, cfg, llm=(engine == "llm"))
        finally:
            audio.close()
    except speech.TransientTranscriptionError:
        # Re-raise so the Service Bus message is retried after the visibility timeout.
        raise
    except Exception as exc:  # noqa: BLE001 - permanent failure: record and move on
        logging.exception("Transcription failed for '%s'", blob_name)
        logging.info("INGEST status=failed engine=%s ms=%d blob=%s", engine, int((time.monotonic() - start) * 1000), blob_name)
        storage.write_error(blob_name, str(exc))
        return

    storage.write_result(blob_name, result)
    logging.info("INGEST status=transcribed engine=%s ms=%d blob=%s", engine, int((time.monotonic() - start) * 1000), blob_name)
    logging.info("Transcript written for '%s'", blob_name)


def record_poison(event: dict) -> None:
    """Record a failure for a message that exhausted its delivery attempts (poison).

    Called by the trigger on the final delivery so a persistently-failing file is
    surfaced (errors container + INGEST status=failed) instead of silently dead-lettering.
    """
    url = event.get("data", {}).get("url")
    if not url:
        return
    _, blob_name = _parse_blob_url(url)
    engine = blob_name.partition("/")[0] or "unknown"
    try:
        storage.write_error(blob_name, "Message exhausted delivery attempts (poison message)")
    except Exception:  # noqa: BLE001 - best effort
        logging.exception("Failed to write poison error record for %s", blob_name)
    logging.info("INGEST status=failed engine=%s ms=0 blob=%s", engine, blob_name)
