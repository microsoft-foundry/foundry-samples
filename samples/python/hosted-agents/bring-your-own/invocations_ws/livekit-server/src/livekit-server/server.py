# Copyright (c) Microsoft. All rights reserved.

"""FastAPI signaling server for the LiveKit sample.

The WebSocket is signaling only:

  client -> server  {"action": "join"}
  server -> client  {"type": "config",
                     "livekit_url": "ws://localhost:7880",
                     "token": "<JWT>",
                     "room": "chat-<uuid>",
                     "identity": "user-<uuid>"}

Once the browser receives the config it uses the LiveKit client SDK to
join the room directly. The agent worker (``agent.py``), running as a
separate process, is dispatched into the room by the LiveKit server.
Audio media flows browser <-> LiveKit <-> agent and never passes through
this server.

The signaling WebSocket can be closed by either side after ``config`` is
delivered; closing it does not tear down the LiveKit room.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import uuid
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from livekit import api
from livekit.protocol.agent_dispatch import RoomAgentDispatch
from livekit.protocol.room import RoomConfiguration
from loguru import logger

_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE / ".env", override=True)


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


def _public_livekit_url() -> str:
    """URL the BROWSER uses to reach the LiveKit server.

    Falls back to ``LIVEKIT_URL`` (used by the agent worker) when not set
    separately. Override with ``LIVEKIT_PUBLIC_URL`` when the agent runs
    in a container and the browser needs a different host (e.g., agent
    sees ``ws://livekit:7880`` while the browser needs
    ``ws://localhost:7880``).
    """
    return (
        os.environ.get("LIVEKIT_PUBLIC_URL")
        or os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
    ).strip()


def _mint_token(room: str, identity: str) -> str:
    api_key = os.environ.get("LIVEKIT_API_KEY", "").strip()
    api_secret = os.environ.get("LIVEKIT_API_SECRET", "").strip()
    if not api_key or not api_secret:
        raise RuntimeError(
            "LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set"
        )
    grants = api.VideoGrants(
        room_join=True,
        room=room,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
    )
    token = (
        api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(grants)
    )

    # Embed an explicit RoomAgentDispatch so this room is handled by
    # OUR worker (matching agent_name set in agent.py) instead of any
    # other auto-dispatch agent the LiveKit project may have.
    agent_name = os.environ.get(
        "LIVEKIT_AGENT_WORKER_NAME", "foundry-azure-voice"
    )
    token = token.with_room_config(
        RoomConfiguration(
            agents=[RoomAgentDispatch(agent_name=agent_name)],
        )
    )
    return token.to_jwt()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/readiness")
async def readiness():
    return {"status": "ok"}


@app.get("/liveness")
async def liveness():
    return {"status": "ok"}


@app.websocket("/invocations_ws")
async def signaling_ws(ws: WebSocket):
    """Signaling channel: hands the browser a LiveKit URL + access token."""
    await ws.accept()
    short = uuid.uuid4().hex[:8]
    room = f"chat-{short}"
    identity = f"user-{short}"
    logger.info("Signaling WS accepted; room={} identity={}", room, identity)

    try:
        # Wait briefly for the browser to send {"action": "join"}, but it's
        # OK if it doesn't -- we send the config either way.
        try:
            first = await asyncio.wait_for(ws.receive_text(), timeout=1.0)
            logger.debug("Received first signaling message: {}", first)
        except asyncio.TimeoutError:
            pass
        except WebSocketDisconnect:
            return

        try:
            token = _mint_token(room, identity)
        except Exception as e:
            await ws.send_json({"type": "error", "message": str(e)})
            await ws.close()
            return

        await ws.send_json(
            {
                "type": "config",
                "livekit_url": _public_livekit_url(),
                "token": token,
                "room": room,
                "identity": identity,
            }
        )

        # Keep the WS open so the chat_client portal can detect a clean
        # close; drain anything the browser sends.
        while True:
            try:
                msg = await ws.receive_text()
                logger.debug("Signaling msg: {}", msg)
            except WebSocketDisconnect:
                return
    except Exception as e:
        logger.exception("Signaling WS error: {}", e)
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
        try:
            await ws.close()
        except Exception:
            pass


async def main():
    port = int(os.environ.get("PORT", "8088"))

    # Spawn the LiveKit agent worker as a child process so a single
    # `python server.py` boots both the signaling endpoint and the
    # agent. Set RUN_AGENT_WORKER=0 to disable (e.g. when running the
    # worker yourself with `python agent.py dev`).
    run_worker = os.environ.get("RUN_AGENT_WORKER", "1") != "0"
    agent_proc: asyncio.subprocess.Process | None = None

    async def _agent_supervisor() -> None:
        """Keep the agent worker running. If it dies we log + restart with
        backoff. We deliberately do NOT bring down the FastAPI server when
        the worker fails -- the signaling endpoint must stay up so the
        Foundry hosted-agent runtime keeps the container marked healthy.
        """
        nonlocal agent_proc
        backoff = 1.0
        while True:
            agent_cmd = [sys.executable, str(_HERE / "agent.py"), "start"]
            logger.info("Launching agent worker: {}", " ".join(agent_cmd))
            agent_proc = await asyncio.create_subprocess_exec(*agent_cmd)
            rc = await agent_proc.wait()
            logger.error(
                "Agent worker exited (code={}); restarting in {:.1f}s",
                rc, backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    logger.info("LiveKit signaling server listening on :{}", port)

    supervisor_task = (
        asyncio.create_task(_agent_supervisor()) if run_worker else None
    )

    try:
        await server.serve()
    finally:
        if supervisor_task:
            supervisor_task.cancel()
            try:
                await supervisor_task
            except (asyncio.CancelledError, Exception):
                pass
        if agent_proc and agent_proc.returncode is None:
            try:
                agent_proc.send_signal(signal.SIGTERM)
                await asyncio.wait_for(agent_proc.wait(), timeout=5)
            except (ProcessLookupError, asyncio.TimeoutError):
                try:
                    agent_proc.kill()
                except ProcessLookupError:
                    pass


if __name__ == "__main__":
    asyncio.run(main())
