#!/usr/bin/env python3
"""Schema, planning, and assertion evaluation for hosted-agent E2E test specs."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

try:
    import yaml
except ImportError:  # pragma: no cover - exercised by the CLI error path
    yaml = None


class SpecError(ValueError):
    """Raised when a test spec does not match the current contract."""


EXPERIENCES = {"azd", "vscode"}
TURN_SOURCES = {"assistant_text", "raw", "session_files"}
TEST_SOURCES = {"console_log", "trace"}
TEXT_SOURCES = {"assistant_text", "raw", "console_log"}
TEXT_TYPES = {"contains", "equals", "regex"}
STATUSES = {"ok", "error", "unset"}
ALIAS_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
if yaml is not None:

    class _UniqueKeyLoader(yaml.SafeLoader):
        pass

    def _construct_unique_mapping(
        loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
    ) -> dict[Any, Any]:
        loader.flatten_mapping(node)
        result: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in result:
                mark = key_node.start_mark
                raise SpecError(
                    f"duplicate key {key!r} at line {mark.line + 1}, "
                    f"column {mark.column + 1}"
                )
            result[key] = loader.construct_object(value_node, deep=deep)
        return result

    _UniqueKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        _construct_unique_mapping,
    )


def _require_mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SpecError(f"{context} must be a mapping")
    if not all(isinstance(key, str) for key in value):
        raise SpecError(f"{context} keys must be strings")
    return value


def _require_keys(
    value: dict[str, Any],
    allowed: set[str],
    context: str,
    required: set[str] | None = None,
) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise SpecError(f"{context} has unknown key(s): {', '.join(sorted(unknown))}")
    missing = (required or set()) - set(value)
    if missing:
        raise SpecError(f"{context} is missing key(s): {', '.join(sorted(missing))}")


def _require_string(value: Any, context: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        suffix = "non-empty " if nonempty else ""
        raise SpecError(f"{context} must be a {suffix}string")
    return value


def _require_count(value: Any, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SpecError(f"{context} must be a non-negative integer")
    return value


def _validate_json_value(
    value: Any, context: str, ancestors: set[int] | None = None
) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SpecError(f"{context} must be a finite JSON number")
        return
    if not isinstance(value, (dict, list)):
        raise SpecError(f"{context} must contain only JSON-compatible values")

    ancestors = set() if ancestors is None else ancestors
    identity = id(value)
    if identity in ancestors:
        raise SpecError(f"{context} must not contain a recursive value")
    ancestors.add(identity)
    try:
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise SpecError(f"{context} mapping keys must be strings")
                _validate_json_value(item, f"{context}[{key!r}]", ancestors)
        else:
            for index, item in enumerate(value):
                _validate_json_value(item, f"{context}[{index}]", ancestors)
    finally:
        ancestors.remove(identity)


def _validate_bounds(value: dict[str, Any], context: str) -> None:
    minimum = _require_count(value.get("min_matches", 1), f"{context}.min_matches")
    maximum_value = value.get("max_matches")
    if maximum_value is not None:
        maximum = _require_count(maximum_value, f"{context}.max_matches")
        if maximum < minimum:
            raise SpecError(
                f"{context}.max_matches must be greater than or equal to min_matches"
            )


def _compile_regex(pattern: Any, context: str) -> str:
    pattern = _require_string(pattern, context)
    try:
        re.compile(pattern)
    except re.error as exc:
        raise SpecError(f"{context} is invalid: {exc}") from exc
    return pattern


def _validate_session_path(path: Any, context: str) -> str:
    path = _require_string(path, context)
    if not path.startswith("/"):
        raise SpecError(f"{context} must be absolute and relative to the session $HOME")
    if "$HOME" in path or "//" in path:
        raise SpecError(f"{context} must not contain $HOME or repeated separators")
    parts = PurePosixPath(path).parts
    if path == "/" or path.endswith("/") or any(part in {".", ".."} for part in parts):
        raise SpecError(
            f"{context} must identify a file and must not contain . or .. segments"
        )
    # PurePosixPath normalizes dot segments, so inspect the original spelling too.
    if any(part in {".", ".."} for part in path.split("/")):
        raise SpecError(f"{context} must not contain . or .. segments")
    return path


def _validate_attribute_predicate(value: Any, context: str) -> None:
    predicate = _require_mapping(value, context)
    _require_keys(predicate, {"exists", "equals", "regex"}, context)
    if len(predicate) != 1:
        raise SpecError(
            f"{context} must contain exactly one of exists, equals, or regex"
        )
    if "exists" in predicate and not isinstance(predicate["exists"], bool):
        raise SpecError(f"{context}.exists must be a boolean")
    if "regex" in predicate:
        _compile_regex(predicate["regex"], f"{context}.regex")


def _validate_assertion(value: Any, scope: str, context: str) -> None:
    assertion = _require_mapping(value, context)
    source = assertion.get("source")
    assertion_type = assertion.get("type")
    if source not in TURN_SOURCES | TEST_SOURCES:
        raise SpecError(f"{context}.source is unsupported")
    if scope == "turn" and source not in TURN_SOURCES:
        raise SpecError(f"{context}.source {source!r} is not valid at turn scope")
    if scope == "test" and source not in TEST_SOURCES:
        raise SpecError(f"{context}.source {source!r} is not valid at test scope")

    if assertion_type in TEXT_TYPES:
        _require_keys(
            assertion,
            {"source", "type", "value", "case_sensitive", "min_matches", "max_matches"},
            context,
            {"source", "type", "value"},
        )
        if source not in TEXT_SOURCES:
            raise SpecError(f"{context} text assertions require a textual source")
        if assertion_type == "equals" and source == "console_log":
            raise SpecError(f"{context} equals is not supported for console_log")
        _require_string(
            assertion["value"],
            f"{context}.value",
            nonempty=assertion_type != "equals",
        )
        if "case_sensitive" in assertion and not isinstance(
            assertion["case_sensitive"], bool
        ):
            raise SpecError(f"{context}.case_sensitive must be a boolean")
        if assertion_type == "regex":
            _compile_regex(assertion["value"], f"{context}.value")
        _validate_bounds(assertion, context)
        return

    if assertion_type == "exists":
        _require_keys(
            assertion, {"source", "type", "path"}, context, {"source", "type", "path"}
        )
        if source != "session_files":
            raise SpecError(f"{context} exists requires source: session_files")
        _validate_session_path(assertion["path"], f"{context}.path")
        return

    if assertion_type == "span":
        _require_keys(
            assertion,
            {
                "source",
                "type",
                "name",
                "attributes",
                "status",
                "min_matches",
                "max_matches",
            },
            context,
            {"source", "type"},
        )
        if source != "trace":
            raise SpecError(f"{context} span requires source: trace")
        if not any(key in assertion for key in ("name", "attributes", "status")):
            raise SpecError(
                f"{context} requires at least one of name, attributes, or status"
            )
        if "name" in assertion:
            _require_string(assertion["name"], f"{context}.name")
        if "status" in assertion and assertion["status"] not in STATUSES:
            raise SpecError(f"{context}.status must be ok, error, or unset")
        if "attributes" in assertion:
            attributes = _require_mapping(
                assertion["attributes"], f"{context}.attributes"
            )
            if not attributes:
                raise SpecError(f"{context}.attributes must not be empty")
            for name, predicate in attributes.items():
                _require_string(name, f"{context}.attributes key")
                _validate_attribute_predicate(
                    predicate, f"{context}.attributes[{name!r}]"
                )
        _validate_bounds(assertion, context)
        return

    raise SpecError(f"{context}.type is unsupported")


def _validate_approvals(value: Any, context: str) -> None:
    approvals = _require_mapping(value, context)
    _require_keys(approvals, {"mcp"}, context, {"mcp"})
    sequence = approvals["mcp"]
    if not isinstance(sequence, list) or not sequence:
        raise SpecError(f"{context}.mcp must be a non-empty sequence")
    for index, step_value in enumerate(sequence, start=1):
        step_context = f"{context}.mcp[{index}]"
        step = _require_mapping(step_value, step_context)
        _require_keys(
            step,
            {"server_label", "name"},
            step_context,
            {"server_label", "name"},
        )
        label = _require_string(step["server_label"], f"{step_context}.server_label")
        name = _require_string(step["name"], f"{step_context}.name")
        if "*" in label or "?" in label:
            raise SpecError(f"{step_context}.server_label must not contain wildcards")
        if "*" in name or "?" in name:
            raise SpecError(f"{step_context}.name must not contain wildcards")


def validate_spec(document: Any) -> dict[str, Any]:
    document = _require_mapping(document, "document")
    _require_keys(
        document,
        {"version", "sample", "tests"},
        "document",
        {"version", "sample", "tests"},
    )
    if document["version"] != 1 or isinstance(document["version"], bool):
        raise SpecError("document.version must be 1")

    sample = _require_mapping(document["sample"], "document.sample")
    _require_keys(
        sample,
        {"owner", "experiences"},
        "document.sample",
        {"owner", "experiences"},
    )
    owner = _require_string(sample["owner"], "document.sample.owner")
    if "@" in owner or not ALIAS_RE.fullmatch(owner):
        raise SpecError(
            "document.sample.owner must be a Microsoft alias without @microsoft.com"
        )
    experiences = sample["experiences"]
    if not isinstance(experiences, list) or not experiences:
        raise SpecError("document.sample.experiences must be a non-empty sequence")
    if any(item not in EXPERIENCES for item in experiences):
        raise SpecError("document.sample.experiences may contain only azd and vscode")
    if len(set(experiences)) != len(experiences):
        raise SpecError("document.sample.experiences must not contain duplicates")

    tests = document["tests"]
    if not isinstance(tests, list) or not tests:
        raise SpecError("document.tests must be a non-empty sequence")
    names: set[str] = set()
    for test_index, test_value in enumerate(tests, start=1):
        context = f"document.tests[{test_index}]"
        test = _require_mapping(test_value, context)
        _require_keys(
            test, {"name", "when", "turns", "assertions"}, context, {"name", "turns"}
        )
        name = _require_string(test["name"], f"{context}.name")
        if name in names:
            raise SpecError(f"{context}.name duplicates test name {name!r}")
        names.add(name)
        if "when" in test:
            when = _require_mapping(test["when"], f"{context}.when")
            _require_keys(when, {"toolbox_label"}, f"{context}.when", {"toolbox_label"})
            _require_string(when["toolbox_label"], f"{context}.when.toolbox_label")
        turns = test["turns"]
        if not isinstance(turns, list) or not turns:
            raise SpecError(f"{context}.turns must be a non-empty sequence")
        for turn_index, turn_value in enumerate(turns, start=1):
            turn_context = f"{context}.turns[{turn_index}]"
            turn = _require_mapping(turn_value, turn_context)
            _require_keys(
                turn,
                {"input", "assertions", "approvals"},
                turn_context,
                {"input"},
            )
            if not isinstance(turn["input"], (str, dict, list)):
                raise SpecError(
                    f"{turn_context}.input must be a string, mapping, or sequence"
                )
            if not isinstance(turn["input"], str):
                _validate_json_value(turn["input"], f"{turn_context}.input")
            if "approvals" in turn:
                _validate_approvals(turn["approvals"], f"{turn_context}.approvals")
            assertions = turn.get("assertions", [])
            if not isinstance(assertions, list):
                raise SpecError(f"{turn_context}.assertions must be a sequence")
            for assertion_index, assertion in enumerate(assertions, start=1):
                _validate_assertion(
                    assertion,
                    "turn",
                    f"{turn_context}.assertions[{assertion_index}]",
                )
        assertions = test.get("assertions", [])
        if not isinstance(assertions, list):
            raise SpecError(f"{context}.assertions must be a sequence")
        for assertion_index, assertion in enumerate(assertions, start=1):
            _validate_assertion(
                assertion, "test", f"{context}.assertions[{assertion_index}]"
            )
    return document


def load_spec(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise SpecError("PyYAML is required to read test-spec.yml")
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except OSError as exc:
        raise SpecError(f"could not read {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise SpecError(f"invalid YAML in {path}: {exc}") from exc
    return validate_spec(value)


def serialize_input(value: Any) -> str:
    if isinstance(value, str):
        return value
    _validate_json_value(value, "turn input")
    try:
        return json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise SpecError(f"turn input is not JSON-compatible: {exc}") from exc


def build_plan(
    document: dict[str, Any],
    toolbox_label: str = "",
    toolbox_query: str = "",
    protocol: str = "responses",
) -> dict[str, Any]:
    if protocol != "responses":
        if any(
            "approvals" in turn for test in document["tests"] for turn in test["turns"]
        ):
            raise SpecError(
                "turn approvals are supported only for the Responses protocol"
            )
        if any(
            assertion.get("source") == "assistant_text"
            for test in document["tests"]
            for turn in test["turns"]
            for assertion in turn.get("assertions", [])
        ):
            raise SpecError(
                "assistant_text assertions are supported only for the Responses protocol"
            )

    tests: list[dict[str, Any]] = []
    global_turn = 0
    for test_index, test in enumerate(document["tests"], start=1):
        expected_label = test.get("when", {}).get("toolbox_label")
        applicable = expected_label is None or expected_label == toolbox_label
        reason = None
        if not applicable:
            reason = f"toolbox_label is {toolbox_label!r}, expected {expected_label!r}"
        turns = test["turns"]
        input_source = "spec"
        if applicable and toolbox_query and expected_label is not None:
            override_input: Any = toolbox_query
            if protocol == "invocations":
                override_input = {"query": toolbox_query}
            turns = [
                {
                    "input": override_input,
                    "assertions": test["turns"][0].get("assertions", []),
                    **(
                        {"approvals": test["turns"][0]["approvals"]}
                        if "approvals" in test["turns"][0]
                        else {}
                    ),
                }
            ]
            input_source = "toolbox_query"
        planned_turns = []
        if applicable:
            for turn_index, turn in enumerate(turns, start=1):
                global_turn += 1
                planned_turns.append(
                    {
                        "turn": turn_index,
                        "global_turn": global_turn,
                        "input": turn["input"],
                        "serialized_input": serialize_input(turn["input"]),
                        "assertions": turn.get("assertions", []),
                        "approvals": turn.get("approvals"),
                    }
                )
        tests.append(
            {
                "index": test_index,
                "name": test["name"],
                "status": "applicable" if applicable else "not_applicable",
                "reason": reason,
                "input_source": input_source,
                "turns": planned_turns,
                "assertions": test.get("assertions", []),
            }
        )
    return {
        "version": 1,
        "sample": document["sample"],
        "tests": tests,
        "turn_count": global_turn,
    }


def decide_mcp_approvals(
    turn: dict[str, Any], response: dict[str, Any], approved_ids: set[str]
) -> dict[str, Any]:
    def error(message: str, requests: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "status": "error",
            "error": message,
            "pending_count": len(requests),
            "requests": [{**item, "decision": "not_approved"} for item in requests],
            "approval_responses": [],
            "new_ids": [],
        }

    if not isinstance(response, dict):
        return error("Responses protocol evidence must be an object", [])
    output = response.get("output") or []
    if not isinstance(output, list):
        return error("Responses protocol output must be an array", [])
    requests = [
        item
        for item in output
        if isinstance(item, dict) and item.get("type") == "mcp_approval_request"
    ]
    observed = [
        {
            "id": item.get("id"),
            "server_label": item.get("server_label"),
            "name": item.get("name"),
            "arguments": item.get("arguments"),
        }
        for item in requests
    ]
    policy = turn.get("approvals")
    if not policy:
        if not requests:
            return {
                "status": "none",
                "pending_count": 0,
                "requests": [],
                "approval_responses": [],
                "new_ids": [],
            }
        return {
            "status": "pending",
            "pending_count": len(requests),
            "requests": [{**item, "decision": "pending"} for item in observed],
            "approval_responses": [],
            "new_ids": [],
        }

    sequence = policy["mcp"]
    step_index = len(approved_ids)
    if not requests:
        if step_index < len(sequence):
            expected = sequence[step_index]
            return error(
                "expected MCP approval step "
                f"{step_index + 1}/{len(sequence)} "
                f"({expected['server_label']}/{expected['name']}) but the response "
                "contained no approval request",
                [],
            )
        return {
            "status": "none",
            "pending_count": 0,
            "requests": [],
            "approval_responses": [],
            "new_ids": [],
            "sequence_complete": True,
        }

    malformed = [
        item
        for item in observed
        if not all(
            isinstance(item.get(field), str) and item[field]
            for field in ("id", "server_label", "name")
        )
    ]
    if malformed:
        return error(
            "mcp_approval_request is missing a non-empty id, server_label, or name",
            observed,
        )
    if len(observed) != 1:
        return error(
            "deterministic MCP approval steps require exactly one request per response",
            observed,
        )

    request = observed[0]
    if request["id"] in approved_ids:
        return error(
            f"previously approved request id was emitted again: {request['id']}",
            observed,
        )
    if step_index >= len(sequence):
        return error(
            "unexpected MCP approval request after the declared sequence was consumed",
            observed,
        )

    expected = sequence[step_index]
    if (
        request["server_label"] != expected["server_label"]
        or request["name"] != expected["name"]
    ):
        return error(
            "MCP approval sequence mismatch at step "
            f"{step_index + 1}/{len(sequence)}: expected "
            f"{expected['server_label']}/{expected['name']}, observed "
            f"{request['server_label']}/{request['name']}",
            observed,
        )

    return {
        "status": "approved",
        "pending_count": 0,
        "step": step_index + 1,
        "sequence_length": len(sequence),
        "expected": expected,
        "requests": [{**request, "decision": "approved"}],
        "approval_responses": [
            {
                "type": "mcp_approval_response",
                "approve": True,
                "approval_request_id": request["id"],
            }
        ],
        "new_ids": [request["id"]],
    }


def _read_text(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, ""
    return True, path.read_text(encoding="utf-8", errors="replace")


def _count_text(assertion: dict[str, Any], text: str) -> int:
    expected = assertion["value"]
    case_sensitive = assertion.get("case_sensitive", True)
    actual = text
    if assertion["type"] != "regex" and not case_sensitive:
        actual = actual.casefold()
        expected = expected.casefold()
    if assertion["type"] == "contains":
        return actual.count(expected)
    if assertion["type"] == "equals":
        return int(actual.rstrip("\r\n") == expected.rstrip("\r\n"))
    flags = 0 if case_sensitive else re.IGNORECASE
    return len(list(re.finditer(expected, actual, flags)))


def _within_bounds(assertion: dict[str, Any], matches: int) -> bool:
    minimum = assertion.get("min_matches", 1)
    maximum = assertion.get("max_matches")
    return matches >= minimum and (maximum is None or matches <= maximum)


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _extract_file_paths(value: Any, parent: str) -> set[str]:
    paths: set[str] = set()
    if isinstance(value, list):
        for item in value:
            paths.update(_extract_file_paths(item, parent))
    elif isinstance(value, dict):
        explicit = value.get("path") or value.get("fullPath") or value.get("remotePath")
        if isinstance(explicit, str):
            paths.add(
                explicit
                if explicit.startswith("/")
                else f"{parent.rstrip('/')}/{explicit}"
            )
        elif isinstance(value.get("name"), str):
            paths.add(f"{parent.rstrip('/')}/{value['name']}")
        for key, child in value.items():
            if key not in {"path", "fullPath", "remotePath", "name"}:
                paths.update(_extract_file_paths(child, parent))
    return paths


def _attribute_matches(
    actual_present: bool, actual: Any, predicate: dict[str, Any]
) -> bool:
    if "exists" in predicate:
        return actual_present is predicate["exists"]
    if not actual_present:
        return False
    if "equals" in predicate:
        return actual == predicate["equals"]
    return re.search(predicate["regex"], _stringify(actual)) is not None


def _span_matches(span: dict[str, Any], assertion: dict[str, Any]) -> bool:
    if "name" in assertion and span.get("name") != assertion["name"]:
        return False
    if (
        "status" in assertion
        and str(span.get("status", "unset")).lower() != assertion["status"]
    ):
        return False
    attributes = span.get("attributes", {})
    if not isinstance(attributes, dict):
        return False
    for name, predicate in assertion.get("attributes", {}).items():
        if not _attribute_matches(name in attributes, attributes.get(name), predicate):
            return False
    return True


def _evaluate_assertion(
    assertion: dict[str, Any],
    *,
    evidence_dir: Path,
    global_turn: int | None,
    console_log: Path,
    trace_file: Path,
    assertion_index: int,
) -> dict[str, Any]:
    source = assertion["source"]
    result: dict[str, Any] = {
        "source": source,
        "type": assertion["type"],
        "expected": assertion,
    }
    if source in {"assistant_text", "raw"}:
        assert global_turn is not None
        suffix = "assistant-text.txt" if source == "assistant_text" else "raw.txt"
        path = evidence_dir / f"turn-{global_turn}-{suffix}"
        exists, text = _read_text(path)
        result.update({"evidence": str(path), "evidence_available": exists})
        if not exists:
            result.update(status="error", observed="evidence file is unavailable")
            return result
        matches = _count_text(assertion, text)
        passed = _within_bounds(assertion, matches)
        result.update(
            status="passed" if passed else "failed", observed={"matches": matches}
        )
        return result

    if source == "session_files":
        assert global_turn is not None
        path = evidence_dir / f"turn-{global_turn}-session-files-{assertion_index}.json"
        result.update({"evidence": str(path), "evidence_available": path.is_file()})
        if not path.is_file():
            result.update(
                status="error", observed="session-file listing is unavailable"
            )
            return result
        try:
            listing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            result.update(
                status="error", observed=f"invalid session-file listing: {exc}"
            )
            return result
        parent = str(PurePosixPath(assertion["path"]).parent)
        paths = _extract_file_paths(listing, parent)
        # The files API contract is $HOME-relative, but older extension builds
        # can expose the sandbox's physical home prefix. Normalize that prefix
        # by accepting only an exact contract-path suffix.
        present = any(
            path == assertion["path"] or path.endswith(assertion["path"])
            for path in paths
        )
        result.update(
            status="passed" if present else "failed",
            observed={"path_exists": present, "listed_paths": sorted(paths)},
        )
        return result

    if source == "console_log":
        exists, text = _read_text(console_log)
        result.update({"evidence": str(console_log), "evidence_available": exists})
        if not exists:
            result.update(
                status="error", observed="console-log evidence is unavailable"
            )
            return result
        matches = _count_text(assertion, text)
        passed = _within_bounds(assertion, matches)
        result.update(
            status="passed" if passed else "failed", observed={"matches": matches}
        )
        return result

    result.update(
        {"evidence": str(trace_file), "evidence_available": trace_file.is_file()}
    )
    if not trace_file.is_file():
        result.update(status="error", observed="trace evidence is unavailable")
        return result
    try:
        trace_value = json.loads(trace_file.read_text(encoding="utf-8"))
        if isinstance(trace_value, dict) and trace_value.get("available") is False:
            result.update(
                status="error",
                observed=trace_value.get("error", "trace evidence is unavailable"),
            )
            return result
        spans = (
            trace_value.get("spans", trace_value)
            if isinstance(trace_value, dict)
            else trace_value
        )
        if not isinstance(spans, list):
            raise ValueError("trace evidence must contain a spans array")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        result.update(status="error", observed=f"invalid trace evidence: {exc}")
        return result
    matches = sum(
        isinstance(span, dict) and _span_matches(span, assertion) for span in spans
    )
    passed = _within_bounds(assertion, matches)
    result.update(
        status="passed" if passed else "failed", observed={"matches": matches}
    )
    return result


def evaluate_plan(
    plan: dict[str, Any], evidence_dir: Path, console_log: Path, trace_file: Path
) -> dict[str, Any]:
    test_results = []
    any_failed = False
    any_error = False
    for test in plan["tests"]:
        if test["status"] == "not_applicable":
            test_results.append(
                {
                    "name": test["name"],
                    "status": "not_applicable",
                    "reason": test["reason"],
                }
            )
            continue
        assertions_results = []
        turn_results = []
        execution_error = False
        for turn in test["turns"]:
            status_path = evidence_dir / f"turn-{turn['global_turn']}-status.json"
            try:
                execution = json.loads(status_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                execution = {"evidence_available": False}
                execution_error = True
            else:
                if not isinstance(execution, dict):
                    execution = {
                        "evidence_available": True,
                        "error": "turn status evidence must be an object",
                    }
                    execution_error = True
                else:
                    exit_code = execution.get("exit_code")
                    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
                        execution["error"] = (
                            "turn status exit_code must be a required integer"
                        )
                        execution_error = True
                    elif exit_code != 0:
                        execution_error = True
                    approvals = execution.get("mcp_approvals")
                    if not isinstance(approvals, dict):
                        approvals = {"error": "mcp_approvals status must be an object"}
                        execution["mcp_approvals"] = approvals
                        execution_error = True
                    else:
                        automatic = approvals.get("automatic")
                        pending = approvals.get("pending")
                        approval_error = approvals.get("error")
                        steps = approvals.get("steps")
                        if (
                            not isinstance(automatic, bool)
                            or not isinstance(pending, int)
                            or isinstance(pending, bool)
                            or pending < 0
                            or not (
                                approval_error is None
                                or isinstance(approval_error, str)
                            )
                            or not isinstance(steps, list)
                        ):
                            execution["error"] = (
                                "turn status mcp_approvals fields are malformed"
                            )
                            execution_error = True
                        if approval_error:
                            execution_error = True
            turn_results.append(
                {
                    "turn": turn["turn"],
                    "global_turn": turn["global_turn"],
                    "execution": execution,
                }
            )
            for assertion_index, assertion in enumerate(turn["assertions"], start=1):
                result = _evaluate_assertion(
                    assertion,
                    evidence_dir=evidence_dir,
                    global_turn=turn["global_turn"],
                    console_log=console_log,
                    trace_file=trace_file,
                    assertion_index=assertion_index,
                )
                result.update(turn=turn["turn"], global_turn=turn["global_turn"])
                assertions_results.append(result)
        for assertion_index, assertion in enumerate(test["assertions"], start=1):
            result = _evaluate_assertion(
                assertion,
                evidence_dir=evidence_dir,
                global_turn=None,
                console_log=console_log,
                trace_file=trace_file,
                assertion_index=assertion_index,
            )
            assertions_results.append(result)
        statuses = {item["status"] for item in assertions_results}
        if execution_error or "error" in statuses:
            status = "error"
            any_error = True
        elif "failed" in statuses:
            status = "failed"
            any_failed = True
        else:
            status = "passed"
        test_results.append(
            {
                "name": test["name"],
                "status": status,
                "turns": turn_results,
                "assertions": assertions_results,
            }
        )
    overall = "error" if any_error else "failed" if any_failed else "passed"
    if test_results and all(
        item["status"] == "not_applicable" for item in test_results
    ):
        overall = "not_applicable"
    return {"status": overall, "tests": test_results}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _emit_error(message: str, report: Path | None = None) -> int:
    if report is not None:
        _write_json(report, {"status": "invalid", "error": message, "tests": []})
    print(f"::error::Invalid hosted-agent test spec: {message}")
    return 2


def _command_validate(args: argparse.Namespace) -> int:
    try:
        document = load_spec(args.spec)
    except SpecError as exc:
        return _emit_error(str(exc), args.report)
    if args.output:
        _write_json(args.output, document)
    if args.report:
        _write_json(args.report, {"status": "valid", "tests": len(document["tests"])})
    print(f"Valid hosted-agent test spec: {args.spec}")
    return 0


def _command_plan(args: argparse.Namespace) -> int:
    try:
        document = load_spec(args.spec)
        plan = build_plan(
            document, args.toolbox_label, args.toolbox_query, args.protocol
        )
    except SpecError as exc:
        return _emit_error(str(exc), args.report)
    _write_json(args.output, plan)
    if args.report:
        _write_json(
            args.report, {"status": "planned", "turn_count": plan["turn_count"]}
        )
    return 0


def _command_decide_approvals(args: argparse.Namespace) -> int:
    try:
        turn = json.loads(args.turn_json.read_text(encoding="utf-8"))
        response = json.loads(args.response.read_text(encoding="utf-8"))
        approved_ids_value = json.loads(args.approved_ids_json)
        if not isinstance(approved_ids_value, list) or not all(
            isinstance(item, str) for item in approved_ids_value
        ):
            raise ValueError("approved ids must be a JSON string array")
        decision = decide_mcp_approvals(turn, response, set(approved_ids_value))
    except Exception as exc:  # Keep malformed CI evidence fail-closed.
        decision = {
            "status": "error",
            "error": f"could not evaluate MCP approvals: {exc}",
            "pending_count": 0,
            "requests": [],
            "approval_responses": [],
            "new_ids": [],
        }
    _write_json(args.output, decision)
    return 1 if decision["status"] == "error" else 0


def _command_evaluate(args: argparse.Namespace) -> int:
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _emit_error(f"could not read execution plan: {exc}", args.report)
    report = evaluate_plan(plan, args.evidence_dir, args.console_log, args.trace_file)
    _write_json(args.report, report)
    for test in report["tests"]:
        print(f"{test['status'].upper()}: {test['name']}")
        for assertion in test.get("assertions", []):
            if assertion["status"] not in {"passed", "not_applicable"}:
                location = f" turn {assertion['turn']}" if "turn" in assertion else ""
                print(
                    f"  {assertion['status'].upper()} {assertion['source']}"
                    f"/{assertion['type']}{location}: expected "
                    f"{json.dumps(assertion['expected'], sort_keys=True)}, observed "
                    f"{json.dumps(assertion.get('observed'), sort_keys=True)}"
                )
    return 0 if report["status"] in {"passed", "not_applicable"} else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--spec", type=Path, required=True)
    validate.add_argument("--output", type=Path)
    validate.add_argument("--report", type=Path)
    validate.set_defaults(func=_command_validate)

    plan = subparsers.add_parser("plan")
    plan.add_argument("--spec", type=Path, required=True)
    plan.add_argument("--toolbox-label", default="")
    plan.add_argument("--toolbox-query", default="")
    plan.add_argument(
        "--protocol", choices=("responses", "invocations"), default="responses"
    )
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--report", type=Path)
    plan.set_defaults(func=_command_plan)

    decide = subparsers.add_parser("decide-approvals")
    decide.add_argument("--turn-json", type=Path, required=True)
    decide.add_argument("--response", type=Path, required=True)
    decide.add_argument("--approved-ids-json", default="[]")
    decide.add_argument("--output", type=Path, required=True)
    decide.set_defaults(func=_command_decide_approvals)

    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--plan", type=Path, required=True)
    evaluate.add_argument("--evidence-dir", type=Path, required=True)
    evaluate.add_argument("--console-log", type=Path, required=True)
    evaluate.add_argument("--trace-file", type=Path, required=True)
    evaluate.add_argument("--report", type=Path, required=True)
    evaluate.set_defaults(func=_command_evaluate)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
