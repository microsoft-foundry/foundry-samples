"""Scoped routine construction and lifecycle operations for chat commands."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from azure.core.exceptions import (
    HttpResponseError,
    ResourceNotFoundError,
    ServiceRequestError,
    ServiceResponseError,
)
from microsoft_agents.hosting.core import TurnContext

from .activity_routing import MESSAGE_DELIVERY_EVENT_NAME

ROUTINE_OPERATION_TIMEOUT_SECONDS = 30
EXPECTED_RECIPIENT_ROLE = "agenticUser"
MESSAGE_SCHEDULE_NAME_PREFIX = "message-schedule-v2"
MESSAGE_SCHEDULE_OWNER_PREFIX = "routines-autopilot:message:v2"
DELIVERY_TRIGGER_NAME = "delivery"
TIMER_TIME_ZONE = "UTC"
MESSAGE_DELIVERY_VERSION = 1
_COMMON_READ_ONLY_METADATA_KEYS = frozenset(
    {
        "id",
        "etag",
        "created_at",
        "updated_at",
        "provisioning_state",
        "system_data",
        "createdAt",
        "updatedAt",
        "provisioningState",
        "systemData",
    }
)
_TRIGGER_READ_ONLY_METADATA_KEYS = _COMMON_READ_ONLY_METADATA_KEYS | {"name"}
_ACTION_READ_ONLY_METADATA_KEYS = _COMMON_READ_ONLY_METADATA_KEYS


class ContextValidationError(ValueError):
    """The authenticated activity lacks required personal-chat routing."""


class StartOutcome(str, Enum):
    CREATED = "created"
    CREATED_AFTER_RECONCILIATION = "created_after_reconciliation"
    ALREADY_ENABLED = "already_enabled"
    REENABLED = "reenabled"
    DIFFERENT_ACTIVE = "different_active"
    CONFLICT = "conflict"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


class StopOutcome(str, Enum):
    STOPPED = "stopped"
    STOPPED_AFTER_RECONCILIATION = "stopped_after_reconciliation"
    ALREADY_STOPPED = "already_stopped"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    CONFLICT = "conflict"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class RoutineSchedule:
    cron_expression: str | None = None
    time_zone: str | None = None
    at: datetime | None = None


@dataclass(frozen=True)
class RoutineSpec:
    name: str
    owner: str
    body: dict[str, object]
    scope_hash: str
    schedule: RoutineSchedule
    message_text: str


@dataclass(frozen=True)
class RoutineScope:
    scope_hash: str
    agent_name: str
    blueprint_id: str
    tenant_id: str
    conversation_id: str
    agentic_user_id: str
    agentic_app_id: str
    routing_activity: Mapping[str, object]


@dataclass(frozen=True)
class OwnedRoutineState:
    active: tuple[RoutineSpec, ...]
    conflict: bool = False
    failed: bool = False
    matching_disabled: RoutineSpec | None = None


def build_routine_scope(
    context: TurnContext,
    *,
    agent_name: str,
    blueprint_id: str,
    expected_tenant_id: str,
) -> RoutineScope:
    """Validate authenticated personal-chat scope and capture action routing."""
    activity = context.activity
    sender = activity.from_property
    recipient = activity.recipient
    conversation = activity.conversation
    channel_id = _channel(activity)
    service_url = _value(activity, "service_url")

    required = {
        "channelId": channel_id,
        "serviceUrl": service_url,
        "sender.id": _value(sender, "id"),
        "sender.aadObjectId": _value(sender, "aad_object_id"),
        "recipient.id": _value(recipient, "id"),
        "recipient.role": _value(recipient, "role"),
        "recipient.agenticAppId": _value(recipient, "agentic_app_id"),
        "recipient.agenticUserId": _value(recipient, "agentic_user_id"),
        "recipient.tenantId": _value(recipient, "tenant_id"),
        "conversation.id": _value(conversation, "id"),
        "conversation.type": _value(conversation, "conversation_type"),
        "conversation.tenantId": _value(conversation, "tenant_id"),
        "blueprintId": blueprint_id,
        "agentName": agent_name,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ContextValidationError(
            "Missing required authenticated activity context: " + ", ".join(missing)
        )
    if channel_id != "msteams":
        raise ContextValidationError("Routine commands are supported only in Teams.")
    if required["conversation.type"] != "personal":
        raise ContextValidationError(
            "Routine commands are supported only in a personal Teams chat."
        )
    if required["recipient.role"] != EXPECTED_RECIPIENT_ROLE:
        raise ContextValidationError(
            "The current activity does not identify an agentic-user recipient."
        )

    tenant_values = {
        str(expected_tenant_id).casefold(),
        str(required["recipient.tenantId"]).casefold(),
        str(required["conversation.tenantId"]).casefold(),
    }
    if len(tenant_values) != 1:
        raise ContextValidationError(
            "The activity tenant does not match the hosted agent tenant."
        )

    scope_values = (
        expected_tenant_id,
        str(required["recipient.agenticAppId"]),
        str(required["recipient.agenticUserId"]),
        str(required["sender.aadObjectId"]),
        str(required["conversation.id"]),
    )
    scope_hash = hashlib.sha256(
        "\x1f".join(value.casefold() for value in scope_values).encode()
    ).hexdigest()
    return RoutineScope(
        scope_hash=scope_hash,
        agent_name=agent_name,
        blueprint_id=blueprint_id,
        tenant_id=expected_tenant_id,
        conversation_id=str(required["conversation.id"]),
        agentic_user_id=str(required["recipient.agenticUserId"]),
        agentic_app_id=str(required["recipient.agenticAppId"]),
        routing_activity=_routing_activity(activity),
    )


def canonical_time_zone(time_zone: str | None) -> str | None:
    return "UTC" if time_zone == "Etc/UTC" else time_zone


def same_routine_request(left: RoutineSpec, right: RoutineSpec) -> bool:
    """Compare intent after stored records pass full ownership validation."""
    return (
        left.scope_hash == right.scope_hash
        and left.message_text == right.message_text
        and left.schedule.at == right.schedule.at
        and left.schedule.cron_expression == right.schedule.cron_expression
        and canonical_time_zone(left.schedule.time_zone) == canonical_time_zone(right.schedule.time_zone)
    )


def build_scheduled_routine_spec(
    scope: RoutineScope,
    *,
    cron_expression: str,
    time_zone: str,
    message_text: str,
) -> RoutineSpec:
    return _build_routine_spec(
        scope,
        schedule=RoutineSchedule(cron_expression, canonical_time_zone(time_zone)),
        message_text=message_text,
    )


def build_timer_routine_spec(
    scope: RoutineScope,
    *,
    at: datetime,
    message_text: str,
) -> RoutineSpec:
    if at.utcoffset() != timedelta(0):
        raise ValueError("Timer instant must be aware UTC.")
    # Timer readback uses whole-second Unix timestamps; hash the stored precision.
    return _build_routine_spec(
        scope,
        schedule=RoutineSchedule(
            time_zone=TIMER_TIME_ZONE,
            at=at.replace(microsecond=0),
        ),
        message_text=message_text,
    )


def _build_routine_spec(
    scope: RoutineScope,
    *,
    schedule: RoutineSchedule,
    message_text: str,
) -> RoutineSpec:
    _validate_message_text(message_text)
    schedule_hash = _schedule_hash(schedule)
    payload_hash = _payload_hash(message_text)
    identity_hash = _message_identity_hash(schedule_hash, payload_hash)
    routine_name = (
        f"{MESSAGE_SCHEDULE_NAME_PREFIX}-{scope.scope_hash[:20]}-"
        f"{identity_hash[:16]}"
    )
    owner = (
        f"{MESSAGE_SCHEDULE_OWNER_PREFIX}:{scope.scope_hash}:"
        f"{schedule_hash}:{payload_hash}"
    )
    input_activity = {
        **scope.routing_activity,
        "type": "event",
        "name": MESSAGE_DELIVERY_EVENT_NAME,
        "value": _delivery_value(
            message_text=message_text,
            scope_hash=scope.scope_hash,
            schedule_hash=schedule_hash,
            routine_name=routine_name,
        ),
    }
    action = {
        "type": "invoke_agent_activityprotocol_api",
        "agent_name": scope.agent_name,
        "input": input_activity,
        "conversation_id": scope.conversation_id,
        "agentic_user_id": scope.agentic_user_id,
        "agentic_app_id": scope.agentic_app_id,
        "agentic_app_blueprint_id": scope.blueprint_id,
        "tenant_id": scope.tenant_id,
    }
    trigger = (
        {
            "type": "timer",
            "at": schedule.at.astimezone(timezone.utc),
            "time_zone": schedule.time_zone,
        }
        if schedule.at is not None
        else {
            "type": "schedule",
            "cron_expression": schedule.cron_expression,
            "time_zone": schedule.time_zone,
        }
    )
    body = {
        "description": owner,
        "enabled": True,
        "triggers": {DELIVERY_TRIGGER_NAME: trigger},
        "action": action,
    }
    return RoutineSpec(
        name=routine_name,
        owner=owner,
        body=body,
        scope_hash=scope.scope_hash,
        schedule=schedule,
        message_text=message_text,
    )


async def ensure_started(
    routines: object,
    spec: RoutineSpec,
    *,
    logger: logging.Logger,
    allow_create: bool = True,
) -> StartOutcome:
    """Create, verify, or safely re-enable the exact scoped routine."""
    try:
        existing = await _get(routines, spec.name)
    except (HttpResponseError, ServiceRequestError, ServiceResponseError, TimeoutError) as error:
        logger.error("Routine start lookup failed (%s, HTTP %s).", type(error).__name__, getattr(error, "status_code", None))
        return StartOutcome.FAILED

    if existing is not None:
        if not routine_matches(existing, spec):
            return StartOutcome.CONFLICT
        enabled = _value(existing, "enabled")
        if enabled is True:
            return StartOutcome.ALREADY_ENABLED
        if enabled is not False:
            return StartOutcome.CONFLICT
        return await _reenable(routines, spec, logger=logger)

    if not allow_create:
        return StartOutcome.CONFLICT

    create_error: BaseException | None = None
    try:
        await asyncio.wait_for(
            routines.create_or_update(spec.name, spec.body, retry_total=0),
            timeout=ROUTINE_OPERATION_TIMEOUT_SECONDS,
        )
    except (HttpResponseError, ServiceRequestError, ServiceResponseError, TimeoutError) as error:
        create_error = error
        logger.error("Routine creation failed (%s, HTTP %s).", type(error).__name__, getattr(error, "status_code", None))

    try:
        readback = await _get(routines, spec.name)
    except (HttpResponseError, ServiceRequestError, ServiceResponseError, TimeoutError) as error:
        logger.error("Routine creation readback failed (%s, HTTP %s).", type(error).__name__, getattr(error, "status_code", None))
        return StartOutcome.UNCERTAIN

    if readback is None:
        outcome = (
            StartOutcome.FAILED
            if isinstance(create_error, HttpResponseError)
            and _is_definitive_rejection(create_error)
            else StartOutcome.UNCERTAIN
        )
        return outcome
    if not routine_matches(readback, spec):
        return StartOutcome.CONFLICT
    enabled = _value(readback, "enabled")
    if enabled is not True:
        return StartOutcome.UNCERTAIN
    outcome = (
        StartOutcome.CREATED
        if create_error is None
        else StartOutcome.CREATED_AFTER_RECONCILIATION
    )
    return outcome


async def ensure_only_started(
    routines: object,
    spec: RoutineSpec,
    *,
    scope: RoutineScope,
    logger: logging.Logger,
) -> StartOutcome:
    if scope.scope_hash != spec.scope_hash:
        return StartOutcome.CONFLICT
    state = await list_owned_routines(routines, scope, logger=logger, requested_spec=spec)
    if state.failed:
        return StartOutcome.FAILED
    if state.conflict or len(state.active) > 1:
        return StartOutcome.CONFLICT
    if state.active and not same_routine_request(state.active[0], spec):
        return StartOutcome.DIFFERENT_ACTIVE
    existing = state.active[0] if state.active else state.matching_disabled
    if existing is not None:
        if not same_routine_request(existing, spec):
            return StartOutcome.CONFLICT
        # Keep the validated record's raw hashes and prevent recreation if it disappears.
        return await ensure_started(routines, existing, logger=logger, allow_create=False)
    return await ensure_started(routines, spec, logger=logger)


async def ensure_stopped(
    routines: object,
    spec: RoutineSpec,
    *,
    logger: logging.Logger,
) -> StopOutcome:
    """Disable the exact scoped routine without mutating any mismatch."""
    try:
        existing = await _get(routines, spec.name)
    except (HttpResponseError, ServiceRequestError, ServiceResponseError, TimeoutError) as error:
        logger.error("Routine stop lookup failed (%s, HTTP %s).", type(error).__name__, getattr(error, "status_code", None))
        return StopOutcome.FAILED

    if existing is None:
        return StopOutcome.NOT_FOUND
    if not routine_matches(existing, spec):
        return StopOutcome.CONFLICT
    enabled = _value(existing, "enabled")
    if enabled is False:
        return StopOutcome.ALREADY_STOPPED
    if enabled is not True:
        return StopOutcome.CONFLICT
    return await _disable(routines, spec, logger=logger)


async def ensure_scope_stopped(
    routines: object,
    scope: RoutineScope,
    *,
    logger: logging.Logger,
) -> StopOutcome:
    state = await list_owned_routines(routines, scope, logger=logger)
    if state.failed:
        return StopOutcome.FAILED
    if state.conflict:
        return StopOutcome.CONFLICT
    if len(state.active) > 1:
        return StopOutcome.AMBIGUOUS
    if not state.active:
        return StopOutcome.NOT_FOUND
    return await ensure_stopped(routines, state.active[0], logger=logger)


async def list_owned_routines(
    routines: object,
    scope: RoutineScope,
    *,
    logger: logging.Logger,
    now: datetime | None = None,
    requested_spec: RoutineSpec | None = None,
) -> OwnedRoutineState:
    active: list[RoutineSpec] = []
    matching_disabled: RoutineSpec | None = None
    conflict = False
    observed_at = now or datetime.now(timezone.utc)
    message_prefix = (
        f"{MESSAGE_SCHEDULE_NAME_PREFIX}-{scope.scope_hash[:20]}-"
    )
    try:
        async with asyncio.timeout(ROUTINE_OPERATION_TIMEOUT_SECONDS):
            async for routine in routines.list():
                name = _value(routine, "name")
                if isinstance(name, str) and name.startswith(message_prefix):
                    candidate = _scheduled_spec_from_routine(routine, scope)
                    if candidate is None:
                        conflict = True
                        continue
                else:
                    continue
                if not routine_matches(routine, candidate):
                    conflict = True
                    continue
                enabled = _value(routine, "enabled")
                if enabled is not True and enabled is not False:
                    conflict = True
                elif enabled is False and requested_spec is not None and same_routine_request(candidate, requested_spec):
                    if matching_disabled is None or (
                        candidate.schedule.time_zone != "UTC", candidate.name
                    ) < (
                        matching_disabled.schedule.time_zone != "UTC", matching_disabled.name
                    ):
                        matching_disabled = candidate
                elif enabled is True and (
                    candidate.schedule.at is None or candidate.schedule.at > observed_at
                ):
                    active.append(candidate)
    except (HttpResponseError, ServiceRequestError, ServiceResponseError, TimeoutError) as error:
        logger.error("Routine scope lookup failed (%s, HTTP %s).", type(error).__name__, getattr(error, "status_code", None))
        return OwnedRoutineState((), failed=True)
    return OwnedRoutineState(
        tuple(active),
        conflict=conflict,
        matching_disabled=matching_disabled,
    )


def routine_matches(routine: object, spec: RoutineSpec) -> bool:
    """Return whether an existing routine is exactly the owned expected routine."""
    actual = _plain(routine)
    expected = spec.body
    triggers = _value(actual, "triggers")
    if not isinstance(triggers, Mapping) or set(triggers) != {DELIVERY_TRIGGER_NAME}:
        return False
    trigger = triggers[DELIVERY_TRIGGER_NAME]
    expected_trigger = expected["triggers"][DELIVERY_TRIGGER_NAME]
    return (
        _value(actual, "name") == spec.name
        and _value(actual, "description") == spec.owner
        and _matches_owned_mapping(
            trigger,
            expected_trigger,
            allowed_extra_keys=_TRIGGER_READ_ONLY_METADATA_KEYS,
        )
        and _matches_owned_mapping(
            _action_for_comparison(_value(actual, "action")),
            _action_for_comparison(expected["action"]),
            allowed_extra_keys=_ACTION_READ_ONLY_METADATA_KEYS,
        )
    )


def _action_for_comparison(action: object) -> object:
    """Exclude only Activity display labels, without changing stored routing."""
    value = _plain(action)
    if not isinstance(value, Mapping):
        return value
    activity = value.get("input")
    if not isinstance(activity, Mapping):
        return value
    comparable = dict(activity)
    for key in ("from", "recipient", "conversation"):
        identity = comparable.get(key)
        if isinstance(identity, Mapping):
            comparable[key] = {field: item for field, item in identity.items() if field != "name"}
    return {**value, "input": comparable}


def _scheduled_spec_from_routine(
    routine: object,
    scope: RoutineScope,
) -> RoutineSpec | None:
    triggers = _value(_plain(routine), "triggers")
    if not isinstance(triggers, Mapping) or len(triggers) != 1:
        return None
    trigger_name, trigger = next(iter(triggers.items()))
    if trigger_name != DELIVERY_TRIGGER_NAME:
        return None
    trigger_type = _value(trigger, "type")
    if trigger_type == "schedule":
        cron_expression = _value(trigger, "cron_expression")
        time_zone = _value(trigger, "time_zone")
        if not isinstance(cron_expression, str) or not isinstance(time_zone, str):
            return None
        schedule = RoutineSchedule(cron_expression, time_zone)
    elif trigger_type == "timer":
        at = _as_datetime(_value(trigger, "at"))
        time_zone = _value(trigger, "time_zone")
        if at is None or time_zone != TIMER_TIME_ZONE:
            return None
        schedule = RoutineSchedule(time_zone=time_zone, at=at)
    else:
        return None
    message_text = _message_from_delivery_action(routine, scope, schedule)
    if message_text is None:
        return None
    return _build_routine_spec(scope, schedule=schedule, message_text=message_text)


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return None
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    return None


async def _reenable(
    routines: object,
    spec: RoutineSpec,
    *,
    logger: logging.Logger,
) -> StartOutcome:
    enable_error: BaseException | None = None
    try:
        await asyncio.wait_for(
            routines.enable(spec.name, retry_total=0),
            timeout=ROUTINE_OPERATION_TIMEOUT_SECONDS,
        )
    except (HttpResponseError, ServiceRequestError, ServiceResponseError, TimeoutError) as error:
        enable_error = error
        logger.error("Routine enable failed (%s, HTTP %s).", type(error).__name__, getattr(error, "status_code", None))

    try:
        readback = await _get(routines, spec.name)
    except (HttpResponseError, ServiceRequestError, ServiceResponseError, TimeoutError) as error:
        logger.error("Routine enable readback failed (%s, HTTP %s).", type(error).__name__, getattr(error, "status_code", None))
        return StartOutcome.UNCERTAIN

    if readback is None:
        return StartOutcome.UNCERTAIN
    if not routine_matches(readback, spec):
        return StartOutcome.CONFLICT
    enabled = _value(readback, "enabled")
    if enabled is True:
        return StartOutcome.REENABLED
    if enabled is not False:
        return StartOutcome.CONFLICT
    outcome = (
        StartOutcome.FAILED
        if isinstance(enable_error, HttpResponseError)
        and _is_definitive_rejection(enable_error)
        else StartOutcome.UNCERTAIN
    )
    return outcome


async def _disable(
    routines: object,
    spec: RoutineSpec,
    *,
    logger: logging.Logger,
) -> StopOutcome:
    disable_error: BaseException | None = None
    try:
        await asyncio.wait_for(
            routines.disable(spec.name, retry_total=0),
            timeout=ROUTINE_OPERATION_TIMEOUT_SECONDS,
        )
    except (HttpResponseError, ServiceRequestError, ServiceResponseError, TimeoutError) as error:
        disable_error = error
        logger.error("Routine disable failed (%s, HTTP %s).", type(error).__name__, getattr(error, "status_code", None))

    try:
        readback = await _get(routines, spec.name)
    except (HttpResponseError, ServiceRequestError, ServiceResponseError, TimeoutError) as error:
        logger.error("Routine disable readback failed (%s, HTTP %s).", type(error).__name__, getattr(error, "status_code", None))
        return StopOutcome.UNCERTAIN

    if readback is None:
        return StopOutcome.STOPPED_AFTER_RECONCILIATION
    if not routine_matches(readback, spec):
        return StopOutcome.CONFLICT
    enabled = _value(readback, "enabled")
    if enabled is False:
        outcome = (
            StopOutcome.STOPPED
            if disable_error is None
            else StopOutcome.STOPPED_AFTER_RECONCILIATION
        )
        return outcome
    if enabled is not True:
        return StopOutcome.CONFLICT
    outcome = (
        StopOutcome.FAILED
        if isinstance(disable_error, HttpResponseError)
        and _is_definitive_rejection(disable_error)
        else StopOutcome.UNCERTAIN
    )
    return outcome


async def _get(routines: object, routine_name: str) -> object | None:
    try:
        return await asyncio.wait_for(
            routines.get(routine_name),
            timeout=ROUTINE_OPERATION_TIMEOUT_SECONDS,
        )
    except ResourceNotFoundError:
        return None


def _routing_activity(activity: object) -> dict[str, object]:
    sender = _value(activity, "from_property")
    recipient = _value(activity, "recipient")
    conversation = _value(activity, "conversation")
    sender_value: dict[str, object] = {"id": _value(sender, "id")}
    if _value(sender, "name"):
        sender_value["name"] = _value(sender, "name")
    sender_value["aadObjectId"] = _value(sender, "aad_object_id")

    recipient_value: dict[str, object] = {
        "id": _value(recipient, "id"),
        "role": _value(recipient, "role"),
        "agenticAppId": _value(recipient, "agentic_app_id"),
        "agenticUserId": _value(recipient, "agentic_user_id"),
        "tenantId": _value(recipient, "tenant_id"),
    }
    if _value(recipient, "name"):
        recipient_value["name"] = _value(recipient, "name")

    conversation_value: dict[str, object] = {
        "id": _value(conversation, "id"),
        "conversationType": _value(conversation, "conversation_type"),
        "tenantId": _value(conversation, "tenant_id"),
    }
    if _value(conversation, "name"):
        conversation_value["name"] = _value(conversation, "name")

    return {
        "channelId": _channel(activity),
        "serviceUrl": _value(activity, "service_url"),
        "from": sender_value,
        "recipient": recipient_value,
        "conversation": conversation_value,
    }


def delivery_event_text(
    context: TurnContext,
    *,
    agent_name: str,
    blueprint_id: str,
    expected_tenant_id: str,
) -> str:
    activity = context.activity
    if (
        _value(activity, "type") != "event"
        or _channel(activity) != "msteams"
        or _value(activity, "name") != MESSAGE_DELIVERY_EVENT_NAME
        or not activity.is_agentic_request()
    ):
        raise ContextValidationError("The activity is not a routine delivery event.")
    scope = build_routine_scope(
        context,
        agent_name=agent_name,
        blueprint_id=blueprint_id,
        expected_tenant_id=expected_tenant_id,
    )
    value = _plain(_value(activity, "value"))
    expected_keys = {
        "version",
        "text",
        "scopeHash",
        "scheduleHash",
        "payloadHash",
        "routineName",
    }
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise ContextValidationError("The routine delivery value is malformed.")
    message_text = value["text"]
    schedule_hash = value["scheduleHash"]
    payload_hash = value["payloadHash"]
    routine_name = value["routineName"]
    if (
        value["version"] != MESSAGE_DELIVERY_VERSION
        or not isinstance(message_text, str)
        or not isinstance(schedule_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", schedule_hash)
        or not isinstance(payload_hash, str)
        or payload_hash != _payload_hash(message_text)
        or value["scopeHash"] != scope.scope_hash
        or not isinstance(routine_name, str)
    ):
        raise ContextValidationError("The routine delivery value failed validation.")
    _validate_message_text(message_text)
    identity_hash = _message_identity_hash(schedule_hash, payload_hash)
    expected_name = (
        f"{MESSAGE_SCHEDULE_NAME_PREFIX}-{scope.scope_hash[:20]}-"
        f"{identity_hash[:16]}"
    )
    if routine_name != expected_name:
        raise ContextValidationError("The routine delivery name is not owned.")
    return message_text


def _delivery_value(
    *,
    message_text: str,
    scope_hash: str,
    schedule_hash: str,
    routine_name: str,
) -> dict[str, object]:
    return {
        "version": MESSAGE_DELIVERY_VERSION,
        "text": message_text,
        "scopeHash": scope_hash,
        "scheduleHash": schedule_hash,
        "payloadHash": _payload_hash(message_text),
        "routineName": routine_name,
    }


def _message_from_delivery_action(
    routine: object,
    scope: RoutineScope,
    schedule: RoutineSchedule,
) -> str | None:
    action = _plain(_value(_plain(routine), "action"))
    if not isinstance(action, Mapping):
        return None
    input_activity = _plain(action.get("input"))
    if not isinstance(input_activity, Mapping):
        return None
    value = _plain(input_activity.get("value"))
    if (
        input_activity.get("type") != "event"
        or input_activity.get("name") != MESSAGE_DELIVERY_EVENT_NAME
        or not isinstance(value, Mapping)
    ):
        return None
    message_text = value.get("text")
    if not isinstance(message_text, str):
        return None
    try:
        _validate_message_text(message_text)
    except ValueError:
        return None
    schedule_hash = _schedule_hash(schedule)
    payload_hash = _payload_hash(message_text)
    identity_hash = _message_identity_hash(schedule_hash, payload_hash)
    expected_name = (
        f"{MESSAGE_SCHEDULE_NAME_PREFIX}-{scope.scope_hash[:20]}-"
        f"{identity_hash[:16]}"
    )
    if value != _delivery_value(
        message_text=message_text,
        scope_hash=scope.scope_hash,
        schedule_hash=schedule_hash,
        routine_name=expected_name,
    ):
        return None
    return message_text


def _schedule_hash(schedule: RoutineSchedule) -> str:
    schedule_key = (
        f"timer\x1f{schedule.at.astimezone(timezone.utc).isoformat()}"
        if schedule.at is not None
        else f"{schedule.cron_expression}\x1f{schedule.time_zone}"
    )
    return hashlib.sha256(schedule_key.encode()).hexdigest()


def _payload_hash(message_text: str) -> str:
    return hashlib.sha256(message_text.encode("utf-8")).hexdigest()


def _message_identity_hash(schedule_hash: str, payload_hash: str) -> str:
    return hashlib.sha256(
        json.dumps(
            {"payloadHash": payload_hash, "scheduleHash": schedule_hash},
            ensure_ascii=True, separators=(",", ":"), sort_keys=True,
        ).encode()
    ).hexdigest()


def _validate_message_text(message_text: str) -> None:
    if not message_text.strip():
        raise ValueError("The scheduled message is invalid.")


def _channel(activity: object) -> str | None:
    channel_id = _value(activity, "channel_id")
    channel = _value(channel_id, "channel")
    if isinstance(channel, str) and channel:
        return channel
    return channel_id if isinstance(channel_id, str) and channel_id else None


def _matches_owned_mapping(
    actual: object,
    expected: object,
    *,
    allowed_extra_keys: frozenset[str],
) -> bool:
    actual_value = _plain(actual)
    expected_value = _plain(expected)
    if not isinstance(actual_value, Mapping) or not isinstance(expected_value, Mapping):
        return False
    actual_keys = set(actual_value)
    expected_keys = set(expected_value)
    if not expected_keys.issubset(actual_keys):
        return False
    if not (actual_keys - expected_keys).issubset(allowed_extra_keys):
        return False
    return all(
        _matches_exact(actual_value[key], expected_item)
        for key, expected_item in expected_value.items()
    )


def _matches_exact(actual: object, expected: object) -> bool:
    actual_value = _plain(actual)
    expected_value = _plain(expected)
    if isinstance(expected_value, datetime):
        return _as_datetime(actual_value) == expected_value.astimezone(timezone.utc)
    if isinstance(expected_value, Mapping):
        return (
            isinstance(actual_value, Mapping)
            and set(actual_value) == set(expected_value)
            and all(
                _matches_exact(actual_value[key], expected_item)
                for key, expected_item in expected_value.items()
            )
        )
    if isinstance(expected_value, list):
        return (
            isinstance(actual_value, list)
            and len(actual_value) == len(expected_value)
            and all(
                _matches_exact(actual_item, expected_item)
                for actual_item, expected_item in zip(actual_value, expected_value)
            )
        )
    return actual_value == expected_value


def _plain(value: object) -> object:
    if hasattr(value, "as_dict"):
        return _plain(value.as_dict())
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _value(item: object, key: str) -> object:
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)


def _is_definitive_rejection(error: HttpResponseError) -> bool:
    status = error.status_code
    return status is not None and 400 <= status < 500 and status not in {408, 429}
