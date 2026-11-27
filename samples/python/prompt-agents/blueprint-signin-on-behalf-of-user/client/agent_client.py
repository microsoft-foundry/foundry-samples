import os
import sys
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import DeviceCodeCredential, get_bearer_token_provider
from openai import APIConnectionError, APIStatusError, OpenAI
from openai.types.responses import Response


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Set {name} before running the client.")
    return value


def find_consent_link(response: Response) -> str | None:
    for item in response.output:
        if item.type != "oauth_consent_request":
            continue
        link = getattr(item, "consent_link", None)
        if not isinstance(link, str):
            raise ValueError(
                "The agent requested MCP consent without a valid HTTPS consent link."
            )
        parsed = urlsplit(link)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(
                "The agent requested MCP consent without a valid HTTPS consent link."
            )
        return link
    return None


def main() -> int:
    try:
        tenant_id = required("AZURE_TENANT_ID")
        blueprint_id = required("GREETING_BLUEPRINT_ID")
        client_id = required("GREETING_CLIENT_ID")
        endpoint = urlsplit(required("GREETING_AGENT_ENDPOINT"))
        if endpoint.scheme != "https" or not endpoint.netloc:
            raise ValueError("The agent endpoint must use HTTPS.")

        base_url = urlunsplit(
            (endpoint.scheme, endpoint.netloc, endpoint.path, "", "")
        )
        with DeviceCodeCredential(
            tenant_id=tenant_id, client_id=client_id
        ) as credential:
            token_provider = get_bearer_token_provider(
                credential, f"api://{blueprint_id}/access_agent"
            )
            with OpenAI(
                base_url=base_url,
                api_key=token_provider,
                default_query=dict(parse_qsl(endpoint.query)),
            ) as client:
                response = client.responses.create(
                    input="Call the greet tool once and report its greeting and invocation ID verbatim."
                )

        if consent_link := find_consent_link(response):
            print(
                "The MCP tool needs your consent. Open this link, sign in as the same user, "
                f"and review the requested permission: {consent_link}",
                file=sys.stderr,
            )
            print("After consenting, run the client again.", file=sys.stderr)
            return 2

        text = response.output_text
        if not text.strip():
            raise ValueError("The agent did not return an answer.")
        print(text)
        return 0
    except ClientAuthenticationError as error:
        print(f"Sign-in failed: {error}", file=sys.stderr)
        return 1
    except APIStatusError as error:
        print(
            f"The agent request failed: HTTP {error.status_code}. {error}",
            file=sys.stderr,
        )
        return 1
    except APIConnectionError as error:
        print(f"The agent request failed: {error}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"Sample failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
