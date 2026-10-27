"""Exercise generic hosted runtime discovery and credential-free execution."""

import importlib.util
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "check_hosted_agent_runtime.py"
SPEC = importlib.util.spec_from_file_location("hosted_runtime_checks", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
ROOT = PurePosixPath("samples/python/hosted-agents/example/src/worker")
PROJECT = """[project]
name = "worker"
version = "0.1.0"
[dependency-groups]
dev = ["ruff==0.9.4"]
[tool.hosted-agent-validation]
commands = [["python", "-m", "unittest", "discover"], ["ruff", "check", "."]]
"""
MANIFEST = """services:
  worker:
    host: azure.ai.agent
    language: python
    project: src/worker
"""


class RuntimeChecksTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Runtime tests")
        self.git("config", "user.email", "runtime@example.com")
        self.base = self.commit()

    def git(self, *arguments):
        return subprocess.check_output(
            ["git", "-C", str(self.repo), *arguments], text=True, stderr=subprocess.PIPE
        ).strip()

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture", "--allow-empty")
        return self.git("rev-parse", "HEAD")

    def write(self, relative, content):
        path = self.repo / str(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def runtime(self, project=PROJECT, manifest=MANIFEST):
        self.write(ROOT.parent.parent / "azure.yaml", manifest)
        self.write(ROOT / "pyproject.toml", project)
        self.write(ROOT / "uv.lock", "version = 1\n")
        self.write(ROOT / "main.py", "print('worker')\n")

    def requirements_migration(self, *, declared=True, archive=False):
        project = (
            PROJECT if declared else PROJECT.split("[tool.hosted-agent-validation]")[0]
        )
        self.runtime(project=project)
        base = self.commit()
        project_file = self.repo / str(ROOT) / "pyproject.toml"
        if archive:
            self.git("config", "diff.renames", "true")
            project_file.rename(project_file.with_name("pyproject.previous.toml"))
        else:
            project_file.unlink()
        (self.repo / str(ROOT) / "uv.lock").unlink()
        self.write(ROOT / "requirements.txt", "ruff==0.9.4\n")
        return base, self.commit()

    def test_discovers_a_generic_service_project(self):
        self.runtime()
        checks = module.discover_checks(self.repo, self.base, self.commit())
        self.assertEqual([item.root for item in checks], [ROOT])
        self.assertEqual(
            checks[0].commands[0], ("python", "-m", "unittest", "discover")
        )

    def test_unrelated_change_does_not_run_runtime(self):
        self.runtime()
        base = self.commit()
        self.write("README.md", "documentation\n")
        self.assertEqual(module.discover_checks(self.repo, base, self.commit()), [])

    def test_changed_source_runs_existing_runtime(self):
        self.runtime()
        base = self.commit()
        self.write(ROOT / "main.py", "print('changed')\n")
        self.assertEqual(
            [
                item.root
                for item in module.discover_checks(self.repo, base, self.commit())
            ],
            [ROOT],
        )

    def test_manifest_change_runs_existing_runtime(self):
        self.runtime()
        base = self.commit()
        self.write(ROOT.parent.parent / "azure.yaml", MANIFEST + "name: updated\n")
        self.assertEqual(len(module.discover_checks(self.repo, base, self.commit())), 1)

    def test_shared_runner_change_runs_declared_runtimes(self):
        self.runtime()
        base = self.commit()
        self.write(".github/scripts/check_hosted_agent_runtime.py", "changed\n")
        self.assertEqual(len(module.discover_checks(self.repo, base, self.commit())), 1)

    def test_undeclared_legacy_runtime_is_not_claimed_as_tested(self):
        self.runtime(project=PROJECT.split("[tool.hosted-agent-validation]")[0])
        self.assertEqual(
            module.discover_checks(self.repo, self.base, self.commit()), []
        )

    def test_removing_declaration_fails_closed(self):
        self.runtime()
        base = self.commit()
        self.write(
            ROOT / "pyproject.toml", PROJECT.split("[tool.hosted-agent-validation]")[0]
        )
        with self.assertRaisesRegex(ValueError, "cannot remove validation"):
            module.discover_checks(self.repo, base, self.commit())

    def test_removing_project_manifest_fails_closed(self):
        self.runtime()
        base = self.commit()
        (self.repo / str(ROOT) / "pyproject.toml").unlink()
        with self.assertRaisesRegex(ValueError, "cannot remove validation"):
            module.discover_checks(self.repo, base, self.commit())

    def test_requirements_migration_fails_closed(self):
        base, head = self.requirements_migration()
        with self.assertRaisesRegex(ValueError, "cannot remove validation"):
            module.discover_checks(self.repo, base, head)

    def test_requirements_migration_cli_fails_closed(self):
        base, head = self.requirements_migration()
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo",
                str(self.repo),
                "--base",
                base,
                "--head",
                head,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("cannot remove validation", result.stderr)
        self.assertNotIn("Validated", result.stdout)

    def test_archived_project_cannot_disable_validation(self):
        base, head = self.requirements_migration(archive=True)
        changes = self.git("diff", "--name-only", f"{base}..{head}").splitlines()
        self.assertNotIn(str(ROOT / "pyproject.toml"), changes)
        with self.assertRaisesRegex(ValueError, "cannot remove validation"):
            module.discover_checks(self.repo, base, head)

    def test_legacy_requirements_migration_remains_grandfathered(self):
        base, head = self.requirements_migration(declared=False)
        self.assertEqual(module.discover_checks(self.repo, base, head), [])

    def test_removed_hosted_service_is_not_required_to_keep_validation(self):
        self.runtime()
        base = self.commit()
        (self.repo / str(ROOT.parent.parent) / "azure.yaml").unlink()
        self.assertEqual(module.discover_checks(self.repo, base, self.commit()), [])

    def test_non_hosted_service_is_not_selected(self):
        self.runtime(manifest=MANIFEST.replace("azure.ai.agent", "azure.ai.project"))
        self.assertEqual(
            module.discover_checks(self.repo, self.base, self.commit()), []
        )

    def test_missing_lock_fails(self):
        self.runtime()
        (self.repo / str(ROOT) / "uv.lock").unlink()
        with self.assertRaisesRegex(ValueError, "requires uv.lock"):
            module.discover_checks(self.repo, self.base, self.commit())

    def test_invalid_declarations_fail(self):
        for value in ('"pytest tests"', "[]", "[[]]", '[["python", 1]]'):
            with self.subTest(value=value):
                content = PROJECT.split("commands =")[0] + "commands = " + value
                with self.assertRaises(ValueError):
                    module.parse_checks(content.encode(), ROOT)

    def test_missing_dev_group_fails(self):
        content = PROJECT.replace('[dependency-groups]\ndev = ["ruff==0.9.4"]\n', "")
        with self.assertRaisesRegex(ValueError, "dev dependency group"):
            module.parse_checks(content.encode(), ROOT)

    def test_invalid_tool_table_fails_cleanly(self):
        with self.assertRaisesRegex(ValueError, "tool must be a table"):
            module.parse_checks(b"tool = 1", ROOT)

    def test_invalid_dev_group_fails_cleanly(self):
        content = PROJECT.replace('dev = ["ruff==0.9.4"]', "dev = 1")
        with self.assertRaisesRegex(ValueError, "dev dependency group"):
            module.parse_checks(content.encode(), ROOT)

    def test_shell_free_frozen_execution_and_state_cleanup(self):
        self.runtime()
        checks = module.parse_checks(PROJECT.encode(), ROOT)
        with patch.object(module.subprocess, "run") as run:
            module.validate_runtime(self.repo, checks)
        self.assertEqual(
            run.call_args_list[0].args[0], ["uv", "sync", "--frozen", "--group", "dev"]
        )
        self.assertEqual(
            run.call_args_list[1].args[0][:7],
            ["uv", "run", "--frozen", "--group", "dev", "--", "python"],
        )
        self.assertEqual(run.call_count, 3)
        for call in run.call_args_list:
            self.assertEqual(call.kwargs["cwd"], (self.repo / str(ROOT)).resolve())
            self.assertNotIn("shell", call.kwargs)
            self.assertTrue(call.kwargs["check"])
            environment = call.kwargs["env"]
            self.assertEqual(environment["OTEL_SDK_DISABLED"], "true")
            for name in (
                "LANGSMITH_TRACING",
                "LANGSMITH_TRACING_V2",
                "LANGCHAIN_TRACING",
                "LANGCHAIN_TRACING_V2",
            ):
                self.assertEqual(environment[name], "false")
            self.assertFalse(
                Path(environment["AGENTSERVER_STATE_ROOT"]).parent.exists()
            )

    def test_failed_check_stops_remaining_commands(self):
        self.runtime()
        checks = module.parse_checks(PROJECT.encode(), ROOT)
        error = subprocess.CalledProcessError(1, ["python", "-m", "unittest"])
        with patch.object(module.subprocess, "run", side_effect=[None, error]) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                module.validate_runtime(self.repo, checks)
        self.assertEqual(run.call_count, 2)

    def test_runtime_directory_cannot_escape_repository(self):
        (Path(self.temporary.name) / "outside").mkdir()
        checks = module.RuntimeChecks(PurePosixPath("../outside"), (("python",),))
        with self.assertRaisesRegex(ValueError, "escapes"):
            module.validate_runtime(self.repo, checks)


if __name__ == "__main__":
    unittest.main()
