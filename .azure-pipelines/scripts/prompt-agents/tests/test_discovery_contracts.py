"""Offline contract validation and discovery edge cases."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "discover_samples.py"
SPEC = importlib.util.spec_from_file_location("prompt_discovery_contracts", SCRIPT)
discovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(discovery)
SAMPLE_ROOT = "samples/cli/prompt-agents"


class DiscoveryContractTests(unittest.TestCase):
    def setUp(self):
        imports = mock.patch.object(sys, "path", [str(SCRIPT.parent), *sys.path])
        imports.start()
        self.addCleanup(imports.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.repo = Path(directory.name)
        (self.repo / SAMPLE_ROOT).mkdir(parents=True)
        self.blacklist({})

    def blacklist(self, entries):
        path = self.repo / discovery.BLACKLIST_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries), encoding="utf-8")
        return path

    def sample(self, name="01-basic", agent=None):
        path = self.repo / SAMPLE_ROOT / name / "azure.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        service = {"host": "azure.ai.agent", "kind": "prompt", "project": ".", "uses": ["project"], **(agent or {})}
        services = {"project": {"host": "azure.ai.project"}, "agent": service}
        if service.get("harness") == {"type": "github_copilot_preview"}:
            services["toolbox"] = {"host": "azure.ai.toolbox", "uses": ["project"], "tools": [{"type": "web_search"}]}
            service.update(uses=["project", "toolbox"], toolbox={"name": "toolbox"})
        path.write_text(yaml.safe_dump({"name": "agent-" + name.replace("/", "-"), "services": services}), encoding="utf-8")
        return path

    def contract(self, name="01-basic", tests=None):
        path = self.repo / discovery.fixture_dir_for_sample(f"{SAMPLE_ROOT}/{name}") / "test-spec.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump({
            "version": 1, "sample": {"owner": "test", "experiences": ["azd"]},
            "tests": tests if tests is not None else [{"name": "answer", "turns": [{
                "input": "Say ready", "assertions": [{"source": "assistant_text", "type": "equals", "value": "ready"}],
            }]}],
        }), encoding="utf-8")
        return path

    def test_contract_required_but_discovery_still_lists_manifest(self):
        self.sample()
        self.assertEqual(discovery.discover(self.repo)["count"], 1)
        with self.assertRaisesRegex(discovery.DiscoveryError, "non-skipped sample requires a contract"):
            discovery.validate_contracts(self.repo)

    def test_reject_unsupported_evidence_even_when_filtered_out(self):
        for managed in (False, True):
            for turn, message in (
                ({"input": "hello", "assertions": [{"source": "raw", "type": "contains", "value": "hello"}]}, "raw response evidence"),
                ({"input": [{"role": "user", "content": "hello"}]}, "only string input"),
                ({"input": "hello", "assertions": [{"source": "session_files", "type": "exists", "path": "/answer.txt"}]}, "session_files.*not supported"),
            ):
                with self.subTest(managed=managed, turn=turn):
                    self.sample(agent={"harness": {"type": "github_copilot_preview"}} if managed else {})
                    self.contract(tests=[{"name": "valid", "turns": [{"input": "hello", "assertions": [
                        {"source": "assistant_text", "type": "equals", "value": "ready"}]}]},
                        {"name": "filtered", "when": {"toolbox_label": "not-selected"}, "turns": [turn]}])
                    with self.assertRaisesRegex((ValueError, RuntimeError), message):
                        discovery.validate_contracts(self.repo)

    def test_validation_precedes_manual_and_changed_filters(self):
        self.sample()
        self.contract()
        self.sample("invalid", agent={"kind": "hosted"})
        self.contract("invalid")
        for mode in ("all", "changed"):
            with self.subTest(mode=mode):
                output, errors = io.StringIO(), io.StringIO()
                with mock.patch.object(discovery.subprocess, "run") as run:
                    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                        code = discovery.main(["discover", "--repo", str(self.repo), "--validate-contracts",
                                               "--mode", mode, "--sample-filter", "no-match"])
                self.assertEqual(code, 1)
                self.assertEqual(output.getvalue(), "")
                self.assertIn("agent kind must be prompt", errors.getvalue())
                run.assert_not_called()

    def test_orphan_fixture_fails_even_when_blacklisted(self):
        self.sample()
        self.contract()
        self.contract("orphan")
        for entries in ({}, {f"{SAMPLE_ROOT}/orphan": "No manifest"}):
            with self.subTest(entries=entries):
                self.blacklist(entries)
                with self.assertRaisesRegex(discovery.DiscoveryError, "fixture has no sample manifest"):
                    discovery.validate_contracts(self.repo)

    def test_blacklist_bypasses_invalid_contract_but_restoring_exposes_it(self):
        self.sample()
        spec = self.contract(tests=[{"name": "no-assertions", "turns": [{"input": "hello"}]}])
        self.blacklist({f"{SAMPLE_ROOT}/01-basic": "Unsupported"})
        self.assertEqual(discovery.discover(self.repo)["count"], 0)
        discovery.validate_contracts(self.repo)
        changed = spec.relative_to(self.repo).as_posix()
        self.assertEqual(discovery.discover(self.repo, [changed])["count"], 0)
        self.blacklist({})
        self.assertEqual(discovery.discover(self.repo, [changed])["count"], 1)
        with self.assertRaisesRegex(RuntimeError, "assert observable output"):
            discovery.validate_contracts(self.repo)

    def test_fixture_changes_select_owning_sample(self):
        self.sample()
        spec = self.contract()
        discovery.validate_contracts(self.repo)
        selected = discovery.discover(self.repo, [spec.relative_to(self.repo).as_posix()])
        self.assertEqual([entry["samplePath"] for entry in selected["entries"]], [f"{SAMPLE_ROOT}/01-basic"])

    def test_blacklist_rejects_duplicates_and_invalid_shapes(self):
        self.sample()
        self.contract()
        sample = f"{SAMPLE_ROOT}/01-basic"
        for content, error, message in (
            (f'{{"{sample}":"one","{sample}":"two"}}', discovery.DiscoveryError, "duplicate blacklist path"),
            ("[]", discovery.DiscoveryError, "blacklist must map sample paths"),
            (json.dumps({f"{SAMPLE_ROOT}/../outside": "reason"}), discovery.DiscoveryError, "invalid blacklist sample path"),
            (json.dumps({sample: " "}), discovery.DiscoveryError, "blacklist reason must be a nonempty string"),
        ):
            with self.subTest(content=content):
                self.blacklist({}).write_text(content, encoding="utf-8")
                for operation in (discovery.load_blacklist, discovery.discover, discovery.validate_contracts):
                    with self.assertRaisesRegex(error, message):
                        operation(self.repo)

    def test_changed_mode_uses_nul_separated_paths_and_fails_closed(self):
        self.sample("old")
        self.sample("new")
        paths = [f"{SAMPLE_ROOT}/{name}/file.py" for name in ("old", "new")]
        diff = subprocess.CompletedProcess([], 0, "\0".join(paths) + "\0", "")
        with mock.patch.object(discovery.subprocess, "run", return_value=diff) as run:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = discovery.main(["discover", "--repo", str(self.repo), "--mode", "changed", "--base-ref", "base"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["count"], 2)
        self.assertEqual(run.call_args.args[0], ["git", "diff", "--name-only", "--no-renames", "-z", "base...HEAD", "--"])
        with mock.patch.object(discovery.subprocess, "run", side_effect=subprocess.CalledProcessError(128, "git")):
            with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(discovery.main(["discover", "--repo", str(self.repo), "--mode", "changed"]), 1)
            self.assertEqual(output.getvalue(), "")

    def test_public_repo_candidates_have_contracts(self):
        repo = SCRIPT.parents[3]
        records = discovery.discover(repo)["entries"]
        self.assertIn("01-basic", {Path(item["samplePath"]).name for item in records})
        discovery.validate_contracts(repo)


if __name__ == "__main__":
    unittest.main()
