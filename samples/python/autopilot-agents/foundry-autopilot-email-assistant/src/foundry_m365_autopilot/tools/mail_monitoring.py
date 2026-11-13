# Copyright (c) Microsoft. All rights reserved.

"""Validated mail-monitoring filters and shared/local persistence."""

from __future__ import annotations

import ast

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.storage.blob import ContentSettings
from azure.storage.blob.aio import BlobServiceClient, ContainerClient

MAIL_FILTER_VERSION = "1.0"
MANAGER_CONVERSATION_VERSION = "1.0"
MAX_FILTER_CONDITIONS = 20
_ALLOWED_OPERATORS = {
    "originalSender.address": frozenset({"equals", "in"}),
    "subject": frozenset({"equals", "contains", "containsAny"}),
    "body.text": frozenset({"equals", "contains", "containsAny"}),
    "sentAt": frozenset({"before", "after", "between"}),
    "importance": frozenset({"equals", "in"}),
}
_IMPORTANCE_VALUES = frozenset({"low", "normal", "high"})


class MailFilterValidationError(ValueError):
    """Raised when a model-produced mail filter is not safe and well formed."""


class MailMonitoringStorageError(RuntimeError):
    """Raised when monitoring configuration cannot be accessed safely."""


class AzureBlobMailMonitoringStore:
    """Persist monitoring configuration in a shared private blob container."""

    def __init__(
        self,
        account_url: str,
        container_name: str,
        credential: Any,
        *,
        container_client: Optional[ContainerClient] = None,
    ) -> None:
        if container_client is not None:
            self._service: Optional[BlobServiceClient] = None
            self._container = container_client
            return
        if not account_url.strip() or not container_name.strip():
            raise ValueError("Blob account URL and container name are required")
        self._service = BlobServiceClient(account_url=account_url, credential=credential)
        self._container = self._service.get_container_client(container_name)

    async def get(self, tenant_id: str, agent_user_id: str) -> Optional[dict[str, Any]]:
        blob = self._container.get_blob_client(_configuration_name(tenant_id, agent_user_id))
        try:
            payload = json.loads(await (await blob.download_blob()).readall())
        except ResourceNotFoundError:
            return None
        except (AzureError, json.JSONDecodeError, UnicodeDecodeError) as ex:
            raise MailMonitoringStorageError(
                "Unable to read mail-monitoring configuration from Azure Blob Storage"
            ) from ex
        if not isinstance(payload, dict) or payload.get("version") != MAIL_FILTER_VERSION:
            return None
        return payload

    async def save(
        self,
        tenant_id: str,
        agent_user_id: str,
        manager: dict[str, str],
        source_text: str,
        filter_expression: dict[str, Any],
    ) -> dict[str, Any]:
        payload = _build_payload(
            tenant_id, agent_user_id, manager, source_text, filter_expression
        )
        await self._write(tenant_id, agent_user_id, payload)
        return payload

    async def disable(self, tenant_id: str, agent_user_id: str) -> dict[str, Any]:
        payload = await self.get(tenant_id, agent_user_id) or {
            "version": MAIL_FILTER_VERSION,
            "tenantId": tenant_id,
            "agentUserId": agent_user_id,
        }
        payload["enabled"] = False
        payload["updatedAt"] = _utc_now()
        await self._write(tenant_id, agent_user_id, payload)
        return payload

    async def enable(self, tenant_id: str, agent_user_id: str) -> dict[str, Any]:
        payload = await self.get(tenant_id, agent_user_id)
        if not payload or not payload.get("filter"):
            raise MailFilterValidationError("No saved monitoring rule is available")
        payload["enabled"] = True
        payload["updatedAt"] = _utc_now()
        await self._write(tenant_id, agent_user_id, payload)
        return payload

    async def get_manager_conversation(
        self, tenant_id: str, agent_user_id: str
    ) -> Optional[dict[str, Any]]:
        blob = self._container.get_blob_client(
            _manager_conversation_name(tenant_id, agent_user_id)
        )
        try:
            payload = json.loads(await (await blob.download_blob()).readall())
        except ResourceNotFoundError:
            return None
        except (AzureError, json.JSONDecodeError, UnicodeDecodeError) as ex:
            raise MailMonitoringStorageError(
                "Unable to read Manager conversation from Azure Blob Storage"
            ) from ex
        if not isinstance(payload, dict) or payload.get("version") != (
            MANAGER_CONVERSATION_VERSION
        ):
            return None
        return payload

    async def save_manager_conversation(
        self,
        tenant_id: str,
        agent_user_id: str,
        conversation: dict[str, Any],
    ) -> None:
        blob = self._container.get_blob_client(
            _manager_conversation_name(tenant_id, agent_user_id)
        )
        try:
            await blob.upload_blob(
                json.dumps(conversation, ensure_ascii=False, indent=2, sort_keys=True),
                overwrite=True,
                content_settings=ContentSettings(content_type="application/json"),
            )
        except AzureError as ex:
            raise MailMonitoringStorageError(
                "Unable to save Manager conversation to Azure Blob Storage"
            ) from ex

    async def close(self) -> None:
        if self._service is not None:
            await self._service.close()

    async def _write(
        self, tenant_id: str, agent_user_id: str, payload: dict[str, Any]
    ) -> None:
        blob = self._container.get_blob_client(_configuration_name(tenant_id, agent_user_id))
        try:
            await blob.upload_blob(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                overwrite=True,
                content_settings=ContentSettings(content_type="application/json"),
            )
        except AzureError as ex:
            raise MailMonitoringStorageError(
                "Unable to save mail-monitoring configuration to Azure Blob Storage"
            ) from ex


class LocalFileMailMonitoringStore:
    """Persist one JSON configuration per tenant and Agent User for local use."""

    def __init__(self, root: Optional[Path] = None) -> None:
        configured = os.getenv("MAIL_MONITOR_CONFIG_DIR", "").strip()
        self.root = root or (
            Path(configured).expanduser()
            if configured
            else Path.home() / ".a365agent" / "mail-monitor-config"
        )

    async def get(self, tenant_id: str, agent_user_id: str) -> Optional[dict[str, Any]]:
        path = self._path(tenant_id, agent_user_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("version") != MAIL_FILTER_VERSION:
            return None
        return payload

    async def save(
        self,
        tenant_id: str,
        agent_user_id: str,
        manager: dict[str, str],
        source_text: str,
        filter_expression: dict[str, Any],
    ) -> dict[str, Any]:
        payload = _build_payload(
            tenant_id, agent_user_id, manager, source_text, filter_expression
        )
        self._write(tenant_id, agent_user_id, payload)
        return payload

    async def disable(self, tenant_id: str, agent_user_id: str) -> dict[str, Any]:
        payload = await self.get(tenant_id, agent_user_id) or {
            "version": MAIL_FILTER_VERSION,
            "tenantId": tenant_id,
            "agentUserId": agent_user_id,
        }
        payload["enabled"] = False
        payload["updatedAt"] = _utc_now()
        self._write(tenant_id, agent_user_id, payload)
        return payload

    async def enable(self, tenant_id: str, agent_user_id: str) -> dict[str, Any]:
        payload = await self.get(tenant_id, agent_user_id)
        if not payload or not payload.get("filter"):
            raise MailFilterValidationError("No saved monitoring rule is available")
        payload["enabled"] = True
        payload["updatedAt"] = _utc_now()
        self._write(tenant_id, agent_user_id, payload)
        return payload

    async def get_manager_conversation(
        self, tenant_id: str, agent_user_id: str
    ) -> Optional[dict[str, Any]]:
        path = self.root / _manager_conversation_name(tenant_id, agent_user_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("version") != (
            MANAGER_CONVERSATION_VERSION
        ):
            return None
        return payload

    async def save_manager_conversation(
        self,
        tenant_id: str,
        agent_user_id: str,
        conversation: dict[str, Any],
    ) -> None:
        path = self.root / _manager_conversation_name(tenant_id, agent_user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(conversation, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _write(self, tenant_id: str, agent_user_id: str, payload: dict[str, Any]) -> None:
        path = self._path(tenant_id, agent_user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _path(self, tenant_id: str, agent_user_id: str) -> Path:
        return self.root / _configuration_name(tenant_id, agent_user_id)


def _build_payload(
    tenant_id: str,
    agent_user_id: str,
    manager: dict[str, str],
    source_text: str,
    filter_expression: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": MAIL_FILTER_VERSION,
        "enabled": True,
        "tenantId": tenant_id,
        "agentUserId": agent_user_id,
        "managerObjectId": str(manager.get("id") or ""),
        "managerUpn": str(manager.get("userPrincipalName") or manager.get("mail") or ""),
        "sourceText": source_text.strip(),
        "filter": normalize_filter(filter_expression),
        "updatedAt": _utc_now(),
    }


def _configuration_name(tenant_id: str, agent_user_id: str) -> str:
    if not tenant_id.strip() or not agent_user_id.strip():
        raise ValueError("tenant_id and agent_user_id are required")
    digest = hashlib.sha256(
        f"{tenant_id.strip()}:{agent_user_id.strip()}".encode("utf-8")
    ).hexdigest()
    return f"{digest}.json"


def _manager_conversation_name(tenant_id: str, agent_user_id: str) -> str:
    return f"{_configuration_name(tenant_id, agent_user_id)[:-5]}.conversation.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_filter(expression: Any) -> dict[str, Any]:
    """Validate and canonicalize a simple all/any list of atomic conditions."""

    if not isinstance(expression, dict):
        raise MailFilterValidationError("filter must be a JSON object")
    if set(expression) - {"match", "conditions"}:
        raise MailFilterValidationError("filter contains unsupported properties")
    match = str(expression.get("match") or "").strip().lower()
    if match not in {"all", "any"}:
        raise MailFilterValidationError("filter.match must be 'all' or 'any'")
    conditions = expression.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise MailFilterValidationError("filter.conditions must be a non-empty array")
    if len(conditions) > MAX_FILTER_CONDITIONS:
        raise MailFilterValidationError(
            f"filter supports at most {MAX_FILTER_CONDITIONS} conditions"
        )
    return {
        "match": match,
        "conditions": [_normalize_condition(condition) for condition in conditions],
    }


def matches_filter(expression: dict[str, Any], mail: dict[str, Any]) -> bool:
    """Evaluate a validated filter against a normalized mail context."""

    try:
        normalized = normalize_filter(expression)
    except MailFilterValidationError:
        return False
    results = [_matches_condition(item, mail) for item in normalized["conditions"]]
    return all(results) if normalized["match"] == "all" else any(results)


def describe_filter(expression: dict[str, Any]) -> str:
    """Render a short deterministic description for status and confirmations."""

    normalized = normalize_filter(expression)
    connector = " 且 " if normalized["match"] == "all" else " 或 "
    descriptions = []
    for condition in normalized["conditions"]:
        field = {
            "originalSender.address": "原始发件人",
            "subject": "主题",
            "body.text": "正文",
            "sentAt": "发送时间",
            "importance": "重要性",
        }[condition["field"]]
        operator = {
            "equals": "等于",
            "in": "属于",
            "contains": "包含",
            "containsAny": "包含任一",
            "before": "早于",
            "after": "晚于",
            "between": "介于",
        }[condition["operator"]]
        value = condition["value"]
        if isinstance(value, list):
            rendered = "、".join(str(item) for item in value)
        elif isinstance(value, dict):
            rendered = f"{value['start']} 至 {value['end']}"
        else:
            rendered = str(value)
        descriptions.append(f"{field}{operator}“{rendered}”")
    return connector.join(descriptions)


def _normalize_condition(condition: Any) -> dict[str, Any]:
    if not isinstance(condition, dict):
        raise MailFilterValidationError("each condition must be a JSON object")
    if set(condition) != {"field", "operator", "value"}:
        raise MailFilterValidationError(
            "each condition must contain only field, operator, and value"
        )
    field = str(condition.get("field") or "").strip()
    operator = str(condition.get("operator") or "").strip()
    if field not in _ALLOWED_OPERATORS:
        raise MailFilterValidationError(f"unsupported filter field: {field}")
    if operator not in _ALLOWED_OPERATORS[field]:
        raise MailFilterValidationError(
            f"operator {operator!r} is not supported for field {field!r}"
        )
    value = condition.get("value")
    if field == "originalSender.address":
        value = _normalize_address_value(value, operator == "in")
    elif field in {"subject", "body.text"}:
        value = _normalize_text_value(value, operator == "containsAny")
    elif field == "importance":
        value = _normalize_importance_value(value, operator == "in")
    elif field == "sentAt":
        value = _normalize_datetime_value(value, operator)
    return {"field": field, "operator": operator, "value": value}


def _normalize_address_value(value: Any, multiple: bool) -> str | list[str]:
    values = value if multiple else [value]
    if not isinstance(values, list) or not values or len(values) > 50:
        raise MailFilterValidationError("email address value is invalid")
    normalized = []
    for item in values:
        address = str(item or "").strip().casefold()
        if "@" not in address or any(character.isspace() for character in address):
            raise MailFilterValidationError(f"invalid email address: {item!r}")
        normalized.append(address)
    return normalized if multiple else normalized[0]


def _normalize_text_value(value: Any, multiple: bool) -> str | list[str]:
    if not multiple and isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                legacy_value = ast.literal_eval(stripped)
            except (SyntaxError, ValueError):
                legacy_value = None
            if isinstance(legacy_value, list):
                value = legacy_value
    if not multiple and isinstance(value, list):
        if len(value) != 1:
            raise MailFilterValidationError(
                "scalar text operators require exactly one text value"
            )
        value = value[0]
    values = value if multiple else [value]
    if not isinstance(values, list) or not values or len(values) > 50:
        raise MailFilterValidationError("text filter value is invalid")
    normalized = []
    for item in values:
        text = str(item or "").strip()
        if not text or len(text) > 500:
            raise MailFilterValidationError("text values must contain 1-500 characters")
        normalized.append(text)
    return normalized if multiple else normalized[0]


def _normalize_importance_value(value: Any, multiple: bool) -> str | list[str]:
    values = value if multiple else [value]
    if not isinstance(values, list) or not values:
        raise MailFilterValidationError("importance value is invalid")
    normalized = [str(item or "").strip().lower() for item in values]
    if any(item not in _IMPORTANCE_VALUES for item in normalized):
        raise MailFilterValidationError("importance must be low, normal, or high")
    return normalized if multiple else normalized[0]


def _normalize_datetime_value(value: Any, operator: str) -> str | dict[str, str]:
    if operator == "between":
        if not isinstance(value, dict) or set(value) != {"start", "end"}:
            raise MailFilterValidationError(
                "sentAt between requires start and end ISO 8601 values"
            )
        start = _canonical_datetime(value["start"])
        end = _canonical_datetime(value["end"])
        if _parse_datetime(start) >= _parse_datetime(end):
            raise MailFilterValidationError("sentAt start must be earlier than end")
        return {"start": start, "end": end}
    return _canonical_datetime(value)


def _canonical_datetime(value: Any) -> str:
    parsed = _parse_datetime(str(value or "").strip())
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as ex:
        raise MailFilterValidationError(
            f"invalid ISO 8601 date/time value: {value!r}"
        ) from ex


def _matches_condition(condition: dict[str, Any], mail: dict[str, Any]) -> bool:
    actual = _get_mail_value(mail, condition["field"])
    if actual is None or actual == "":
        return False
    operator = condition["operator"]
    expected = condition["value"]
    if condition["field"] == "sentAt":
        try:
            actual_time = _parse_datetime(str(actual))
            if actual_time.tzinfo is None:
                actual_time = actual_time.replace(tzinfo=timezone.utc)
            if operator == "before":
                return actual_time < _parse_datetime(str(expected))
            if operator == "after":
                return actual_time > _parse_datetime(str(expected))
            return _parse_datetime(expected["start"]) <= actual_time <= _parse_datetime(
                expected["end"]
            )
        except (MailFilterValidationError, TypeError, KeyError):
            return False
    actual_text = str(actual).casefold()
    if operator == "equals":
        return actual_text == str(expected).casefold()
    if operator == "in":
        return actual_text in {str(item).casefold() for item in expected}
    if operator == "contains":
        return str(expected).casefold() in actual_text
    if operator == "containsAny":
        return any(str(item).casefold() in actual_text for item in expected)
    return False


def _get_mail_value(mail: dict[str, Any], field: str) -> Any:
    value: Any = mail
    for part in field.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value
