"""
Create, poll, list, and cancel a real outbound call job (azure-ai-projects==2.11.0).

Set FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_VOICE_AGENT_NAME (an existing Voice Agent),
FOUNDRY_TELEPHONY_CONNECTION_NAME (same-project Twilio, ACS/Teams Phone
extensibility, or preview SipOutbound), FOUNDRY_TELEPHONY_SOURCE, and
FOUNDRY_TELEPHONY_DESTINATION. Use your authorized source and a consenting test
recipient. Teams sources are resource-account GUIDs; other sources and ALL
outbound recipients are E.164 phone numbers. SipAddress is transfer-only in 2.11.0.
No inbound binding is needed. Connections/numbers/permissions must already exist.

Run: python voice_agent_telephony_call_job.py --provider twilio --place-call
Without --place-call, nothing is sent. With it, dialing may start immediately
and incur charges; rerunning creates a new intent. Waits are bounded and
unfinished jobs are cancelled in finally. Cancellation stops future attempts,
not an already connected call; conflicts/errors are surfaced. History is kept.
For a non-dialing lifecycle test add --schedule-only: a single intent is scheduled
ten minutes ahead, inspected, cancelled, deleted, and checked for 404 before it
can dispatch. A cleanup failure still requires recovery before its scheduled time.
"""

import argparse
import time
from datetime import datetime, timedelta, timezone
from itertools import islice
from uuid import uuid4

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    FixedIntervalRetryPolicy,
    TelephonyCallJob,
    TelephonyCallJobCreate,
    TelephonyCallJobSchedule,
)
from azure.core import MatchConditions
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from voice_agent_util import PROVIDERS, phone_number, required_env, source_address

TERMINAL_JOB_STATUSES = {"completed", "blocked", "expired", "failed", "cancelled"}


def build_job(
    provider: str, *, scheduled_at: datetime | None = None
) -> TelephonyCallJobCreate:
    return TelephonyCallJobCreate(
        connection_name=required_env("FOUNDRY_TELEPHONY_CONNECTION_NAME"),
        source=source_address(provider, required_env("FOUNDRY_TELEPHONY_SOURCE")),
        destination=phone_number(required_env("FOUNDRY_TELEPHONY_DESTINATION")),
        purpose="Consented SDK sample test call",
        retry_policy=FixedIntervalRetryPolicy(max_attempts=1, interval=timedelta(0)),
        schedule=(
            TelephonyCallJobSchedule(
                not_before=scheduled_at,
                expires_at=scheduled_at + timedelta(minutes=1),
            )
            if scheduled_at is not None
            else None
        ),
    )


def wait_for_job(
    telephony, agent_name: str, job_id: str, timeout: float
) -> TelephonyCallJob:
    deadline = time.monotonic() + timeout
    while True:
        current = telephony.get_call_job(agent_name=agent_name, call_job_id=job_id)
        print(f"Call job {job_id}: {current.status}")
        if current.status in TERMINAL_JOB_STATUSES:
            return current
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"Call job {job_id} is still {current.status}; inspect it before retrying."
            )
        time.sleep(min(2, remaining))


def cancel_unfinished_job(
    telephony, agent_name: str, job_id: str, timeout: float
) -> None:
    current, etag = telephony.get_call_job(
        agent_name=agent_name,
        call_job_id=job_id,
        cls=lambda _response, job, headers: (job, headers["ETag"]),
    )
    if current.status in TERMINAL_JOB_STATUSES:
        return
    if not etag:
        raise RuntimeError(
            "The job GET did not return an ETag; refusing an unconditional cancellation."
        )
    cancelled = telephony.cancel_call_job(
        agent_name=agent_name,
        call_job_id=job_id,
        etag=etag,
        match_condition=MatchConditions.IfNotModified,
    )
    if cancelled.status not in TERMINAL_JOB_STATUSES:
        wait_for_job(telephony, agent_name, job_id, timeout)
    print(f"Future attempts for call job {job_id} have stopped.")


def run_call_job(
    client: AIProjectClient,
    agent_name: str,
    job: TelephonyCallJobCreate,
    timeout: float,
    *,
    schedule_only: bool = False,
) -> None:
    if schedule_only and (
        job.schedule is None
        or job.schedule.not_before is None
        or job.schedule.not_before <= datetime.now(timezone.utc) + timedelta(minutes=5)
    ):
        raise ValueError("A schedule-only job must be at least five minutes ahead.")
    telephony = client.voice_agents.telephony
    key = str(uuid4())
    print(
        f"Submitting one {'scheduled intent' if schedule_only else 'real call'} "
        f"(idempotency key {key}); an ambiguous submission must be investigated."
    )
    created = telephony.create_call_job(
        agent_name=agent_name, job=job, idempotency_key=key
    )
    try:
        print(f"Accepted call job {created.id}.")
        print(
            f"If cancellation fails, inspect job {created.id} in agent {agent_name}; "
            "an active call may continue and incur charges."
        )
        for item in islice(
            telephony.list_call_jobs(agent_name=agent_name, limit=10), 10
        ):
            print(f"Call job: {item.id} ({item.status})")
        if schedule_only:
            current = telephony.get_call_job(
                agent_name=agent_name, call_job_id=created.id
            )
            if current.attempt_count != 0:
                raise RuntimeError(
                    "The scheduled intent unexpectedly attempted a call."
                )
            print(f"Verified scheduled intent {created.id} with zero attempts.")
        else:
            final = wait_for_job(telephony, agent_name, created.id, timeout)
            print(f"Terminal status: {final.status}; reason: {final.terminal_reason}")
    finally:
        cancel_unfinished_job(telephony, agent_name, created.id, timeout)
        if schedule_only:
            current = telephony.get_call_job(
                agent_name=agent_name, call_job_id=created.id
            )
            if (
                current.status not in TERMINAL_JOB_STATUSES
                or current.attempt_count != 0
            ):
                raise RuntimeError(
                    "The schedule-only job is not terminal with zero attempts; inspect it."
                )
            telephony.delete_call_job(agent_name=agent_name, call_job_id=created.id)
            try:
                telephony.get_call_job(agent_name=agent_name, call_job_id=created.id)
            except ResourceNotFoundError:
                print(f"Deleted scheduled intent {created.id}; GET verified 404.")
            else:
                raise RuntimeError(
                    f"Call job {created.id} still exists after deletion."
                )
            if current.status != "cancelled":
                raise RuntimeError(
                    f"Scheduled intent ended as {current.status}, not cancelled; "
                    "the zero-attempt terminal job was deleted, not counted as a successful call."
                )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=PROVIDERS, default="twilio")
    parser.add_argument(
        "--place-call",
        action="store_true",
        help="Authorize one real, potentially billable call.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60,
        help="Seconds per wait (greater than 0, at most 120).",
    )
    parser.add_argument(
        "--schedule-only",
        action="store_true",
        help="Inspect and cancel a future intent before it dials; delete it and verify 404.",
    )
    args = parser.parse_args(argv)
    if not args.place_call:
        print(
            "No call placed. Configure your source, consenting recipient, and connection; opt in with --place-call."
        )
        return
    if not 0 < args.timeout <= 120:
        parser.error("--timeout must be greater than 0 and at most 120 seconds.")

    load_dotenv()
    endpoint = required_env("FOUNDRY_PROJECT_ENDPOINT")
    agent_name = required_env("FOUNDRY_VOICE_AGENT_NAME")
    job = build_job(
        args.provider,
        scheduled_at=(
            datetime.now(timezone.utc) + timedelta(minutes=10)
            if args.schedule_only
            else None
        ),
    )
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint,
            credential=credential,
            allow_preview=args.provider == "sip",
            connection_timeout=10,
            read_timeout=30,
            retry_total=0,
        ) as client,
    ):
        run_call_job(
            client, agent_name, job, args.timeout, schedule_only=args.schedule_only
        )


if __name__ == "__main__":
    main()
