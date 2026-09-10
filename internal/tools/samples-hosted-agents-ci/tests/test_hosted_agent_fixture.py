#!/usr/bin/env python3
"""Unit tests for hosted-agent sample-to-fixture path resolution."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location(
    "hosted_agent_fixture", SCRIPTS / "hosted_agent_fixture.py"
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class FixturePathTests(unittest.TestCase):
    def test_python_path_preserves_framework_and_protocol(self):
        result = module.fixture_dir_for_sample(
            "samples/python/hosted-agents/agent-framework/responses/06-files"
        )
        self.assertEqual(
            str(result),
            "internal/tools/samples-hosted-agents/python/agent-framework/responses/06-files",
        )

    def test_same_basename_maps_to_distinct_fixture(self):
        first = module.fixture_dir_for_sample(
            "samples/python/hosted-agents/agent-framework/responses/06-files"
        )
        second = module.fixture_dir_for_sample(
            "samples/python/hosted-agents/langgraph/responses/06-files"
        )
        self.assertNotEqual(first, second)

    def test_csharp_path_without_protocol_directory_is_preserved(self):
        result = module.fixture_dir_for_sample(
            "samples/csharp/hosted-agents/agent-framework/file-tools"
        )
        self.assertEqual(
            str(result),
            "internal/tools/samples-hosted-agents/csharp/agent-framework/file-tools",
        )

    def test_fixture_round_trip(self):
        sample = "samples/python/hosted-agents/bring-your-own/invocations/toolbox"
        fixture = module.fixture_dir_for_sample(sample)
        resolved = module.sample_dir_for_fixture(str(fixture / "test-spec.yml"))
        self.assertEqual(str(resolved), sample)

    def test_payload_fixture_round_trip(self):
        sample = "samples/csharp/hosted-agents/agent-framework/browser-automation"
        fixture = module.fixture_dir_for_sample(sample)
        resolved = module.sample_dir_for_fixture(str(fixture / "test-payload.txt"))
        self.assertEqual(str(resolved), sample)

    def test_sample_outside_supported_roots_is_rejected(self):
        with self.assertRaisesRegex(module.FixturePathError, "must be below"):
            module.fixture_dir_for_sample("samples/python/agents/example")

    def test_orphan_fixture_shape_is_rejected(self):
        with self.assertRaisesRegex(module.FixturePathError, "sample path"):
            module.sample_dir_for_fixture(
                "internal/tools/samples-hosted-agents/python/test-spec.yml"
            )

    def test_unknown_fixture_filename_is_rejected(self):
        with self.assertRaisesRegex(module.FixturePathError, "must end with"):
            module.sample_dir_for_fixture(
                "internal/tools/samples-hosted-agents/python/example/README.md"
            )

    def test_non_normalized_path_is_rejected(self):
        with self.assertRaisesRegex(module.FixturePathError, "normalized"):
            module.fixture_dir_for_sample(
                "samples/python/hosted-agents/../hosted-agents/example"
            )

    def test_cli_reports_resolution_errors_on_stderr(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = module.main(
                ["fixture-dir", "--sample-dir", "samples/python/agents/example"]
            )
        self.assertEqual(result, 2)
        self.assertIn("error:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
