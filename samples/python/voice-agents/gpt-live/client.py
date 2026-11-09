#!/usr/bin/env python3
"""Connect to an azd-deployed Foundry GPT Live agent with the OpenAI Live SDK."""

import argparse
import asyncio
import base64
import contextlib
import io
import json
import os
import re
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import CredentialUnavailableError
from azure.identity.aio import AzureCliCredential, get_bearer_token_provider
from dotenv import load_dotenv
from openai import AsyncOpenAI
from openai.resources.live.live import AsyncLiveConnection
from websockets.exceptions import ConnectionClosed

from audio_common import RATE, Audio, AudioError
from transcript_common import TranscriptDisplay

PREVIEW = "VoiceAgents=V1Preview"
API_VERSION = "v1"
TOKEN_SCOPE = "https://ai.azure.com/.default"
_SECRET = re.compile(
    r"(?i)([\"']?(?:authorization|api[-_]?key|access[-_]?token|token|sig|secret|password)[\"']?)"
    r"(\s*[:=]\s*)(?:bearer\s+)?(\"[^\"]*\"|'[^']*'|[^\s,;&}\]]+)"
)
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_URL_QUERY = re.compile(r"((?:https?|wss?)://[^\s?]+)\?[^\s]+")
_LONG_DATA = re.compile(r"(?<![\w-])[A-Za-z0-9+/]{80,}={0,2}(?![\w-])")
_PAYLOAD = re.compile(
    r'(?i)(["\']?(?:audio|input_audio|payload|body)["\']?\s*[:=]\s*)'
    r'("[^"]*"|\'[^\']*\'|\S+)'
)


class DemoError(Exception):
    pass


@dataclass
class SessionEvidence:
    input_transcript: str = ""
    output_transcript: str = ""
    output_audio_base64_chars: int = 0
    delegation_ids: list[str] = field(default_factory=list)
    backend_text: dict[str, str] = field(default_factory=dict)
    backend_completed: set[str] = field(default_factory=set)
    closed: bool = False

    async def observe(self, connection, event, transcript):
        del connection, transcript
        if event.type == "session.input_transcript.delta":
            self.input_transcript += event.delta
        elif event.type == "session.output_transcript.delta":
            self.output_transcript += event.delta
        elif event.type == "session.output_audio.delta":
            self.output_audio_base64_chars += len(event.delta)
        elif event.type == "session.delegation.created":
            if event.delegation.id not in self.delegation_ids:
                self.delegation_ids.append(event.delegation.id)
        elif event.type == "response.event" and event.delegation_id:
            kind = event.event.get("type")
            if kind == "response.output_text.delta":
                self.backend_text[event.delegation_id] = self.backend_text.get(
                    event.delegation_id, ""
                ) + event.event.get("delta", "")
            elif kind == "response.completed":
                self.backend_completed.add(event.delegation_id)
        elif event.type == "session.closed":
            self.closed = True

    def result(self) -> dict:
        correlated = [
            delegation_id
            for delegation_id in self.delegation_ids
            if delegation_id in self.backend_completed
            and self.backend_text.get(delegation_id, "").strip()
        ]
        return {
            "input_transcript": self.input_transcript,
            "output_transcript": self.output_transcript,
            "output_audio_base64_chars": self.output_audio_base64_chars,
            "delegation_ids": self.delegation_ids,
            "correlated_completed_delegations": correlated,
            "backend_text": self.backend_text,
            "closed": self.closed,
        }


class EntraAuth(httpx.Auth):
    """Share automatically refreshed Azure CLI tokens between REST and the SDK."""

    def __init__(self, credential):
        self.token_provider = get_bearer_token_provider(credential, TOKEN_SCOPE)

    async def async_auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {await self.token_provider()}"
        yield request


async def converse(
    connection: AsyncLiveConnection,
    audio: Audio,
    transcript: TranscriptDisplay,
    backend_model: str,
    *,
    managed_delegation: bool = False,
    event_handler=None,
) -> str | None:
    """The whole SDK event/audio loop is here so the sample can be read on its own."""
    events = connection.__aiter__()
    stop = transcript.stop_requested
    loop = asyncio.get_running_loop()
    old_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, lambda *_: loop.call_soon_threadsafe(stop.set))
    session_id = None
    conversation_id = None
    closed = close_sent = False
    audio_started = False
    replied = set()
    tasks = []

    async def observe(event):
        nonlocal closed
        if event_handler is not None:
            await event_handler(connection, event, transcript)
        if event.type == "error":
            raise DemoError(f"Live error: {sanitize_diagnostic(event.error.message)}")
        if event.type == "session.output_audio.delta":
            audio.play(base64.b64decode(event.delta, validate=True))
        elif event.type == "session.input_transcript.delta":
            transcript.append_user(event.delta)
        elif event.type == "session.output_transcript.delta":
            transcript.append_agent(event.delta)
        elif event.type.startswith("session.managed_delegation."):
            # Foundry-specific events survive the OpenAI SDK parser as extra fields.
            # These are diagnostics only: Foundry already forwards accepted guidance.
            phase = event.type.rsplit(".", 1)[-1]
            statuses = {
                "started": "Prompt agent started",
                "request": "Prompt agent request sent",
                "progress": "Receiving accepted prompt-agent guidance",
                "completed": "Prompt agent completed",
                "failed": "Prompt agent failed",
            }
            if phase not in statuses:
                return
            status = statuses[phase]
            text = None
            if phase in {"progress", "completed"}:
                # These fields are cumulative, not token deltas or spoken captions.
                text = (
                    "\n".join(
                        f"[{tag}] {value}"
                        for field, tag in (
                            ("spoken_text", "commentary"),
                            ("background_context", "thinking"),
                        )
                        if isinstance(value := getattr(event, field, None), str)
                        and value
                    )
                    or None
                )
            elif phase == "failed":
                status += f": {getattr(event, 'error_code', 'unknown_error')}"
                # Preserve previously accepted text on partial failure. Do not show
                # rejected output, retry the backend, or interrupt its spoken fallback.
            transcript.update_agent_activity(
                event.delegation_id,
                title=f"Managed delegation → {backend_model}",
                status=status,
                text=text,
            )
        elif event.type == "session.delegation.created":
            delegation = event.delegation
            if managed_delegation:
                # Managed sessions retain the native event name, but Foundry
                # projects its target to indicate that the service owns execution.
                if delegation.target != "foundry_managed_agent":
                    raise DemoError(
                        "Expected Foundry-managed delegation, but received "
                        f"delegation target '{delegation.target}'. Check that the "
                        "service supports foundry_managed_agent with tagged_text; "
                        "no client fallback was run."
                    )
                transcript.update_agent_activity(
                    delegation.id,
                    title=f"Managed delegation → {backend_model}",
                    status="Prompt agent delegation requested",
                )
                return
            transcript.update_agent_activity(
                delegation.id,
                title=(
                    "Delegation → "
                    f"{backend_model if delegation.target == 'responses' else delegation.target}"
                ),
                status="Delegation requested",
            )
            if delegation.target == "client" and delegation.id not in replied:
                replied.add(delegation.id)
                content = (
                    "This demo uses a Responses backend, not a client executor. "
                    "Please continue the English lesson."
                )
                await connection.session.commentary.append(
                    delegation_id=delegation.id,
                    content=content,
                )
        elif event.type == "response.event":
            if managed_delegation:
                # Only managed lifecycle events report validated prompt-agent output.
                return
            # Backend guidance is not the spoken teacher transcript.
            backend = event.event
            kind = backend.get("type")
            activity_id = event.delegation_id or "uncorrelated-backend"
            statuses = {
                "response.created": "Backend response started",
                "response.in_progress": "Backend response in progress",
                "response.output_text.delta": "Receiving backend guidance",
                "response.completed": "Backend response completed",
                "response.failed": "Backend response failed",
                "response.incomplete": "Backend response incomplete",
                "error": "Backend error",
            }
            if kind in statuses:
                transcript.update_agent_activity(
                    activity_id,
                    title=(
                        f"{'Delegation' if event.delegation_id else 'Uncorrelated backend'} "
                        f"→ {backend_model}"
                    ),
                    status=statuses[kind],
                    delta=(
                        backend.get("delta", "")
                        if kind == "response.output_text.delta"
                        else ""
                    ),
                )
            if kind in {
                "error",
                "response.failed",
                "response.incomplete",
            }:
                raise DemoError(
                    f"Teaching backend reported {backend['type']}; check its deployment "
                    "and configuration."
                )
        elif event.type == "session.closed":
            closed = True
            transcript.set_status(
                f"Session closed: {event.reason}; cumulative Live usage: "
                f"{event.usage.seconds} seconds"
            )
            if event.reason == "connection_lost":
                raise DemoError(
                    "Upstream connection was lost; native finalization is not confirmed."
                )

    async def receive():
        async for event in events:
            await observe(event)
            if closed:
                return
        raise DemoError(
            "WebSocket ended without session.closed; finalization is unconfirmed."
        )

    async def send_microphone():
        # audio.frames() yields PCM only; encoding and SDK calls belong to this sample.
        async for pcm in audio.frames(stop):
            encoded = base64.b64encode(pcm).decode("ascii")
            await connection.session.input_audio.append(audio=encoded)

    try:
        # Foundry owns session.start. Wait for service-owned readiness; do not start again.
        async with asyncio.timeout(30):
            async for event in events:
                await observe(event)
                if event.type == "session.started":
                    session_id = event.session.id
                    # Foundry adds this top-level field; it is not session.id.
                    # The OpenAI SDK preserves service-specific fields as extras.
                    value = getattr(event, "conversation_id", None)
                    if isinstance(value, str) and value.strip():
                        conversation_id = value
                    actual_format = event.session.audio.format
                    if actual_format and (actual_format.type, actual_format.rate) != (
                        "audio/pcm",
                        RATE,
                    ):
                        raise DemoError(
                            "The negotiated format is not the requested PCM16/24 kHz."
                        )
                    break
                if closed:
                    raise DemoError("Live closed before startup completed.")
            else:
                raise DemoError("WebSocket ended before session.started.")
        if not stop.is_set():
            transcript.set_status(
                f"Ready: {session_id}. Speak into your microphone; Ctrl+C ends the English lesson."
            )
            audio.start()
            audio_started = True
        receiver = asyncio.create_task(receive())
        sender = asyncio.create_task(send_microphone())
        stopped = asyncio.create_task(stop.wait())
        tasks.extend([receiver, sender, stopped])
        done, _ = await asyncio.wait(
            [receiver, sender, stopped], return_when=asyncio.FIRST_COMPLETED
        )
        if receiver in done:
            receiver.result()
        elif sender in done:
            sender.result()
        stop.set()
        audio.stop_microphone()
        sender.cancel()
        await asyncio.gather(sender, return_exceptions=True)
        if not receiver.done():
            transcript.set_status("Closing; waiting for session.closed...")
            close_sent = True
            async with asyncio.timeout(5):
                await connection.session.close()
            async with asyncio.timeout(15):
                await receiver
        if audio_started:
            await audio.drain()
        return conversation_id
    except ConnectionClosed as exc:
        close_context = sanitize_diagnostic(
            f"code={getattr(exc, 'code', 'unknown')} reason={getattr(exc, 'reason', '')}"
        )
        raise DemoError(
            "WebSocket ended without session.closed; finalization is unconfirmed. "
            + close_context
        ) from exc
    finally:
        stop.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if session_id and not closed and not close_sent:
            with contextlib.suppress(Exception):
                async with asyncio.timeout(3):
                    await connection.session.close()
        signal.signal(signal.SIGINT, old_sigint)


async def check_deployments(http, base, payload):
    """Check the configured model deployments with read-only requests."""
    definition = payload["definition"]
    deployments = {
        "GPT_LIVE_DEPLOYMENT": definition["model"],
    }
    delegation = definition.get("delegation") or {}
    if delegation.get("type") == "responses":
        deployments["RESPONSE_DELEGATION_DEPLOYMENT"] = delegation["responses"]["model"]
    for setting, name in deployments.items():
        response = await http.get(
            f"{base}/deployments/{quote(name, safe='')}",
            params={"api-version": API_VERSION},
        )
        if response.status_code == 404:
            raise DemoError(
                f"Deployment '{name}' was not found in this project. "
                f"Check the existing agent's deployment, or {setting} for a new agent. "
                + format_http_error(response, f"Check deployment '{name}'")
            )
        check_response(response, f"Check deployment '{name}'")
        if response.json().get("name") != name:
            raise DemoError(f"Deployment readback did not match {setting}='{name}'.")
        print(f"Deployment verified: {setting}={name}", flush=True)


async def main(
    *,
    input_wav: Path | None = None,
    no_playback: bool = False,
    save_audio: Path | None = None,
    tail_seconds: float = 12,
    result_json: Path | None = None,
    expect_backend: str | None = None,
):
    base = project_endpoint()
    name = required("AGENT_NAME")
    agent_url = f"{base}/agents/{quote(name, safe='')}"
    credential = project_credential()
    auth = EntraAuth(credential)
    async with (
        credential,
        httpx.AsyncClient(
            auth=auth,
            headers={"Foundry-Features": PREVIEW},
            timeout=30,
            follow_redirects=False,
        ) as http,
    ):
        evidence = SessionEvidence()
        with Audio(
            input_wav=input_wav,
            no_playback=no_playback,
            save_audio=save_audio,
            tail_seconds=tail_seconds,
        ) as audio:
            response = await http.get(agent_url, params={"api-version": API_VERSION})
            if response.status_code == 404:
                raise DemoError(
                    f"Agent '{name}' was not found. Deploy it with azd first. "
                    + format_http_error(response, "Read agent")
                )
            check_response(response, "Read agent")
            latest = response.json()["versions"]["latest"]
            definition = latest["definition"]
            if definition.get("sub_protocol") != "live":
                raise DemoError(
                    "AGENT_NAME must reference a GPT Live agent with sub_protocol=live."
                )
            version = latest["version"]
            print(f"Using azd-deployed agent: {name}, version {version}", flush=True)
            await check_deployments(http, base, {"definition": definition})
            delegation = definition.get("delegation") or {}
            managed_delegation = delegation.get("type") in {
                "foundry_managed_agent",
                "managed_prompt_agent",
            }
            backend_model = (
                f"{delegation['agent_name']}:{delegation.get('agent_version') or 'active'}"
                if managed_delegation
                else (delegation.get("responses") or {}).get("model")
                or delegation.get("type", "client")
            )

            async with AsyncOpenAI(
                api_key=auth.token_provider,
                base_url=f"{agent_url}/endpoint/protocols/voice",
                max_retries=0,
            ) as client:
                async with client.live.connect(
                    extra_headers={"Foundry-Features": PREVIEW},
                    extra_query={
                        "api-version": API_VERSION,
                        "x-agent-version-override": str(version),
                    },
                    max_retries=0,
                    websocket_connection_options={
                        "open_timeout": 20,
                        "close_timeout": 5,
                        "max_size": 1024 * 1024,
                    },
                ) as connection:
                    async with TranscriptDisplay() as transcript:
                        conversation_id = await converse(
                            connection,
                            audio,
                            transcript,
                            backend_model,
                            managed_delegation=managed_delegation,
                            event_handler=evidence.observe,
                        )
        if conversation_id:
            print(f"Conversation id: {conversation_id}", flush=True)
        else:
            print(
                "No persisted conversation id was returned (store may be false).",
                flush=True,
            )
        result = evidence.result()
        if result_json:
            await asyncio.to_thread(
                result_json.parent.mkdir, parents=True, exist_ok=True
            )
            await asyncio.to_thread(
                result_json.write_text,
                json.dumps(result, indent=2),
                encoding="utf-8",
            )
        if input_wav:
            if not (
                result["closed"]
                and result["input_transcript"].strip()
                and result["output_transcript"].strip()
                and result["output_audio_base64_chars"] > 0
                and result["correlated_completed_delegations"]
            ):
                raise DemoError(
                    "WAV smoke assertions did not all pass; inspect --result-json."
                )
            if expect_backend:
                guidance = "\n".join(result["backend_text"].values())
                if expect_backend.casefold() not in guidance.casefold():
                    raise DemoError(
                        f"Backend guidance did not contain expected text: {expect_backend!r}."
                    )


# HTTP authentication, URL construction, and error handling stay in this sample.
def required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise DemoError(f"Set {name} in .env or the process environment.")
    return value


def project_endpoint():
    value = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "").strip()
    if not value:
        raise DemoError(
            "Set FOUNDRY_PROJECT_ENDPOINT=https://YOUR-RESOURCE.services.ai.azure.com/"
            "api/projects/YOUR-PROJECT "
            "in .env. This creates a voice agent in an EXISTING project, not a new Azure project."
        )
    url = urlsplit(value.strip())
    local = url.hostname in {"localhost", "127.0.0.1", "::1"}
    path = url.path.rstrip("/")
    if (
        not url.hostname
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or (url.scheme != "https" and not (local and url.scheme == "http"))
        or not path.startswith("/api/projects/")
        or not path.removeprefix("/api/projects/")
        or "/" in path.removeprefix("/api/projects/")
    ):
        raise DemoError(
            "Use an HTTPS project endpoint ending in /api/projects/YOUR-PROJECT "
            "without credentials/query/fragment."
        )
    return urlunsplit((url.scheme, url.netloc, path, "", ""))


def project_credential():
    # Select the matching signed-in account without changing az's global default.
    subscription = os.getenv("AZURE_SUBSCRIPTION_ID", "").strip() or None
    return AzureCliCredential(subscription=subscription)


def sanitize_diagnostic(value, limit=500):
    """Keep useful error context while removing common credential/payload forms."""
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = _URL_QUERY.sub(r"\1?[REDACTED]", text)
    text = _BEARER.sub("Bearer [REDACTED]", text)
    text = _SECRET.sub(r"\1\2[REDACTED]", text)
    text = _PAYLOAD.sub(r"\1[REDACTED]", text)
    text = _LONG_DATA.sub("[REDACTED DATA]", text)
    text = " ".join(text.split())
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def _request_id(response=None, exception=None):
    headers = getattr(response, "headers", {}) or {}
    for name in ("x-request-id", "x-ms-request-id", "request-id"):
        if value := headers.get(name):
            return sanitize_diagnostic(value, 128)
    for name in ("request_id", "requestId"):
        if value := getattr(exception, name, None):
            return sanitize_diagnostic(value, 128)
    return None


def format_http_error(response, action, exception=None):
    status = getattr(response, "status_code", None) or getattr(
        exception, "status_code", None
    )
    parts = [f"{action}: HTTP {status or 'error'}"]
    try:
        body = response.json()
    except (AttributeError, TypeError, ValueError):
        body = None
    has_message = False
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict):
            if code := error.get("code"):
                parts.append(f"code={sanitize_diagnostic(code, 100)}")
            if message := error.get("message"):
                parts.append(f"message={sanitize_diagnostic(message)}")
                has_message = True
        elif isinstance(error, str) and error.strip():
            parts.append(f"message={sanitize_diagnostic(error)}")
            has_message = True
        if not has_message and (message := body.get("message")):
            parts.append(f"message={sanitize_diagnostic(message)}")
            has_message = True
    if not has_message:
        text = sanitize_diagnostic(getattr(response, "text", ""))
        if text:
            parts.append(f"message={text}")
    if request_id := _request_id(response, exception):
        parts.append(f"request_id={request_id}")
    return "; ".join(parts)


def format_unexpected_error(exc):
    response = getattr(exc, "response", None)
    status = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
    if status:
        detail = format_http_error(response, type(exc).__name__, exc)
    else:
        detail = type(exc).__name__
        if request_id := _request_id(exception=exc):
            detail += f"; request_id={request_id}"
    if not status and (message := sanitize_diagnostic(exc)):
        detail += f"; context={message}"
    return detail


def check_response(response, action):
    if response.is_success:
        return
    hint = {
        401: "Run az login again and check AZURE_SUBSCRIPTION_ID.",
        403: "Check the signed-in identity's project permissions and preview access.",
        404: "Check the project endpoint and whether this service has the Live implementation.",
        409: "The generated agent name already exists; run the demo again.",
        429: "Deployment quota is exhausted; retry later.",
    }.get(response.status_code, "Check the request and service configuration.")
    raise DemoError(f"{format_http_error(response, action)}. {hint}")


def run_cli():
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--input-wav", type=Path)
    parser.add_argument("--no-playback", action="store_true")
    parser.add_argument("--save-audio", type=Path)
    parser.add_argument("--tail-seconds", type=float, default=12)
    parser.add_argument("--result-json", type=Path)
    parser.add_argument("--expect-backend")
    args = parser.parse_args()
    try:
        load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)
        asyncio.run(
            main(
                input_wav=args.input_wav,
                no_playback=args.no_playback,
                save_audio=args.save_audio,
                tail_seconds=args.tail_seconds,
                result_json=args.result_json,
                expect_backend=args.expect_backend,
            )
        )
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130) from None
    except (ClientAuthenticationError, CredentialUnavailableError):
        print(
            "\nAzure CLI authentication failed. Run az login with an account that "
            "can access this project, and check AZURE_SUBSCRIPTION_ID in .env.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    except (DemoError, AudioError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as exc:
        print(f"\nUnexpected error: {format_unexpected_error(exc)}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    run_cli()
