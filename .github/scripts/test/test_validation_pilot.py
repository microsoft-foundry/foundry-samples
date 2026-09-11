#!/usr/bin/env python3
"""Focused contract tests for the representative validation pilot producer."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "run-validation-pilot.py"
DISCOVERY = ROOT / "scripts" / "discover-validation-samples.py"
COMPLETENESS = ROOT / "scripts" / "validate-validation-pilot-results.py"
WORKFLOW = ROOT / "workflows" / "validation-pilot.yml"
SELFTEST_WORKFLOW = ROOT / "workflows" / "scripts-selftest.yml"

DISCOVERY_SPEC = importlib.util.spec_from_file_location("validation_discovery", DISCOVERY)
assert DISCOVERY_SPEC and DISCOVERY_SPEC.loader
validation_discovery = importlib.util.module_from_spec(DISCOVERY_SPEC)
DISCOVERY_SPEC.loader.exec_module(validation_discovery)


class ValidationPilotTests(unittest.TestCase):
    def write_fake_yq(self, directory: Path) -> Path:
        yq = directory / "yq"
        yq.write_text(
            """#!/usr/bin/env python3
import re
import sys
from pathlib import Path

import yaml

if len(sys.argv) != 4 or sys.argv[1] != "eval":
    raise SystemExit(2)

query = sys.argv[2]
document = yaml.safe_load(Path(sys.argv[3]).read_text(encoding="utf-8"))


def resolve(path):
    current = document
    if path == ".":
        return current
    for part in path.lstrip(".").split("."):
        if not part:
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(?:[[]([0-9]+)[]])?", part)
        if not match:
            raise SystemExit(2)
        current = current[match.group(1)]
        if match.group(2) is not None:
            current = current[int(match.group(2))]
    return current


def print_value(value):
    if isinstance(value, bool):
        print("true" if value else "false")
    elif value is None:
        print("null")
    elif isinstance(value, (dict, list)):
        print(yaml.safe_dump(value), end="")
    else:
        print(value)


if query == ".":
    print_value(document)
    raise SystemExit(0)

root_has_match = re.fullmatch(r'has\\("([^"]+)"\\)', query)
if root_has_match:
    print("true" if isinstance(document, dict) and root_has_match.group(1) in document else "false")
    raise SystemExit(0)

has_match = re.fullmatch(r'(.+) \\| has\\("([^"]+)"\\)', query)
if has_match:
    value = resolve(has_match.group(1))
    print("true" if isinstance(value, dict) and has_match.group(2) in value else "false")
    raise SystemExit(0)

kind_match = re.fullmatch(r"(.+) \\| kind", query)
if kind_match:
    value = resolve(kind_match.group(1))
    print("map" if isinstance(value, dict) else "seq" if isinstance(value, list) else "scalar")
    raise SystemExit(0)

tag_match = re.fullmatch(r"(.+) \\| tag", query)
if tag_match:
    value = resolve(tag_match.group(1))
    print("!!str" if isinstance(value, str) else "!!null" if value is None else "!!int")
    raise SystemExit(0)

length_match = re.fullmatch(r"(.+) \\| length", query)
if length_match:
    print(len(resolve(length_match.group(1))))
    raise SystemExit(0)

print_value(resolve(query))
""",
            encoding="utf-8",
        )
        yq.chmod(0o755)
        return yq

    def test_discovery_rejects_unsafe_or_reserved_sample_ids(self) -> None:
        invalid_ids = (
            ("python-has,comma", "must contain only"),
            ("manifest", "collides with a reserved"),
            ("run-123-4", "collides with a reserved"),
        )
        for identifier, message in invalid_ids:
            with self.subTest(identifier=identifier):
                with self.assertRaisesRegex(
                    validation_discovery.DiscoveryError,
                    message,
                ):
                    validation_discovery.validate_sample_id(
                        identifier,
                        f"samples/python/{identifier}",
                    )

    def test_workflow_calls_report_after_completeness(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  report:", workflow)
        self.assertIn("needs: completeness", workflow)
        self.assertIn("if: ${{ always() && !cancelled() }}", workflow)
        self.assertIn("uses: ./.github/workflows/validation-report.yml", workflow)
        self.assertIn(
            "results-artifact: validation-pilot-run-${{ github.run_id }}-${{ github.run_attempt }}",
            workflow,
        )

    def test_dashboard_publication_falls_back_after_optional_handoff_failures(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        publish_dashboard = workflow.split("  publish-dashboard:", 1)[1]
        self.assertEqual(publish_dashboard.count("continue-on-error: true"), 3)
        self.assertIn(
            'if [ "${{ steps.download.outcome }}" = "success" ] && \\\n'
            "            python .github/scripts/render-validation-dashboard.py",
            publish_dashboard,
        )
        self.assertIn(
            "python .github/scripts/render-fallback-dashboard.py",
            publish_dashboard,
        )

    def test_dashboard_harness_runs_fallback_renderer_tests(self) -> None:
        workflow = SELFTEST_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "python .github/scripts/test/test-render-fallback-dashboard.py",
            workflow,
        )

    def test_discovery_covers_full_inventory_and_explicitly_skips_rust(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = [
                ("csharp", "zeta", "name: zeta\n"),
                ("java", "alpha", "name: alpha\n"),
                (
                    "python",
                    "beta",
                    "name: beta\nlive_service_validation:\n  command: \"true\"\n",
                ),
                ("typescript", "gamma", "name: gamma\n"),
                ("javascript", "delta", "name: delta\n"),
                ("rust", "epsilon", "name: epsilon\n"),
            ]
            for language, name, contents in metadata:
                sample_metadata = root / "samples" / language / name / "sample.yaml"
                sample_metadata.parent.mkdir(parents=True)
                sample_metadata.write_text(contents, encoding="utf-8")
            manifest = root / "manifest.json"
            matrix = root / "matrix.json"
            build_readiness_matrix = root / "build-readiness-matrix.json"
            live_service_matrix = root / "live-service-matrix.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(DISCOVERY),
                    "--root",
                    str(root),
                    "--manifest",
                    str(manifest),
                    "--matrix",
                    str(matrix),
                    "--build-readiness-matrix",
                    str(build_readiness_matrix),
                    "--live-service-matrix",
                    str(live_service_matrix),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(
                [sample["path"] for sample in payload["samples"]],
                [
                    "samples/csharp/zeta",
                    "samples/java/alpha",
                    "samples/javascript/delta",
                    "samples/python/beta",
                    "samples/rust/epsilon",
                    "samples/typescript/gamma",
                ],
            )
            self.assertTrue(
                all(
                    set(sample) == {"id", "path", "language", "shape"}
                    for sample in payload["samples"]
                )
            )
            self.assertEqual(
                {value["validator_language"] for value in payload["validation"].values() if value["validator_language"]},
                {"csharp", "java", "python", "typescript"},
            )
            self.assertTrue(all(sample["shape"] == "full-fleet" for sample in payload["samples"]))
            declared_live_service_paths = {
                sample["path"]
                for sample in payload["samples"]
                if payload["validation"][sample["id"]][
                    "live_service_validation_declared"
                ]
            }
            self.assertEqual(
                declared_live_service_paths,
                {"samples/python/beta"},
            )
            self.assertEqual(
                payload["validation"]["javascript-delta"]["validator_language"],
                "typescript",
            )
            self.assertEqual(
                payload["validation"]["rust-epsilon"],
                {
                    "eligible": False,
                    "live_service_validation_declared": False,
                    "skip_reason": "language 'rust' is not supported by build readiness",
                    "validator_language": "",
                },
            )
            self.assertEqual(json.loads(matrix.read_text(encoding="utf-8"))["include"], [
                {**sample, **payload["validation"][sample["id"]]} for sample in payload["samples"]
            ])
            self.assertTrue(
                all(
                    not sample["live_service_validation_declared"]
                    for sample in json.loads(
                        build_readiness_matrix.read_text()
                    )["include"]
                )
            )
            self.assertEqual(
                {
                    sample["path"]
                    for sample in json.loads(live_service_matrix.read_text())[
                        "include"
                    ]
                },
                declared_live_service_paths,
            )

    def test_workflow_isolates_declared_live_service_warm_project_jobs(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(workflow.count("environment: L4-validation"), 1)
        self.assertIn(
            "matrix: ${{ fromJSON(needs.discover.outputs.build_readiness_matrix) }}",
            workflow,
        )
        self.assertIn(
            "matrix: ${{ fromJSON(needs.discover.outputs.live_service_matrix) }}",
            workflow,
        )
        self.assertIn(
            "AZURE_AI_PROJECT_ENDPOINT: ${{ vars.AZURE_AI_PROJECT_ENDPOINT }}",
            workflow,
        )
        self.assertIn(
            "MODEL_DEPLOYMENT: ${{ vars.MODEL_DEPLOYMENT }}",
            workflow,
        )
        self.assertIn('SKIP_PROVISION: "true"', workflow)
        self.assertIn('python -m pip install -r "${{ matrix.path }}/requirements.txt"', workflow)

    def test_live_service_substitutions_replace_instructional_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = root / "samples" / "python" / "substitution"
            sample.mkdir(parents=True)
            (sample / "quickstart.py").write_text(
                'PROJECT_ENDPOINT = "your_project_endpoint"\n'
                'AGENT_NAME = "your_agent_name"\n',
                encoding="utf-8",
            )
            (sample / "check.py").write_text(
                "from pathlib import Path\n"
                "text = Path('quickstart.py').read_text(encoding='utf-8')\n"
                "assert 'https://validation.example/api/projects/project' in text\n"
                "assert 'your_agent_name' in text\n",
                encoding="utf-8",
            )
            (sample / "sample.yaml").write_text(
                "name: substitution\n"
                "live_service_validation:\n"
                "  command: \"python check.py\"\n"
                "  substitutions:\n"
                "    - file: quickstart.py\n"
                "      replacements:\n"
                "        - placeholder: \"your_project_endpoint\"\n"
                "          env: AZURE_AI_PROJECT_ENDPOINT\n",
                encoding="utf-8",
            )
            self.write_fake_yq(root)
            env = {
                **os.environ,
                "PATH": f"{root}{os.pathsep}{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
                "SKIP_PROVISION": "true",
                "AZURE_AI_PROJECT_ENDPOINT": "https://validation.example/api/projects/project",
            }
            completed = subprocess.run(
                [
                    "bash",
                    str(ROOT / "scripts" / "validate-sample.sh"),
                    "--mode",
                    "live-service",
                    "--sample-dir",
                    str(sample),
                ],
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("verdict=pass", completed.stdout)
            quickstart = (sample / "quickstart.py").read_text(encoding="utf-8")
            self.assertIn("https://validation.example/api/projects/project", quickstart)
            self.assertIn("your_agent_name", quickstart)

    def test_live_service_substitutions_do_not_require_python(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = root / "samples" / "csharp" / "substitution"
            sample.mkdir(parents=True)
            (sample / "Program.cs").write_text(
                'var endpoint = "your_project_endpoint";\n',
                encoding="utf-8",
            )
            (sample / "sample.yaml").write_text(
                "name: substitution\n"
                "live_service_validation:\n"
                "  command: \"grep -q 'https://validation.example/api/projects/project' Program.cs\"\n"
                "  substitutions:\n"
                "    - file: Program.cs\n"
                "      replacements:\n"
                "        - placeholder: \"your_project_endpoint\"\n"
                "          env: AZURE_AI_PROJECT_ENDPOINT\n",
                encoding="utf-8",
            )
            self.write_fake_yq(root)
            # A caller without a Python toolchain must still get substitutions.
            broken_python = root / "python"
            broken_python.write_text(
                "#!/bin/sh\necho 'python must not be required' >&2\nexit 97\n",
                encoding="utf-8",
            )
            broken_python.chmod(0o755)
            env = {
                **os.environ,
                "PATH": f"{root}{os.pathsep}{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
                "SKIP_PROVISION": "true",
                "AZURE_AI_PROJECT_ENDPOINT": "https://validation.example/api/projects/project",
            }
            completed = subprocess.run(
                [
                    "bash",
                    str(ROOT / "scripts" / "validate-sample.sh"),
                    "--mode",
                    "live-service",
                    "--sample-dir",
                    str(sample),
                ],
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("verdict=pass", completed.stdout)
            self.assertNotIn("python must not be required", completed.stderr)
            self.assertEqual(
                (sample / "Program.cs").read_text(encoding="utf-8"),
                'var endpoint = "https://validation.example/api/projects/project";\n',
            )

    def test_live_service_substitutions_reject_trailing_parent_directory_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = root / "samples" / "python" / "parent"
            (sample / "subdir").mkdir(parents=True)
            (sample / "sample.yaml").write_text(
                "name: parent\n"
                "live_service_validation:\n"
                "  command: \"true\"\n"
                "  substitutions:\n"
                "    - file: subdir/..\n"
                "      replacements:\n"
                "        - placeholder: \"your_project_endpoint\"\n"
                "          env: AZURE_AI_PROJECT_ENDPOINT\n",
                encoding="utf-8",
            )
            self.write_fake_yq(root)
            env = {
                **os.environ,
                "PATH": f"{root}{os.pathsep}{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
                "SKIP_PROVISION": "true",
                "AZURE_AI_PROJECT_ENDPOINT": "https://validation.example/api/projects/project",
            }
            completed = subprocess.run(
                [
                    "bash",
                    str(ROOT / "scripts" / "validate-sample.sh"),
                    "--mode",
                    "live-service",
                    "--sample-dir",
                    str(sample),
                ],
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(completed.returncode, 2, completed.stdout)
            self.assertIn("must stay inside the sample directory: subdir/..", completed.stderr)

    def test_live_service_substitutions_treat_glob_placeholders_literally(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = root / "samples" / "python" / "literal"
            sample.mkdir(parents=True)
            (sample / "config.txt").write_text(
                "value=token*?[value]\n"
                "other=tokenXYZvalue\n"
                "again=token*?[value]\n",
                encoding="utf-8",
            )
            (sample / "sample.yaml").write_text(
                "name: literal\n"
                "live_service_validation:\n"
                "  command: \"grep -Fq 'literal replacement' config.txt && grep -Fq 'tokenXYZvalue' config.txt\"\n"
                "  substitutions:\n"
                "    - file: config.txt\n"
                "      replacements:\n"
                "        - placeholder: \"token*?[value]\"\n"
                "          env: AZURE_AI_PROJECT_ENDPOINT\n",
                encoding="utf-8",
            )
            self.write_fake_yq(root)
            env = {
                **os.environ,
                "PATH": f"{root}{os.pathsep}{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
                "SKIP_PROVISION": "true",
                "AZURE_AI_PROJECT_ENDPOINT": "literal replacement",
            }
            completed = subprocess.run(
                [
                    "bash",
                    str(ROOT / "scripts" / "validate-sample.sh"),
                    "--mode",
                    "live-service",
                    "--sample-dir",
                    str(sample),
                ],
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                (sample / "config.txt").read_text(encoding="utf-8"),
                "value=literal replacement\n"
                "other=tokenXYZvalue\n"
                "again=literal replacement\n",
            )

    def test_live_service_substitutions_leave_files_untouched_when_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = root / "samples" / "python" / "partial"
            sample.mkdir(parents=True)
            original = (
                'PROJECT_ENDPOINT = "your_project_endpoint"\n'
                'AGENT_NAME = "your_agent_name"\n'
            )
            (sample / "quickstart.py").write_text(original, encoding="utf-8")
            (sample / "sample.yaml").write_text(
                "name: partial\n"
                "live_service_validation:\n"
                "  command: \"true\"\n"
                "  substitutions:\n"
                "    - file: quickstart.py\n"
                "      replacements:\n"
                "        - placeholder: \"your_project_endpoint\"\n"
                "          env: AZURE_AI_PROJECT_ENDPOINT\n"
                "        - placeholder: \"missing_placeholder\"\n"
                "          env: AZURE_AI_PROJECT_ENDPOINT\n",
                encoding="utf-8",
            )
            self.write_fake_yq(root)
            env = {
                **os.environ,
                "PATH": f"{root}{os.pathsep}{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
                "SKIP_PROVISION": "true",
                "AZURE_AI_PROJECT_ENDPOINT": "https://validation.example/api/projects/project",
            }
            completed = subprocess.run(
                [
                    "bash",
                    str(ROOT / "scripts" / "validate-sample.sh"),
                    "--mode",
                    "live-service",
                    "--sample-dir",
                    str(sample),
                ],
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(completed.returncode, 2, completed.stdout)
            self.assertIn("verdict=error", completed.stdout)
            self.assertEqual(
                (sample / "quickstart.py").read_text(encoding="utf-8"), original
            )

    def test_live_service_substitutions_reject_binary_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = root / "samples" / "python" / "binary"
            sample.mkdir(parents=True)
            original = b'your_project_endpoint\x00binary\n'
            (sample / "payload.bin").write_bytes(original)
            (sample / "sample.yaml").write_text(
                "name: binary\n"
                "live_service_validation:\n"
                "  command: \"true\"\n"
                "  substitutions:\n"
                "    - file: payload.bin\n"
                "      replacements:\n"
                "        - placeholder: \"your_project_endpoint\"\n"
                "          env: AZURE_AI_PROJECT_ENDPOINT\n",
                encoding="utf-8",
            )
            self.write_fake_yq(root)
            env = {
                **os.environ,
                "PATH": f"{root}{os.pathsep}{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
                "SKIP_PROVISION": "true",
                "AZURE_AI_PROJECT_ENDPOINT": "https://validation.example/api/projects/project",
            }
            completed = subprocess.run(
                [
                    "bash",
                    str(ROOT / "scripts" / "validate-sample.sh"),
                    "--mode",
                    "live-service",
                    "--sample-dir",
                    str(sample),
                ],
                capture_output=True,
                text=True,
                env=env,
            )

            self.assertEqual(completed.returncode, 2, completed.stdout)
            self.assertIn("NUL-free text file", completed.stderr)
            self.assertEqual((sample / "payload.bin").read_bytes(), original)

    def test_discovery_jobs_install_pinned_dependencies(self) -> None:
        for workflow_path in (WORKFLOW, SELFTEST_WORKFLOW):
            workflow = workflow_path.read_text(encoding="utf-8")
            self.assertIn("uses: actions/setup-python@v5", workflow)
            self.assertIn("python-version: '3.12'", workflow)
            self.assertIn(
                "python -m pip install -r .github/scripts/requirements.txt",
                workflow,
            )

    def test_discovery_rejects_legacy_l4_metadata_with_migration_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = root / "samples" / "python" / "legacy"
            sample.mkdir(parents=True)
            (sample / "sample.yaml").write_text(
                "name: legacy\nl4:\n  command: \"true\"\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(DISCOVERY),
                    "--root",
                    str(root),
                    "--manifest",
                    str(root / "manifest.json"),
                    "--matrix",
                    str(root / "matrix.json"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn(
                "rename it to 'live_service_validation'", completed.stderr
            )

    def test_discovery_recognizes_indented_live_service_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = root / "samples" / "python" / "indented"
            sample.mkdir(parents=True)
            (sample / "sample.yaml").write_text(
                "  name: indented\n"
                "  live_service_validation:\n"
                "    command: \"true\"\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(DISCOVERY),
                    "--root",
                    str(root),
                    "--manifest",
                    str(root / "manifest.json"),
                    "--matrix",
                    str(root / "matrix.json"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            manifest = json.loads(
                (root / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertTrue(
                manifest["validation"]["python-indented"][
                    "live_service_validation_declared"
                ]
            )

    def test_discovery_skips_malformed_yaml_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            broken = root / "samples" / "python" / "broken" / "sample.yaml"
            broken.parent.mkdir(parents=True)
            broken.write_text("live_service_validation: [\n", encoding="utf-8")
            valid = root / "samples" / "python" / "valid" / "sample.yaml"
            valid.parent.mkdir(parents=True)
            valid.write_text("name: valid\n", encoding="utf-8")

            payload = validation_discovery.discover(root)

            broken_validation = payload["validation"]["python-broken"]
            self.assertFalse(broken_validation["eligible"])
            self.assertFalse(
                broken_validation["live_service_validation_declared"]
            )
            self.assertIn(
                "samples/python/broken/sample.yaml: invalid YAML",
                broken_validation["skip_reason"],
            )
            self.assertTrue(payload["validation"]["python-valid"]["eligible"])

    def test_discovery_marks_unreadable_yaml_with_metadata_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "samples" / "python" / "unreadable" / "sample.yaml"
            metadata.parent.mkdir(parents=True)
            metadata.write_text("name: unreadable\n", encoding="utf-8")
            with mock.patch.object(
                Path,
                "read_text",
                side_effect=PermissionError("permission denied"),
            ):
                payload = validation_discovery.discover(root)

            validation = payload["validation"]["python-unreadable"]
            self.assertFalse(validation["eligible"])
            self.assertRegex(
                validation["skip_reason"],
                r"samples/python/unreadable/sample\.yaml: could not read",
            )

    def test_discovery_rejects_duplicate_derived_sample_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "samples" / "python" / "a-b" / "sample.yaml"
            second = root / "samples" / "python" / "a" / "b" / "sample.yaml"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_text("name: first\n", encoding="utf-8")
            second.write_text("live_service_validation: [\n", encoding="utf-8")

            with self.assertRaisesRegex(
                validation_discovery.DiscoveryError,
                "duplicate derived sample ID 'python-a-b'",
            ):
                validation_discovery.discover(root)

    def test_sample_failure_is_a_complete_valid_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            validator = root / "validator.sh"
            validator.write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
            output = root / "sample-result.json"
            diagnostic = root / "diagnostics.log"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--sample-id",
                    "fixture",
                    "--language",
                    "python",
                    "--shape",
                    "fixture",
                    "--sample-path",
                    "samples/python/fixture",
                    "--validator",
                    str(validator),
                    "--bash",
                    sys.executable,
                    "--output",
                    str(output),
                    "--diagnostic",
                    str(diagnostic),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["outcome"], "sample failure")
            self.assertEqual(result["completed_stage"], "build readiness validation")
            self.assertTrue(diagnostic.is_file())

    def test_completeness_rejects_missing_matrix_member(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "samples": [
                            {"id": "one", "path": "samples/python/one", "language": "python", "shape": "fixture"},
                            {"id": "two", "path": "samples/java/two", "language": "java", "shape": "fixture"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            artifacts = root / "artifacts" / "validation-pilot-one"
            artifacts.mkdir(parents=True)
            (artifacts / "diagnostics.log").write_text("diagnostic\n", encoding="utf-8")
            (artifacts / "sample-result.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "sample": {"id": "one", "path": "samples/python/one", "language": "python", "shape": "fixture"},
                        "outcome": "passed",
                        "completed_stage": "build readiness validation",
                        "duration_seconds": 1,
                        "diagnostic_reference": "diagnostics.log",
                        "artifact_reference": "sample-result.json",
                        "completed_at": "2026-08-10T00:00:00Z",
                        "run": {"run_id": "1"},
                    }
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(COMPLETENESS),
                    "--manifest",
                    str(manifest),
                    "--artifacts",
                    str(root / "artifacts"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("missing result artifacts: two", completed.stderr)

    def test_completeness_accepts_historical_schema_one_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = {
                "id": "one",
                "path": "samples/python/one",
                "language": "python",
                "shape": "fixture",
            }
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps({"schema_version": 1, "samples": [sample]}),
                encoding="utf-8",
            )
            artifact = root / "artifacts" / "validation-pilot-one"
            artifact.mkdir(parents=True)
            (artifact / "diagnostics.log").write_text(
                "diagnostic\n", encoding="utf-8"
            )
            (artifact / "sample-result.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "sample": sample,
                        "outcome": "passed",
                        "completed_stage": "L3 validation",
                        "duration_seconds": 1,
                        "diagnostic_reference": "diagnostics.log",
                        "artifact_reference": "sample-result.json",
                        "completed_at": "2026-08-10T00:00:00Z",
                        "run": {"run_id": "1"},
                    }
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(COMPLETENESS),
                    "--manifest",
                    str(manifest),
                    "--artifacts",
                    str(root / "artifacts"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(
                (root / "artifacts" / "run-summary.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(summary["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
