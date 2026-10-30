"""Exercise the three samples through real HTTP and independent server processes."""

import contextlib
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from a2a.types import Task
from google.protobuf.json_format import ParseDict

ROOT = Path(__file__).resolve().parents[6]
SAMPLES = ROOT / "samples/python/hosted-agents/bring-your-own/a2a"
HELPER = (
    ROOT / ".azure-pipelines/scripts/hosted-agents/scripts/invoke_hosted_agent_a2a.py"
)
SPEC = importlib.util.spec_from_file_location("a2a_smoke", HELPER)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
PROJECTS = {
    "echo": SAMPLES / "echo/src/echo-a2a",
    "report": SAMPLES / "long-running-tasks/src/report-a2a",
    "persistence": SAMPLES / "task-persistence/src/persistent-a2a",
}
UV = shutil.which("uv")
if UV is None:
    raise RuntimeError("Install uv 0.11.7 or later to run the sample tests")


def sample_environment(project):
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(
            (
                "FOUNDRY_",
                "APPLICATIONINSIGHTS_",
                "OTEL_",
                "PIP_",
                "UV_INDEX",
                "UV_DEFAULT_INDEX",
                "UV_EXTRA_INDEX",
            )
        )
        and key
        not in {
            "PYTHONPATH",
            "VIRTUAL_ENV",
            "UV_PROJECT_ENVIRONMENT",
            "UV_CONFIG_FILE",
            "UV_PRERELEASE",
        }
    }
    environment["UV_CACHE_DIR"] = str(project.parent / "uv-cache")
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


@contextlib.contextmanager
def server(project, state_root):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as log:
        environment = sample_environment(project)
        environment.update(
            PORT=str(port),
            HOST="127.0.0.1",
            A2A_AGENT_URL=f"http://127.0.0.1:{port}/a2a",
            AGENTSERVER_STATE_ROOT=str(state_root),
            PYTHONNOUSERSITE="1",
        )
        process = subprocess.Popen(
            [UV, "run", "--frozen", "--python", sys.executable, "python", "main.py"],
            cwd=project,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        endpoint = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 180
            while True:
                if process.poll() is not None:
                    log.seek(0)
                    raise RuntimeError(
                        f"{project.name} exited during startup:\n{log.read()}"
                    )
                try:
                    with urlopen(endpoint + "/readiness", timeout=1) as response:
                        if response.status == 200:
                            break
                except (URLError, TimeoutError):
                    if time.monotonic() >= deadline:
                        log.seek(0)
                        raise TimeoutError(
                            f"{project.name} did not become ready:\n{log.read()}"
                        )
                    time.sleep(0.05)
            yield module.A2AClient(endpoint + "/a2a"), process, log
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


class NativeSampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory(prefix="native-a2a-frozen-")
        cls.addClassCleanup(directory.cleanup)
        cls.projects = {}
        for name, source in PROJECTS.items():
            target = Path(directory.name) / name
            shutil.copytree(
                source,
                target,
                ignore=shutil.ignore_patterns(
                    ".venv", "__pycache__", "*.pyc", ".task-state"
                ),
            )
            cls.projects[name] = target

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state_root = Path(self.directory.name) / "state"

    def test_echo_with_native_client_and_exact_task_round_trip(self):
        with server(self.projects["echo"], self.state_root) as (client, _, __):
            result = module.run_scenario(
                client, {"message": "hello", "expected_text": "Echo: hello"}
            )
            self.assertEqual(result["initial_task"], result["task"])
            native = subprocess.run(
                [
                    UV,
                    "run",
                    "--frozen",
                    "--python",
                    sys.executable,
                    "python",
                    "test_client.py",
                    "--endpoint",
                    client.endpoint.removesuffix("/a2a"),
                ],
                cwd=self.projects["echo"],
                env=sample_environment(self.projects["echo"]),
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(0, native.returncode, native.stdout + native.stderr)
            self.assertIn("Echo: hello", native.stdout)

    def test_unicode_and_multiline_artifacts(self):
        text = "hello\n\u00e9\u4f60\u597d\n"
        with server(self.projects["echo"], self.state_root) as (client, _, __):
            result = module.run_scenario(
                client, {"message": text, "expected_text": f"Echo: {text}"}
            )
            self.assertEqual("TASK_STATE_COMPLETED", result["task"]["status"]["state"])

    def test_report_returns_before_completion_and_can_be_polled(self):
        with server(self.projects["report"], self.state_root) as (client, _, __):
            result = module.run_scenario(
                client,
                {
                    "message": "quarterly results",
                    "expected_text": "Report: quarterly results",
                    "return_immediately": True,
                },
            )
            self.assertIn(
                result["initial_task"]["status"]["state"],
                {"TASK_STATE_SUBMITTED", "TASK_STATE_WORKING"},
            )
            self.assertEqual("TASK_STATE_COMPLETED", result["task"]["status"]["state"])
            with self.assertRaisesRegex(RuntimeError, "CancelTask failed"):
                client.rpc("CancelTask", {"id": result["task"]["id"]})

    def test_cancellation_stays_terminal_and_emits_no_report(self):
        with server(self.projects["report"], self.state_root) as (client, _, log):
            result = module.run_scenario(
                client,
                {
                    "message": "cancel me",
                    "expected_text": "",
                    "return_immediately": True,
                    "cancel": True,
                },
            )
            time.sleep(2.2)
            task = client.rpc("GetTask", {"id": result["task"]["id"]})
            self.assertEqual("TASK_STATE_CANCELED", task["status"]["state"])
            self.assertFalse(task.get("artifacts"))
            log.seek(0)
            self.assertNotIn("A2A_REPORT_COMPLETED", log.read())

    def test_full_snapshot_survives_actual_process_reconstruction(self):
        with server(self.projects["persistence"], self.state_root) as (
            writer,
            process,
            _,
        ):
            result = module.run_scenario(
                writer,
                {
                    "message": "remember this result",
                    "expected_text": "Persisted: remember this result",
                    "list_tasks": True,
                },
            )
            first_pid = process.pid
        with server(self.projects["persistence"], self.state_root) as (
            reader,
            process,
            log,
        ):
            reader.discover()
            self.assertNotEqual(first_pid, process.pid)
            self.assertEqual(
                result["task"], reader.rpc("GetTask", {"id": result["task"]["id"]})
            )
            page = reader.rpc(
                "ListTasks",
                {
                    "contextId": result["task"]["contextId"],
                    "pageSize": 10,
                    "includeArtifacts": True,
                },
            )
            self.assertEqual(
                [ParseDict(result["task"], Task())],
                [ParseDict(task, Task()) for task in page["tasks"]],
            )
            log.seek(0)
            self.assertNotIn("A2A_PERSISTED task_id=", log.read())
            self.assertFalse(
                any(
                    exchange["request"]
                    and exchange["request"]["method"] == "SendMessage"
                    for exchange in reader.exchanges
                )
            )

    def test_persistence_separates_local_simulated_callers(self):
        with server(self.projects["persistence"], self.state_root) as (client, _, __):
            client.headers["x-agent-user-id"] = "sample-user-a"
            result = module.run_scenario(
                client, {"message": "private", "expected_text": "Persisted: private"}
            )
            client.headers["x-agent-user-id"] = "sample-user-b"
            with self.assertRaisesRegex(RuntimeError, "GetTask failed"):
                client.rpc("GetTask", {"id": result["task"]["id"]})
            self.assertFalse(client.rpc("ListTasks", {"pageSize": 10}).get("tasks"))

    def test_reads_do_not_create_absent_task_storage(self):
        with server(self.projects["persistence"], self.state_root) as (client, _, __):
            before = sorted(
                path.relative_to(self.state_root) for path in self.state_root.rglob("*")
            )
            with self.assertRaisesRegex(RuntimeError, "GetTask failed"):
                client.rpc("GetTask", {"id": "missing"})
            self.assertFalse(client.rpc("ListTasks", {"pageSize": 10}).get("tasks"))
            self.assertEqual(
                before,
                sorted(
                    path.relative_to(self.state_root)
                    for path in self.state_root.rglob("*")
                ),
            )


if __name__ == "__main__":
    unittest.main()
