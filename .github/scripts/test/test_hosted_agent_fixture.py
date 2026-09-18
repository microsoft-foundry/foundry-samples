#!/usr/bin/env python3
"""Unit tests for hosted-agent sample-to-fixture path resolution."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath

SCRIPTS = Path(__file__).resolve().parents[1]
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
            ".azure-pipelines/hosted-agent-tests/python/agent-framework/responses/06-files",
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
            ".azure-pipelines/hosted-agent-tests/csharp/agent-framework/file-tools",
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
                ".azure-pipelines/hosted-agent-tests/python/test-spec.yml"
            )

    def test_unknown_fixture_filename_is_rejected(self):
        with self.assertRaisesRegex(module.FixturePathError, "must end with"):
            module.sample_dir_for_fixture(
                ".azure-pipelines/hosted-agent-tests/python/example/README.md"
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


class SkiplistTests(unittest.TestCase):
    def test_comments_blank_lines_and_exact_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = "samples/python/hosted-agents/framework/example"
            path = root / module.CI_SKIPLIST
            path.parent.mkdir(parents=True)
            path.write_bytes(f"\ufeff# comment\r\n \r\n  {sample}  \r\n{sample}\r\n".encode("utf-8"))
            paths = module.load_skiplist(root, module.CI_SKIPLIST)
            self.assertEqual(paths, {PurePosixPath(sample)})
            self.assertNotIn(PurePosixPath(sample + "-other"), paths)

    def test_invalid_paths_and_missing_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / module.CI_SKIPLIST
            with self.assertRaises(module.FixturePathError):
                module.load_skiplist(root, module.CI_SKIPLIST)
            path.parent.mkdir(parents=True)
            for value in (
                "/absolute/path", "samples/python/agents/example",
                "samples/python/hosted-agents", "samples/python/hosted-agents/../example",
                "samples/python/hosted-agents//example", "samples/python/hosted-agents/example/",
                "samples/python/hosted-agents/foo\\bar",
            ):
                with self.subTest(path=value):
                    path.write_text(value, encoding="utf-8")
                    with self.assertRaises(module.FixturePathError):
                        module.load_skiplist(root, module.CI_SKIPLIST)

    def test_cli_exports_separate_whole_and_code_lists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = (module.CI_SKIPLIST, module.CODE_CI_SKIPLIST)
            samples = ("samples/python/hosted-agents/whole", "samples/csharp/hosted-agents/code")
            for filename, sample in zip(paths, samples):
                path = root / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(sample + "\n", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(0, module.main(["skiplists", "--repo-root", str(root)]))
            self.assertEqual(json.loads(output.getvalue()), {"samples": [samples[0]], "code": [samples[1]]})


if __name__ == "__main__":
    unittest.main()
