"""Offline discovery tests for prompt-agent matrix selection."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "discover_samples.py"
SPEC = importlib.util.spec_from_file_location("prompt_discovery", SCRIPT)
discovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(discovery)
SAMPLE_ROOT = "samples/cli/prompt-agents"


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.repo = Path(directory.name)
        (self.repo / SAMPLE_ROOT).mkdir(parents=True)
        blacklist = self.repo / discovery.BLACKLIST_PATH
        blacklist.parent.mkdir(parents=True)
        blacklist.write_text("{}", encoding="utf-8")


    def sample(self, name="01-basic", *, managed=False, harness_type="microsoft_copilot_preview"):
        path = self.repo / SAMPLE_ROOT / name / "azure.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        agent = {"host": "azure.ai.agent", "kind": "prompt", "uses": ["project"]}
        if managed:
            agent["harness"] = {"type": harness_type}
        document = {"name": name, "services": {
            "project": {"host": "azure.ai.project"}, "agent": agent,
        }}
        path.write_text(yaml.safe_dump(document), encoding="utf-8")
        return path

    def test_accepts_multiple_harness_identifiers_and_rejects_invalid_harness(self):
        for harness_type in ("github_copilot_preview", "microsoft_copilot_preview"):
            with self.subTest(harness_type=harness_type):
                self.sample("04-foundry-toolbox", managed=True, harness_type=harness_type)
                entry = discovery.discover(self.repo)["entries"][0]
                self.assertEqual(entry["executionProfile"], "managed")
                self.assertEqual(entry["harnessType"], harness_type)
        for bad_harness in ("", "bad harness", {"type": ""}, {"type": "ok", "extra": 1}):
            with self.subTest(bad_harness=bad_harness):
                manifest = self.sample("04-foundry-toolbox")
                doc = yaml.safe_load(manifest.read_text(encoding="utf-8"))
                doc["services"]["agent"]["harness"] = bad_harness
                manifest.write_text(yaml.safe_dump(doc), encoding="utf-8")
                with self.assertRaisesRegex(discovery.DiscoveryError, "harness.type must be a nonempty identifier"):
                    discovery.discover(self.repo)

    def test_profiles_fixture_changes_and_full_run_paths(self):
        self.sample()
        self.sample("04-foundry-toolbox", managed=True)
        result = discovery.discover(self.repo)
        self.assertEqual((result["count"], result["count_prompt"], result["count_managed"]), (2, 1, 1))
        self.assertEqual(len(result["matrix_all"]), 2)
        fixture = ".azure-pipelines/prompt-agent-tests/cli/04-foundry-toolbox/test-spec.yml"
        selected = discovery.discover(self.repo, [fixture])
        self.assertEqual([entry["executionProfile"] for entry in selected["entries"]], ["managed"])
        for path in discovery.FULL_RUN_PATHS | {discovery.BLACKLIST_PATH}:
            with self.subTest(path=path):
                self.assertEqual(discovery.discover(self.repo, [path]), result)

    def test_blacklist_and_filter_cannot_select_excluded_sample(self):
        self.sample()
        self.sample("02-tools")
        (self.repo / discovery.BLACKLIST_PATH).write_text(
            json.dumps({f"{SAMPLE_ROOT}/02-tools": "no tool evidence"}), encoding="utf-8",
        )
        self.assertEqual(discovery.discover(self.repo, sample_filter="02-tools")["count"], 0)
        self.assertEqual(discovery.discover(self.repo)["count"], 1)
        self.assertEqual(discovery.discover(self.repo, sample_filter="*")["count"], 1)

    def test_invalid_manifest_and_blacklist_fail_closed(self):
        manifest = self.sample()
        manifest.write_text("name: first\nname: second\nservices: {}", encoding="utf-8")
        with self.assertRaisesRegex(discovery.DiscoveryError, "duplicate manifest key"):
            discovery.discover(self.repo)
        (self.repo / discovery.BLACKLIST_PATH).write_text(
            json.dumps({f"{SAMPLE_ROOT}/../outside": "invalid"}), encoding="utf-8",
        )
        with self.assertRaisesRegex(discovery.DiscoveryError, "invalid blacklist sample path"):
            discovery.discover(self.repo)

    def test_hydration_requires_exactly_one_match(self):
        record = [{"comboId": "one"}]
        self.assertEqual(discovery.hydrate(record, "one"), record[0])
        for entries in ([], record * 2, {}, [None]):
            with self.subTest(entries=entries), self.assertRaises(discovery.DiscoveryError):
                discovery.hydrate(entries, "one")


if __name__ == "__main__":
    unittest.main()
