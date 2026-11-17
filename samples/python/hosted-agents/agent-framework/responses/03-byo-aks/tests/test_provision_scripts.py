import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SAMPLE = Path(__file__).resolve().parents[1]

FAKE_AZ = r"""#!/usr/bin/env python
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["FAKE_AZ_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\n")

case = os.environ["FAKE_AZ_CASE"]
json_output = "json" in args
if args[:2] == ["group", "show"]:
    pass
elif args[:1] == ["rest"]:
    rows = [
        ["Standard_D4ds_v5", "4", "16", "True", "True", "V2", "x64"],
        ["Standard_D8as_v5", "8", "32", "True", "True", "V2", "x64"],
    ]
    if json_output:
        keys = ["Name", "Vcpus", "MemoryGB", "PremiumIO", "AcceleratedNetworking", "HyperVGenerations", "Architecture"]
        print(json.dumps([dict(zip(keys, row)) for row in rows]))
    else:
        print("\n".join("\t".join(row) for row in rows))
elif args[:2] == ["aks", "list"]:
    if case == "cluster-list-fails":
        print("simulated cluster list failure", file=sys.stderr)
        sys.exit(3)
    names = [] if case == "create" else ["test-aks"]
    print(json.dumps(names) if json_output else "\n".join(names))
elif args[:3] == ["aks", "nodepool", "list"]:
    if case == "pool-list-fails":
        print("simulated node pool list failure", file=sys.stderr)
        sys.exit(3)
    names = [] if case == "create" else ["sandbox"]
    print(json.dumps(names) if json_output else "\n".join(names))
elif args[:2] == ["aks", "show"] or args[:3] == ["aks", "nodepool", "show"]:
    if case == "cluster-show-retry" and args[:2] == ["aks", "show"]:
        with open(os.environ["FAKE_AZ_LOG"], encoding="utf-8") as log:
            attempts = sum(json.loads(line)[:2] == ["aks", "show"] for line in log)
        if attempts == 1:
            print("simulated transient query failure", file=sys.stderr)
            sys.exit(3)
    print("Succeeded")
elif args[:2] == ["aks", "create"] or args[:3] == ["aks", "nodepool", "add"]:
    if case != "create":
        sys.exit("unexpected mutation")
else:
    sys.exit("unexpected az command: " + repr(args))
"""


class ProvisionScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shells = []
        if bash := shutil.which("bash"):
            cls.shells.append(("bash", [bash, str(SAMPLE / "provision_aks.sh")]))
        if pwsh := shutil.which("pwsh"):
            cls.shells.append(("powershell", [pwsh, "-NoProfile", "-File", str(SAMPLE / "provision_aks.ps1")]))
        if not cls.shells:
            raise unittest.SkipTest("Neither Bash nor PowerShell is available")

    def run_script(self, shell, command, case, apply=True, version="1.36.3"):
        with tempfile.TemporaryDirectory(prefix="byo-aks-fake-az-") as directory:
            temp = Path(directory)
            fake = temp / "fake_az.py"
            fake.write_text(FAKE_AZ, encoding="utf-8")
            fake.chmod(0o755)
            if os.name == "nt":
                (temp / "az.cmd").write_text(
                    f'@echo off\r\n"{sys.executable}" "{fake}" %*\r\nexit /b %errorlevel%\r\n',
                    encoding="utf-8",
                )
                (temp / "az").write_text(
                    '#!/usr/bin/env bash\nexec python "$FAKE_AZ_SCRIPT" "$@"\n',
                    encoding="utf-8",
                )
            else:
                shutil.copyfile(fake, temp / "az")
                (temp / "az").chmod(0o755)

            log = temp / "calls.jsonl"
            env = os.environ.copy()
            env.update(
                PATH=str(temp) + os.pathsep + env.get("PATH", ""),
                AZURE_SUBSCRIPTION_ID="test-subscription",
                RESOURCE_GROUP="test-rg",
                AZURE_LOCATION="westus2",
                AKS_NAME="test-aks",
                KUBERNETES_VERSION=version,
                FAKE_AZ_LOG=str(log),
                FAKE_AZ_CASE=case,
                FAKE_AZ_SCRIPT=str(fake),
                SKU_QUERY_TIMEOUT_SECONDS="20",
                SKU_QUERY_MAX_ATTEMPTS="1",
            )
            flag = ["--apply"] if shell == "bash" else ["-Apply"]
            result = subprocess.run(
                command + (flag if apply else []),
                cwd=SAMPLE,
                env=env,
                text=True,
                capture_output=True,
                timeout=60,
            )
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            return result, calls

    def test_preview_requires_explicit_version_and_never_calls_azure(self):
        for shell, command in self.shells:
            with self.subTest(shell=shell):
                result, calls = self.run_script(shell, command, "reuse", apply=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Mode:                    preview", result.stdout)
                self.assertEqual(calls, [])

                result, calls = self.run_script(shell, command, "reuse", apply=False, version="")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("KUBERNETES_VERSION", result.stderr)
                self.assertEqual(calls, [])

    def test_failed_discovery_never_creates_a_cluster_or_pool(self):
        for shell, command in self.shells:
            for case in ("cluster-list-fails", "pool-list-fails"):
                with self.subTest(shell=shell, case=case):
                    result, calls = self.run_script(shell, command, case)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Failed to list", result.stderr)
                    self.assertTrue(calls, result.stdout + result.stderr)
                    self.assertFalse(any(call[:2] == ["aks", "create"] for call in calls))
                    self.assertFalse(any(call[:3] == ["aks", "nodepool", "add"] for call in calls))

    def test_create_and_reuse_never_change_account_or_network_rules(self):
        for shell, command in self.shells:
            for case in ("create", "reuse"):
                with self.subTest(shell=shell, case=case):
                    result, calls = self.run_script(shell, command, case)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertTrue(calls)
                    self.assertFalse(any(call[:2] == ["account", "set"] for call in calls))
                    self.assertFalse(any(call[:1] == ["network"] for call in calls))
                    for call in calls:
                        if call[:1] != ["rest"]:
                            self.assertIn("--subscription", call)
                            self.assertIn("test-subscription", call)
                    cluster_creates = [call for call in calls if call[:2] == ["aks", "create"]]
                    pool_creates = [call for call in calls if call[:3] == ["aks", "nodepool", "add"]]
                    self.assertEqual(len(cluster_creates), int(case == "create"))
                    self.assertEqual(len(pool_creates), int(case == "create"))
                    if pool_creates:
                        self.assertIn("KataVmIsolation", pool_creates[0])
                        self.assertIn("agents.ai.azure.com/sandbox-node=true", pool_creates[0])

    def test_failed_provisioning_query_is_reported_and_retried(self):
        for shell, command in self.shells:
            with self.subTest(shell=shell):
                result, calls = self.run_script(shell, command, "cluster-show-retry")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Could not query provisioning state", result.stdout + result.stderr)
                self.assertEqual(sum(call[:2] == ["aks", "show"] for call in calls), 2)


if __name__ == "__main__":
    unittest.main()
