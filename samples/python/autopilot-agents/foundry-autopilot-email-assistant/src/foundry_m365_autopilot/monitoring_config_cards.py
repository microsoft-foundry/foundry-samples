"""Adaptive Card forms for creating and editing email-monitoring rules."""

from __future__ import annotations

import json
from typing import Any

from .tools.mail_monitoring import MailFilterValidationError, normalize_filter

CONFIGURE_FORM_VERB = "configureMailMonitoringForm"
EDIT_JSON_VERB = "editMailMonitoringJson"
SUBMIT_ACTION_KEY = "monitoringAction"
CONFIGURE_FORM_SUBMIT_TEXT = "/submit-email-monitoring-form"
EDIT_JSON_SUBMIT_TEXT = "/submit-email-monitoring-json"


def build_monitoring_form_attachment(config: Any = None) -> dict[str, Any]:
    values = _form_values(config)
    return _attachment(
        [
            _heading("Configure email monitoring"),
            {
                "type": "TextBlock",
                "text": "Add one or more conditions. Blank fields are ignored.",
                "wrap": True,
                "isSubtle": True,
                "spacing": "Small",
            },
            {
                "type": "Input.ChoiceSet",
                "id": "matchMode",
                "label": "Match conditions",
                "value": values["matchMode"],
                "choices": [
                    {"title": "All conditions", "value": "all"},
                    {"title": "Any condition", "value": "any"},
                ],
            },
            {
                "type": "Input.Text",
                "id": "senderAddress",
                "label": "Original sender address",
                "placeholder": "approvals@contoso.com",
                "style": "Email",
                "value": values["senderAddress"],
            },
            {
                "type": "Input.Text",
                "id": "subjectContains",
                "label": "Subject contains",
                "placeholder": "Approval",
                "value": values["subjectContains"],
                "maxLength": 500,
            },
            {
                "type": "Input.Text",
                "id": "bodyContains",
                "label": "Body contains",
                "isMultiline": True,
                "value": values["bodyContains"],
                "maxLength": 500,
            },
            {
                "type": "Input.ChoiceSet",
                "id": "importance",
                "label": "Importance",
                "value": values["importance"],
                "choices": [
                    {"title": "Any importance", "value": ""},
                    {"title": "High", "value": "high"},
                    {"title": "Normal", "value": "normal"},
                    {"title": "Low", "value": "low"},
                ],
            },
        ],
        [
            {
                "type": "Action.Submit",
                "title": "Save and enable",
                "data": {
                    SUBMIT_ACTION_KEY: CONFIGURE_FORM_VERB,
                    "schemaVersion": "1.0",
                    "msteams": {
                        "type": "messageBack",
                        "displayText": "Save email monitoring configuration",
                        "text": CONFIGURE_FORM_SUBMIT_TEXT,
                        "value": {SUBMIT_ACTION_KEY: CONFIGURE_FORM_VERB},
                    },
                },
            }
        ],
    )


def build_monitoring_json_attachment(config: Any) -> dict[str, Any]:
    editable = config if isinstance(config, dict) else {}
    return _attachment(
        [
            _heading("Edit email monitoring JSON"),
            {
                "type": "TextBlock",
                "text": (
                    "Edit sourceText and filter. Identity, ownership, and timestamp "
                    "fields are always taken from the current Activity context."
                ),
                "wrap": True,
                "isSubtle": True,
                "spacing": "Small",
            },
            {
                "type": "Input.Text",
                "id": "configJson",
                "label": "Existing config",
                "isMultiline": True,
                "value": json.dumps(
                    editable,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    default=str,
                ),
            },
        ],
        [
            {
                "type": "Action.Submit",
                "title": "Validate and save",
                "data": {
                    SUBMIT_ACTION_KEY: EDIT_JSON_VERB,
                    "schemaVersion": "1.0",
                    "msteams": {
                        "type": "messageBack",
                        "displayText": "Save email monitoring JSON",
                        "text": EDIT_JSON_SUBMIT_TEXT,
                        "value": {SUBMIT_ACTION_KEY: EDIT_JSON_VERB},
                    },
                },
            }
        ],
    )


def build_monitoring_config_error_attachment(
    message: str, *, retry_attachment: dict[str, Any] | None = None
) -> dict[str, Any]:
    body = [
        {
            "type": "TextBlock",
            "text": "Unable to save email monitoring",
            "weight": "Bolder",
            "size": "Large",
            "color": "Attention",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": str(message or "The submitted configuration is invalid."),
            "wrap": True,
            "spacing": "Medium",
        },
    ]
    retry_content = retry_attachment.get("content") if retry_attachment else None
    if isinstance(retry_content, dict):
        body.extend(retry_content.get("body", []))
        actions = retry_content.get("actions", [])
    else:
        actions = []
    return _attachment(body, actions)


def build_form_configuration_arguments(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise MailFilterValidationError("Adaptive Card data must be a JSON object")
    conditions: list[dict[str, Any]] = []
    _append_condition(
        conditions,
        "originalSender.address",
        "equals",
        data.get("senderAddress"),
    )
    _append_condition(conditions, "subject", "contains", data.get("subjectContains"))
    _append_condition(conditions, "body.text", "contains", data.get("bodyContains"))
    _append_condition(conditions, "importance", "equals", data.get("importance"))
    filter_expression = normalize_filter(
        {"match": data.get("matchMode", "all"), "conditions": conditions}
    )
    return {
        "source_text": "Configured with the email monitoring Adaptive Card form.",
        "filter": filter_expression,
    }


def build_json_configuration_arguments(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise MailFilterValidationError("Adaptive Card data must be a JSON object")
    raw_json = str(data.get("configJson") or "").strip()
    if not raw_json:
        raise MailFilterValidationError("configJson is required")
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as ex:
        raise MailFilterValidationError(
            f"Config must be valid JSON: {ex.msg} at line {ex.lineno}, column {ex.colno}"
        ) from ex
    if not isinstance(payload, dict):
        raise MailFilterValidationError("Config must be a JSON object")
    filter_expression = payload.get("filter", payload)
    normalized_filter = normalize_filter(filter_expression)
    source_text = str(payload.get("sourceText") or "").strip()
    return {
        "source_text": source_text or "Updated with the email monitoring JSON editor.",
        "filter": normalized_filter,
    }


def get_execute_action(activity_value: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(activity_value, dict):
        return "", {}
    action = activity_value.get("action")
    if not isinstance(action, dict):
        return "", {}
    data = action.get("data")
    return str(action.get("verb") or ""), data if isinstance(data, dict) else {}


def get_submit_action(activity_value: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(activity_value, dict):
        return "", {}
    data = dict(activity_value)
    teams_data = data.get("msteams")
    teams_value = teams_data.get("value") if isinstance(teams_data, dict) else None
    if isinstance(teams_value, dict):
        data.update(teams_value)
    verb = str(data.get(SUBMIT_ACTION_KEY) or "")
    return verb, data


def _append_condition(
    conditions: list[dict[str, Any]], field: str, operator: str, value: Any
) -> None:
    normalized = str(value or "").strip()
    if normalized:
        conditions.append({"field": field, "operator": operator, "value": normalized})


def _form_values(config: Any) -> dict[str, str]:
    values = {
        "matchMode": "all",
        "senderAddress": "",
        "subjectContains": "",
        "bodyContains": "",
        "importance": "",
    }
    if not isinstance(config, dict) or not isinstance(config.get("filter"), dict):
        return values
    filter_expression = config["filter"]
    if filter_expression.get("match") in {"all", "any"}:
        values["matchMode"] = filter_expression["match"]
    field_map = {
        ("originalSender.address", "equals"): "senderAddress",
        ("subject", "contains"): "subjectContains",
        ("body.text", "contains"): "bodyContains",
        ("importance", "equals"): "importance",
    }
    for condition in filter_expression.get("conditions", []):
        if not isinstance(condition, dict):
            continue
        input_id = field_map.get((condition.get("field"), condition.get("operator")))
        if input_id and isinstance(condition.get("value"), str):
            values[input_id] = condition["value"]
    return values


def _heading(text: str) -> dict[str, Any]:
    return {
        "type": "TextBlock",
        "text": text,
        "weight": "Bolder",
        "size": "Large",
        "wrap": True,
    }


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