#!/usr/bin/env python3
"""
TC01 step 5 - test the model through the AI Gateway tier (the "Discover" call).

This is the code equivalent of the AI Gateway tier portal's Discover playground:
it sends an OpenAI-compatible chat completion to the gateway, which authenticates
the api-key, applies your policies (for example, the token rate limit from step 4),
and routes the request to the imported gpt-5.4 deployment.

The client always authenticates to the gateway with a gateway api-key (a runtime
access key or the built-in key) - that is separate from how the gateway reaches
the backend. In this sample the gateway->Foundry leg is keyless (managed identity);
the caller->gateway leg still uses the api-key header shown below.

Verified against:
    https://learn.microsoft.com/azure/api-management/quickstart-ai-gateway-create#4-call-the-gateway

Prerequisites
-------------
- You deployed main.bicep, which created the AI Gateway (AIGateway SKU) and imported
  the gpt-5.4 model over managed identity. See README.md.
- You have a key from the gateway **Keys** page at https://ai.gateway.azure.com -
  either the built-in key or the 'default' runtime key the template created.
- Package:
    pip install openai

Inputs (flags or environment variables)
---------------------------------------
    --base-url  / AI_GATEWAY_BASE_URL   https://<gateway>.azure-api.net/default/models/openai/v1
    --api-key   / AI_GATEWAY_API_KEY    the gateway key (sent in the api-key header)
    --model                             model name registered on the gateway (default: gpt-5.4)

Copy the exact base URL from your gateway's overview page rather than building it
by hand. The api-key is a secret - prefer the AI_GATEWAY_API_KEY environment
variable over passing it on the command line.

Usage
-----
    export AI_GATEWAY_BASE_URL="https://<gateway>.azure-api.net/default/models/openai/v1"
    export AI_GATEWAY_API_KEY="<gateway-key>"

    # single call - verifies the model answers through the gateway
    python test-model-via-gateway.py --prompt "Say hello in five words."

    # burst - exercises the token rate-limit policy (expect HTTP 429 after the budget)
    python test-model-via-gateway.py --repeat 12
"""
import argparse
import os

from openai import OpenAI
from openai import APIStatusError, AuthenticationError, RateLimitError


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test a model through the AI Gateway tier."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("AI_GATEWAY_BASE_URL"),
        help="Gateway OpenAI base URL, e.g. https://<gateway>.azure-api.net/default/models/openai/v1",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("AI_GATEWAY_API_KEY"),
        help="Gateway key sent in the api-key header (prefer the AI_GATEWAY_API_KEY env var).",
    )
    parser.add_argument(
        "--model",
        default="gpt-5.4",
        help="Model name registered on the gateway (default: gpt-5.4).",
    )
    parser.add_argument(
        "--prompt",
        default="Say hello in five words.",
        help="User message to send.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Send the prompt N times to exercise the token rate-limit policy (default: 1).",
    )
    args = parser.parse_args()

    if not args.base_url:
        parser.error("--base-url is required (or set AI_GATEWAY_BASE_URL).")
    if not args.api_key:
        parser.error("--api-key is required (or set AI_GATEWAY_API_KEY).")

    # The gateway authenticates the api-key header, not the OpenAI api_key argument.
    client = OpenAI(
        base_url=args.base_url,
        api_key="unused",
        default_headers={"api-key": args.api_key},
    )

    throttled = 0
    for i in range(1, args.repeat + 1):
        try:
            response = client.chat.completions.create(
                model=args.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": args.prompt},
                ],
            )
            print(f"[{i}/{args.repeat}] OK: {response.choices[0].message.content}")
        except AuthenticationError:
            print(
                f"[{i}/{args.repeat}] 401 - check the api-key header and that the key is active."
            )
        except RateLimitError:
            throttled += 1
            print(
                f"[{i}/{args.repeat}] 429 THROTTLED by the gateway token rate-limit policy."
            )
        except APIStatusError as exc:
            if exc.status_code == 404:
                print(
                    f"[{i}/{args.repeat}] 404 - '{args.model}' is not a model on the gateway."
                )
            else:
                print(f"[{i}/{args.repeat}] {exc.status_code} - {exc.message}")

    if args.repeat > 1:
        print(
            f"\nDone. {throttled} of {args.repeat} calls were throttled by the token rate-limit policy."
        )


if __name__ == "__main__":
    main()
