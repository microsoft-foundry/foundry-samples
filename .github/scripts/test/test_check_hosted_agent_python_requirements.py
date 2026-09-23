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

    def add_uv_service(
        self,
        sample: str = "samples/python/hosted-agents/framework/uv-example",
        service: str = "src/example",
    ) -> str:
        root = self.add_service(
            sample=sample,
            service=service,
            requirements=None,
        )
        self.repo.write(
            f"{root}/pyproject.toml",
            '[project]\nname = "example"\nversion = "0.1.0"\n'
            'requires-python = ">=3.11"\ndependencies = ["six==1.16.0"]\n',
        )
        self.repo.write(
            f"{root}/uv.lock",
            'version = 1\nrevision = 3\nrequires-python = ">=3.11"\n\n'
            "[[package]]\n"
            'name = "example"\nversion = "0.1.0"\n'
            'source = { editable = "." }\n'
            'dependencies = [{ name = "six" }]\n\n'
            "[[package]]\n"
            'name = "six"\nversion = "1.16.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )
        return root

    def findings(self, *, resolve: bool = False):
        return checker.collect_findings(
            self.repo.path, self.base, "HEAD", resolve, sys.executable
        )

    def test_new_service_with_pinned_requirements_fallback_passes(self) -> None:
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

    def test_new_service_with_uv_project_and_lock_passes(self) -> None:
        self.add_uv_service()
        self.repo.commit("add uv sample")
        self.assertEqual([], self.findings())

    def test_incomplete_uv_pair_fails(self) -> None:
        for present, missing in (
            ("pyproject.toml", "uv.lock"),
            ("uv.lock", "pyproject.toml"),
        ):
            with self.subTest(missing=missing):
                repo = GitRepository()
                self.addCleanup(repo.cleanup)
                sample = "samples/python/hosted-agents/framework/incomplete"
                service = "src/incomplete"
                repo.write(
                    f"{sample}/azure.yaml",
                    "name: incomplete\nservices:\n  incomplete:\n"
                    "    language: python\n    project: src/incomplete\n",
                )
                repo.write(f"{sample}/{service}/main.py", "pass\n")
                content = (
                    '[project]\nname = "incomplete"\nversion = "0.1.0"\n'
                    if present == "pyproject.toml"
                    else 'version = 1\nrevision = 3\nrequires-python = ">=3.13"\n'
                )
                repo.write(f"{sample}/{service}/{present}", content)
                repo.commit("add incomplete uv sample")
                findings = checker.collect_findings(
                    repo.path,
                    repo.run("rev-parse", "HEAD^"),
                    "HEAD",
                    False,
                    sys.executable,
                )
                self.assertEqual(["PYREQ001"], [finding.code for finding in findings])

    def test_uv_pair_takes_precedence_over_legacy_requirements(self) -> None:
        root = self.add_uv_service()
        self.repo.write(f"{root}/requirements.txt", "six>=1.0\n")
        self.repo.commit("add uv-native sample with legacy requirements fallback")
        self.assertEqual([], self.findings())

    def test_uv_project_change_requires_updated_lock(self) -> None:
        root = self.add_uv_service()
        self.repo.commit("add uv sample")
        self.base = self.repo.run("rev-parse", "HEAD")
        self.repo.write(
            f"{root}/pyproject.toml",
            '[project]\nname = "example"\nversion = "0.1.0"\n'
            'requires-python = ">=3.11"\ndependencies = ["six==1.17.0"]\n',
        )
        self.repo.commit("change uv dependencies")
        self.assertEqual(["PYREQ006"], [finding.code for finding in self.findings()])

    def test_uv_config_change_requires_updated_lock(self) -> None:
        root = self.add_uv_service()
        self.repo.write(f"{root}/uv.toml", "system-certs = true\n")
        self.repo.commit("add uv sample")
        self.base = self.repo.run("rev-parse", "HEAD")
        self.repo.write(f"{root}/uv.toml", "system-certs = false\n")
        self.repo.commit("change uv configuration")
        self.assertEqual(["PYREQ006"], [finding.code for finding in self.findings()])

    def test_uv_resolution_is_wired_through_repository_check(self) -> None:
        root = self.add_uv_service()
        self.repo.commit("add uv sample")
        with mock.patch.object(
            checker, "validate_uv_resolution", return_value=[]
        ) as validate:
            self.assertEqual([], self.findings(resolve=True))
        validate.assert_called_once()
        self.assertEqual(PurePosixPath(root), validate.call_args.args[3])
        self.assertEqual("uv", validate.call_args.args[5])

    def test_uv_project_and_lock_can_change_together(self) -> None:
        root = self.add_uv_service()
        self.repo.commit("add uv sample")
        self.base = self.repo.run("rev-parse", "HEAD")
        self.repo.write(
            f"{root}/pyproject.toml",
            '[project]\nname = "example"\nversion = "0.1.0"\n'
            'requires-python = ">=3.11"\ndependencies = ["six==1.17.0"]\n',
        )
        self.repo.write(
            f"{root}/uv.lock",
            'version = 1\nrevision = 3\nrequires-python = ">=3.11"\n\n'
            "[[package]]\n"
            'name = "example"\nversion = "0.1.0"\n'
            'source = { editable = "." }\n'
            'dependencies = [{ name = "six" }]\n\n'
            "[[package]]\n"
            'name = "six"\nversion = "1.17.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n',
        )
        self.repo.commit("update uv dependencies")
        self.assertEqual([], self.findings())

    def test_deleting_requirements_adopts_existing_uv_lock_without_lock_churn(
        self,
    ) -> None:
        root = self.add_uv_service()
        self.repo.write(f"{root}/requirements.txt", "six==1.16.0\n")
        self.repo.commit("add dual-lock sample")
        self.base = self.repo.run("rev-parse", "HEAD")
        self.repo.remove(f"{root}/requirements.txt")
        self.repo.commit("adopt uv lock")
        self.assertEqual([], self.findings())

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

    def test_nested_uv_project_is_checked_independently(self) -> None:
        root = self.add_service()
        nested = f"{root}/tool"
        self.repo.write(
            f"{nested}/pyproject.toml",
            '[project]\nname = "tool"\nversion = "0.1.0"\n',
        )
        self.repo.write(
            f"{nested}/uv.lock",
            'version = 1\nrevision = 3\nrequires-python = ">=3.11"\n\n'
            "[[package]]\n"
            'name = "tool"\nversion = "0.1.0"\n'
            'source = { editable = "." }\n',
        )
        self.repo.commit("add nested uv project")
        self.base = self.repo.run("rev-parse", "HEAD")
        self.repo.write(f"{nested}/uv.lock", "not valid toml =\n")
        self.repo.commit("break nested uv lock")
        findings = self.findings()
        self.assertEqual(["PYREQ010"], [finding.code for finding in findings])
        self.assertEqual(PurePosixPath(nested), findings[0].root)

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


class UvLockParserTests(unittest.TestCase):
    root = PurePosixPath("samples/python/hosted-agents/x/src/x")
    source = root / "uv.lock"

    def parse(self, lock_content: str, project_content: str | None = None):
        return checker.parse_uv_lock(
            lock_content,
            project_content or '[project]\nname = "example"\nversion = "0.1.0"\n',
            self.root,
            self.source,
            self.source,
        )

    def test_registry_and_project_editable_sources_are_allowed(self) -> None:
        findings = self.parse(
            "[[package]]\n"
            'name = "example"\nversion = "0.1.0"\n'
            'source = { editable = "." }\n\n'
            "[[package]]\n"
            'name = "six"\nversion = "1.16.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
        )
        self.assertEqual([], findings)

    def test_virtual_root_project_source_is_allowed(self) -> None:
        findings = self.parse(
            "[[package]]\n"
            'name = "example"\nversion = "0.1.0"\n'
            'source = { virtual = "." }\n'
        )
        self.assertEqual([], findings)

    def test_mutable_and_nonportable_sources_are_rejected(self) -> None:
        findings = self.parse(
            "[[package]]\n"
            'name = "git-package"\nversion = "1.0.0"\n'
            'source = { git = "https://example.test/repo" }\n\n'
            "[[package]]\n"
            'name = "url-package"\nversion = "1.0.0"\n'
            'source = { url = "https://example.test/package.whl" }\n\n'
            "[[package]]\n"
            'name = "local-package"\nversion = "1.0.0"\n'
            'source = { directory = "../local" }\n\n'
            "[[package]]\n"
            'name = "private-package"\nversion = "1.0.0"\n'
            'source = { registry = "https://packages.example.test/simple" }\n'
        )
        self.assertEqual(
            ["PYREQ003", "PYREQ011", "PYREQ004", "PYREQ009"],
            [finding.code for finding in findings],
        )

    def test_missing_version_and_malformed_toml_are_rejected(self) -> None:
        findings = self.parse(
            "[[package]]\n"
            'name = "six"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
        )
        self.assertEqual(["PYREQ002"], [finding.code for finding in findings])
        self.assertEqual(
            ["PYREQ010"],
            [finding.code for finding in self.parse("not valid toml =\n")],
        )


class ExceptionTests(unittest.TestCase):
    def load_rule(self, **overrides):
        rule = {
            "path": "samples/python/hosted-agents/x/src/x",
            "code": "PYREQ003",
            "reason": "Package wheel is not available yet.",
            "owner": "@microsoft-foundry/hosted-agents",
            "issue": "https://github.com/microsoft-foundry/foundry-samples/issues/983",
            "expires": "2099-01-01",
        }
        rule.update(overrides)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "exceptions.toml"
            path.write_text(
                "[[exceptions]]\n"
                + "\n".join(
                    f"{key} = {json.dumps(value)}" for key, value in rule.items()
                ),
                encoding="utf-8",
            )
            return checker.load_exceptions(path)

    def test_valid_public_issue_exception_applies(self) -> None:
        rules = self.load_rule()
        root = PurePosixPath("samples/python/hosted-agents/x/src/x")
        finding = checker.Finding("PYREQ003", "vcs", root, root / "requirements.txt")
        remaining, used = checker.apply_exceptions([finding], rules)
        self.assertEqual([], remaining)
        self.assertEqual(rules, used)

    def test_exception_text_fields_require_nonempty_strings(self) -> None:
        for field in ("path", "code", "reason", "owner", "issue"):
            for value in ("", " \t ", 0, False, [], {}):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(checker.CheckError, field):
                        self.load_rule(**{field: value})

    def test_issue_requires_this_public_repository_issue_url(self) -> None:
        invalid_urls = (
            "https://github.com/microsoft-foundry/foundry-samples-pr/issues/983",
            "http://github.com/microsoft-foundry/foundry-samples/issues/983",
            "https://github.com/microsoft-foundry/foundry-samples/pull/983",
            "https://github.com/microsoft-foundry/foundry-samples/issues/",
            "https://github.com/microsoft-foundry/foundry-samples/issues/0",
            "https://github.com/microsoft-foundry/foundry-samples/issues/983?token=value",
            "https://github.com/microsoft-foundry/foundry-samples/issues/983/extra",
            "https://github.com.example.com/microsoft-foundry/foundry-samples/issues/983",
            "https://github.com@other.example/microsoft-foundry/foundry-samples/issues/983",
        )
        for issue in invalid_urls:
            with self.subTest(issue=issue):
                with self.assertRaisesRegex(checker.CheckError, "issue"):
                    self.load_rule(issue=issue)

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

    def test_uv_validation_runs_lock_check_and_export(self) -> None:
        root = PurePosixPath("samples/python/hosted-agents/x/src/x")
        trigger = root / "uv.lock"
        completed = subprocess.CompletedProcess([], 0, "", "")
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            project = repo / root / "pyproject.toml"
            lock = repo / root / "uv.lock"
            project.parent.mkdir(parents=True)
            project.write_text(
                '[project]\nname = "x"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            lock.write_text(
                'version = 1\n[[package]]\nname = "x"\nversion = "0.1.0"\n'
                'source = { editable = "." }\n',
                encoding="utf-8",
            )
            uv_config = repo / root / "uv.toml"
            uv_config.write_text("native-tls = true\n", encoding="utf-8")

            def fake_read_tree_file(_repo, _revision, path):
                return (repo / path).read_bytes()

            commands = []

            def fake_run(command, **kwargs):
                project_root = Path(command[command.index("--project") + 1])
                self.assertEqual(
                    "native-tls = true\n",
                    (project_root / "uv.toml").read_text(encoding="utf-8"),
                )
                commands.append(command)
                return completed

            with (
                mock.patch.object(
                    checker, "read_tree_file", side_effect=fake_read_tree_file
                ),
                mock.patch.object(checker.subprocess, "run", side_effect=fake_run),
            ):
                findings = checker.validate_uv_resolution(
                    repo,
                    "HEAD",
                    {root / "pyproject.toml", root / "uv.lock", root / "uv.toml"},
                    root,
                    trigger,
                    "test-uv",
                )
        self.assertEqual([], findings)
        self.assertEqual(["test-uv", "lock", "--check"], commands[0][:3])
        self.assertEqual(["test-uv", "export", "--frozen"], commands[1][:3])
        self.assertIn("--no-dev", commands[1])
        self.assertIn("--no-emit-project", commands[1])
        self.assertEqual(
            "requirements-txt", commands[1][commands[1].index("--format") + 1]
        )

    def test_missing_uv_is_reported_as_checker_infrastructure_error(self) -> None:
        root = PurePosixPath("samples/python/hosted-agents/x/src/x")
        trigger = root / "uv.lock"
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(
                checker,
                "read_tree_file",
                return_value=b'[project]\nname = "x"\nversion = "0.1.0"\n',
            ),
            mock.patch.object(checker.subprocess, "run", side_effect=FileNotFoundError),
        ):
            with self.assertRaisesRegex(checker.CheckError, "uv executable not found"):
                checker.validate_uv_resolution(
                    Path(directory),
                    "HEAD",
                    {root / "pyproject.toml", root / "uv.lock"},
                    root,
                    trigger,
                    "missing-uv",
                )

    def test_uv_validation_failure_is_reported(self) -> None:
        root = PurePosixPath("samples/python/hosted-agents/x/src/x")
        trigger = root / "uv.lock"
        completed = subprocess.CompletedProcess([], 1, "", "lock is stale")
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(
                checker,
                "read_tree_file",
                return_value=b'[project]\nname = "x"\nversion = "0.1.0"\n',
            ),
            mock.patch.object(checker.subprocess, "run", return_value=completed),
        ):
            findings = checker.validate_uv_resolution(
                Path(directory),
                "HEAD",
                {root / "pyproject.toml", root / "uv.lock"},
                root,
                trigger,
                "uv",
            )
        self.assertEqual(["PYREQ012"], [finding.code for finding in findings])
        self.assertIn("lock is stale", findings[0].detail)


if __name__ == "__main__":
    unittest.main()
