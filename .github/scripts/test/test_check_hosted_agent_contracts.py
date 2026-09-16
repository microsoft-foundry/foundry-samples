#!/usr/bin/env python3
"""Unit tests for new hosted-agent behavior-contract coverage policy."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "check_hosted_agent_contracts", SCRIPTS / "check_hosted_agent_contracts.py"
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)

SAMPLE = PurePosixPath(
    "samples/python/hosted-agents/agent-framework/responses/new-agent"
)
MANIFEST = """\
services:
  agent:
    host: azure.ai.agent
    protocols:
      - protocol: responses
        version: 1.0.0
"""
CONTRACT = """\
version: 1
sample:
  owner: sampleowner
  experiences: [azd]
tests:
  - name: defining-behavior
    turns:
      - input: hello
        assertions:
          - source: assistant_text
            type: contains
            value: hello
"""


class ChangeClassificationTests(unittest.TestCase):
    def test_new_manifest_adds_sample(self):
        result = module.new_sample_dirs(set(), {SAMPLE / "azure.yaml"})
        self.assertEqual(result, [SAMPLE])

    def test_existing_sample_update_is_ignored(self):
        manifests = {SAMPLE / "azure.yaml"}
        self.assertEqual(module.new_sample_dirs(manifests, manifests), [])

    def test_deleted_sample_is_ignored(self):
        self.assertEqual(module.new_sample_dirs({SAMPLE / "azure.yaml"}, set()), [])

    def test_moved_sample_is_not_a_new_onboarding(self):
        old = PurePosixPath(
            "samples/python/hosted-agents/agent-framework/responses/old-agent/azure.yaml"
        )
        destination = SAMPLE / "azure.yaml"
        self.assertEqual(
            module.new_sample_dirs({old}, {destination}, {destination}), []
        )


class GitChangeTests(unittest.TestCase):
    def test_manifest_rename_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(
                ["git", "config", "user.email", "ci@example.com"], cwd=repo, check=True
            )
            subprocess.run(["git", "config", "user.name", "CI"], cwd=repo, check=True)
            old = repo / "samples/python/hosted-agents/framework/responses/old"
            old.mkdir(parents=True)
            (old / "azure.yaml").write_text(MANIFEST, encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "old"], cwd=repo, check=True)
            new = repo / SAMPLE
            new.parent.mkdir(parents=True, exist_ok=True)
            old.rename(new)
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "move"], cwd=repo, check=True)

            destinations = module.renamed_manifest_destinations(repo, "HEAD^", "HEAD")
            self.assertEqual(destinations, {SAMPLE / "azure.yaml"})


class ContractCoverageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.repo = Path(self.directory.name)
        sample_dir = self.repo / SAMPLE
        sample_dir.mkdir(parents=True)
        (sample_dir / "azure.yaml").write_text(MANIFEST, encoding="utf-8")

    def tearDown(self):
        self.directory.cleanup()

    def fixture_spec(self) -> Path:
        fixture = module.fixture_dir_for_sample(str(SAMPLE))
        return self.repo / fixture / "test-spec.yml"

    def test_new_sample_without_contract_fails(self):
        errors = module.check_new_samples(self.repo, [SAMPLE])
        self.assertEqual(len(errors), 1)
        error = errors[0]
        self.assertIn("Missing hosted-agent behavior contract", error)
        self.assertIn(str(SAMPLE), error)
        self.assertIn("agent-framework/responses/new-agent/test-spec.yml", error)
        self.assertIn("--protocol responses", error)
        self.assertIn("hosted_agent_test_spec.py validate", error)
        self.assertIn(module.DOCUMENTATION_URL, error)

    def test_new_sample_with_valid_contract_passes(self):
        spec = self.fixture_spec()
        spec.parent.mkdir(parents=True)
        spec.write_text(CONTRACT, encoding="utf-8")
        self.assertEqual(module.check_new_samples(self.repo, [SAMPLE]), [])

    def test_contract_schema_errors_fail(self):
        spec = self.fixture_spec()
        spec.parent.mkdir(parents=True)
        invalid_contracts = (
            CONTRACT.replace("  owner: sampleowner\n", ""),
            CONTRACT.replace("owner: sampleowner", "owner: user@example.com"),
            CONTRACT.replace("experiences: [azd]", "experiences: []"),
            CONTRACT.replace("version: 1", "version: 1\nversion: 1"),
            CONTRACT.replace("source: assistant_text", "source: console_log"),
        )
        for contract in invalid_contracts:
            with self.subTest(contract=contract):
                spec.write_text(contract, encoding="utf-8")
                errors = module.check_new_samples(self.repo, [SAMPLE])
                self.assertEqual(len(errors), 1)
                self.assertIn("Invalid hosted-agent behavior contract", errors[0])

    def test_public_contract_location(self):
        self.assertEqual(
            self.fixture_spec().relative_to(self.repo).as_posix(),
            ".azure-pipelines/hosted-agent-tests/python/agent-framework/responses/new-agent/test-spec.yml",
        )

    def test_malformed_contract_fails(self):
        spec = self.fixture_spec()
        spec.parent.mkdir(parents=True)
        spec.write_text("version: 1\n", encoding="utf-8")
        errors = module.check_new_samples(self.repo, [SAMPLE])
        self.assertEqual(len(errors), 1)
        error = errors[0]
        self.assertIn("Invalid hosted-agent behavior contract", error)
        self.assertIn("Problem:\n  document is missing key(s): sample, tests", error)
        self.assertIn("hosted_agent_test_spec.py validate", error)
        self.assertIn(module.DOCUMENTATION_URL, error)

    def test_protocol_incompatible_contract_fails_planning(self):
        manifest = self.repo / SAMPLE / "azure.yaml"
        manifest.write_text(
            MANIFEST.replace("protocol: responses", "protocol: invocations"),
            encoding="utf-8",
        )
        spec = self.fixture_spec()
        spec.parent.mkdir(parents=True)
        spec.write_text(CONTRACT, encoding="utf-8")
        errors = module.check_new_samples(self.repo, [SAMPLE])
        self.assertEqual(len(errors), 1)
        self.assertIn("assistant_text", errors[0])

    def test_ci_skipped_sample_does_not_require_contract(self):
        (self.repo / SAMPLE / ".ci-skip").touch()
        self.assertEqual(module.check_new_samples(self.repo, [SAMPLE]), [])

    def test_malformed_manifest_reports_policy_error(self):
        manifest = self.repo / SAMPLE / "azure.yaml"
        manifest.write_text("services: []\n", encoding="utf-8")
        spec = self.fixture_spec()
        spec.parent.mkdir(parents=True)
        spec.write_text(CONTRACT, encoding="utf-8")
        errors = module.check_new_samples(self.repo, [SAMPLE])
        self.assertEqual(len(errors), 1)
        self.assertIn("Manifest:\n  " + str(SAMPLE / "azure.yaml"), errors[0])
        self.assertIn("Problem:\n  services must be a mapping", errors[0])
        self.assertIn(module.DOCUMENTATION_URL, errors[0])


if __name__ == "__main__":
    unittest.main()
