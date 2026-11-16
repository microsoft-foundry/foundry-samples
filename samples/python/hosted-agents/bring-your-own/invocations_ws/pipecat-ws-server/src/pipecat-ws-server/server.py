# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(override=False)

from bot_websocket_server import run_bot


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


@app.websocket("/invocations_ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection accepted")
    try:
        await run_bot(websocket)
    except Exception:
        logger.exception("run_bot failed")


async def main():
    port = int(os.environ.get("PORT", "8088"))
    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
