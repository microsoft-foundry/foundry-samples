"""Exercise the shared startup rule using framework-independent manifests."""

import importlib.util
import contextlib
import io
from pathlib import Path
import tempfile
import unittest

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "check_hosted_agent_startup.py"
SPEC = importlib.util.spec_from_file_location("check_hosted_agent_startup", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
RUNNER = module.HOSTING_MODULE


class StartupPolicyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.repo = Path(directory.name)
        self.path = self.repo / module.SAMPLE_ROOT / "framework/scenario/azure.yaml"
        self.path.parent.mkdir(parents=True)
        self.service = {
            "host": "azure.ai.agent",
            "codeConfiguration": {"entryPoint": f"-m {RUNNER} --protocol responses"},
            "startupCommand": f"uv run --no-sync python -m {RUNNER} --protocol responses",
            "protocols": [{"protocol": "responses", "version": "99.0"}],
        }

    def check(self):
        self.path.write_text(
            yaml.safe_dump({"services": {"arbitrary-name": self.service}}), encoding="utf-8"
        )
        return module.check_repository(self.repo)

    def assert_valid(self):
        self.assertEqual(self.check(), (1, []))

    def assert_invalid(self, message):
        count, errors = self.check()
        self.assertEqual(count, 1)
        self.assertTrue(any(message in error for error in errors), errors)

    def test_equivalent_launchers_and_argument_order(self):
        for command in (
            f"python -m {RUNNER} --protocol responses",
            f"python3.13 -u -m {RUNNER} --config ./langgraph.json --protocol=responses",
            f".venv/bin/python -m {RUNNER} --port 9000 --host 127.0.0.1 --protocol responses",
            f"uv run --frozen --python 3.13 python -m {RUNNER} --protocol responses",
            f"uv run --no-sync --module {RUNNER} --protocol responses",
            f'"C:\\Program Files\\Python313\\python.exe" -m {RUNNER} --protocol responses',
            ["python", "-m", RUNNER, "--protocol", "responses"],
        ):
            with self.subTest(command=command):
                self.service["startupCommand"] = command
                self.assert_valid()

    def test_missing_empty_or_non_hosting_startup_fails(self):
        for command in (None, "", "python main.py", f"echo python -m {RUNNER} --protocol responses"):
            with self.subTest(command=command):
                self.service["startupCommand"] = command
                self.assert_invalid("startupCommand" if not command else "module")

    def test_protocol_mismatch_fails(self):
        self.service["startupCommand"] = f"python -m {RUNNER} --protocol invocations"
        self.assert_invalid("protocol must match")

    def test_invocations_is_supported(self):
        self.service["codeConfiguration"]["entryPoint"] = f"-m {RUNNER} --protocol invocations"
        self.service["startupCommand"] = f"python -m {RUNNER} --protocol invocations"
        self.service["protocols"] = [{"protocol": "invocations"}]
        self.assert_valid()

    def test_hosted_entrypoint_can_be_an_argument_array(self):
        self.service["codeConfiguration"]["entryPoint"] = [
            "-m", RUNNER, "--protocol", "responses",
        ]
        self.assert_valid()

    def test_local_command_requires_a_launcher(self):
        self.service["startupCommand"] = f"-m {RUNNER} --protocol responses"
        self.assert_invalid("invoked by Python or uv run")

    def test_python_does_not_accept_uv_only_module_flag(self):
        self.service["codeConfiguration"]["entryPoint"] = f"--module {RUNNER} --protocol responses"
        self.assert_invalid("invoked by Python or uv run")

    def test_missing_or_different_protocol_declaration_fails(self):
        for protocols in (None, [], [{"protocol": "invocations"}], "responses"):
            with self.subTest(protocols=protocols):
                self.service["protocols"] = protocols
                self.assert_invalid("protocols must declare")

    def test_option_order_and_json_whitespace_are_irrelevant(self):
        self.service["codeConfiguration"]["entryPoint"] += (
            " --option resilient_background=true --option steerable_conversations=true"
        )
        self.service["startupCommand"] += (
            ' --option="steerable_conversations= true " --option resilient_background=true'
        )
        self.assert_valid()

    def test_missing_changed_or_extra_options_fail(self):
        self.service["codeConfiguration"]["entryPoint"] += " --option resilient_background=true"
        for options in ("", " --option resilient_background=false", " --option resilient_background=1",
                        " --option resilient_background=true --option steerable_conversations=true"):
            with self.subTest(options=options):
                self.service["startupCommand"] = f"python -m {RUNNER} --protocol responses{options}"
                self.assert_invalid("options must match")

    def test_last_option_wins_as_in_the_hosting_cli(self):
        self.service["codeConfiguration"]["entryPoint"] += " --option setting=old --option setting=new"
        self.service["startupCommand"] += " --option setting=new"
        self.assert_valid()

    def test_invalid_module_arguments_fail(self):
        for arguments in ("", "--protocol", "--protocol responses --option bad",
                          "--protocol responses --option =true", "--protocol responses --option key="):
            with self.subTest(arguments=arguments):
                self.service["startupCommand"] = f"python -m {RUNNER} {arguments}"
                count, errors = self.check()
                self.assertEqual(count, 1)
                self.assertTrue(errors)

    def test_graph_and_config_must_match(self):
        for arguments, setting in (("other-agent --protocol responses", "agent"),
                                   ("--protocol responses --config another.json", "config")):
            with self.subTest(arguments=arguments):
                self.service["startupCommand"] = f"python -m {RUNNER} {arguments}"
                self.assert_invalid(f"{setting} must match")

    def test_one_sided_migration_to_or_from_module_hosting_fails(self):
        self.service["codeConfiguration"]["entryPoint"] = "main.py"
        self.assert_invalid("must invoke")

    def test_custom_hosts_are_not_subject_to_module_rule(self):
        self.service["codeConfiguration"]["entryPoint"] = "main.py"
        self.service.pop("startupCommand")
        self.assertEqual(self.check(), (0, []))

    def test_other_service_types_are_ignored(self):
        self.service["host"] = "azure.ai.project"
        self.service.pop("startupCommand")
        self.assertEqual(self.check(), (0, []))

    def test_discovery_is_independent_of_sample_and_service_names(self):
        self.assert_valid()
        relocated = self.repo / module.SAMPLE_ROOT / "different/nested/location/azure.yaml"
        relocated.parent.mkdir(parents=True)
        self.path.rename(relocated)
        self.assertEqual(module.check_repository(self.repo), (1, []))

    def test_all_manifests_are_checked_not_just_one_sample(self):
        self.assert_valid()
        other = self.path.parent.parent / "another/azure.yaml"
        other.parent.mkdir()
        service = dict(self.service)
        service.pop("startupCommand")
        other.write_text(yaml.safe_dump({"services": {"second": service}}), encoding="utf-8")
        count, errors = module.check_repository(self.repo)
        self.assertEqual(count, 2)
        self.assertEqual(len(errors), 1)
        self.assertIn("services.second", errors[0])

    def test_invalid_manifests_fail(self):
        for contents in ("[invalid yaml", "[]", "services: []"):
            with self.subTest(contents=contents):
                self.path.write_text(contents, encoding="utf-8")
                self.assertTrue(module.check_repository(self.repo)[1])

    def test_invalid_commands_fail_without_crashing_the_checker(self):
        for field in ("startupCommand", "entryPoint"):
            for command in ('python "unterminated', {"command": "python"}, ["python", None]):
                with self.subTest(field=field, command=command):
                    service = self.service if field == "startupCommand" else self.service["codeConfiguration"]
                    previous = service[field]
                    service[field] = command
                    self.assertTrue(self.check()[1])
                    service[field] = previous

    def test_cli_returns_failure_for_invalid_configuration(self):
        self.assert_valid()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(module.main(["--repo-root", str(self.repo)]), 0)
            self.service.pop("startupCommand")
            self.check()
            self.assertEqual(module.main(["--repo-root", str(self.repo)]), 1)

    def test_wrong_repository_root_does_not_silently_pass(self):
        self.assertTrue(module.check_repository(self.repo / "missing")[1])


if __name__ == "__main__":
    unittest.main()
