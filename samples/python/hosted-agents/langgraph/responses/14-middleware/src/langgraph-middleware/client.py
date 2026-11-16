"""Review native LangChain middleware decisions over local or Foundry Responses."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from openai import OpenAI

INTERRUPT_NAME = "__hosted_agent_adapter_interrupt__"
DEFAULT_PROMPT = (
    "Send an email to alice@example.com with subject Project update "
    "and body The review starts at 10:00."
)


def create_response(
    client: OpenAI, *, input: Any, stream: bool = False, **options: Any
) -> dict[str, Any]:
    """Return the terminal Responses object for JSON or SSE transport."""
    response: Any = client.responses.create(input=input, stream=stream, **options)
    if not stream:
        payload = response.model_dump(mode="json")
    else:
        payload = None
        with response:
            for event in response:
                if event.type in {
                    "response.completed",
                    "response.failed",
                    "response.incomplete",
                }:
                    payload = event.response.model_dump(mode="json")
                elif event.type == "error":
                    raise RuntimeError(str(event))
        if payload is None:
            raise RuntimeError("Response stream ended without a terminal event")
    status = payload.get("status")
    if status != "completed":
        details = payload.get("error") or payload.get("incomplete_details") or payload
        raise RuntimeError(f"Response did not complete (status={status!r}): {details}")
    return payload


def build_resume_items(
    response: dict[str, Any],
    decision: str,
    edited_recipient: str | None = None,
) -> list[dict[str, Any]]:
    """Build standard approval replies or rich native edit decisions.

    Args:
        response: The paused Responses object, including interrupt output items.
        decision: Apply approve, edit, or reject to every displayed action.
        edited_recipient: Replacement recipient for an edit decision.

    Returns:
        MCP approval responses for approve/reject, or function-call outputs
        carrying interrupt-keyed LangGraph resume values for edit.

    Raises:
        ValueError: No review exists or a requested decision is not allowed.
    """
    if decision not in {"approve", "edit", "reject"}:
        raise ValueError(f"Unknown decision {decision!r}")
    item_type = "function_call" if decision == "edit" else "mcp_approval_request"
    replies = []
    for item in response.get("output", []):
        if item.get("type") != item_type or item.get("name") != INTERRUPT_NAME:
            continue
        review = json.loads(item["arguments"])["value"]
        actions = review["action_requests"]
        configs = review["review_configs"]
        decisions = []
        for action, config in zip(actions, configs, strict=True):
            if decision not in config["allowed_decisions"]:
                raise ValueError(f"Decision {decision!r} is not allowed")
            if decision == "edit":
                if not edited_recipient:
                    raise ValueError("An edited recipient is required")
                decisions.append(
                    {
                        "type": "edit",
                        "edited_action": {
                            "name": action["name"],
                            "args": {**action["args"], "recipient": edited_recipient},
                        },
                    }
                )
        if decision != "edit":
            reply: dict[str, Any] = {
                "type": "mcp_approval_response",
                "approval_request_id": item["id"],
                "approve": decision == "approve",
            }
            if decision == "reject":
                reply["reason"] = "Rejected by the reviewer; do not retry."
            replies.append(reply)
            continue
        call_id = item["call_id"]
        replies.append(
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps({"resume": {call_id: {"decisions": decisions}}}),
            }
        )
    if not replies:
        raise ValueError("No middleware review was returned")
    return replies


def review_agent(client: OpenAI, args: argparse.Namespace, **options: Any) -> None:
    """Display results and ask for a decision only when a review is pending."""
    paused = create_response(client, input=args.prompt, stream=args.stream, **options)
    print(json.dumps(paused, indent=2))
    if not any(
        item.get("type") == "mcp_approval_request"
        and item.get("name") == INTERRUPT_NAME
        for item in paused.get("output", [])
    ):
        if any(
            item.get("type") == "function_call" and item.get("name") == INTERRUPT_NAME
            for item in paused.get("output", [])
        ):
            raise RuntimeError(
                "Pending middleware review is missing its mcp_approval_request."
            )
        return
    decision = (
        args.decision
        or input("Decision for all actions [approve/edit/reject]: ").strip()
    )
    recipient = args.recipient
    if decision == "edit" and not recipient:
        recipient = input("Replacement recipient: ").strip()
    replies = build_resume_items(paused, decision, recipient)
    finished = create_response(
        client,
        input=replies,
        previous_response_id=paused["id"],
        stream=args.stream,
        **options,
    )
    print(json.dumps(finished, indent=2))
    if any(
        item.get("type") in {"function_call", "mcp_approval_request"}
        and item.get("name") == INTERRUPT_NAME
        for item in finished.get("output", [])
    ):
        raise RuntimeError(
            f"Response {finished['id']} is still awaiting human review; "
            "this client handles one review round only."
        )


def main() -> None:
    """Run the reviewer locally or against a deployed Foundry agent."""
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8088/")
    parser.add_argument(
        "--agent-name", help="Invoke this deployed agent through Foundry"
    )
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--decision", choices=["approve", "edit", "reject"])
    parser.add_argument("--recipient", help="Replacement recipient for edit")
    parser.add_argument("--stream", action="store_true")
    args = parser.parse_args()
    if args.agent_name:
        with DefaultAzureCredential() as credential:
            with AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential
            ) as project:
                with project.get_openai_client(agent_name=args.agent_name) as client:
                    review_agent(client, args)
    else:
        with OpenAI(base_url=args.base_url, api_key="local", max_retries=0) as client:
            review_agent(client, args)


if __name__ == "__main__":
    main()
