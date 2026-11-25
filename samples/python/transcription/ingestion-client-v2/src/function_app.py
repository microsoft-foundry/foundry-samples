"""Ingestion Client v2 - Azure Functions (Python v2) entry point.

Pipeline: blob upload -> Event Grid -> Service Bus queue -> this function ->
Speech-to-text (batch | fast | llm) -> transcript in the output storage account.
"""
import json
import logging
import os

import azure.functions as func

from shared.processing import process_blob_event, record_poison

# Quiet noisy Azure SDK HTTP/identity logging so the live debug log shows pipeline events.
for _noisy in (
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.identity",
    "azure.servicebus",
    "urllib3",
    "uamqp",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

app = func.FunctionApp()

# Match the queue's maxDeliveryCount so the final delivery records a poison message
# instead of letting it silently dead-letter.
MAX_DELIVERY_COUNT = int(os.environ.get("MAX_DELIVERY_COUNT", "10") or 10)


@app.service_bus_queue_trigger(
    arg_name="message",
    queue_name="%SERVICE_BUS_QUEUE%",
    connection="ServiceBusConnection",
)
def transcribe(message: func.ServiceBusMessage) -> None:
    body = message.get_body().decode("utf-8")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logging.error("Message body is not valid JSON; dropping. First 500 chars: %s", body[:500])
        return

    events = payload if isinstance(payload, list) else [payload]
    blob_events = [e for e in events if (e.get("eventType") or e.get("type")) == "Microsoft.Storage.BlobCreated"]
    try:
        for event in blob_events:
            process_blob_event(event)
    except Exception:
        # A transient failure was re-raised from processing. On the final delivery,
        # record the failure and swallow it so the file is surfaced (errors container +
        # INGEST status=failed) instead of silently dead-lettering.
        if message.delivery_count >= MAX_DELIVERY_COUNT:
            logging.exception("Poison message after %d deliveries; recording and dropping", message.delivery_count)
            for event in blob_events:
                record_poison(event)
            return
        raise


@app.timer_trigger(arg_name="timer", schedule="0 */5 * * * *", run_on_startup=False, use_monitor=True)
def poll_batch(timer: func.TimerRequest) -> None:
    """Every 5 minutes, reconcile in-flight batch jobs (no-op in fast/llm mode)."""
    from shared.batch_poller import poll_batch_jobs

    poll_batch_jobs()


@app.timer_trigger(arg_name="timer", schedule="0 */1 * * * *", run_on_startup=False, use_monitor=True)
def aggregate_batch(timer: func.TimerRequest) -> None:
    """Every minute, group pending batch files into single multi-file transcription jobs."""
    from shared.batch_aggregator import flush_pending

    flush_pending()
