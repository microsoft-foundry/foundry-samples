"""Meeting delegate state validation and persistence."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

MEETING_DELEGATE_VERSION = "1.0"
MAX_OPENING_MESSAGE_CHARS = 1000
MAX_QUESTION_CHARS = 500
MAX_ANSWER_CHARS = 1000
MAX_RULES = 20


def join_web_url_alias(join_web_url: str) -> str:
    value = join_web_url.strip()
    return f"join-web-url:{hashlib.sha256(value.encode('utf-8')).hexdigest()}" if value else ""


class MeetingDelegateValidationError(ValueError):
    """Raised when a meeting delegate payload is unsafe or incomplete."""


class MeetingDelegateStorageError(RuntimeError):
    """Raised when meeting delegate state cannot be accessed safely."""


class AzureBlobMeetingDelegateStore:
    def __init__(self, account_url: str, container_name: str, credential: Any) -> None:
        if not account_url.strip() or not container_name.strip():
            raise ValueError("Blob account URL and container name are required")
        from azure.storage.blob.aio import BlobServiceClient

        self._service = BlobServiceClient(account_url=account_url, credential=credential)
        self._container = self._service.get_container_client(container_name)

    async def get(
        self, tenant_id: str, agent_user_id: str, meeting_id: str
    ) -> Optional[dict[str, Any]]:
        from azure.core.exceptions import AzureError, ResourceNotFoundError

        blob = self._container.get_blob_client(
            _delegate_name(tenant_id, agent_user_id, meeting_id)
        )
        try:
            payload = json.loads(await (await blob.download_blob()).readall())
        except ResourceNotFoundError:
            return None
        except (AzureError, json.JSONDecodeError, UnicodeDecodeError) as ex:
            raise MeetingDelegateStorageError(
                "Unable to read meeting delegate state from Azure Blob Storage"
            ) from ex
        if _is_delegate_alias(payload):
            canonical_id = str(payload.get("meetingId") or "")
            if canonical_id and canonical_id != meeting_id:
                return await self.get(tenant_id, agent_user_id, canonical_id)
        return payload if _is_delegate_payload(payload) else None

    async def save(self, delegate: dict[str, Any]) -> dict[str, Any]:
        await self._write(
            delegate,
            _delegate_name(
                delegate["tenantId"], delegate["agentUserId"], delegate["meetingId"]
            ),
        )
        return delegate

    async def save_alias(
        self,
        tenant_id: str,
        agent_user_id: str,
        alias_id: str,
        meeting_id: str,
    ) -> None:
        if not alias_id or alias_id == meeting_id:
            return
        await self._write(
            _delegate_alias(meeting_id),
            _delegate_name(tenant_id, agent_user_id, alias_id),
        )

    async def find_by_schedule(
        self,
        tenant_id: str,
        agent_user_id: str,
        scheduled_start_time: str,
        scheduled_end_time: str,
    ) -> Optional[dict[str, Any]]:
        from azure.core.exceptions import AzureError

        matches: list[dict[str, Any]] = []
        prefix = _delegate_prefix(tenant_id, agent_user_id)
        try:
            async for item in self._container.list_blobs(name_starts_with=prefix):
                name = str(getattr(item, "name", "") or "")
                if not name.endswith(".json"):
                    continue
                blob = self._container.get_blob_client(name)
                payload = json.loads(await (await blob.download_blob()).readall())
                if _matches_schedule(
                    payload, scheduled_start_time, scheduled_end_time
                ):
                    matches.append(payload)
        except (AzureError, json.JSONDecodeError, UnicodeDecodeError) as ex:
            raise MeetingDelegateStorageError(
                "Unable to find meeting delegate state in Azure Blob Storage"
            ) from ex
        return matches[0] if len(matches) == 1 else None

    async def close(self) -> None:
        await self._service.close()

    async def _write(self, payload: dict[str, Any], name: str) -> None:
        from azure.core.exceptions import AzureError
        from azure.storage.blob import ContentSettings

        blob = self._container.get_blob_client(name)
        try:
            await blob.upload_blob(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                overwrite=True,
                content_settings=ContentSettings(content_type="application/json"),
            )
        except AzureError as ex:
            raise MeetingDelegateStorageError(
                "Unable to save meeting delegate state to Azure Blob Storage"
            ) from ex


class LocalFileMeetingDelegateStore:
    def __init__(self, root: Optional[Path] = None) -> None:
        configured = os.getenv("MEETING_DELEGATE_CONFIG_DIR", "").strip()
        self.root = root or (
            Path(configured).expanduser()
            if configured
            else Path.home() / ".a365agent" / "meeting-delegates"
        )

    async def get(
        self, tenant_id: str, agent_user_id: str, meeting_id: str
    ) -> Optional[dict[str, Any]]:
        path = self.root / _delegate_name(tenant_id, agent_user_id, meeting_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if _is_delegate_alias(payload):
            canonical_id = str(payload.get("meetingId") or "")
            if canonical_id and canonical_id != meeting_id:
                return await self.get(tenant_id, agent_user_id, canonical_id)
        return payload if _is_delegate_payload(payload) else None

    async def save(self, delegate: dict[str, Any]) -> dict[str, Any]:
        self._write(
            delegate,
            _delegate_name(
                delegate["tenantId"], delegate["agentUserId"], delegate["meetingId"]
            ),
        )
        return delegate

    async def save_alias(
        self,
        tenant_id: str,
        agent_user_id: str,
        alias_id: str,
        meeting_id: str,
    ) -> None:
        if not alias_id or alias_id == meeting_id:
            return
        self._write(
            _delegate_alias(meeting_id),
            _delegate_name(tenant_id, agent_user_id, alias_id),
        )

    async def find_by_schedule(
        self,
        tenant_id: str,
        agent_user_id: str,
        scheduled_start_time: str,
        scheduled_end_time: str,
    ) -> Optional[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        directory = self.root / _delegate_prefix(tenant_id, agent_user_id)
        for path in directory.glob("*.json") if directory.exists() else []:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if _matches_schedule(payload, scheduled_start_time, scheduled_end_time):
                matches.append(payload)
        return matches[0] if len(matches) == 1 else None

    def _write(self, payload: dict[str, Any], name: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


async def configure_delegate(
    store: Any,
    *,
    tenant_id: str,
    agent_user_id: str,
    manager: dict[str, str],
    request: dict[str, Any],
) -> dict[str, Any]:
    delegate = build_delegate(
        tenant_id=tenant_id,
        agent_user_id=agent_user_id,
        manager=manager,
        request=request,
    )
    return await store.save(delegate)


def build_delegate(
    *,
    tenant_id: str,
    agent_user_id: str,
    manager: dict[str, str],
    request: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise MeetingDelegateValidationError(
            "Meeting delegate configuration must be a JSON object."
        )
    meeting_id = _required_string(request, "meetingId")
    chat_id = _optional_bounded_string(request.get("chatId") or "", "chatId", 300)
    subject = _bounded_string(request.get("subject") or meeting_id, "subject", 200)
    opening_message = _optional_bounded_string(
        request.get("openingMessage") or "", "openingMessage", MAX_OPENING_MESSAGE_CHARS
    )
    answer_rules = _normalize_answer_rules(request.get("answerRules") or [])
    now = _utc_now()
    return {
        "id": str(request.get("id") or f"meeting-delegate-{uuid4()}"),
        "version": MEETING_DELEGATE_VERSION,
        "tenantId": tenant_id,
        "agentUserId": agent_user_id,
        "managerObjectId": manager.get("id", ""),
        "manager": {
            "displayName": manager.get("displayName", ""),
            "userPrincipalName": manager.get("userPrincipalName", ""),
            "mail": manager.get("mail", ""),
        },
        "meetingId": meeting_id,
        "chatId": chat_id,
        "joinWebUrl": str(request.get("joinWebUrl") or ""),
        "scheduledStartTime": _optional_bounded_string(
            request.get("scheduledStartTime") or "", "scheduledStartTime", 100
        ),
        "scheduledEndTime": _optional_bounded_string(
            request.get("scheduledEndTime") or "", "scheduledEndTime", 100
        ),
        "subject": subject,
        "source": str(request.get("source") or "existing_meeting"),
        "delegationEnabled": bool(request.get("delegationEnabled", True)),
        "openingMessage": {
            "enabled": bool(opening_message),
            "message": opening_message,
            "sent": False,
            "maxSendCount": 1,
        },
        "reactiveRules": {
            "requireAgentMention": True,
            "unmatchedQuestionPolicy": "reply_unknown",
            "answerRules": answer_rules,
        },
        "createdAt": now,
        "updatedAt": now,
        "createdBy": manager.get("id", ""),
        "updatedBy": manager.get("id", ""),
    }


def summarize_delegate(delegate: dict[str, Any]) -> str:
    rules = (((delegate.get("reactiveRules") or {}).get("answerRules")) or [])
    return (
        f"Meeting delegate configured for {delegate.get('subject')}. "
        f"Meeting ID: {delegate.get('meetingId')}. Chat ID: {delegate.get('chatId')}. "
        f"Approved answer rules: {len(rules)}. "
        "Only this Digital Worker's current Manager can change this delegate."
    )


def extract_meeting_id(activity: Any, message: str = "") -> str:
    channel_data = getattr(activity, "channel_data", None)
    meeting = _get_value(channel_data, "meeting")
    candidate = str(_get_value(meeting, "id") or "").strip()
    if candidate:
        return candidate
    for value in _walk_values(channel_data):
        if isinstance(value, dict):
            for key in ("meetingId", "meeting_id"):
                candidate = str(value.get(key) or "").strip()
                if candidate:
                    return candidate
        elif isinstance(value, str) and value.startswith("meeting:"):
            return value.split(":", 1)[1]
    match = re.search(r"meetingId\s*[:=]\s*([\w:.-]+)", message)
    return match.group(1) if match else ""


def describe_meeting_activity(activity: Any, message: str = "") -> dict[str, Any]:
    channel_data = getattr(activity, "channel_data", None)
    conversation = getattr(activity, "conversation", None)
    recipient = getattr(activity, "recipient", None)
    meeting_id = extract_meeting_id(activity, message)
    if isinstance(channel_data, dict):
        channel_data_keys = sorted(str(key) for key in channel_data)
    else:
        channel_data_keys = []
    mention_entities = _mention_entities(activity)
    return {
        "activity": _fingerprint(getattr(activity, "id", "")),
        "channel": str(getattr(activity, "channel_id", "") or "(missing)"),
        "conversation": _fingerprint(_get_value(conversation, "id")),
        "conversationType": str(
            _get_value(conversation, "conversation_type", "conversationType", "type")
            or "(missing)"
        ),
        "channelDataType": type(channel_data).__name__,
        "channelDataKeys": channel_data_keys,
        "meeting": _fingerprint(meeting_id),
        "mentioned": message_mentions_agent(activity, message),
        "mentionEntityCount": len(mention_entities),
        "mentionEntityIds": [
            _fingerprint(_get_value(_get_value(entity, "mentioned"), "id"))
            for entity in mention_entities
        ],
        "recipientIds": [
            _fingerprint(value)
            for value in (
                _get_value(recipient, "id"),
                _get_value(recipient, "agentic_app_id", "agenticAppId"),
                _get_value(recipient, "agentic_user_id", "agenticUserId"),
            )
            if value
        ],
    }


def message_mentions_agent(activity: Any, message: str) -> bool:
    normalized = message.casefold()
    if "@agent" in normalized or "@digital worker" in normalized:
        return True
    recipient = getattr(activity, "recipient", None)
    for value in (
        getattr(recipient, "name", ""),
        getattr(recipient, "id", ""),
        getattr(recipient, "agentic_app_id", ""),
        getattr(recipient, "agentic_user_id", ""),
    ):
        if value and f"@{str(value).casefold()}" in normalized:
            return True
    recipient_ids = {
        str(value).casefold()
        for value in (
            _get_value(recipient, "id"),
            _get_value(recipient, "agentic_app_id", "agenticAppId"),
            _get_value(recipient, "agentic_user_id", "agenticUserId"),
        )
        if value
    }
    for entity in _mention_entities(activity):
        mentioned_id = str(
            _get_value(_get_value(entity, "mentioned"), "id") or ""
        ).casefold()
        if mentioned_id and mentioned_id in recipient_ids:
            return True
    return False


def _mention_entities(activity: Any) -> list[Any]:
    get_mentions = getattr(activity, "get_mentions", None)
    if callable(get_mentions):
        try:
            return list(get_mentions() or [])
        except (AttributeError, TypeError, ValueError):
            pass
    return [
        entity
        for entity in getattr(activity, "entities", None) or []
        if str(_get_value(entity, "type") or "").casefold() == "mention"
    ]


def _normalize_answer_rules(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise MeetingDelegateValidationError("answerRules must be an array.")
    if len(value) > MAX_RULES:
        raise MeetingDelegateValidationError(
            f"At most {MAX_RULES} answer rules are supported."
        )
    rules: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise MeetingDelegateValidationError(
                "Each answer rule must be a JSON object."
            )
        questions = item.get("questions") or []
        if isinstance(questions, str):
            questions = [questions]
        if not isinstance(questions, list) or not questions:
            raise MeetingDelegateValidationError(
                "Each answer rule requires at least one question."
            )
        answer = _bounded_string(item.get("answer"), "answer", MAX_ANSWER_CHARS)
        rules.append(
            {
                "id": str(item.get("id") or f"rule-{index}"),
                "questions": [
                    _bounded_string(question, "question", MAX_QUESTION_CHARS)
                    for question in questions
                ],
                "answer": answer,
                "enabled": bool(item.get("enabled", True)),
            }
        )
    return rules


def _required_string(payload: dict[str, Any], name: str) -> str:
    return _bounded_string(payload.get(name), name, 300)


def _bounded_string(value: Any, name: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise MeetingDelegateValidationError(f"{name} is required.")
    if len(text) > limit:
        raise MeetingDelegateValidationError(
            f"{name} must be {limit} characters or fewer."
        )
    return text


def _optional_bounded_string(value: Any, name: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        raise MeetingDelegateValidationError(
            f"{name} must be {limit} characters or fewer."
        )
    return text


def _matches_schedule(
    payload: Any, scheduled_start_time: str, scheduled_end_time: str
) -> bool:
    if not _is_delegate_payload(payload):
        return False
    expected_start = _normalize_timestamp(scheduled_start_time)
    expected_end = _normalize_timestamp(scheduled_end_time)
    return bool(
        expected_start
        and expected_end
        and _normalize_timestamp(payload.get("scheduledStartTime")) == expected_start
        and _normalize_timestamp(payload.get("scheduledEndTime")) == expected_end
    )


def _normalize_timestamp(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        return ""
    return parsed.astimezone(timezone.utc).isoformat()


def _delegate_name(tenant_id: str, agent_user_id: str, meeting_id: str) -> str:
    return f"{_delegate_prefix(tenant_id, agent_user_id)}{_hash(meeting_id)}.json"


def _delegate_prefix(tenant_id: str, agent_user_id: str) -> str:
    return f"meeting-delegates/{_hash(tenant_id)}/{_hash(agent_user_id)}/"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _fingerprint(value: Any) -> str:
    text = str(value or "").strip()
    return f"sha256:{_hash(text)[:12]}:len={len(text)}" if text else "(missing)"


def _get_value(value: Any, *names: str) -> Any:
    for name in names:
        if isinstance(value, dict) and name in value:
            return value.get(name)
        candidate = getattr(value, name, None)
        if candidate is not None:
            return candidate
    return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_delegate_payload(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("version") == MEETING_DELEGATE_VERSION


def _delegate_alias(meeting_id: str) -> dict[str, str]:
    return {
        "version": MEETING_DELEGATE_VERSION,
        "type": "meeting-delegate-alias",
        "meetingId": meeting_id,
    }


def _is_delegate_alias(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and payload.get("version") == MEETING_DELEGATE_VERSION
        and payload.get("type") == "meeting-delegate-alias"
    )


def _walk_values(value: Any):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_values(item)
    else:
        yield value
