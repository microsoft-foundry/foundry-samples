"""
Schedule, inspect, cancel, and delete one preview campaign (azure-ai-projects==2.11.0).

Use the same endpoint, existing Voice Agent, connection, source, and consenting
E.164 recipient environment variables as voice_agent_telephony_call_job.py.
Run: python voice_agent_campaign.py --provider twilio --schedule-campaign
Without --schedule-campaign, no request is sent. This flag authorizes a real,
potentially billable call if cleanup fails. One recipient is scheduled ten minutes
ahead, with one attempt and an expiry one minute later. Cancellation does not end
connected calls. Ensure consent and comply with applicable calling regulations.

The beta sub-client supplies preview headers. Creation uses a unique name and
If-None-Match; cleanup uses guarded GETs and fresh ETags before cancel/delete.
Cleanup errors are not suppressed: use the printed agent/campaign name to recover.
No existing campaign, dataset, connection, binding, or agent is deleted.
"""

import argparse
from datetime import datetime, timedelta, timezone
from itertools import islice
from typing import TypeVar
from uuid import uuid4

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AtTimeSchedule,
    FixedIntervalRetryPolicy,
    TelephonyCampaign,
    TelephonyRecipient,
)
from azure.core import MatchConditions
from azure.core.exceptions import ResourceNotFoundError
from azure.core.polling import LROPoller
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from voice_agent_util import PROVIDERS, phone_number, required_env, source_address

T = TypeVar("T")
TERMINAL_CAMPAIGN_STATUSES = {"completed", "failed", "cancelled"}


def build_campaign(provider: str, scheduled_at: datetime) -> TelephonyCampaign:
    return TelephonyCampaign(
        connection_name=required_env("FOUNDRY_TELEPHONY_CONNECTION_NAME"),
        source=source_address(provider, required_env("FOUNDRY_TELEPHONY_SOURCE")),
        recipients=[
            TelephonyRecipient(
                destination=phone_number(required_env("FOUNDRY_TELEPHONY_DESTINATION"))
            )
        ],
        schedule=AtTimeSchedule(
            scheduled_at=scheduled_at, expires_at=scheduled_at + timedelta(minutes=1)
        ),
        retry_policy=FixedIntervalRetryPolicy(max_attempts=1, interval=timedelta(0)),
    )


def wait_for_operation(poller: LROPoller[T], timeout: float) -> T:
    # wait() has a timeout but does not itself raise when the background poller is unfinished.
    poller.wait(timeout=timeout)
    if not poller.done():
        raise TimeoutError(
            "Campaign operation did not finish in time; server-side work may continue."
        )
    return poller.result()


def cleanup_campaign(
    campaigns, agent_name: str, name: str, creation_id: str, timeout: float
) -> None:
    try:
        current = campaigns.get(
            agent_name=agent_name, campaign_name=name, operation_id=creation_id
        )
    except ResourceNotFoundError:
        # A failed/ambiguous create can leave no resource; never resubmit to find out.
        print(f"Campaign {name} is absent; no future intent remains at this name.")
        return
    if current.status not in TERMINAL_CAMPAIGN_STATUSES:
        if not current.etag:
            raise RuntimeError(
                "Missing campaign ETag; refusing an unconditional cancellation."
            )
        wait_for_operation(
            campaigns.begin_cancel(
                agent_name=agent_name,
                campaign_name=name,
                etag=current.etag,
                match_condition=MatchConditions.IfNotModified,
                operation_id=str(uuid4()),
            ),
            timeout,
        )
    current = campaigns.get(
        agent_name=agent_name, campaign_name=name, operation_id=creation_id
    )
    if current.status not in TERMINAL_CAMPAIGN_STATUSES:
        raise RuntimeError(
            f"Campaign {name} is still {current.status}; it was NOT deleted and may still place calls."
        )
    if not current.etag:
        raise RuntimeError("Missing campaign ETag; refusing an unconditional delete.")
    wait_for_operation(
        campaigns.begin_delete(
            agent_name=agent_name,
            campaign_name=name,
            etag=current.etag,
            match_condition=MatchConditions.IfNotModified,
            operation_id=str(uuid4()),
        ),
        timeout,
    )
    print(f"Deleted terminal campaign {name}.")


def run_campaign(
    client: AIProjectClient,
    agent_name: str,
    campaign: TelephonyCampaign,
    timeout: float,
) -> None:
    schedule = campaign.schedule
    if not isinstance(schedule, AtTimeSchedule):
        raise ValueError(
            "This sample requires an AtTimeSchedule before it can submit a campaign."
        )
    campaigns = client.beta.voice_agents.telephony
    name = f"voice-sample-{uuid4().hex}"
    creation_id = str(uuid4())
    print(f"Submitting campaign {name} for agent {agent_name}.")
    print(f"Scheduled at {schedule.scheduled_at.isoformat()}.")
    print(
        "If submission is ambiguous or this process stops, inspect/cancel that campaign before its scheduled time."
    )
    try:
        poller = campaigns.begin_create(
            agent_name=agent_name,
            campaign_name=name,
            campaign=campaign,
            operation_id=creation_id,
            etag="*",
            match_condition=MatchConditions.IfMissing,
        )
        print(
            f"Cleanup failures for {name} require manual recovery to prevent later calls."
        )
        prepared = wait_for_operation(poller, timeout)
        print(f"Campaign preparation returned status: {prepared.status}")
        for item in islice(campaigns.list(agent_name=agent_name, limit=10), 10):
            print(f"Campaign: {item.name} ({item.status})")
        current = campaigns.get(
            agent_name=agent_name, campaign_name=name, operation_id=creation_id
        )
        print(f"Retrieved campaign {current.name}: {current.status}")
    finally:
        cleanup_campaign(campaigns, agent_name, name, creation_id, timeout)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=PROVIDERS, default="twilio")
    parser.add_argument(
        "--schedule-campaign",
        action="store_true",
        help="Authorize a real outbound campaign.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60,
        help="Seconds per operation (greater than 0, at most 120).",
    )
    args = parser.parse_args(argv)
    if not args.schedule_campaign:
        print(
            "No campaign scheduled. Configure your resources and consenting recipient; "
            "opt in with --schedule-campaign."
        )
        return
    if not 0 < args.timeout <= 120:
        parser.error("--timeout must be greater than 0 and at most 120 seconds.")

    load_dotenv()
    endpoint = required_env("FOUNDRY_PROJECT_ENDPOINT")
    agent_name = required_env("FOUNDRY_VOICE_AGENT_NAME")
    campaign = build_campaign(
        args.provider, datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint,
            credential=credential,
            polling_interval=2,
            connection_timeout=10,
            read_timeout=30,
            retry_total=0,
        ) as client,
    ):
        run_campaign(client, agent_name, campaign, args.timeout)


if __name__ == "__main__":
    main()
