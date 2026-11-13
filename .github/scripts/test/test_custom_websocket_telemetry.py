"""Regressions for telemetry startup in custom, non-AgentServer WebSocket apps."""

from __future__ import annotations

import ast
import importlib.util
import logging
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[3]
RUNTIMES = (
    ("livekit-server", "livekit-server"),
    ("pipecat-webrtc", "pipecat-ws-webrtc"),
    ("pipecat-ws-server", "pipecat-ws-server"),
)


def runtime_path(sample: str, project: str) -> Path:
    return (
        ROOT
        / "samples/python/hosted-agents/bring-your-own/invocations_ws"
        / sample
        / "src"
        / project
    )


class CustomWebSocketTelemetryTests(unittest.TestCase):
    def test_default_setup_is_idempotent_and_preserves_safe_log_settings(self) -> None:
        for sample, project in RUNTIMES:
            for connection_string in (None, "test-connection"):
                with self.subTest(sample=sample, connection=connection_string):
                    distro = types.ModuleType("microsoft.opentelemetry")
                    configure = MagicMock()
                    distro.use_microsoft_opentelemetry = configure
                    loguru = types.ModuleType("loguru")
                    loguru.logger = MagicMock()
                    modules = {"microsoft.opentelemetry": distro, "loguru": loguru}
                    spec = importlib.util.spec_from_file_location(
                        "custom_telemetry_under_test",
                        runtime_path(sample, project) / "telemetry.py",
                    )
                    assert spec and spec.loader
                    module = importlib.util.module_from_spec(spec)
                    with (
                        patch.dict(sys.modules, modules),
                        patch.dict(os.environ, {}, clear=True),
                        patch.object(logging, "basicConfig") as configure_logging,
                    ):
                        if connection_string:
                            os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"] = (
                                connection_string
                            )
                        spec.loader.exec_module(module)
                        with patch.object(module, "find_spec", return_value=None):
                            module.configure_telemetry()
                            module.configure_telemetry()
                        configure_logging.assert_called_once_with(level=logging.INFO)
                        configure.assert_called_once_with(
                            enable_azure_monitor=bool(connection_string),
                            azure_monitor_connection_string=connection_string,
                            enable_sensitive_data=False,
                            instrumentation_options={"openai": {"enabled": False}},
                        )
                        loguru.logger.remove.assert_called_once()
                        sink = loguru.logger.add.call_args
                        self.assertIsInstance(sink.args[0], logging.Handler)
                        self.assertEqual(sink.kwargs["level"], "INFO")
                        self.assertFalse(sink.kwargs["diagnose"])
                        self.assertFalse(sink.kwargs["backtrace"])

    def test_loguru_sink_forwards_records_to_standard_logging(self) -> None:
        for sample, project in RUNTIMES:
            with self.subTest(sample=sample):
                distro = types.ModuleType("microsoft.opentelemetry")
                distro.use_microsoft_opentelemetry = MagicMock()
                loguru = types.ModuleType("loguru")
                loguru.logger = MagicMock()
                spec = importlib.util.spec_from_file_location(
                    "custom_telemetry_under_test",
                    runtime_path(sample, project) / "telemetry.py",
                )
                assert spec and spec.loader
                module = importlib.util.module_from_spec(spec)
                with patch.dict(
                    sys.modules, {"microsoft.opentelemetry": distro, "loguru": loguru}
                ):
                    spec.loader.exec_module(module)
                    record = logging.makeLogRecord(
                        {
                            "name": "custom.websocket",
                            "msg": "Connection accepted",
                            "levelno": logging.INFO,
                        }
                    )
                    with patch.object(logging, "getLogger") as get_logger:
                        module.ForwardToLogging().emit(record)
                        get_logger.assert_called_once_with("custom.websocket")
                        get_logger.return_value.handle.assert_called_once_with(record)

    def test_each_server_initializes_telemetry_before_bot_import_or_app_creation(
        self,
    ) -> None:
        for sample, project in RUNTIMES:
            with self.subTest(sample=sample):
                tree = ast.parse(
                    (runtime_path(sample, project) / "server.py").read_text(
                        encoding="utf-8-sig"
                    )
                )
                setup = [
                    node.lineno
                    for node in tree.body
                    if isinstance(node, ast.Expr)
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == "configure_telemetry"
                ]
                apps = [
                    node.lineno
                    for node in tree.body
                    if isinstance(node, ast.Assign)
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == "FastAPI"
                ]
                self.assertEqual(len(setup), 1)
                self.assertTrue(apps and setup[0] < min(apps))

    def test_livekit_worker_initializes_each_process_and_does_not_log_payloads(
        self,
    ) -> None:
        tree = ast.parse(
            (runtime_path("livekit-server", "livekit-server") / "agent.py").read_text(
                encoding="utf-8-sig"
            )
        )
        entrypoint = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "entrypoint"
        )
        calls = [node for node in ast.walk(entrypoint) if isinstance(node, ast.Call)]
        self.assertTrue(
            any(
                isinstance(node.func, ast.Name)
                and node.func.id == "configure_telemetry"
                for node in calls
            )
        )
        logs = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "info"
        ]
        self.assertFalse(
            any(
                any(
                    isinstance(argument, ast.Name) and argument.id == "payload"
                    for argument in node.args
                )
                for node in logs
            )
        )

    def test_pipecat_info_logs_do_not_include_model_supplied_reasons(self) -> None:
        tree = ast.parse(
            (
                runtime_path("pipecat-ws-server", "pipecat-ws-server")
                / "bot_websocket_server.py"
            ).read_text(encoding="utf-8-sig")
        )
        logs = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "info"
        ]
        self.assertFalse(
            any(
                any(
                    isinstance(item, ast.Name) and item.id == "reason"
                    for argument in node.args
                    for item in ast.walk(argument)
                )
                for node in logs
            )
        )


if __name__ == "__main__":
    unittest.main()
