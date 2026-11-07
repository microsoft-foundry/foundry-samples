#!/usr/bin/env python3
"""Invoke a blocking native A2A 1.0 turn and collect validated Task evidence."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4


def _run(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=960,
        env={**os.environ, "AZD_ALPHA_ENABLE_AGENTS_A2A": "true"},
    )


def task_text(body: str, request_id: str) -> str:
    response = json.loads(body)
    if not isinstance(response, dict) or response.get("jsonrpc") != "2.0":
        raise ValueError("A2A response must be a JSON-RPC 2.0 object")
    if response.get("id") != request_id:
        raise ValueError("A2A response ID does not match the request")
    if response.get("error") is not None:
        raise ValueError(f"A2A JSON-RPC error: {json.dumps(response['error'])}")
    result = response.get("result")
    task = result.get("task") if isinstance(result, dict) else None
    if (
        not isinstance(task, dict)
        or not isinstance(task.get("id"), str)
        or not task["id"]
    ):
        raise ValueError("A2A SendMessage did not return a Task with an ID")
    status = task.get("status")
    if not isinstance(status, dict) or status.get("state") != "TASK_STATE_COMPLETED":
        raise ValueError(
            f"A2A Task did not complete successfully: {json.dumps(status)}"
        )
    artifacts = task.get("artifacts", [])
    if not isinstance(artifacts, list):
        raise ValueError("A2A Task artifacts must be an array")
    texts = []
    for artifact in artifacts:
        if not isinstance(artifact, dict) or not isinstance(
            artifact.get("parts"), list
        ):
            raise ValueError("A2A artifact must contain a parts array")
        for part in artifact["parts"]:
            if not isinstance(part, dict):
                raise ValueError("A2A artifact part must be an object")
            if "text" in part:
                if not isinstance(part["text"], str):
                    raise ValueError("A2A artifact text must be a string")
                texts.append(part["text"])
    text = "\n".join(texts)
    if not text.strip():
        raise ValueError("Completed A2A Task returned no text artifact evidence")
    return text


def invoke_turn(
    turn: int,
    turn_file: Path,
    turn_record_file: Path,
    evidence_dir: Path,
    request_attempt: int,
    *,
    environment: Mapping[str, str] = os.environ,
    transport: Callable[[Sequence[str]], subprocess.CompletedProcess[str]] = _run,
    temp_dir: Path = Path("/tmp"),
) -> dict[str, Any]:
    session = environment.get("CI_AGENT_SESSION_ID")
    agent = environment.get("FOUNDRY_AGENT_NAME")
    if not session or not agent:
        raise ValueError("CI_AGENT_SESSION_ID and FOUNDRY_AGENT_NAME are required")
    record = json.loads(turn_record_file.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError("A2A turn record must be an object")
    if record.get("approvals") is not None or "previous_turn" in record:
        raise ValueError("A2A does not support Responses approvals or previous_turn")
    request_id = str(uuid4())
    request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "SendMessage",
        "params": {
            "message": {
                "messageId": str(uuid4()),
                "role": "ROLE_USER",
                "parts": [{"text": turn_file.read_text(encoding="utf-8").rstrip("\n")}],
            },
            "configuration": {"returnImmediately": False},
        },
    }
    request_file = temp_dir / f"req-{turn}.json"
    request_json = json.dumps(request, indent=2)
    request_file.write_text(request_json, encoding="utf-8")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    prefix = evidence_dir / f"turn-{turn}-attempt-{request_attempt}-a2a"
    Path(f"{prefix}-request.json").write_text(request_json, encoding="utf-8")
    raw = ""
    body = ""
    headers = ""
    http_code = ""
    text = ""
    error = ""
    exit_code = 1
    terminal = False
    try:
        result = transport(
            [
                "azd",
                "ai",
                "agent",
                "invoke",
                agent,
                "--protocol",
                "a2a",
                "--a2a-version",
                "1.0",
                "--input-file",
                str(request_file),
                "--session-id",
                session,
                "--output",
                "raw",
                "--no-prompt",
            ]
        )
        raw = result.stdout
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        body = raw
        if raw.startswith("HTTP/"):
            sections = re.split(r"\r?\n\r?\n", raw, maxsplit=1)
            if len(sections) != 2:
                raise ValueError("A2A raw HTTP response has no body separator")
            headers, body = sections
            match = re.fullmatch(
                r"HTTP/\S+\s+([0-9]{3})(?:\s+.*)?", headers.splitlines()[0]
            )
            if not match:
                raise ValueError("A2A raw HTTP response has an invalid status line")
            http_code = match[1]
        if result.returncode:
            error = f"A2A invoke failed with exit code {result.returncode}"
        elif http_code and http_code not in {"200", "201"}:
            error = f"A2A invoke failed with HTTP {http_code}"
        else:
            text = task_text(body, request_id)
            exit_code = 0
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        error = str(exc)
        terminal = True
    if error:
        print(f"A2A invocation error: {error}", file=sys.stderr)
    output = raw + (f"\nA2A invocation error: {error}\n" if error else "")
    for suffix, content in (
        ("out", output),
        ("raw", body),
        ("headers", headers),
        ("response", text),
    ):
        extension = "json" if suffix == "raw" else "txt"
        (temp_dir / f"invoke-{suffix}-{turn}.{extension}").write_text(
            content, encoding="utf-8"
        )
    Path(f"{prefix}-response.txt").write_text(raw, encoding="utf-8")
    outcome = {
        "turn_exit": exit_code,
        "http_code": http_code,
        "approval_terminal_error": terminal,
        "approval_error": error,
        "approval_events": [],
        "approval_pending_count": 0,
        "approval_auto": False,
    }
    (temp_dir / f"invoke-result-{turn}.json").write_text(
        json.dumps(outcome), encoding="utf-8"
    )
    return outcome


def main(argv: Sequence[str]) -> int:
    if len(argv) != 5:
        raise ValueError(
            "Expected turn, input file, turn record, evidence directory and attempt"
        )
    return invoke_turn(
        int(argv[0]), Path(argv[1]), Path(argv[2]), Path(argv[3]), int(argv[4])
    )["turn_exit"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
