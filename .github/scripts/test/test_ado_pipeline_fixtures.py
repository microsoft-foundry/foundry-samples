"""Validate every published ADO fixture without deploying or invoking samples."""

from pathlib import Path
import sys
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hosted_agent_fixture import CI_SKIPLIST, CODE_CI_SKIPLIST, FIXTURE_ROOT, load_skiplist, sample_dir_for_fixture
from hosted_agent_test_spec import build_plan, load_spec


ROOT = Path(__file__).resolve().parents[3]


class PublishedFixtureTests(unittest.TestCase):
    def test_skiplist_entries_map_to_public_samples(self):
        for filename in (CI_SKIPLIST, CODE_CI_SKIPLIST):
            for sample in load_skiplist(ROOT, filename):
                with self.subTest(skiplist=str(filename), sample=str(sample)):
                    self.assertTrue((ROOT / sample / "azure.yaml").is_file())

    def test_all_fixtures_map_to_public_samples(self):
        fixtures = sorted(
            path for path in (ROOT / FIXTURE_ROOT).rglob("*")
            if path.name in {"test-spec.yml", "test-payload.txt"}
        )
        self.assertTrue(fixtures, "Expected the migrated hosted-agent fixtures")
        for fixture in fixtures:
            relative = fixture.relative_to(ROOT).as_posix()
            with self.subTest(fixture=relative):
                sample = ROOT / sample_dir_for_fixture(relative)
                manifest = sample / "azure.yaml"
                self.assertTrue(manifest.is_file(), f"Orphan fixture: {relative}")
                if fixture.name != "test-spec.yml":
                    continue
                document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
                protocols = {
                    entry["protocol"]
                    for service in document["services"].values()
                    if service.get("host") == "azure.ai.agent"
                    for entry in service.get("protocols", [])
                }
                protocol = "invocations" if "invocations" in protocols else "responses"
                build_plan(load_spec(fixture), protocol=protocol)


if __name__ == "__main__":
    unittest.main()
