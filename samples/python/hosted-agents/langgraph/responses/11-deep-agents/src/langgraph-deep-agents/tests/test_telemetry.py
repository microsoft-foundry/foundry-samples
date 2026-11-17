"""Check default telemetry independently of other tests' global instrumentation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


class DefaultTelemetryTests(unittest.TestCase):
    def test_stock_host_records_content_by_default(self) -> None:
        self.check_content_capture(None)

    def test_explicit_opt_out_keeps_spans_and_logs_without_content(self) -> None:
        self.check_content_capture("false")

    def check_content_capture(self, setting: str | None) -> None:
        environment = dict(os.environ)
        for key in (
            "OTEL_SDK_DISABLED",
            "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED",
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT",
            "APPLICATIONINSIGHTS_CONNECTION_STRING",
            "APPLICATION_INSIGHTS_CONNECTION_STRING",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
        ):
            environment.pop(key, None)
        if setting is not None:
            environment["AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"] = setting
            environment["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = setting
        else:
            environment["AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"] = "true"
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("telemetry_probe.py"))],
            env=environment,
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        summaries = [
            json.loads(line)
            for line in result.stdout.splitlines()
            if line.startswith('{"telemetry_enabled":')
        ]
        self.assertEqual(len(summaries), 1, result.stdout[-3000:])
        summary = summaries[0]
        self.assertTrue(summary["telemetry_enabled"])
        self.assertEqual(summary["publication_span_count"], 1)
        self.assertEqual(summary["message_content_captured"], setting is None)
        self.assertEqual(summary["tool_content_captured"], setting is None)


if __name__ == "__main__":
    unittest.main()
