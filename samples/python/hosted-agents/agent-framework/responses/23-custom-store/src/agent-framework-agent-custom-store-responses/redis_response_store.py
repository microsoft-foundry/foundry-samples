# Copyright (c) Microsoft. All rights reserved.

"""Persist Responses protocol conversation history in Redis."""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Iterable, cast

from azure.ai.agentserver.responses import (
    PlatformContext,
    ResponseObject,
    ResponseProviderProtocol,
)
from azure.ai.agentserver.responses.models import OutputItem, get_conversation_id
from azure.ai.agentserver.responses.store import ResponseAlreadyExistsError

from redis_database import RedisDatabase, get_local_user_id, partition_for

DEFAULT_RESPONSE_TTL_SECONDS = 86_400


def _get_positive_int(name: str, default: int) -> int:
    """Read a positive integer environment setting."""
    configured_value = os.getenv(name, str(default))
    try:
        value = int(configured_value)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer.") from error
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _serialize(value: Any) -> str:
    """Serialize a Responses model or mapping to compact JSON."""
    if hasattr(value, "as_dict") and callable(value.as_dict):
        value = value.as_dict()
    return json.dumps(value, separators=(",", ":"), default=str)


def _deserialize_mapping(value: str, *, kind: str) -> dict[str, Any]:
    """Deserialize one stored value and reject corrupt non-object payloads."""
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise RuntimeError(f"Stored {kind} is not a JSON object.")
    return decoded


def _item_id(item: Any) -> str | None:
    """Extract an item identifier from a mapping or model."""
    value = item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
    return str(value) if value is not None else None


def _collect_items(items: Iterable[OutputItem]) -> list[tuple[str, str]]:
    """Serialize identified items while preserving input order."""
    item_values: list[tuple[str, str]] = []
    for item in items:
        identifier = _item_id(item)
        if identifier is not None:
            item_values.append((identifier, _serialize(item)))
    return item_values


class RedisResponseStore(ResponseProviderProtocol):
    """Store response envelopes, items, and history indexes in Redis.

    Every response envelope is a Redis hash whose retention is enforced by a
    native key TTL, so expired responses disappear without a sweep. Transcript
    items are individual TTL keys, and a per-conversation sorted set indexes the
    responses in creation order for continuation lookups.
    """

    def __init__(
        self,
        *,
        database: RedisDatabase,
        ttl_seconds: int,
        local_user_id: str,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be a positive integer.")
        if not local_user_id:
            raise ValueError("local_user_id must not be empty.")
        self._database = database
        self._ttl_seconds = ttl_seconds
        self._local_user_id = local_user_id

    def _partition(self, context: PlatformContext | None) -> str:
        """Return a non-identifying tenant partition for stored keys."""
        user_id = context.user_id_key if context is not None else None
        return partition_for(user_id, self._local_user_id)

    def _response_key(self, partition: str, response_id: str) -> str:
        return self._database.partition_key("resp", partition, response_id)

    def _item_key(self, partition: str, item_id: str) -> str:
        return self._database.partition_key("item", partition, item_id)

    def _conversation_key(self, partition: str, conversation_id: str) -> str:
        return self._database.partition_key("conv", partition, conversation_id)

    async def create_response(
        self,
        response: ResponseObject,
        input_items: Iterable[OutputItem] | None,
        history_item_ids: Iterable[str] | None,
        *,
        context: PlatformContext | None = None,
    ) -> None:
        """Persist a response and its input, output, and history references."""
        partition = self._partition(context)
        response_id = str(response.get("id"))
        history_ids = list(history_item_ids or [])
        input_values = _collect_items(input_items or [])
        output_values = _collect_items(response.get("output") or [])
        item_values = [*input_values, *output_values]
        conversation_id = get_conversation_id(response)

        client = await self._database.connect()
        response_key = self._response_key(partition, response_id)
        async with self._database.write_lock:
            existing = await client.hgetall(response_key)
            if existing and existing.get("deleted") != "1":
                raise ResponseAlreadyExistsError(response_id)

            sequence = await client.incr(self._database.key("seq")) if conversation_id else 0
            mapping = {
                "generation": uuid.uuid4().hex,
                "response": _serialize(response),
                "input_item_ids": json.dumps([identifier for identifier, _ in input_values]),
                "output_item_ids": json.dumps([identifier for identifier, _ in output_values]),
                "history_item_ids": json.dumps(history_ids),
                "conversation_id": conversation_id or "",
                "deleted": "0",
            }
            pipe = client.pipeline(transaction=True)
            # Drop any tombstone fields before rewriting the envelope.
            pipe.delete(response_key)
            pipe.hset(response_key, mapping=mapping)
            pipe.expire(response_key, self._ttl_seconds)
            self._write_items(pipe, partition, item_values)
            self._refresh_items(pipe, partition, history_ids)
            if conversation_id:
                conversation_key = self._conversation_key(partition, conversation_id)
                # NX preserves the original ordering score across re-creation.
                pipe.zadd(conversation_key, {response_id: sequence}, nx=True)
                pipe.expire(conversation_key, self._ttl_seconds)
            await pipe.execute()

    async def get_response(
        self,
        response_id: str,
        *,
        context: PlatformContext | None = None,
    ) -> ResponseObject:
        """Load a response envelope by identifier."""
        partition = self._partition(context)
        client = await self._database.connect()
        envelope = await client.hgetall(self._response_key(partition, response_id))
        if not envelope or envelope.get("deleted") == "1":
            raise KeyError(f"response '{response_id}' not found")
        response = json.loads(envelope["response"])
        if not isinstance(response, dict):
            raise RuntimeError(f"Stored response '{response_id}' is corrupt.")
        return cast(ResponseObject, response)

    async def update_response(
        self,
        response: ResponseObject,
        *,
        context: PlatformContext | None = None,
    ) -> None:
        """Replace a response envelope and its output-item index."""
        partition = self._partition(context)
        response_id = str(response.get("id"))
        output_values = _collect_items(response.get("output") or [])
        conversation_id = get_conversation_id(response)

        client = await self._database.connect()
        response_key = self._response_key(partition, response_id)
        async with self._database.write_lock:
            envelope = await client.hgetall(response_key)
            if not envelope or envelope.get("deleted") == "1":
                raise KeyError(f"response '{response_id}' not found")

            retained_item_ids = [
                *json.loads(envelope["history_item_ids"]),
                *json.loads(envelope["input_item_ids"]),
            ]
            sequence = await client.incr(self._database.key("seq")) if conversation_id else 0
            pipe = client.pipeline(transaction=True)
            pipe.hset(
                response_key,
                mapping={
                    "response": _serialize(response),
                    "output_item_ids": json.dumps([identifier for identifier, _ in output_values]),
                    "conversation_id": conversation_id or "",
                },
            )
            pipe.expire(response_key, self._ttl_seconds)
            self._write_items(pipe, partition, output_values)
            self._refresh_items(pipe, partition, retained_item_ids)
            if conversation_id:
                conversation_key = self._conversation_key(partition, conversation_id)
                pipe.zadd(conversation_key, {response_id: sequence}, nx=True)
                pipe.expire(conversation_key, self._ttl_seconds)
            await pipe.execute()

    async def delete_response(
        self,
        response_id: str,
        *,
        context: PlatformContext | None = None,
    ) -> None:
        """Soft-delete a response while retaining a temporary tombstone."""
        partition = self._partition(context)
        client = await self._database.connect()
        response_key = self._response_key(partition, response_id)
        async with self._database.write_lock:
            envelope = await client.hgetall(response_key)
            if not envelope or envelope.get("deleted") == "1":
                raise KeyError(f"response '{response_id}' not found")
            pipe = client.pipeline(transaction=True)
            pipe.hset(response_key, "deleted", "1")
            pipe.expire(response_key, self._ttl_seconds)
            await pipe.execute()

    async def get_input_items(
        self,
        response_id: str,
        limit: int = 20,
        ascending: bool = False,
        after: str | None = None,
        before: str | None = None,
        *,
        context: PlatformContext | None = None,
    ) -> list[OutputItem]:
        """Load paginated history and input items for one response."""
        partition = self._partition(context)
        client = await self._database.connect()
        envelope = await client.hgetall(self._response_key(partition, response_id))
        if not envelope:
            raise KeyError(f"response '{response_id}' not found")
        if envelope.get("deleted") == "1":
            raise ValueError(f"response '{response_id}' has been deleted")

        item_ids = [*json.loads(envelope["history_item_ids"]), *json.loads(envelope["input_item_ids"])]
        ordered_ids = item_ids if ascending else list(reversed(item_ids))
        if after is not None and after in ordered_ids:
            ordered_ids = ordered_ids[ordered_ids.index(after) + 1 :]
        if before is not None and before in ordered_ids:
            ordered_ids = ordered_ids[: ordered_ids.index(before)]
        safe_limit = max(1, min(100, int(limit)))
        items = await self.get_items(ordered_ids[:safe_limit], context=context)
        return [item for item in items if item is not None]

    async def get_items(
        self,
        item_ids: Iterable[str],
        *,
        context: PlatformContext | None = None,
    ) -> list[OutputItem | None]:
        """Load items by identifier while preserving order and misses."""
        identifiers = list(item_ids)
        if not identifiers:
            return []
        partition = self._partition(context)
        client = await self._database.connect()
        values = await client.mget([self._item_key(partition, item_id) for item_id in identifiers])
        return [
            cast(OutputItem, _deserialize_mapping(value, kind="response item"))
            if value is not None
            else None
            for value in values
        ]

    async def get_history_item_ids(
        self,
        previous_response_id: str | None,
        conversation_id: str | None,
        limit: int,
        *,
        context: PlatformContext | None = None,
    ) -> list[str]:
        """Resolve chronological item identifiers for response continuation."""
        if limit <= 0:
            return []
        partition = self._partition(context)
        client = await self._database.connect()

        response_ids: list[str] = []
        if previous_response_id is not None:
            response_ids.append(previous_response_id)
        if conversation_id is not None:
            # The sorted set orders responses by their creation sequence.
            members = await client.zrange(self._conversation_key(partition, conversation_id), 0, -1)
            response_ids.extend(members)
        if not response_ids:
            return []

        resolved: list[str] = []
        for response_id in response_ids:
            envelope = await client.hgetall(self._response_key(partition, response_id))
            if not envelope or envelope.get("deleted") == "1":
                continue
            resolved.extend(json.loads(envelope["history_item_ids"]))
            resolved.extend(json.loads(envelope["input_item_ids"]))
            resolved.extend(json.loads(envelope["output_item_ids"]))
        return resolved[-limit:]

    def _write_items(
        self,
        pipe: Any,
        partition: str,
        item_values: list[tuple[str, str]],
    ) -> None:
        """Queue item writes with a refreshed retention window."""
        for item_id, value in item_values:
            pipe.set(self._item_key(partition, item_id), value, ex=self._ttl_seconds)

    def _refresh_items(
        self,
        pipe: Any,
        partition: str,
        item_ids: list[str],
    ) -> None:
        """Queue retention-window extensions on referenced items already stored."""
        for item_id in item_ids:
            pipe.expire(self._item_key(partition, item_id), self._ttl_seconds)


def create_response_store(database: RedisDatabase) -> RedisResponseStore:
    """Create the Redis-backed Responses store."""
    return RedisResponseStore(
        database=database,
        ttl_seconds=_get_positive_int("REDIS_RESPONSE_TTL_SECONDS", DEFAULT_RESPONSE_TTL_SECONDS),
        local_user_id=get_local_user_id(),
    )
