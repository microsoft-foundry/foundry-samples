#!/usr/bin/env python3
"""Invoke one hosted-agent Responses turn, including explicit MCP approvals."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from hosted_agent_test_spec import decide_mcp_approvals


Transport = Callable[[Path, Path, Path, Mapping[str, str]], tuple[int, str]]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _post(
    request_file: Path,
    headers_file: Path,
    raw_file: Path,
    environment: Mapping[str, str],
) -> tuple[int, str]:
    headers_file.unlink(missing_ok=True)
    raw_file.unlink(missing_ok=True)
    result = subprocess.run(
        [
            "curl",
            "-sS",
            "-D",
            str(headers_file),
            "-o",
            str(raw_file),
            "-w",
            "%{http_code}",
            "-X",
            "POST",
            environment["AGENT_RESPONSES_URL"],
            "-H",
            f"Authorization: Bearer {environment['AAD_TOKEN']}",
            "-H",
            "Content-Type: application/json",
            "-H",
            f"x-agent-version-override: {environment['DEPLOYED_AGENT_VERSION']}",
            "--max-time",
            "300",
            "--data",
            f"@{request_file}",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    return result.returncode, result.stdout


def _assistant_text(response: dict[str, Any]) -> str:
    text: list[str] = []
    output = response.get("output", [])
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for part in content:
            if (
                isinstance(part, dict)
                and part.get("type") == "output_text"
                and isinstance(part.get("text"), str)
            ):
                text.append(part["text"])
    return "\n".join(text)


def _required_environment(environment: Mapping[str, str]) -> dict[str, str]:
    required = (
        "AGENT_RESPONSES_URL",
        "AAD_TOKEN",
        "DEPLOYED_AGENT_VERSION",
        "CI_AGENT_SESSION_ID",
    )
    missing = [name for name in required if not environment.get(name)]
    if missing:
        raise ValueError(f"{', '.join(missing)} is required")
    return {name: environment[name] for name in required}


def invoke_turn(
    turn: int,
    turn_file: Path,
    turn_record_file: Path,
    evidence_dir: Path,
    request_attempt: int,
    *,
    environment: Mapping[str, str] = os.environ,
    transport: Transport = _post,
    temp_dir: Path = Path("/tmp"),
) -> dict[str, Any]:
    env = _required_environment(environment)
    line = turn_file.read_text(encoding="utf-8").rstrip("\n")
    turn_record = json.loads(turn_record_file.read_text(encoding="utf-8"))
    if not isinstance(turn_record, dict):
        raise ValueError("turn record must be a JSON object")

    request_file = temp_dir / f"req-{turn}.json"
    headers_file = temp_dir / f"invoke-headers-{turn}.txt"
    raw_file = temp_dir / f"invoke-raw-{turn}.json"
    output_file = temp_dir / f"invoke-out-{turn}.txt"
    response_text_file = temp_dir / f"invoke-response-{turn}.txt"
    result_file = temp_dir / f"invoke-result-{turn}.json"

    approval_policy = turn_record.get("approvals")
    approval_auto = (
        isinstance(approval_policy, dict) and approval_policy.get("mcp") is not None
    )
    approval_sequence = approval_policy.get("mcp", []) if approval_auto else []
    approval_sequence_length = len(approval_sequence)
    request: dict[str, Any] = {
        "input": line,
        "stream": False,
        "store": approval_auto,
        "agent_session_id": env["CI_AGENT_SESSION_ID"],
    }
    _write_json(request_file, request)

    approval_terminal_error = False
    approval_error = ""
    approval_events: list[dict[str, Any]] = []
    approval_pending_count = 0
    approval_step = 0
    approved_ids: set[str] = set()
    assistant_parts: list[str] = []
    http_code = ""
    transport_exit = 0
    response_error = ""

    while True:
        step_prefix = (
            evidence_dir
            / f"turn-{turn}-attempt-{request_attempt}-approval-step-{approval_step}"
        )
        approval_pending_count = 0
        transport_exit, http_code = transport(request_file, headers_file, raw_file, env)
        shutil.copyfile(request_file, Path(f"{step_prefix}-request.json"))
        if raw_file.is_file():
            shutil.copyfile(raw_file, Path(f"{step_prefix}-response.json"))
        if headers_file.is_file():
            shutil.copyfile(headers_file, Path(f"{step_prefix}-headers.txt"))

        if transport_exit != 0 or http_code not in {"200", "201"}:
            break

        try:
            response = json.loads(raw_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            response_error = f"Responses body is not valid JSON: {exc}"
            break
        if not isinstance(response, dict):
            response_error = "Responses body must be a JSON object"
            break
        response_status = response.get("status")
        if response_status != "completed":
            response_error = (
                "Responses request did not complete successfully: "
                f"status={response_status!r}"
            )
            break

        step_text = _assistant_text(response)
        if step_text:
            assistant_parts.append(step_text)

        decision = decide_mcp_approvals(turn_record, response, approved_ids)
        decision = {**decision, "response_index": approval_step}
        approval_events.append(decision)
        decision_status = decision.get("status")
        approval_pending_count = decision.get("pending_count", 0)

        if decision_status == "none":
            break
        if decision_status == "pending":
            print(
                f"::warning::Turn {turn} has {approval_pending_count} pending MCP "
                "approval request(s); auto-approval is not enabled"
            )
            break
        if decision_status == "error":
            approval_terminal_error = True
            approval_error = str(decision.get("error", "MCP approval policy error"))
            print(f"::error::MCP approval policy error: {approval_error}")
            for observed in decision.get("requests", []):
                print(
                    "::error::Observed approval request: "
                    f"server_label={observed.get('server_label')} "
                    f"name={observed.get('name')} id={observed.get('id')} "
                    f"decision={observed.get('decision')}"
                )
            break
        if decision_status != "approved":
            approval_terminal_error = True
            approval_error = f"invalid MCP approval decision status: {decision_status}"
            decision.update(
                status="error",
                error=approval_error,
                approval_responses=[],
                new_ids=[],
            )
            for observed in decision.get("requests", []):
                observed["decision"] = "not_approved"
            print(f"::error::{approval_error}")
            break

        previous_response_id = response.get("id")
        if not isinstance(previous_response_id, str) or not previous_response_id:
            approval_terminal_error = True
            approval_error = "cannot continue MCP approval: response has no id"
            decision.update(status="error", error=approval_error)
            decision["approval_responses"] = []
            decision["new_ids"] = []
            for observed in decision.get("requests", []):
                observed["decision"] = "not_approved"
            print(f"::error::{approval_error}")
            break

        approved_ids.update(decision["new_ids"])
        approval_step += 1
        request = {
            "input": decision["approval_responses"],
            "previous_response_id": previous_response_id,
            "stream": False,
            "store": True,
            "agent_session_id": env["CI_AGENT_SESSION_ID"],
        }
        _write_json(request_file, request)
        print(
            "Auto-approving expected sample request "
            f"(step {approval_step}/{approval_sequence_length})"
        )

    assistant_text = "\n".join(assistant_parts)
    response_text_file.write_text(
        f"{assistant_text}\n" if assistant_text else "", encoding="utf-8"
    )
    successful = (
        transport_exit == 0
        and http_code in {"200", "201"}
        and not approval_terminal_error
        and not response_error
    )

    output_lines = [f"HTTP {http_code or '000'}"]
    if successful:
        output_lines.append("--- Agent response ---")
        if assistant_text:
            output_lines.append(assistant_text)
        else:
            output_lines.append("(no assistant text in response — full body:)")
            if raw_file.is_file():
                output_lines.append(
                    raw_file.read_text(encoding="utf-8", errors="replace")
                )
        output_lines.append("--- end response ---")
    else:
        if approval_error:
            output_lines.append(f"MCP approval policy error: {approval_error}")
        if response_error:
            output_lines.append(response_error)
        if raw_file.is_file():
            output_lines.append(raw_file.read_text(encoding="utf-8", errors="replace"))
    output_file.write_text(
        "\n".join(output_lines).rstrip("\n") + "\n", encoding="utf-8"
    )

    result = {
        "turn_exit": 0 if successful else 1,
        "http_code": http_code,
        "approval_terminal_error": approval_terminal_error,
        "approval_error": approval_error,
        "approval_events": approval_events,
        "approval_pending_count": approval_pending_count,
        "approval_auto": approval_auto,
        "approval_step": approval_step,
        "response_error": response_error,
    }
    _write_json(result_file, result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) != 5:
        print(
            "usage: invoke_hosted_agent_responses.py <turn> <turn-input-file> "
            "<turn-record-json> <evidence-dir> <attempt>",
            file=sys.stderr,
        )
        return 2
    try:
        invoke_turn(
            int(args[0]),
            Path(args[1]),
            Path(args[2]),
            Path(args[3]),
            int(args[4]),
        )
    except Exception as exc:
        print(f"::error::Responses invocation helper failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
