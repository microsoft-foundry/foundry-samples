"""
Inspect/control inbound calls and manage transfer targets (azure-ai-projects==2.11.0).

Set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_VOICE_AGENT_NAME to your own Voice Agent.
Run: python voice_agent_telephony_calls.py --action list --run
For get, end, or transfer, also supply --call-id with the EXACT service call ID.
End/transfer act on a connected call, not on a call job. Transfer additionally
needs --target naming an already configured target, never a raw phone number.
The SDK documents these operations for inbound calls; do not substitute a job ID.

The targets action creates a NEW disposable Voice Agent, reads its empty target
set, replaces it with one consenting E.164 destination, verifies it, then clears
it and deletes the new agent version. Set FOUNDRY_TELEPHONY_TRANSFER_DESTINATION.
FOUNDRY_VOICE_AGENT_NAME must be unused for this action (or omit it for a unique
name). This never replaces another agent's targets, changes provider routing, or
dials a call. Connections, inbound routing, and consent remain prerequisites.
"""

import argparse
import os
import time
from itertools import islice

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    TelephonyCallRecord,
    TelephonyCallSummary,
    TelephonyTransferTarget,
    VoiceAgentDefinition,
    VoiceModelType,
)
from azure.ai.projects.operations import VoiceAgentsTelephonyOperations
from azure.core import MatchConditions
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from voice_agent_util import (
    PROVIDERS,
    phone_number,
    required_env,
    require_new_agent,
    sample_agent_name,
)

CONNECTED_PHASES = {
    "answered",
    "media_connected",
    "agent_session_ready",
    "bridging",
    "managing",
}


def list_active_calls(
    telephony: VoiceAgentsTelephonyOperations, agent_name: str
) -> list[TelephonyCallSummary]:
    """The 2.11.0 active-call view is list_calls(status='in_progress')."""
    calls = list(
        islice(
            telephony.list_calls(agent_name=agent_name, status="in_progress", limit=10),
            10,
        )
    )
    for call in calls:
        print(f"Call {call.id}: {call.status}, phase={call.phase}")
    return calls


def get_connected_call(
    telephony: VoiceAgentsTelephonyOperations, agent_name: str, call_id: str
) -> TelephonyCallRecord:
    if not call_id.strip():
        raise ValueError("An exact service-generated call ID is required.")
    call = telephony.get_call(agent_name=agent_name, call_id=call_id)
    if call.id != call_id:
        raise RuntimeError("The returned call does not match the requested ID.")
    if call.status != "in_progress" or call.phase not in CONNECTED_PHASES:
        raise ValueError(f"Call {call_id} is not connected; no control was sent.")
    return call


def wait_for_call_end(
    telephony: VoiceAgentsTelephonyOperations,
    agent_name: str,
    call_id: str,
    timeout: float,
) -> TelephonyCallRecord:
    deadline = time.monotonic() + timeout
    while True:
        call = telephony.get_call(agent_name=agent_name, call_id=call_id)
        if call.id != call_id:
            raise RuntimeError("The returned call does not match the requested ID.")
        if call.status in {"success", "failed"} and call.ended_at is not None:
            return call
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"Call {call_id} has not ended; inspect this exact call before retrying."
            )
        time.sleep(min(1, remaining))


def end_connected_call(
    telephony: VoiceAgentsTelephonyOperations,
    agent_name: str,
    call_id: str,
    timeout: float,
) -> TelephonyCallRecord:
    if not 0 < timeout <= 120:
        raise ValueError("Use a timeout greater than 0 and at most 120 seconds.")
    get_connected_call(telephony, agent_name, call_id)
    telephony.end_call(agent_name=agent_name, call_id=call_id)
    # An accepted control, like a cancelled job, is not proof of disconnection.
    ended = wait_for_call_end(telephony, agent_name, call_id, timeout)
    print(f"Call {ended.id} ended: {ended.status}, reason={ended.end_reason}.")
    return ended


def transfer_connected_call(
    telephony: VoiceAgentsTelephonyOperations,
    agent_name: str,
    call_id: str,
    target: str,
) -> TelephonyCallRecord:
    get_connected_call(telephony, agent_name, call_id)
    targets = telephony.get_transfer_targets(agent_name=agent_name)
    if not any(item.name == target for item in targets.transfer_targets):
        raise ValueError("Choose the exact name of a configured transfer target.")
    transferred = telephony.transfer_call(
        agent_name=agent_name, call_id=call_id, target=target
    )
    print(
        f"Transfer requested for {call_id}: {transferred.status}. "
        "This is not proof that the destination answered or the call ended."
    )
    return transferred


def run_transfer_targets(
    telephony: VoiceAgentsTelephonyOperations,
    agent_name: str,
    destination: str,
) -> None:
    target = TelephonyTransferTarget(
        name="sample-operator",
        description="Consenting test operator; transfer only on explicit request.",
        destination=phone_number(destination),
    )
    current, etag = telephony.get_transfer_targets(
        agent_name=agent_name,
        cls=lambda _response, targets, headers: (targets, headers["ETag"]),
    )
    if current.transfer_targets:
        raise ValueError("Refusing to replace pre-existing transfer targets.")
    if not isinstance(etag, str) or not etag:
        raise RuntimeError("Missing target ETag; refusing an unconditional replace.")
    telephony.replace_transfer_targets(
        agent_name=agent_name,
        transfer_targets=[target],
        etag=etag,
        match_condition=MatchConditions.IfNotModified,
    )
    try:
        configured = telephony.get_transfer_targets(agent_name=agent_name)
        if [item.as_dict() for item in configured.transfer_targets] != [
            target.as_dict()
        ]:
            raise RuntimeError("The new transfer target was not persisted.")
        print("Verified the new agent's sample-operator transfer target.")
    finally:
        current, etag = telephony.get_transfer_targets(
            agent_name=agent_name,
            cls=lambda _response, targets, headers: (targets, headers["ETag"]),
        )
        if [item.as_dict() for item in current.transfer_targets] != [target.as_dict()]:
            raise RuntimeError(
                "Targets changed concurrently; refusing to clear someone else's configuration."
            )
        if not isinstance(etag, str) or not etag:
            raise RuntimeError("Missing target ETag; refusing an unconditional clear.")
        telephony.replace_transfer_targets(
            agent_name=agent_name,
            transfer_targets=[],
            etag=etag,
            match_condition=MatchConditions.IfNotModified,
        )
        if telephony.get_transfer_targets(agent_name=agent_name).transfer_targets:
            raise RuntimeError("The run-owned transfer target was not cleared.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--action",
        choices=("list", "get", "end", "transfer", "targets"),
        default="list",
    )
    parser.add_argument("--provider", choices=PROVIDERS, default="twilio")
    parser.add_argument("--run", action="store_true", help="Opt in to this action.")
    parser.add_argument("--call-id", help="Exact inbound service call ID you own.")
    parser.add_argument("--target", help="Name of an already configured target.")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args(argv)
    if not args.run:
        print("No request sent. Choose an action and explicitly opt in with --run.")
        return
    if not 0 < args.timeout <= 120:
        parser.error("--timeout must be greater than 0 and at most 120 seconds.")
    if args.action in {"get", "end", "transfer"} and not args.call_id:
        parser.error("--call-id is required; job IDs are not call IDs.")
    if args.action == "transfer" and not args.target:
        parser.error("--target must name an already configured transfer target.")

    load_dotenv()
    endpoint = required_env("FOUNDRY_PROJECT_ENDPOINT")
    name = (
        sample_agent_name("voice-transfer-targets")
        if args.action == "targets"
        else required_env("FOUNDRY_VOICE_AGENT_NAME")
    )
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint,
            credential=credential,
            allow_preview=args.provider == "sip",
            connection_timeout=10,
            read_timeout=20,
            retry_total=0,
        ) as client,
    ):
        telephony = client.voice_agents.telephony
        if args.action == "targets":
            destination = required_env("FOUNDRY_TELEPHONY_TRANSFER_DESTINATION")
            phone_number(destination)
            require_new_agent(client, name)
            created = client.agents.create_version(
                agent_name=name,
                definition=VoiceAgentDefinition(
                    model_type=VoiceModelType.MANAGED,
                    model=os.environ.get("FOUNDRY_VOICE_AGENT_MODEL") or "gpt-realtime",
                    instructions="You are a concise, helpful test assistant.",
                ),
            )
            try:
                run_transfer_targets(telephony, name, destination)
            finally:
                client.agents.delete_version(
                    agent_name=name, agent_version=created.version
                )
        elif args.action == "list":
            list_active_calls(telephony, name)
        elif args.action == "get":
            call = telephony.get_call(agent_name=name, call_id=args.call_id)
            print(f"Call {call.id}: {call.status}, phase={call.phase}")
        elif args.action == "end":
            end_connected_call(telephony, name, args.call_id, args.timeout)
        elif args.action == "transfer":
            transfer_connected_call(telephony, name, args.call_id, args.target)


if __name__ == "__main__":
    main()
