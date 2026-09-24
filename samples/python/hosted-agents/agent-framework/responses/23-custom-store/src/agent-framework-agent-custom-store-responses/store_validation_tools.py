# Copyright (c) Microsoft. All rights reserved.

"""Tools that exercise and inspect the four custom Redis stores."""

from __future__ import annotations

from typing import Annotated, Never
from uuid import uuid4

from agent_framework import (
    Executor,
    FunctionTool,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    tool,
)
from azure.ai.agentserver.core import AgentConfig, get_request_context
from pydantic import Field
from redis_database import RedisDatabase, get_local_user_id, partition_for
from redis_state_stores import RedisCheckpointStoreProvider

CHECKPOINT_WORKFLOW_NAME = "custom-store-validation"


class _CheckpointMarkerExecutor(Executor):
    """Yield a marker so a real workflow checkpoint contains deterministic state."""

    @handler
    async def record_marker(self, marker: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output(marker)


def create_store_validation_tools(database: RedisDatabase) -> list[FunctionTool]:
    """Create tools that validate checkpoint, approval, and stored-record data."""
    checkpoint_provider = RedisCheckpointStoreProvider(database)

    @tool(approval_mode="never_require")
    async def validate_checkpoint_store(
        marker: Annotated[str, Field(description="Exact marker to persist in a workflow checkpoint.")],
    ) -> str:
        """Run a checkpointed workflow, then load and verify its saved checkpoint."""
        request_context = get_request_context()
        context_id = request_context.call_id or uuid4().hex
        checkpoint_store = checkpoint_provider.get_store(
            config=AgentConfig.from_env(),
            context_id=f"validation-{context_id}",
            platform_context=request_context,
        )
        workflow = WorkflowBuilder(
            start_executor=_CheckpointMarkerExecutor(id="record-marker"),
            name=CHECKPOINT_WORKFLOW_NAME,
        ).build()

        events = await workflow.run(marker, checkpoint_storage=checkpoint_store)
        if events.get_outputs() != [marker]:
            raise RuntimeError("The checkpoint validation workflow returned an unexpected output.")

        checkpoint_ids = await checkpoint_store.list_checkpoint_ids(workflow_name=CHECKPOINT_WORKFLOW_NAME)
        if not checkpoint_ids:
            raise RuntimeError("The checkpoint validation workflow did not persist a checkpoint.")
        checkpoints = [await checkpoint_store.load(checkpoint_id) for checkpoint_id in checkpoint_ids]
        if any(checkpoint.workflow_name != CHECKPOINT_WORKFLOW_NAME for checkpoint in checkpoints):
            raise RuntimeError("The checkpoint validation workflow loaded unexpected data.")
        stored_values = [
            message.data
            for checkpoint in checkpoints
            for messages in checkpoint.messages.values()
            for message in messages
        ]
        if marker not in stored_values:
            raise RuntimeError("The checkpoint validation workflow did not reload the persisted marker.")

        return f"CHECKPOINT_STORE_OK {marker}"

    @tool(approval_mode="always_require")
    def approve_incident_change(
        change_id: Annotated[str, Field(description="Change request identifier to approve.")],
    ) -> str:
        """Approve a simulated incident change after host-managed human approval."""
        return f"APPROVAL_STORE_OK {change_id}"

    @tool(approval_mode="never_require")
    async def inspect_custom_store() -> str:
        """Return record counts for the current user across all four custom stores."""
        request_context = get_request_context()
        partition = partition_for(request_context.user_id, get_local_user_id())
        client = await database.connect()
        # Each store owns a distinct key prefix, so a per-store SCAN counts only
        # that store's keys for this partition. Expired keys are excluded natively.
        stores = (
            ("response_store", database.partition_key("resp", partition, "*")),
            ("agent_session_store", database.partition_key("session", partition, "*")),
            ("checkpoint_store", database.partition_key("ckpt", partition, "*")),
            ("function_approval_store", database.partition_key("approval", partition, "*")),
        )
        counts: list[str] = []
        for label, pattern in stores:
            count = 0
            async for _ in client.scan_iter(match=pattern, count=100):
                count += 1
            counts.append(f"{label}={count}")
        return f"STORE_COUNTS {' '.join(counts)}"

    return [validate_checkpoint_store, approve_incident_change, inspect_custom_store]