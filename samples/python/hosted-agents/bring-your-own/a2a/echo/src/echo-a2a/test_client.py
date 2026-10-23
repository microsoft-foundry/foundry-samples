# Copyright (c) Microsoft. All rights reserved.

"""Dedicated local or hosted E2E client for the native A2A echo sample."""

import argparse
import asyncio
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import get_artifact_text, get_message_text, new_text_message
from a2a.types import Role, SendMessageRequest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://localhost:8088")
    parser.add_argument(
        "--card-path",
        default="invocations/a2a/.well-known/agent-card.json",
    )
    parser.add_argument("--message", default="hello")
    parser.add_argument("--azure-auth", action="store_true")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    headers: dict[str, str] = {}
    if args.azure_auth:
        from azure.identity import AzureCliCredential

        token = AzureCliCredential().get_token("https://ai.azure.com/.default")
        headers["Authorization"] = f"Bearer {token.token}"

    endpoint = urlsplit(args.endpoint)
    base_url = urlunsplit((endpoint.scheme, endpoint.netloc, endpoint.path, "", ""))
    query = dict(parse_qsl(endpoint.query))

    async with httpx.AsyncClient(
        headers=headers,
        params=query,
        timeout=60.0,
    ) as http_client:
        client = await create_client(
            base_url,
            ClientConfig(streaming=False, httpx_client=http_client),
            relative_card_path=args.card_path,
            resolver_http_kwargs={"headers": headers},
        )
        request = SendMessageRequest(
            message=new_text_message(args.message, role=Role.ROLE_USER)
        )

        outputs: list[str] = []
        async for response in client.send_message(request):
            if response.HasField("message"):
                outputs.append(get_message_text(response.message))
            elif response.HasField("task"):
                outputs.extend(get_artifact_text(artifact) for artifact in response.task.artifacts)

        expected = f"Echo: {args.message}"
        if expected not in outputs:
            raise RuntimeError(f"Expected {expected!r}, received {outputs!r}")
        print(expected, flush=True)


if __name__ == "__main__":
    asyncio.run(_run(_parse_args()))
