# Copyright (c) Microsoft. All rights reserved.

"""Entry point for the basic Python Voice Live Bridge hosted agent."""

from __future__ import annotations

import logging
import os
from typing import Any

from azure.ai.agentserver.invocations.voice import VoiceAgentServerHost

from voice_runtime import create_app as create_voice_app


def create_app(**host_options: Any) -> VoiceAgentServerHost:
    """Create the Voice Live Bridge application."""
    return create_voice_app(**host_options)


def main() -> None:
    """Run the hosted-agent server."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    create_app().run()


if __name__ == "__main__":
    main()
