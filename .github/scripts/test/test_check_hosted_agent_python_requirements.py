from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).parents[1] / "check-hosted-agent-python-requirements.py"
SPEC = importlib.util.spec_from_file_location("hosted_agent_requirements", SCRIPT)
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


class GitRepository:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.run("init", "-q")
        self.run("config", "user.name", "Test User")
        self.run("config", "user.email", "test@example.com")
        self.write("README.md", "fixture\n")
        self.commit("base fixture")

    def cleanup(self) -> None:
        self.temp.cleanup()

    def run(self, *args: str) -> str:
        return subprocess.run(
            [
                "git",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.hooksPath=/dev/null",
                "-C",
                str(self.path),
                *args,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def write(self, relative: str, content: str) -> None:
        path = self.path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def remove(self, relative: str) -> None:
        (self.path / relative).unlink()

    def commit(self, message: str) -> str:
        self.run("add", "-A")
        self.run("commit", "-q", "-m", message)
        return self.run("rev-parse", "HEAD")


class RepositoryCheckTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.repo = GitRepository()
        self.addCleanup(self.repo.cleanup)
        self.base = self.repo.run("rev-parse", "HEAD")

    def add_service(
        self,
        sample: str = "samples/python/hosted-agents/framework/example",
        service: str = "src/example",
        requirements: str | None = "six==1.16.0\n",
    ) -> str:
        self.repo.write(
            f"{sample}/azure.yaml",
            "name: example\nservices:\n  example:\n    language: python\n"
            f"    project: {service}\n",
        )
        self.repo.write(f"{sample}/{service}/main.py", "print('hello')\n")
        if requirements is not None:
            self.repo.write(f"{sample}/{service}/requirements.txt", requirements)
        return f"{sample}/{service}"

    def findings(self, *, resolve: bool = False):
        return checker.collect_findings(
            self.repo.path, self.base, "HEAD", resolve, sys.executable
        )

    def test_new_service_with_pinned_requirements_passes(self) -> None:
        self.add_service()
        self.repo.commit("add sample")
        self.assertEqual([], self.findings())

    def test_new_service_over_existing_requirements_does_not_require_export_churn(
        self,
    ) -> None:
        sample = "samples/python/hosted-agents/framework/adopt"
        root = f"{sample}/src/adopt"
        self.repo.write(f"{root}/main.py", "pass\n")
        self.repo.write(f"{root}/requirements.txt", "six==1.16.0\n")
        self.repo.commit("add existing code")
        self.base = self.repo.run("rev-parse", "HEAD")
        self.repo.write(
            f"{sample}/azure.yaml",
            "name: adopt\nservices:\n  adopt:\n    language: python\n    project: src/adopt\n",
        )
        self.repo.commit("adopt as hosted service")
        self.assertEqual([], self.findings())

    def test_new_service_without_requirements_fails_and_points_at_runtime(self) -> None:
        root = self.add_service(requirements=None)
        self.repo.commit("add sample")
        findings = self.findings()
        self.assertEqual(["PYREQ001"], [finding.code for finding in findings])
        self.assertEqual(PurePosixPath(root), findings[0].root)

    def test_new_manifest_checks_each_python_service_only(self) -> None:
        sample = "samples/python/hosted-agents/framework/multi"
        self.repo.write(
            f"{sample}/azure.yaml",
            "name: multi\nservices:\n"
            "  one:\n    language: python\n    project: src/one\n"
            "  two:\n    language: python\n    project: src/two\n"
            "  web:\n    language: js\n    project: src/web\n",
        )
        for name in ("one", "two", "web"):
            self.repo.write(f"{sample}/src/{name}/main.py", "pass\n")
        self.repo.write(f"{sample}/src/one/requirements.txt", "six==1.16.0\n")
        self.repo.commit("add multi-service sample")
        findings = self.findings()
        self.assertEqual(["PYREQ001"], [finding.code for finding in findings])
        self.assertTrue(str(findings[0].root).endswith("src/two"))

    def test_source_only_change_to_legacy_sample_is_grandfathered(self) -> None:
        root = self.add_service(requirements="six>=1.0\n")
        self.repo.commit("add legacy sample")
        self.base = self.repo.run("rev-parse", "HEAD")
        self.repo.write(f"{root}/main.py", "print('changed')\n")
        self.repo.commit("change source")
        self.assertEqual([], self.findings())

    def test_requirements_change_activates_static_policy(self) -> None:
        root = self.add_service(requirements="six>=1.0\n")
        self.repo.commit("add legacy sample")
        self.base = self.repo.run("rev-parse", "HEAD")
        self.repo.write(f"{root}/requirements.txt", "six>=1.1\n")
        self.repo.commit("change requirements")
        self.assertEqual(["PYREQ002"], [finding.code for finding in self.findings()])

    def test_authoring_input_requires_updated_export(self) -> None:
        root = self.add_service()
        self.repo.write(
            f"{root}/pyproject.toml",
            '[project]\nname="example"\nversion="0.1"\ndependencies=["six"]\n',
        )
        self.repo.commit("add existing sample")
        self.base = self.repo.run("rev-parse", "HEAD")
        self.repo.write(
            f"{root}/pyproject.toml",
            '[project]\nname="example"\nversion="0.1"\ndependencies=["six>=1"]\n',
        )
        self.repo.commit("change authoring input")
        self.assertEqual(["PYREQ006"], [finding.code for finding in self.findings()])

    def test_authoring_input_and_export_can_change_together(self) -> None:
        root = self.add_service()
        self.repo.write(
            f"{root}/pyproject.toml",
            '[project]\nname="example"\nversion="0.1"\ndependencies=["six"]\n',
        )
        self.repo.commit("add existing sample")
        self.base = self.repo.run("rev-parse", "HEAD")
        self.repo.write(
            f"{root}/pyproject.toml",
            '[project]\nname="example"\nversion="0.1"\ndependencies=["six>=1"]\n',
        )
        self.repo.write(f"{root}/requirements.txt", "six==1.17.0\n")
        self.repo.commit("update dependencies")
        self.assertEqual([], self.findings())

    def test_nested_client_requirements_are_checked_independently(self) -> None:
        root = self.add_service()
        nested = f"{root}/chat_client"
        self.repo.write(f"{nested}/main.py", "pass\n")
        self.repo.write(f"{nested}/requirements.txt", "httpx>=0.28\n")
        self.repo.commit("add existing nested client")
        self.base = self.repo.run("rev-parse", "HEAD")
        self.repo.write(f"{nested}/requirements.txt", "httpx>=0.27\n")
        self.repo.commit("change nested client")
        findings = self.findings()
        self.assertEqual(["PYREQ002"], [finding.code for finding in findings])
        self.assertEqual(PurePosixPath(nested), findings[0].root)

    def test_nested_pyproject_without_nested_artifact_belongs_to_service(self) -> None:
        root = self.add_service()
        self.repo.commit("add existing sample")
        self.base = self.repo.run("rev-parse", "HEAD")
        self.repo.write(
            f"{root}/tools/pyproject.toml",
            '[project]\nname="tool"\nversion="0.1"\n',
        )
        self.repo.commit("add nested metadata")
        findings = self.findings()
        self.assertEqual(["PYREQ006"], [finding.code for finding in findings])
        self.assertEqual(PurePosixPath(root), findings[0].root)

    def test_requirements_dev_is_not_a_runtime_trigger(self) -> None:
        root = self.add_service(requirements="six>=1\n")
        self.repo.write(f"{root}/requirements-dev.in", "pytest>=8\n")
        self.repo.commit("add existing sample")
        self.base = self.repo.run("rev-parse", "HEAD")
        self.repo.write(f"{root}/requirements-dev.in", "pytest>=9\n")
        self.repo.commit("update local test tools")
        self.assertEqual([], self.findings())

    def test_non_hosted_python_path_is_ignored(self) -> None:
        self.repo.write("samples/python/quickstart/new/requirements.txt", "six>=1\n")
        self.repo.write("samples/python/quickstart/new/main.py", "pass\n")
        self.repo.commit("change other python sample")
        self.assertEqual([], self.findings())

    def test_deleted_requirements_from_existing_service_fails(self) -> None:
        root = self.add_service()
        self.repo.commit("add existing sample")
        self.base = self.repo.run("rev-parse", "HEAD")
        self.repo.remove(f"{root}/requirements.txt")
        self.repo.commit("remove requirements")
        self.assertEqual(["PYREQ001"], [finding.code for finding in self.findings()])

    def test_policy_url_appears_in_text_and_ado_annotation(self) -> None:
        finding = checker.Finding(
            "PYREQ002",
            "pin it",
            PurePosixPath("samples/python/hosted-agents/x/src/x"),
            PurePosixPath("samples/python/hosted-agents/x/src/x/requirements.txt"),
            PurePosixPath("samples/python/hosted-agents/x/src/x/requirements.txt"),
            4,
        )
        output = io.StringIO()
        with mock.patch("sys.stdout", output):
            checker.print_findings([finding], "https://example/policy", True)
        rendered = output.getvalue()
        self.assertIn("https://example/policy", rendered)
        self.assertIn("##vso[task.logissue type=error", rendered)
        self.assertIn("linenumber=4", rendered)


class RequirementParserTests(unittest.TestCase):
    root = PurePosixPath("samples/python/hosted-agents/x/src/x")
    source = root / "requirements.txt"

    def parse(self, content: str):
        return checker.parse_requirements(content, self.root, self.source, self.source)

    def test_exact_extras_markers_prereleases_and_hashes_are_allowed(self) -> None:
        requirements, findings = self.parse(
            "pkg[one,two]==1.0.0b2 ; python_version >= '3.11' \\\n"
            "    --hash=sha256:abc\n"
        )
        self.assertEqual([], findings)
        self.assertEqual("pkg", requirements[0].name)

    def test_inline_comments_are_allowed(self) -> None:
        requirements, findings = self.parse("six==1.16.0  # via example\n")
        self.assertEqual([], findings)
        self.assertEqual("six", requirements[0].name)

    def test_empty_or_comment_only_artifact_is_allowed(self) -> None:
        requirements, findings = self.parse("# Standard library only.\n")
        self.assertEqual([], requirements)
        self.assertEqual([], findings)

    def test_bare_ranges_compatible_and_wildcards_fail(self) -> None:
        _, findings = self.parse("one\ntwo>=2\nthree~=3.0\nfour==4.*\nfive!=5.0\n")
        self.assertEqual(["PYREQ002"] * 5, [finding.code for finding in findings])

    def test_includes_options_editable_local_urls_and_vcs_fail(self) -> None:
        _, findings = self.parse(
            "-r base.txt\n"
            "--extra-index-url https://example.invalid/simple\n"
            "-e ../shared\n"
            "../local\n"
            "pkg @ https://example.invalid/pkg.whl\n"
            "vcs @ git+https://github.com/example/repo@main\n"
        )
        self.assertEqual(
            ["PYREQ005", "PYREQ009", "PYREQ004", "PYREQ004", "PYREQ011", "PYREQ003"],
            [finding.code for finding in findings],
        )

    def test_invalid_requirement_reports_line(self) -> None:
        _, findings = self.parse("not a valid requirement ===\n")
        self.assertEqual("PYREQ010", findings[0].code)
        self.assertEqual(1, findings[0].line)


class ExceptionTests(unittest.TestCase):
    def test_expired_exception_does_not_hide_a_finding(self) -> None:
        root = PurePosixPath("samples/python/hosted-agents/x/src/x")
        finding = checker.Finding("PYREQ003", "vcs", root, root / "requirements.txt")
        expired = checker.ExceptionRule(
            root,
            "PYREQ003",
            "temporary",
            "@owner",
            "https://example.test/issue",
            checker.dt.date(2000, 1, 1),
        )
        remaining, used = checker.apply_exceptions([finding], [expired])
        self.assertEqual([finding], remaining)
        self.assertEqual([], used)


class ResolverComparisonTests(unittest.TestCase):
    def test_timeout_is_reported_as_checker_infrastructure_error(self) -> None:
        root = PurePosixPath("samples/python/hosted-agents/x/src/x")
        source = root / "requirements.txt"
        with mock.patch.object(
            checker.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["pip"], 180),
        ):
            with self.assertRaises(checker.CheckError):
                checker.resolve_requirements(
                    "six==1.16.0\n",
                    source,
                    [checker.Requirement("six==1.16.0")],
                    root,
                    source,
                    sys.executable,
                )

    def test_missing_transitive_dependency_is_reported(self) -> None:
        root = PurePosixPath("samples/python/hosted-agents/x/src/x")
        requirement = checker.Requirement("requests==2.32.3")
        report = {
            "install": [
                {"metadata": {"name": "requests", "version": "2.32.3"}},
                {"metadata": {"name": "urllib3", "version": "2.2.3"}},
            ]
        }
        completed = subprocess.CompletedProcess([], 0, "", "")
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            source = root / "requirements.txt"
            path = repo / source
            path.parent.mkdir(parents=True)
            path.write_text("requests==2.32.3\n", encoding="utf-8")

            def fake_run(command, **kwargs):
                requirement_path = Path(command[command.index("-r") + 1])
                self.assertNotEqual(path, requirement_path)
                self.assertEqual(
                    "requests==2.32.3\n",
                    requirement_path.read_text(encoding="utf-8"),
                )
                report_path = Path(command[command.index("--report") + 1])
                report_path.write_text(json.dumps(report), encoding="utf-8")
                return completed

            with mock.patch.object(checker.subprocess, "run", side_effect=fake_run):
                findings = checker.resolve_requirements(
                    "requests==2.32.3\n",
                    source,
                    [requirement],
                    root,
                    source,
                    sys.executable,
                )
        self.assertEqual(["PYREQ007"], [finding.code for finding in findings])
        self.assertIn("urllib3", findings[0].message)


if __name__ == "__main__":
    unittest.main()
