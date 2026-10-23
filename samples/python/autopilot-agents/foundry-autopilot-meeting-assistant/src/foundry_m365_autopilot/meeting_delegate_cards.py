"""Adaptive Card forms for meeting delegate answer rules."""

from __future__ import annotations

import re
from typing import Any

from .meeting_store import MAX_RULES, MeetingDelegateValidationError

ADD_RULE_VERB = "meetingDelegateAddRule"
REMOVE_RULE_VERB = "meetingDelegateRemoveRule"
SAVE_RULES_VERB = "meetingDelegateSaveRules"
CONFIGURE_RULES_VERB = "meetingDelegateConfigureRules"
SUBMIT_ACTION_KEY = "meetingDelegateAction"
SUBMIT_TEXT = "/submit-meeting-delegate-card"
SUBMIT_DISPLAY_TEXTS = {
    CONFIGURE_RULES_VERB: "Configure meeting replies",
    ADD_RULE_VERB: "Add meeting reply question",
    REMOVE_RULE_VERB: "Delete meeting reply question",
    SAVE_RULES_VERB: "Save meeting reply rules",
}
LEGACY_SUBMIT_DISPLAY_TEXTS = {"Add question", "Delete question", "Save"}


def build_meeting_delegate_attachment(
    config: Any = None, *, message: str = "", is_error: bool = False
) -> dict[str, Any]:
    values = _form_values(config)
    if not values["meetingId"]:
        return _attachment(
            [
                {
                    "type": "TextBlock",
                    "text": "Configure meeting reply rules",
                    "weight": "Bolder",
                    "size": "Large",
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": (
                        message
                        or "Meeting ID is missing. Open the meeting list and select "
                        "Configure replies for the meeting again."
                    ),
                    "color": "Attention",
                    "weight": "Bolder",
                    "wrap": True,
                },
            ],
            [],
        )
    rules = values["answerRules"]
    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": "Configure meeting reply rules",
            "weight": "Bolder",
            "size": "Large",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": "Only this Digital Worker's current Manager can save these rules.",
            "isSubtle": True,
            "wrap": True,
            "spacing": "Small",
        },
    ]
    if message:
        body.append(
            {
                "type": "TextBlock",
                "text": message,
                "color": "Attention" if is_error else "Good",
                "weight": "Bolder",
                "wrap": True,
                "spacing": "Medium",
            }
        )
    body.extend(
        [
            {
                "type": "Input.Toggle",
                "id": "delegationEnabled",
                "title": "Enable automatic replies for this meeting",
                "value": _toggle_value(values["delegationEnabled"]),
                "valueOn": "true",
                "valueOff": "false",
            },
            {
                "type": "TextBlock",
                "text": "Approved question and answer rules",
                "weight": "Bolder",
                "spacing": "Large",
                "wrap": True,
            },
        ]
    )
    for index, rule in enumerate(rules):
        body.append(_rule_container(index, rule, len(rules), values))

    actions: list[dict[str, Any]] = []
    if len(rules) < MAX_RULES:
        actions.append(
            _submit_action("Add question", ADD_RULE_VERB, len(rules), values)
        )
    actions.append(_submit_action("Save", SAVE_RULES_VERB, len(rules), values))
    return _attachment(body, actions)


def extract_configuration_meeting_id(message: str) -> str:
    text = str(message or "").strip()
    patterns = (
        r"(?:meeting\s*id|event\s*id|(?:this|the)\s+id|id|meeting|会议)\s*[:：=]\s*([^\s,，。]+)",
        r"(?:自动回复|auto(?:matic)?\s*repl(?:y|ies))\s*[:：=]\s*([^\s,，。]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def get_submit_action(activity_value: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(activity_value, dict):
        return "", {}
    data = dict(activity_value)
    teams_data = data.get("msteams")
    teams_value = teams_data.get("value") if isinstance(teams_data, dict) else None
    if isinstance(teams_value, dict):
        for key, value in teams_value.items():
            if value not in (None, "") or not data.get(key):
                data[key] = value
    return str(data.get(SUBMIT_ACTION_KEY) or ""), data


def is_submit_message(message: str) -> bool:
    normalized = str(message or "").strip().casefold()
    return normalized in {
        SUBMIT_TEXT.casefold(),
        *(text.casefold() for text in SUBMIT_DISPLAY_TEXTS.values()),
        *(text.casefold() for text in LEGACY_SUBMIT_DISPLAY_TEXTS),
    }


def rebuild_form_data(data: Any, verb: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise MeetingDelegateValidationError(
            "Adaptive Card data must be a JSON object."
        )
    count = _rule_count(data)
    rules = [_submitted_rule(data, index) for index in range(count)]
    if verb == ADD_RULE_VERB:
        if len(rules) >= MAX_RULES:
            raise MeetingDelegateValidationError(
                f"At most {MAX_RULES} answer rules are supported."
            )
        rules.append({"questions": [""], "answer": "", "enabled": True})
    elif verb == REMOVE_RULE_VERB:
        remove_index = _integer(data.get("removeIndex"), -1)
        if remove_index < 0 or remove_index >= len(rules):
            raise MeetingDelegateValidationError("The selected question no longer exists.")
        rules.pop(remove_index)
    return {
        "meetingId": str(data.get("meetingId") or "").strip(),
        "chatId": str(data.get("chatId") or "").strip(),
        "subject": str(data.get("subject") or "").strip(),
        "joinWebUrl": str(data.get("joinWebUrl") or "").strip(),
        "scheduledStartTime": str(data.get("scheduledStartTime") or "").strip(),
        "scheduledEndTime": str(data.get("scheduledEndTime") or "").strip(),
        "delegationEnabled": _is_enabled(data.get("delegationEnabled")),
        "answerRules": rules,
    }


def build_configuration_request(data: Any) -> dict[str, Any]:
    config = rebuild_form_data(data, SAVE_RULES_VERB)
    rules: list[dict[str, Any]] = []
    for index, rule in enumerate(config["answerRules"], start=1):
        question = str((rule.get("questions") or [""])[0]).strip()
        answer = str(rule.get("answer") or "").strip()
        if not question and not answer:
            continue
        if not question or not answer:
            raise MeetingDelegateValidationError(
                f"Question {index} requires both a question and an answer."
            )
        rules.append(
            {
                "id": str(rule.get("id") or f"rule-{index}"),
                "questions": [question],
                "answer": answer,
                "enabled": bool(rule.get("enabled", True)),
            }
        )
    config["answerRules"] = rules
    return config


def _rule_container(
    index: int, rule: dict[str, Any], count: int, metadata: dict[str, Any]
) -> dict[str, Any]:
    question = str((rule.get("questions") or [""])[0])
    return {
        "type": "Container",
        "separator": True,
        "spacing": "Medium",
        "items": [
            {
                "type": "TextBlock",
                "text": f"Question {index + 1}",
                "weight": "Bolder",
                "wrap": True,
            },
            {
                "type": "Input.Text",
                "id": f"question_{index}",
                "label": "Question",
                "value": question,
                "maxLength": 500,
            },
            {
                "type": "Input.Text",
                "id": f"answer_{index}",
                "label": "Approved answer",
                "value": str(rule.get("answer") or ""),
                "isMultiline": True,
                "maxLength": 1000,
            },
            {
                "type": "Input.Toggle",
                "id": f"ruleEnabled_{index}",
                "title": "Enable this question",
                "value": _toggle_value(rule.get("enabled", True)),
                "valueOn": "true",
                "valueOff": "false",
            },
            {
                "type": "ActionSet",
                "actions": [
                    _submit_action(
                        "Delete question",
                        REMOVE_RULE_VERB,
                        count,
                        metadata,
                        remove_index=index,
                    )
                ],
            },
        ],
    }


def _submit_action(
    title: str,
    verb: str,
    rule_count: int,
    metadata: dict[str, Any],
    *,
    remove_index: int | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        SUBMIT_ACTION_KEY: verb,
        "schemaVersion": "1.0",
        "ruleCount": rule_count,
        "meetingId": str(metadata.get("meetingId") or ""),
        "chatId": str(metadata.get("chatId") or ""),
        "subject": str(metadata.get("subject") or ""),
        "joinWebUrl": str(metadata.get("joinWebUrl") or ""),
        "scheduledStartTime": str(metadata.get("scheduledStartTime") or ""),
        "scheduledEndTime": str(metadata.get("scheduledEndTime") or ""),
    }
    if remove_index is not None:
        value["removeIndex"] = remove_index
    return {
        "type": "Action.Submit",
        "title": title,
        "data": {
            **value,
            "msteams": {
                "type": "messageBack",
                "text": SUBMIT_TEXT,
                "value": value,
            },
        },
    }


def _form_values(config: Any) -> dict[str, Any]:
    source = config if isinstance(config, dict) else {}
    reactive_rules = source.get("reactiveRules")
    rules = source.get("answerRules")
    if rules is None and isinstance(reactive_rules, dict):
        rules = reactive_rules.get("answerRules")
    normalized_rules = [dict(rule) for rule in rules or [] if isinstance(rule, dict)]
    if not normalized_rules:
        normalized_rules = [{"questions": [""], "answer": "", "enabled": True}]
    return {
        "meetingId": str(source.get("meetingId") or ""),
        "chatId": str(source.get("chatId") or ""),
        "subject": str(source.get("subject") or ""),
        "joinWebUrl": str(source.get("joinWebUrl") or ""),
        "scheduledStartTime": str(source.get("scheduledStartTime") or ""),
        "scheduledEndTime": str(source.get("scheduledEndTime") or ""),
        "delegationEnabled": bool(source.get("delegationEnabled", True)),
        "answerRules": normalized_rules[:MAX_RULES],
    }


def _submitted_rule(data: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "id": str(data.get(f"ruleId_{index}") or f"rule-{index + 1}"),
        "questions": [str(data.get(f"question_{index}") or "")],
        "answer": str(data.get(f"answer_{index}") or ""),
        "enabled": _is_enabled(data.get(f"ruleEnabled_{index}", "true")),
    }


def _rule_count(data: dict[str, Any]) -> int:
    count = _integer(data.get("ruleCount"), 1)
    return max(1, min(count, MAX_RULES))


def _integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"true", "1", "yes", "on"}


def _toggle_value(value: Any) -> str:
    return "true" if _is_enabled(value) else "false"


def _attachment(
    body: list[dict[str, Any]], actions: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "contentType": "application/vnd.microsoft.card.adaptive",
        "content": {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.5",
            "body": body,
            "actions": actions,
        },
    }
