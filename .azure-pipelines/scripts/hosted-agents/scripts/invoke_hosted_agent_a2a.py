#!/usr/bin/env python3
"""Discover a native A2A agent and verify its Task workflow over real HTTP."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".github" / "scripts"))
from hosted_agent_test_spec import validate_a2a_input


class A2AClient:
    def __init__(
        self,
        endpoint: str,
        headers: Mapping[str, str] | None = None,
        timeout: float = 30,
    ) -> None:
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("endpoint must be an absolute HTTP(S) A2A JSON-RPC URL")
        self.endpoint = endpoint
        self.headers = {**(headers or {}), "A2A-Version": "1.0"}
        self.timeout = timeout
        self.exchanges: list[dict[str, Any]] = []
        self.last_http_status: int | None = None

    def _request(
        self, url: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            url, data=data, headers={**self.headers, "Content-Type": "application/json"}
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                self.last_http_status = response.status
                document = json.load(response)
        except HTTPError as error:
            self.last_http_status = error.code
            raise RuntimeError(
                f"A2A HTTP {error.code}: {error.read().decode('utf-8', errors='replace')}"
            ) from error
        if not isinstance(document, dict):
            raise ValueError("A2A response must be a JSON object")
        self.exchanges.append({"request": payload, "response": document})
        return document

    def discover(self) -> dict[str, Any]:
        endpoint = urlsplit(self.endpoint)
        suffix = (
            "/agentCard/v1.0"
            if "/endpoint/protocols/a2a" in endpoint.path
            else "/.well-known/agent-card.json"
        )
        card_url = urlunsplit(
            endpoint._replace(path=endpoint.path.rstrip("/") + suffix)
        )
        card = self._request(card_url)
        interfaces = card.get("supportedInterfaces", [])
        if not card.get("name") or not any(
            interface.get("protocolBinding") == "JSONRPC"
            and interface.get("protocolVersion") == "1.0"
            for interface in interfaces
        ):
            raise ValueError("Agent Card must declare a JSONRPC A2A 1.0 interface")
        return card

    def rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request = {
            "jsonrpc": "2.0",
            "id": uuid.uuid4().hex,
            "method": method,
            "params": params,
        }
        response = self._request(self.endpoint, request)
        if response.get("jsonrpc") != "2.0" or response.get("id") != request["id"]:
            raise ValueError(
                "A2A response has an invalid JSON-RPC version or request ID"
            )
        if "error" in response:
            raise RuntimeError(f"A2A {method} failed: {json.dumps(response['error'])}")
        result = response.get("result")
        if not isinstance(result, dict):
            raise ValueError(f"A2A {method} did not return an object result")
        return result


def run_scenario(client: A2AClient, scenario: dict[str, Any]) -> dict[str, Any]:
    validate_a2a_input(scenario)
    if "timeout_seconds" in scenario:
        client.timeout = scenario["timeout_seconds"]
    card = client.discover()
    initial = client.rpc(
        "SendMessage",
        {
            "message": {
                "messageId": uuid.uuid4().hex,
                "role": "ROLE_USER",
                "parts": [{"text": scenario["message"]}],
            },
            "configuration": {
                "returnImmediately": scenario.get("return_immediately", False)
            },
        },
    ).get("task")
    if not isinstance(initial, dict) or not initial.get("id"):
        raise ValueError("SendMessage did not return a Task with an ID")
    task_id = initial["id"]
    canceled = scenario.get("cancel", False)
    if canceled:
        canceled_task = client.rpc("CancelTask", {"id": task_id})
        if canceled_task.get("status", {}).get("state") != "TASK_STATE_CANCELED":
            raise ValueError("CancelTask did not return TASK_STATE_CANCELED")
    deadline = time.monotonic() + client.timeout
    while True:
        task = client.rpc("GetTask", {"id": task_id})
        state = task.get("status", {}).get("state")
        if state == ("TASK_STATE_CANCELED" if canceled else "TASK_STATE_COMPLETED"):
            break
        if state not in {"TASK_STATE_SUBMITTED", "TASK_STATE_WORKING"}:
            raise ValueError(f"Task reached unexpected state: {state!r}")
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Task {task_id} did not reach its expected terminal state"
            )
        time.sleep(0.1)
    if task.get("id") != task_id:
        raise ValueError("GetTask returned a different Task")
    text = "".join(
        part.get("text", "")
        for artifact in task.get("artifacts", [])
        for part in artifact.get("parts", [])
    )
    if not canceled and "expected_pattern" in scenario:
        if re.fullmatch(scenario["expected_pattern"], text) is None:
            raise ValueError("Artifact did not match the required output pattern")
    else:
        expected = "" if canceled else scenario["expected_text"]
        if text != expected:
            raise ValueError(f"Expected artifact text {expected!r}, received {text!r}")
    listed_ids = []
    if scenario.get("list_tasks", False):
        page = client.rpc(
            "ListTasks", {"contextId": task.get("contextId", ""), "pageSize": 100}
        )
        listed_ids = [item["id"] for item in page.get("tasks", [])]
        if task_id not in listed_ids:
            raise ValueError("Saved Task was absent from ListTasks")
    return {
        "card_name": card["name"],
        "initial_task": initial,
        "task": task,
        "listed_task_ids": listed_ids,
    }


def invoke_turn(
    turn: int,
    turn_file: Path,
    evidence_dir: Path,
    attempt: int,
    *,
    environment: Mapping[str, str] = os.environ,
    temp_dir: Path = Path("/tmp"),
) -> dict[str, Any]:
    required = (
        "AGENT_A2A_URL",
        "AAD_TOKEN",
        "DEPLOYED_AGENT_VERSION",
        "CI_AGENT_SESSION_ID",
    )
    if missing := [key for key in required if not environment.get(key)]:
        raise ValueError(f"Missing A2A invocation environment: {', '.join(missing)}")
    endpoint = urlsplit(environment["AGENT_A2A_URL"])
    query = dict(parse_qsl(endpoint.query))
    query["agent_session_id"] = environment["CI_AGENT_SESSION_ID"]
    client = A2AClient(
        urlunsplit(endpoint._replace(query=urlencode(query))),
        headers={
            "Authorization": f"Bearer {environment['AAD_TOKEN']}",
            "x-agent-version-override": environment["DEPLOYED_AGENT_VERSION"],
        },
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = run_scenario(client, json.loads(turn_file.read_text(encoding="utf-8")))
        successful = True
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        result = {"error": str(error)}
        successful = False
    output = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    (temp_dir / f"invoke-out-{turn}.txt").write_text(output, encoding="utf-8")
    (evidence_dir / f"turn-{turn}-attempt-{attempt}-a2a.json").write_text(
        json.dumps(client.exchanges, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    status = {
        "turn_exit": 0 if successful else 1,
        "http_code": str(client.last_http_status or ""),
    }
    (temp_dir / f"invoke-result-{turn}.json").write_text(
        json.dumps(status), encoding="utf-8"
    )
    return status


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and not args[0].startswith("-"):
        if len(args) != 5:
            raise ValueError(
                "cloud invocation requires turn, input, turn record, evidence directory and attempt"
            )
        return invoke_turn(int(args[0]), Path(args[1]), Path(args[3]), int(args[4]))[
            "turn_exit"
        ]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://localhost:8088/a2a")
    parser.add_argument("--message", default="hello")
    parser.add_argument("--expected-text", default="Echo: hello")
    parser.add_argument("--return-immediately", action="store_true")
    parser.add_argument("--cancel", action="store_true")
    parser.add_argument("--list-tasks", action="store_true")
    parser.add_argument(
        "--task-id", help="Read an existing Task without invoking the executor"
    )
    parser.add_argument("--azure-auth", action="store_true")
    options = parser.parse_args(args)
    headers = {}
    if options.azure_auth:
        import subprocess

        token = subprocess.check_output(
            [
                "az",
                "account",
                "get-access-token",
                "--resource",
                "https://ai.azure.com",
                "--query",
                "accessToken",
                "-o",
                "tsv",
            ],
            text=True,
        ).strip()
        if not token:
            raise ValueError("Azure CLI did not return an access token")
        headers["Authorization"] = f"Bearer {token}"
    client = A2AClient(options.endpoint, headers=headers)
    result = (
        client.rpc("GetTask", {"id": options.task_id})
        if options.task_id
        else run_scenario(
            client,
            {
                "message": options.message,
                "expected_text": options.expected_text,
                "return_immediately": options.return_immediately,
                "cancel": options.cancel,
                "list_tasks": options.list_tasks,
            },
        )
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        print(f"A2A validation failed: {error}", file=sys.stderr)
        sys.exit(1)
