# Copyright (c) Microsoft. All rights reserved.

"""Redis-backed agent session, workflow checkpoint, and function approval stores.

These three stores complement the Redis Responses store. Each one implements the
Agent Framework hosting extension point it plugs into and persists to the shared
Redis instance:

* ``RedisAgentSessionStore`` implements ``SessionStore`` for MAF agent sessions.
* ``RedisCheckpointStore`` implements ``CheckpointStorage`` for workflow
  checkpoints, scoped to one workflow context.
* ``RedisFunctionApprovalStore`` implements ``FunctionApprovalStore`` for
  human-in-the-loop function approval requests.

Every key is namespaced by the requesting user so one caller cannot read another
caller's state.
"""

from __future__ import annotations

import json
from datetime import datetime

from agent_framework import (
    AgentSession,
    CheckpointID,
    CheckpointStorage,
    Content,
    SessionStore,
    WorkflowCheckpoint,
    WorkflowCheckpointException,
)
from agent_framework._workflows._checkpoint_encoding import (
    decode_checkpoint_value,
    encode_checkpoint_value,
)
from agent_framework_foundry_hosting import (
    ContextScopedStoreProvider,
    FunctionApprovalStore,
    StoreProvider,
)
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext

from redis_database import RedisDatabase, get_local_user_id, partition_for

# region Agent session persistence


class RedisAgentSessionStore(SessionStore):
    """Agent session store backed by the shared Redis instance."""

    def __init__(self, database: RedisDatabase, partition: str) -> None:
        super().__init__()
        self._database = database
        self._partition = partition

    def _key(self, session_id: str) -> str:
        return self._database.partition_key("session", self._partition, session_id)

    async def get(self, session_id: str) -> AgentSession | None:
        SessionStore.validate_session_id(session_id)
        client = await self._database.connect()
        value = await client.get(self._key(session_id))
        if value is None:
            return None
        return AgentSession.from_dict(json.loads(value))

    async def set(self, session_id: str, session: AgentSession) -> None:
        SessionStore.validate_session_id(session_id)
        client = await self._database.connect()
        await client.set(self._key(session_id), json.dumps(session.to_dict()))

    async def delete(self, session_id: str) -> None:
        SessionStore.validate_session_id(session_id)
        client = await self._database.connect()
        await client.delete(self._key(session_id))


class RedisAgentSessionStoreProvider(StoreProvider[SessionStore]):
    """Provide the Redis agent session store for each request."""

    def __init__(self, database: RedisDatabase) -> None:
        self._database = database
        self._local_user_id = get_local_user_id()

    def get_store(
        self,
        *,
        config: AgentConfig,
        platform_context: FoundryAgentRequestContext,
    ) -> SessionStore:
        partition = partition_for(platform_context.user_id, self._local_user_id)
        return RedisAgentSessionStore(self._database, partition)


# endregion Agent session persistence

# region Checkpoint persistence


class RedisCheckpointStore(CheckpointStorage):
    """Workflow checkpoint store scoped to a single workflow context.

    Each checkpoint is a Redis hash, and a per-workflow set indexes the
    checkpoint IDs so a workflow run can be listed and pruned as a collection.
    """

    def __init__(self, database: RedisDatabase, partition: str, context_id: str) -> None:
        if not context_id:
            raise ValueError("context_id must be provided to initialize a checkpoint store.")
        self._database = database
        self._partition = partition
        self._context_id = context_id

    def _checkpoint_key(self, checkpoint_id: str) -> str:
        return self._database.partition_key(
            "ckpt", self._partition, self._context_id, checkpoint_id
        )

    def _index_key(self, workflow_name: str) -> str:
        return self._database.partition_key(
            "ckptidx", self._partition, self._context_id, workflow_name
        )

    async def save(self, checkpoint: WorkflowCheckpoint) -> CheckpointID:
        client = await self._database.connect()
        async with self._database.write_lock:
            pipe = client.pipeline(transaction=True)
            pipe.hset(
                self._checkpoint_key(checkpoint.checkpoint_id),
                mapping={
                    "workflow_name": checkpoint.workflow_name,
                    "timestamp": checkpoint.timestamp,
                    "value": json.dumps(encode_checkpoint_value(checkpoint.to_dict())),
                },
            )
            pipe.sadd(self._index_key(checkpoint.workflow_name), checkpoint.checkpoint_id)
            await pipe.execute()
        return checkpoint.checkpoint_id

    async def load(self, checkpoint_id: CheckpointID) -> WorkflowCheckpoint:
        client = await self._database.connect()
        value = await client.hget(self._checkpoint_key(checkpoint_id), "value")
        if value is None:
            raise WorkflowCheckpointException(f"No checkpoint found with ID {checkpoint_id}")
        return WorkflowCheckpoint.from_dict(
            decode_checkpoint_value(json.loads(value), allowed_types=frozenset())
        )

    async def list_checkpoints(self, *, workflow_name: str) -> list[WorkflowCheckpoint]:
        client = await self._database.connect()
        checkpoint_ids = await client.smembers(self._index_key(workflow_name))
        checkpoints: list[WorkflowCheckpoint] = []
        for checkpoint_id in checkpoint_ids:
            value = await client.hget(self._checkpoint_key(checkpoint_id), "value")
            if value is None:
                continue
            checkpoints.append(
                WorkflowCheckpoint.from_dict(
                    decode_checkpoint_value(json.loads(value), allowed_types=frozenset())
                )
            )
        return checkpoints

    async def delete(self, checkpoint_id: CheckpointID) -> bool:
        client = await self._database.connect()
        checkpoint_key = self._checkpoint_key(checkpoint_id)
        async with self._database.write_lock:
            workflow_name = await client.hget(checkpoint_key, "workflow_name")
            pipe = client.pipeline(transaction=True)
            pipe.delete(checkpoint_key)
            if workflow_name is not None:
                pipe.srem(self._index_key(workflow_name), checkpoint_id)
            results = await pipe.execute()
        return bool(results[0])

    async def get_latest(self, *, workflow_name: str) -> WorkflowCheckpoint | None:
        checkpoints = await self.list_checkpoints(workflow_name=workflow_name)
        if not checkpoints:
            return None
        return max(checkpoints, key=lambda checkpoint: datetime.fromisoformat(checkpoint.timestamp))

    async def list_checkpoint_ids(self, *, workflow_name: str) -> list[CheckpointID]:
        checkpoints = await self.list_checkpoints(workflow_name=workflow_name)
        return [checkpoint.checkpoint_id for checkpoint in checkpoints]


class RedisCheckpointStoreProvider(ContextScopedStoreProvider[CheckpointStorage]):
    """Provide the Redis checkpoint store scoped to a workflow context."""

    def __init__(self, database: RedisDatabase) -> None:
        self._database = database
        self._local_user_id = get_local_user_id()

    def get_store(
        self,
        *,
        config: AgentConfig,
        context_id: str,
        platform_context: FoundryAgentRequestContext,
    ) -> CheckpointStorage:
        if not context_id:
            raise ValueError("context_id must be provided to get a checkpoint store.")
        partition = partition_for(platform_context.user_id, self._local_user_id)
        return RedisCheckpointStore(self._database, partition, context_id)


# endregion Checkpoint persistence

# region Function approval persistence


class RedisFunctionApprovalStore(FunctionApprovalStore):
    """Function approval store backed by the shared Redis instance."""

    def __init__(self, database: RedisDatabase, partition: str) -> None:
        self._database = database
        self._partition = partition

    def _key(self, approval_request_id: str) -> str:
        return self._database.partition_key("approval", self._partition, approval_request_id)

    async def save_approval_request(self, approval_request_id: str, request: Content) -> None:
        client = await self._database.connect()
        # SET NX makes the create atomic and rejects duplicate approval IDs.
        created = await client.set(
            self._key(approval_request_id), json.dumps(request.to_dict()), nx=True
        )
        if not created:
            raise ValueError(f"Approval request with ID '{approval_request_id}' already exists.")

    async def load_approval_request(self, approval_request_id: str) -> Content:
        client = await self._database.connect()
        value = await client.get(self._key(approval_request_id))
        if value is None:
            raise KeyError(f"Approval request with ID '{approval_request_id}' does not exist.")
        return Content.from_dict(json.loads(value))


class RedisFunctionApprovalStoreProvider(StoreProvider[FunctionApprovalStore]):
    """Provide the Redis function approval store for each request."""

    def __init__(self, database: RedisDatabase) -> None:
        self._database = database
        self._local_user_id = get_local_user_id()

    def get_store(
        self,
        *,
        config: AgentConfig,
        platform_context: FoundryAgentRequestContext,
    ) -> FunctionApprovalStore:
        partition = partition_for(platform_context.user_id, self._local_user_id)
        return RedisFunctionApprovalStore(self._database, partition)


# endregion Function approval persistence
