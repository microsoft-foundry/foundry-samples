"""Invoke under an independent Azure CLI sign-in, or compare two saved receipts."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src" / "agent"))

from azure.identity.aio import AzureCliCredential
from client import send


def compare(left: dict, right: dict) -> dict:
    parents = [item["receipt"] for item in (left, right)]
    calls = [item["downstream"]["receipt"] for item in parents]
    first, second = calls
    checks = {
        "same_nonempty_C_context": bool(first["context_id"])
        and first["context_id"] == second["context_id"],
        "different_nonempty_C_users": bool(first["user_fingerprint"])
        and bool(second["user_fingerprint"])
        and first["user_fingerprint"] != second["user_fingerprint"],
        "different_nonempty_C_sessions": bool(first["hosted_session_id"])
        and bool(second["hosted_session_id"])
        and first["hosted_session_id"] != second["hosted_session_id"],
        "user_preserved_through_each_parent": all(
            parent["user_fingerprint"] == call["user_fingerprint"]
            for parent, call in zip(parents, calls)
        ),
        "distinct_C_task_ids": bool(first["task_id"])
        and bool(second["task_id"])
        and first["task_id"] != second["task_id"],
        "no_other_marker_in_session_history": all(
            item["marker"] != other["marker"]
            for call, other in ((first, second), (second, first))
            for item in call["prior_session_messages"]
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


async def invoke(args: argparse.Namespace) -> None:
    # Bind this test explicitly to the current CLI sign-in, not environment credentials.
    async with AzureCliCredential() as credential:
        reply = await send(
            args.endpoint,
            {"marker": args.marker, "mode": "explicit", "c_context_id": args.context},
            args.context,
            credential,
            {},
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reply, indent=2), encoding="utf-8")
    print(json.dumps(reply["receipt"]["downstream"]["receipt"], indent=2))
    print(f"Saved receipt: {args.output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    call = commands.add_parser("invoke")
    call.add_argument("--endpoint", required=True)
    call.add_argument("--context", required=True)
    call.add_argument("--marker", required=True)
    call.add_argument("--output", type=Path, required=True)
    comparison = commands.add_parser("compare")
    comparison.add_argument("receipts", nargs=2, type=Path)
    args = parser.parse_args()
    if args.command == "invoke":
        asyncio.run(invoke(args))
    else:
        result = compare(*(json.loads(path.read_text(encoding="utf-8")) for path in args.receipts))
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)
