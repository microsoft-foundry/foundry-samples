"""Demonstrate branching, rewind, and regeneration by remembering a number.

Run ``python client.py`` after starting ``python main.py``.
"""

import argparse
from collections.abc import Callable
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential, get_bearer_token_provider


def _create_response(
    client: httpx.Client,
    input: str,
    previous_response_id: str | None,
    token_provider: Callable[[], str] | None,
) -> str:
    body: dict[str, Any] = {"input": input, "store": True, "stream": False}

    if previous_response_id is not None:
        body["previous_response_id"] = previous_response_id

    if token_provider:
        headers = {"Authorization": f"Bearer {token_provider()}"}
    else:
        headers = {}

    response = client.post("responses", json=body, headers=headers)

    response.raise_for_status()
    payload = response.json()
    if payload["status"] != "completed":
        raise RuntimeError(f"Response did not complete: {payload.get('error')}")

    response_id = str(payload["id"])
    text = "".join(
        part["text"]
        for item in payload["output"]
        if item["type"] == "message"
        for part in item["content"]
        if part["type"] == "output_text"
    )
    print(f"Server response: {text}")
    return response_id


def main() -> None:
    """Branch, rewind, continue, and regenerate a remembered number."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8088")
    parser.add_argument(
        "--azure", action="store_true", help="Authenticate to a Foundry-hosted agent."
    )
    args = parser.parse_args()

    token_provider: Callable[[], str] | None = None
    if args.azure:
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential, "https://ai.azure.com/.default"
        )

    client = httpx.Client(
        base_url=args.base_url,
        params={"api-version": "v1"} if args.azure else None,
        timeout=120,
    )

    print("\nA: remember 10 -> 10")
    parent_id = _create_response(
        client,
        "Remember the number 10.",
        None,
        token_provider,
    )

    add_one = "Add 1 to the remembered number."

    print("\nB: branch from A, add 1 -> 11")
    branch_b_id = _create_response(
        client,
        add_one,
        parent_id,
        token_provider,
    )

    print("\nC: branch from A, add 2 -> 12")
    _create_response(
        client,
        "Add 2 to the remembered number.",
        parent_id,
        token_provider,
    )

    print("\nD: rewind to B after C, recall -> 11")
    rewind_id = _create_response(
        client,
        "What number do you remember?",
        branch_b_id,
        token_provider,
    )

    print("\nE: continue D, add 1 -> 12")
    _create_response(
        client,
        add_one,
        rewind_id,
        token_provider,
    )

    print("\nF: regenerate B, same parent and input -> 11")
    _create_response(
        client,
        add_one,
        parent_id,
        token_provider,
    )


if __name__ == "__main__":
    main()
