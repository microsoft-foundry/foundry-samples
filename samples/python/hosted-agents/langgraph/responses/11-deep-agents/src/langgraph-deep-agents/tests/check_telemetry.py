"""Opt-in local check for host telemetry; not part of CI discovery."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


class DefaultTelemetryTests(unittest.TestCase):
    def test_stock_host_captures_content_by_default_and_honors_opt_out(self) -> None:
        environment = dict(os.environ)
        for key in (
            "OTEL_SDK_DISABLED",
            "APPLICATIONINSIGHTS_CONNECTION_STRING",
            "APPLICATION_INSIGHTS_CONNECTION_STRING",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
        ):
            environment.pop(key, None)
        environment["PYTHON_DOTENV_DISABLED"] = "1"
        for capture_content in (True, False):
            with self.subTest(capture_content=capture_content):
                if not capture_content:
                    environment["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = (
                        "false"
                    )
                result = subprocess.run(
                    [sys.executable, str(Path(__file__).with_name("telemetry_probe.py"))],
                    env=environment,
                    capture_output=True,
                    check=False,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stderr[-3000:])
                self.assertEqual(result.stderr.count("Published report report-v1.md"), 1)
                summaries = [
                    json.loads(line)
                    for line in result.stdout.splitlines()
                    if line.startswith('{"model_requests":')
                ]
                self.assertEqual(len(summaries), 1, result.stdout[-3000:])
                summary = summaries[0]
                self.assertEqual(summary["model_requests"], 3)
                self.assertEqual(summary["chat_spans"], 3)
                self.assertEqual(summary["tool_spans"], ["publish_report", "write_file"])
                for source in ("user", "model", "tool_input", "tool_output"):
                    self.assertEqual(summary[f"{source}_captured"], capture_content, source)


if __name__ == "__main__":
    unittest.main()
