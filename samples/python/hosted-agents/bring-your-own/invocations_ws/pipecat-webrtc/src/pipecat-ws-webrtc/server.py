# Copyright (c) Microsoft. All rights reserved.

"""FastAPI server for the pipecat + SmallWebRTC sample.

Mirrors the WebSocket-based ``invocations_ws`` contract used by the sibling
``pipecat-ws-server`` sample, but instead of streaming protobuf audio frames
the WebSocket here is used as the WebRTC *signaling* channel:

  client -> server  {"action": "ice_config"}
  server -> client  {"iceServers": [...]}

  client -> server  {"action": "offer", "data": {"sdp": "...", "type": "offer"}}
  server -> client  {"answer": {"sdp": "...", "type": "answer", "pc_id": "..."}}

  client -> server  {"action": "ice_candidate",
                     "data": {"candidate": "...",
                              "sdp_mid": "...",
                              "sdp_mline_index": 0}}
  server -> client  {"status": "ok"}

  client -> server  {"action": "disconnect"}    (or close the WebSocket)

Once the offer/answer exchange completes, audio flows directly over the
WebRTC peer connection while RTVI control messages travel over the WebRTC
data channel created by the client. The signaling WebSocket can be closed
or left open; closing it does *not* tear down the media connection.
"""

import asyncio
import os
from pathlib import Path
from typing import Any

import uvicorn
from aiortc.sdp import candidate_from_sdp
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from telemetry import configure_telemetry

# Load .env from the same directory as this file BEFORE importing the bot.
load_dotenv(
    Path(__file__).resolve().parent / ".env", override=False
)

configure_telemetry()

from bot_webrtc_server import run_bot  # noqa: E402
from pipecat.transports.smallwebrtc.connection import (  # noqa: E402
    IceServer,
    SmallWebRTCConnection,
)


# ---------------------------------------------------------------------------
# ICE server configuration
# ---------------------------------------------------------------------------

# A public STUN server is always included so the browser can discover its
# server-reflexive (srflx) candidate. This alone is enough for local dev on
# most home networks but will fail behind symmetric NAT and in containerized
# deployments (Azure Container Apps, etc.) where the server has no inbound
# UDP path. For those, supply TURN credentials via the env vars below.
_DEFAULT_STUN_URL = "stun:stun.l.google.com:19302"


def _load_ice_config_from_env() -> dict[str, list[dict[str, Any]]]:
    """Build an iceServers list from env vars.

    Always includes a public STUN server. If ``WEBRTC_TURN_URL`` is set, a
    TURN entry is appended using ``WEBRTC_TURN_USERNAME`` and
    ``WEBRTC_TURN_CREDENTIAL``. ``WEBRTC_TURN_STUN_URL`` (optional) lets you
    advertise the TURN provider's own STUN endpoint alongside the relay so
    the browser can discover srflx candidates through the same host.
    """
    ice_servers: list[dict[str, Any]] = [{"urls": [_DEFAULT_STUN_URL]}]

    turn_url = os.environ.get("WEBRTC_TURN_URL", "").strip()
    if not turn_url:
        logger.warning(
            "WEBRTC_TURN_URL not set — falling back to public STUN only. "
            "WebRTC will fail behind symmetric NAT or in containerized "
            "deployments (Azure Container Apps, etc.). Provide TURN "
            "credentials via WEBRTC_TURN_URL / WEBRTC_TURN_USERNAME / "
            "WEBRTC_TURN_CREDENTIAL for production use."
        )
        return {"iceServers": ice_servers}

    username = os.environ.get("WEBRTC_TURN_USERNAME", "").strip()
    credential = os.environ.get("WEBRTC_TURN_CREDENTIAL", "").strip()
    if not (username and credential):
        raise RuntimeError(
            "WEBRTC_TURN_URL is set but WEBRTC_TURN_USERNAME and/or "
            "WEBRTC_TURN_CREDENTIAL is missing."
        )

    urls = [turn_url]
    turn_stun_url = os.environ.get("WEBRTC_TURN_STUN_URL", "").strip()
    if turn_stun_url:
        urls.append(turn_stun_url)

    ice_servers.append(
        {"urls": urls, "username": username, "credential": credential}
    )
    logger.info(f"Using TURN relay from WEBRTC_TURN_URL ({len(urls)} url(s))")
    return {"iceServers": ice_servers}


async def _build_ice_config() -> dict[str, list[dict[str, Any]]]:
    # Kept async so callers don't need to change if we later add an async
    # token-refresh path (e.g. user-supplied refresh URL).
    return _load_ice_config_from_env()


def _ice_servers_for_aiortc(
    ice_config: dict[str, list[dict[str, Any]]],
) -> list[IceServer]:
    servers: list[IceServer] = []
    for s in ice_config.get("iceServers", []):
        urls = s.get("urls", [])
        if isinstance(urls, str):
            urls = [urls]
        if not urls:
            continue
        servers.append(
            IceServer(
                urls=urls,
                username=s.get("username"),
                credential=s.get("credential"),
            )
        )
    return servers


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI()
# Configure CORS for the sample. Wildcard origins cannot be combined with
# credentialed requests in browsers, so credentials are disabled here.
# For production deployments, replace allow_origins with an explicit allowlist.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/readiness")
async def readiness():
    return {"status": "ok"}


@app.get("/liveness")
async def liveness():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# WebRTC signaling over WebSocket
# ---------------------------------------------------------------------------


@app.websocket("/invocations_ws")
async def signaling_ws(ws: WebSocket):
    """Run a single WebRTC signaling session.

    The peer connection lives in this coroutine; closing the WebSocket
    cleanly (or sending an ``action: disconnect``) tears it down.
    """
    await ws.accept()
    logger.info("Signaling WebSocket accepted")

    pc: SmallWebRTCConnection | None = None
    bot_task: asyncio.Task | None = None
    cached_ice_config: dict[str, Any] | None = None

    try:
        while True:
            msg = await ws.receive_json()
            action = msg.get("action")
            data = msg.get("data") or {}

            if action == "ice_config":
                cached_ice_config = await _build_ice_config()
                await ws.send_json(cached_ice_config)
                continue

            if action == "offer":
                if pc is not None:
                    await ws.send_json(
                        {"error": "peer_connection_already_exists"}
                    )
                    continue

                if cached_ice_config is None:
                    cached_ice_config = await _build_ice_config()
                ice_servers = _ice_servers_for_aiortc(cached_ice_config)

                pc = SmallWebRTCConnection(ice_servers=ice_servers)

                @pc.event_handler("closed")
                async def _on_pc_closed(_conn):
                    logger.info("Peer connection closed")
                    try:
                        await ws.send_json({"type": "closed"})
                    except Exception:
                        pass

                await pc.initialize(sdp=data["sdp"], type=data["type"])

                async def _run_and_log():
                    try:
                        await run_bot(pc)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        logger.exception("Bot runner crashed")

                bot_task = asyncio.create_task(_run_and_log())

                answer = pc.get_answer()
                await ws.send_json({"answer": answer})
                continue

            if action == "ice_candidate":
                if pc is None:
                    await ws.send_json({"error": "no_peer_connection"})
                    continue
                raw = data.get("candidate", "")
                if not raw:
                    await ws.send_json({"status": "ok"})
                    continue
                if raw.startswith("candidate:"):
                    raw = raw.split(":", 1)[1]
                try:
                    candidate = candidate_from_sdp(raw)
                    candidate.sdpMid = data.get("sdp_mid")
                    candidate.sdpMLineIndex = data.get("sdp_mline_index")
                    await pc.add_ice_candidate(candidate)
                except Exception as e:
                    logger.warning(f"add_ice_candidate failed: {e}")
                await ws.send_json({"status": "ok"})
                continue

            if action == "disconnect":
                logger.info("Client requested disconnect")
                break

            await ws.send_json({"error": f"unknown_action:{action}"})

    except WebSocketDisconnect:
        logger.info("Signaling WebSocket disconnected by client")
    except Exception:
        logger.exception("Signaling WebSocket error")
    finally:
        if pc is not None:
            try:
                await pc.disconnect()
            except Exception:
                logger.exception("Error during pc.disconnect()")
        if bot_task is not None and not bot_task.done():
            bot_task.cancel()
            try:
                await bot_task
            except (asyncio.CancelledError, Exception):
                pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    host = os.environ.get("SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8089"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
