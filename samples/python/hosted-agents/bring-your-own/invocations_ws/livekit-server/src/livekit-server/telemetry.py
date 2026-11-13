"""Configure default INFO logs and OpenTelemetry for a custom WebSocket server."""

from __future__ import annotations

import logging
import os
from importlib.util import find_spec

from loguru import logger
from microsoft.opentelemetry import use_microsoft_opentelemetry

_configured = False


class ForwardToLogging(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        logging.getLogger(record.name).handle(record)


def configure_telemetry() -> None:
    """Use one provider per process and keep sensitive framework content opt-in."""
    global _configured
    if _configured:
        return
    logging.basicConfig(level=logging.INFO)
    connection_string = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    use_microsoft_opentelemetry(
        enable_azure_monitor=bool(connection_string),
        azure_monitor_connection_string=connection_string,
        enable_sensitive_data=False,
        instrumentation_options={
            "openai": {
                "enabled": find_spec("openai") is not None
                and find_spec("httpx") is not None
            }
        },
    )
    logger.remove()
    logger.add(
        ForwardToLogging(),
        level="INFO",
        format="{message}",
        backtrace=False,
        diagnose=False,
    )
    _configured = True
