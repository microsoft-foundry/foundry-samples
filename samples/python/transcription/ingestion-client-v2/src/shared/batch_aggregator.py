"""Batch aggregator.

Batch ingest only records a pending marker per file (fast, never throttled). This
timer groups those pending files into a *single* multi-file transcription job using
the batch API's `contentUrls` array - the recommended, efficient pattern that avoids
the create-rate limit a job-per-file design hits under load.

Flow: list pending markers -> chunk into groups of MAX_FILES_PER_JOB -> submit each
group as one job (with retry/backoff) -> delete the markers that were submitted.
"""
import json
import logging
import os

from shared import speech, storage
from shared.config import load_config, validate_config


def flush_pending() -> None:
    pending_container = os.environ.get("BATCH_PENDING_CONTAINER", "batch-pending")
    audio_container = os.environ["AUDIO_INPUT_CONTAINER"]

    try:
        markers = storage.list_blobs(pending_container, account="output")
    except Exception:  # noqa: BLE001 - container may not exist yet
        logging.info("No pending batch files")
        return

    items = []  # (marker_blob, source_path)
    for marker in markers:
        if not marker.endswith(".json"):
            continue
        try:
            rec = json.loads(storage.download(pending_container, marker, account="output"))
        except Exception:  # noqa: BLE001 - skip unreadable marker
            logging.warning("Unreadable pending marker: %s", marker)
            continue
        source = rec.get("source")
        if source:
            items.append((marker, source))

    if not items:
        return

    cfg = validate_config(load_config("batch"), "batch")
    max_files = int(os.environ.get("MAX_FILES_PER_JOB", "100") or 100)
    logging.info("Aggregating %d pending batch file(s) into jobs of up to %d", len(items), max_files)

    for i in range(0, len(items), max_files):
        chunk = items[i:i + max_files]
        blobs = [source for _, source in chunk]
        try:
            speech.submit_batch_group(audio_container, blobs, cfg)
        except speech.TransientTranscriptionError:
            # Throttled even after backoff: leave these markers for the next cycle.
            logging.warning("Batch submit throttled; leaving %d marker(s) for next cycle", len(chunk))
            return
        except Exception as exc:  # noqa: BLE001 - permanent failure: record and drop
            logging.exception("Batch submit permanently failed for %d file(s)", len(chunk))
            for _, source in chunk:
                storage.write_error(source, f"Batch submit failed: {exc}")
                logging.info("INGEST status=failed engine=batch ms=0 blob=%s", source)
            for marker, _ in chunk:
                storage.delete_blob(pending_container, marker, account="output")
            continue

        # Submitted successfully -> remove the markers we just consumed.
        for marker, _ in chunk:
            storage.delete_blob(pending_container, marker, account="output")
