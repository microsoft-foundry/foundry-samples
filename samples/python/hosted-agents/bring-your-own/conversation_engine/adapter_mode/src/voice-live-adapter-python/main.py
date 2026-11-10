# Copyright (c) Microsoft. All rights reserved.

"""CE-only entry point: attach the in-process adapter to the Echo handler."""

from __future__ import annotations

import logging
import os
from typing import Any

from azure.ai.agentserver.invocations.voice import VoiceAgentServerHost

from adapter.runtime import create_app as create_voice_app
from echo_agent import handle_invocation


def create_app(**host_options: Any) -> VoiceAgentServerHost:
    """Create the Voice Live Bridge application."""
    return create_voice_app(handle_invocation, **host_options)


def main() -> None:
    """Run the hosted-agent server."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    create_app().run()


if __name__ == "__main__":
    main()
