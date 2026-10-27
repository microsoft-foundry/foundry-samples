"""Fail-closed regression coverage for sample-owned evidence verifiers."""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hosted_agent_test_spec as spec


class EvidenceVerifierTests(unittest.TestCase):
    def document(self, verifier="verify.py"):
        test = {"name": "artifact", "turns": [{"input": "hello"}]}
        if verifier is not None:
            test["verifier"] = verifier
        return {
            "version": 1,
            "sample": {"owner": "sampleowner", "experiences": ["azd"]},
            "tests": [test],
        }

    def fixture(self, root, body):
        (root / "verify.py").write_text(body, encoding="utf-8")
        source = root / "test-spec.yml"
        source.write_text(json.dumps(self.document()), encoding="utf-8")
        return spec.build_plan(spec.load_spec(source), verifier_directory=root)

    def test_existing_contracts_do_not_gain_verifier_execution(self):
        plan = spec.build_plan(self.document(None))
        self.assertNotIn("verifier", plan["tests"][0])

    def test_paths_shell_commands_and_non_python_files_are_rejected(self):
        for value in [
            "../verify.py",
            "/tmp/verify.py",
            "C:\\verify.py",
            "nested/verify.py",
            "verify.sh",
            "python verify.py",
        ]:
            with self.subTest(value=value), self.assertRaises(spec.SpecError):
                spec.validate_spec(self.document(value))

    def test_missing_script_and_unsupported_profile_fail_planning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "test-spec.yml"
            source.write_text(json.dumps(self.document()), encoding="utf-8")
            with self.assertRaises(spec.SpecError):
                spec.load_spec(source)
            (root / "verify.py").write_text("", encoding="utf-8")
            with self.assertRaises(spec.SpecError):
                spec.build_plan(
                    spec.load_spec(source), verifier_directory=root, profile="prompt"
                )
            with self.assertRaises(spec.SpecError):
                spec.build_plan(spec.load_spec(source))

    def test_symlink_cannot_escape_fixture_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "fixture"
            fixture.mkdir()
            outside = root / "outside.py"
            outside.write_text("", encoding="utf-8")
            try:
                (fixture / "verify.py").symlink_to(outside)
            except OSError:
                self.skipTest("Creating symlinks is not permitted on this host")
            with self.assertRaises(spec.SpecError):
                spec.build_plan(self.document(), verifier_directory=fixture)

    def test_script_receives_evidence_directory_and_global_turn_numbers(self):
        body = (
            "import argparse,json,pathlib\n"
            "parser=argparse.ArgumentParser()\n"
            "parser.add_argument('--evidence-dir',required=True)\n"
            "parser.add_argument('--turns',nargs='+',required=True)\n"
            "args=parser.parse_args()\n"
            "assert pathlib.Path(args.evidence_dir).is_absolute()\n"
            "assert args.turns==['1']\n"
            "print(json.dumps({'status':'passed','reason':'checked'}))\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self.fixture(root, body)
            result = spec._evaluate_verifier(plan["tests"][0], root, root)
            self.assertEqual(result["status"], "passed")

    def test_failed_or_invalid_verifier_output_cannot_pass(self):
        bodies = [
            'print(\'{"status":"failed","reason":"bad_digest"}\')',
            'print(\'{"status":"passed","reason":"checked"}\'); raise SystemExit(1)',
            "print('not json')",
            'print(\'{"status":"passed"}\')',
            'print(\'{"status":"passed","reason":"https://secret.invalid?sig=private"}\')',
        ]
        for body in bodies:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plan = self.fixture(root, body)
                result = spec._evaluate_verifier(plan["tests"][0], root, root)
                self.assertEqual(result["status"], "failed")
                self.assertNotIn("private", json.dumps(result))

    def test_timeout_and_tampered_path_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self.fixture(root, "")
            with patch.object(
                spec.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("verifier", 240),
            ):
                self.assertEqual(
                    spec._evaluate_verifier(plan["tests"][0], root, root)["status"],
                    "failed",
                )
            plan["tests"][0]["verifier"] = "../verify.py"
            self.assertEqual(
                spec._evaluate_verifier(plan["tests"][0], root, root)["status"],
                "failed",
            )

    def test_verifier_failure_is_additional_gate_and_cannot_override_failed_turn(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self.fixture(
                root, 'print(\'{"status":"failed","reason":"changed"}\')'
            )
            status = root / "turn-1-status.json"
            execution = {
                "exit_code": 0,
                "mcp_approvals": {
                    "automatic": False,
                    "pending": 0,
                    "error": None,
                    "steps": [],
                },
            }
            status.write_text(json.dumps(execution), encoding="utf-8")
            result = spec.evaluate_plan(
                plan, root, root / "console", root / "trace", verifier_directory=root
            )
            self.assertEqual(result["status"], "failed")
            execution["exit_code"] = 1
            status.write_text(json.dumps(execution), encoding="utf-8")
            (root / "verify.py").write_text(
                'print(\'{"status":"passed","reason":"checked"}\')', encoding="utf-8"
            )
            result = spec.evaluate_plan(
                plan, root, root / "console", root / "trace", verifier_directory=root
            )
            self.assertEqual(result["status"], "error")

    def test_non_applicable_tests_do_not_execute_verifier(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self.fixture(root, "raise SystemExit(1)")
            plan["tests"][0].update(status="not_applicable", reason="not selected")
            with patch.object(spec.subprocess, "run") as execute:
                result = spec.evaluate_plan(
                    plan,
                    root,
                    root / "console",
                    root / "trace",
                    verifier_directory=root,
                )
            execute.assert_not_called()
            self.assertEqual(result["status"], "not_applicable")

    def test_plans_are_portable_and_execution_requires_fixture_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self.fixture(
                root, 'print(\'{"status":"passed","reason":"checked"}\')'
            )
            self.assertEqual(plan["tests"][0]["verifier"], "verify.py")
            self.assertNotIn(str(root), json.dumps(plan))
            result = spec._evaluate_verifier(plan["tests"][0], root)
            self.assertEqual(result["status"], "failed")

    def test_cli_failure_writes_report_without_disclosing_verifier_streams(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self.fixture(
                root,
                'import sys; print(\'{"status":"failed","reason":"changed"}\'); print(\'https://secret.invalid?sig=private\',file=sys.stderr)',
            )
            plan_path = root / "plan.json"
            report_path = root / "report.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            execution = {
                "exit_code": 0,
                "mcp_approvals": {
                    "automatic": False,
                    "pending": 0,
                    "error": None,
                    "steps": [],
                },
            }
            (root / "turn-1-status.json").write_text(
                json.dumps(execution), encoding="utf-8"
            )
            messages = io.StringIO()
            with contextlib.redirect_stdout(messages):
                result = spec.main(
                    [
                        "evaluate",
                        "--plan",
                        str(plan_path),
                        "--evidence-dir",
                        str(root),
                        "--console-log",
                        str(root / "console"),
                        "--trace-file",
                        str(root / "trace"),
                        "--verifier-directory",
                        str(root),
                        "--report",
                        str(report_path),
                    ]
                )
            self.assertEqual(result, 1)
            self.assertEqual(
                json.loads(report_path.read_text(encoding="utf-8"))["status"], "failed"
            )
            self.assertNotIn("private", messages.getvalue())


if __name__ == "__main__":
    unittest.main()
