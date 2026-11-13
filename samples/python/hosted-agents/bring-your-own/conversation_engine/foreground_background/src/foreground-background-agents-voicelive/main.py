"""Foreground/background agents hosted on the conversation-engine protocol."""

import logging
import os

from agent_logic import ForegroundBackgroundAgent
from conversation_runtime import create_app


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
    create_app(ForegroundBackgroundAgent.from_environment()).run()


if __name__ == "__main__":
    main()
