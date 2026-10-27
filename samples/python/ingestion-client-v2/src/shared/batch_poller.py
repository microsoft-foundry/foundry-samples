"""Batch completion poller.

Batch jobs are submitted asynchronously. This poller reconciles in-flight jobs: when
a job succeeds it pulls the finished transcript from the Speech service and writes a
single blob mirroring the input path (transcriptions/<same path>.json) - identical to
fast/llm - so the results container stays clean. Job status/failures are logged to
Application Insights (the operational plane), not dumped into the results container.

It is a no-op in `fast` / `llm` deployments (no job records are ever written).
"""
import json
import logging
import os
from datetime import datetime, timezone
from urllib.parse import unquote, urlparse

import requests

from shared import speech, storage


def _elapsed_ms(record: dict) -> int:
    """Milliseconds from batch submission (record.submittedAt) to now."""
    submitted = record.get("submittedAt")
    if not submitted:
        return 0
    try:
        started = datetime.fromisoformat(submitted)
        return max(int((datetime.now(timezone.utc) - started).total_seconds() * 1000), 0)
    except Exception:  # noqa: BLE001 - malformed timestamp
        return 0


def _blob_from_source(source_url: str) -> str:
    """Map a submitted contentUrl back to its input blob path (drops container + SAS)."""
    if not source_url:
        return ""
    path = urlparse(source_url).path.lstrip("/")
    _, _, blob = path.partition("/")  # strip the container segment
    return unquote(blob)


def _collect_succeeded(job_url: str, job_json: dict, sources: list, token: str, ms: int) -> bool:
    """Fetch every per-file transcript for a succeeded job and mirror it to the output.

    Returns True when the job's files were listed and processed (so the record can be
    deleted). Returns False on a transient failure to list files (retry next cycle).
    """
    output_container = os.environ["OUTPUT_CONTAINER"]
    files_url = job_json.get("links", {}).get("files") or f"{job_url}/files"
    fr = requests.get(files_url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    if fr.status_code != 200:
        logging.warning("Could not list files for job (HTTP %s); retrying next cycle", fr.status_code)
        return False

    written = set()
    for fv in fr.json().get("values", []):
        if fv.get("kind") != "Transcription":
            continue
        content_url = fv.get("links", {}).get("contentUrl")
        if not content_url:
            continue
        tr = requests.get(content_url, timeout=600)
        if tr.status_code != 200:
            continue
        try:
            src = tr.json().get("source")
        except Exception:  # noqa: BLE001 - unexpected body
            src = None
        blob_path = _blob_from_source(src)
        if not blob_path:
            continue
        storage.upload(output_container, f"{blob_path}.json", tr.content, account="output", content_type="application/json")
        written.add(blob_path)
        logging.info("INGEST status=transcribed engine=batch ms=%d blob=%s", ms, blob_path)

    # Any submitted file with no transcript => that file failed within the job.
    for source in sources:
        if source not in written:
            storage.write_error(source, "Batch transcription produced no result for this file")
            logging.info("INGEST status=failed engine=batch ms=%d blob=%s", ms, source)
    return True


def poll_batch_jobs() -> None:
    jobs_container = os.environ.get("BATCH_JOBS_CONTAINER", "batch-jobs")

    try:
        records = storage.list_blobs(jobs_container, account="output")
    except Exception:  # noqa: BLE001 - container may not exist yet
        logging.info("No batch jobs to poll")
        return

    token = speech.token_for_speech()
    for record_name in records:
        if not record_name.endswith(".json"):
            continue
        try:
            record = json.loads(storage.download(jobs_container, record_name, account="output"))
        except Exception:  # noqa: BLE001 - skip unreadable record
            logging.warning("Unreadable batch job record: %s", record_name)
            continue

        job_url = record.get("jobUrl")
        # New records carry a `sources` list; tolerate a legacy single `source`.
        sources = record.get("sources") or ([record["source"]] if record.get("source") else [])
        if not job_url:
            continue

        resp = requests.get(job_url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
        if resp.status_code != 200:
            logging.warning("Polling %s returned HTTP %d", record_name, resp.status_code)
            continue

        job_json = resp.json()
        status = job_json.get("status")
        ms = _elapsed_ms(record)

        if status == "Succeeded":
            if _collect_succeeded(job_url, job_json, sources, token, ms):
                storage.delete_blob(jobs_container, record_name, account="output")
                logging.info("Batch job %s complete (%d file(s))", record_name, len(sources))
        elif status == "Failed":
            error = job_json.get("properties", {}).get("error", {})
            for source in sources:
                storage.write_error(source, f"Batch transcription failed: {error}")
                logging.info("INGEST status=failed engine=batch ms=%d blob=%s", ms, source)
            storage.delete_blob(jobs_container, record_name, account="output")
            logging.warning("Batch job failed (%d file(s)): %s", len(sources), error)
        else:
            logging.info("Batch job %s status=%s (%d file(s))", record_name, status, len(sources))
