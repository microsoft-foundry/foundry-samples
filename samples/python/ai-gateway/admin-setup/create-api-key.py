"""Step 4 (optional): Create a runtime API key for an application outside Foundry, then test it.

A runtime key grants gateway-wide access. This script never prints, logs, or saves it: it reads the key into memory
and uses it for one test request. Creating a key and reading its value use the interim helpers in gateway_rest.py,
because the typed AI Gateway SDK doesn't cover API keys yet.
"""

import time

from openai import APIStatusError, OpenAI

import gateway_rest
from common import SAMPLE_MARKER, arm_name, credential, gateway_client, get_gateway, runtime_base_url, setting

ATTEMPTS = 6
RETRY_SECONDS = 30
# New keys, aliases, and role assignments can take a few minutes to take effect.
RETRYABLE_STATUS_CODES = (401, 403, 404, 500, 502, 503)


def main() -> None:
    gateways = gateway_client(credential())
    gateway = get_gateway(gateways)
    key_name = arm_name(setting("AI_GATEWAY_API_KEY_NAME", "external-app"))
    alias = setting("AI_GATEWAY_ALIAS", setting("FOUNDRY_MODEL_DEPLOYMENT"))

    key_id = f"{gateway.id}/apiKeys/{key_name}"
    if gateway_rest.get(gateways, key_id) is None:
        gateway_rest.create_or_update(gateways, key_id, {"properties": {"displayName": f"{key_name} - {SAMPLE_MARKER}"}})
        print(f"Created runtime API key '{key_name}'.")
    else:
        print(f"Runtime API key '{key_name}' already exists. Using it without rotating it.")

    api_key = gateway_rest.list_secrets(gateways, key_id)["primaryKey"]
    # The OpenAI client sends the key as "Authorization: Bearer <key>".
    client = OpenAI(base_url=runtime_base_url(gateway), api_key=api_key)

    for attempt in range(1, ATTEMPTS + 1):
        try:
            completion = client.chat.completions.create(
                model=alias,
                messages=[{"role": "user", "content": "In one sentence, what does an AI gateway do?"}],
            )
            break
        except APIStatusError as error:
            if error.status_code not in RETRYABLE_STATUS_CODES or attempt == ATTEMPTS:
                raise
            print(f"The gateway returned {error.status_code}. Retrying in {RETRY_SECONDS} seconds...")
            time.sleep(RETRY_SECONDS)

    print(f"Model '{alias}' replied: {completion.choices[0].message.content}")
    print(f"Give the application the runtime base URL {runtime_base_url(gateway)} and model '{alias}'.")
    print("Share the key through a secret store, such as Azure Key Vault, not in source code or chat.")


if __name__ == "__main__":
    main()
