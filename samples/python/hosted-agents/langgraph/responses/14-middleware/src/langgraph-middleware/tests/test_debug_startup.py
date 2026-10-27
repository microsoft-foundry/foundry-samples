"""Attach debugpy without desktop automation and probe the real agent host."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


def unused_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def test_debugpy_attach_starts_real_host(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1]
    debug_port = unused_port()
    host_port = unused_port()
    while host_port == debug_port:
        host_port = unused_port()
    environment = dict(os.environ)
    environment.update(
        {
            "FOUNDRY_PROJECT_ENDPOINT": "https://example.services.ai.azure.com/api/projects/test",
            "AZURE_AI_MODEL_DEPLOYMENT_NAME": "test-deployment",
            "PORT": str(host_port),
        }
    )
    log_path = tmp_path / "debug-startup.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-Xfrozen_modules=off",
                "-m",
                "debugpy",
                "--listen",
                f"127.0.0.1:{debug_port}",
                "--wait-for-client",
                "--configure-subProcess",
                "false",
                str(source / "main.py"),
            ],
            cwd=tmp_path,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            deadline = time.monotonic() + 60
            while True:
                assert process.poll() is None, log_path.read_text(encoding="utf-8")
                try:
                    connection = socket.create_connection(
                        ("127.0.0.1", debug_port), timeout=1
                    )
                    break
                except OSError:
                    assert time.monotonic() < deadline, "debugpy did not listen"
                    time.sleep(0.1)
            with connection, connection.makefile("rb") as reader:
                messages = []

                def send(sequence, command, arguments):
                    payload = json.dumps(
                        {
                            "seq": sequence,
                            "type": "request",
                            "command": command,
                            "arguments": arguments,
                        }
                    ).encode()
                    connection.sendall(
                        f"Content-Length: {len(payload)}\r\n\r\n".encode() + payload
                    )

                def wait_for(predicate):
                    while True:
                        for message in messages:
                            if predicate(message):
                                return message
                        remaining = deadline - time.monotonic()
                        assert remaining > 0, messages
                        connection.settimeout(remaining)
                        header = reader.readline()
                        assert header.startswith(b"Content-Length: "), header
                        length = int(header.split(b":", 1)[1])
                        assert reader.readline() == b"\r\n"
                        message = json.loads(reader.read(length))
                        messages.append(message)
                        if message["type"] == "response":
                            assert message["success"], message

                send(1, "initialize", {"adapterID": "debugpy", "pathFormat": "path"})
                wait_for(lambda message: message.get("request_seq") == 1)
                send(
                    2, "attach", {"connect": {"host": "127.0.0.1", "port": debug_port}}
                )
                wait_for(lambda message: message.get("event") == "initialized")
                send(3, "configurationDone", {})
                wait_for(lambda message: message.get("request_seq") == 3)
                wait_for(lambda message: message.get("request_seq") == 2)
                while True:
                    assert process.poll() is None, log_path.read_text(encoding="utf-8")
                    try:
                        with urlopen(
                            f"http://127.0.0.1:{host_port}/readiness", timeout=1
                        ) as response:
                            assert response.status == 200
                            assert json.load(response) == {"status": "healthy"}
                        break
                    except (URLError, TimeoutError):
                        assert time.monotonic() < deadline, log_path.read_text(
                            encoding="utf-8"
                        )
                        time.sleep(0.1)
                send(4, "disconnect", {"terminateDebuggee": True})
                wait_for(lambda message: message.get("request_seq") == 4)
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
