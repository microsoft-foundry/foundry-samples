# Copyright (c) Microsoft. All rights reserved.
"""Copilot tools that persist synthetic support cases in Foundry state storage."""

import copy
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from azure.ai.agentserver.core.storage import (
    FoundryStateStore,
    FoundryStorageNotFoundError,
    FoundryStoragePreconditionError,
    StateStoreItem,
)
from copilot import Tool, define_tool
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("a2a.support.tools")


class Parameters(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OpenCase(Parameters):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)


class CaseId(Parameters):
    case_id: str = Field(pattern=r"^case-[a-f0-9]{32}$")


class AddFinding(CaseId):
    finding: str = Field(min_length=1, max_length=4000)


class SaveSummary(CaseId):
    expected_version: int = Field(strict=True, ge=1)
    summary: str = Field(min_length=1, max_length=8000)


class ListCases(Parameters):
    after: str | None = Field(
        default=None, description="Opaque next_after cursor from an earlier listing."
    )


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_tools(
    store: FoundryStateStore,
    operations: list[dict[str, Any]],
    *,
    call_id: str | None = None,
) -> list[Tool]:
    async def read(case_id: str) -> StateStoreItem:
        item = await store.get_item(case_id, call_id=call_id)
        if item is None:
            raise FoundryStorageNotFoundError(
                f"Case {case_id} was not found or is not accessible.", status_code=404
            )
        record = item.value
        if (
            record.get("case_id") != case_id
            or type(record.get("version")) is not int
            or not isinstance(record.get("history"), list)
            or not item.etag
        ):
            raise RuntimeError(
                "Stored case has an invalid record shape or missing ETag"
            )
        return item

    def receipt(action: str, record: dict, etag: str) -> str:
        operations.append({"action": action, "case": record, "etag": etag})
        logger.info(
            "CASE_STORE_OPERATION action=%s case_id=%s version=%s",
            action,
            record["case_id"],
            record["version"],
        )
        return json.dumps(record)

    async def open_case(params: OpenCase, _invocation) -> str:
        timestamp = now()
        record = {
            "case_id": "case-" + uuid4().hex,
            "title": params.title,
            "description": params.description,
            "status": "open",
            "version": 1,
            "created_at": timestamp,
            "updated_at": timestamp,
            "findings": [],
            "resolution_summary": None,
            "history": [
                {"action": "opened", "at": timestamp, "text": params.description}
            ],
            "synthetic": True,
        }
        saved = await store.create_item(
            record["case_id"],
            record,
            tags={"kind": "support-case", "status": "open"},
            call_id=call_id,
        )
        return receipt("opened", record, saved.etag)

    async def get_case(params: CaseId, _invocation) -> str:
        item = await read(params.case_id)
        return receipt("read", item.value, item.etag)

    async def add_finding(params: AddFinding, _invocation) -> str:
        item = await read(params.case_id)
        record = copy.deepcopy(item.value)
        timestamp = now()
        record["findings"].append({"at": timestamp, "text": params.finding})
        record["history"].append(
            {"action": "finding_added", "at": timestamp, "text": params.finding}
        )
        record["version"] += 1
        record["updated_at"] = timestamp
        # A previous summary remains in history, but is no longer the current summary.
        record["resolution_summary"] = None
        record["status"] = "open"
        saved = await store.set_item(
            params.case_id,
            record,
            if_match=item.etag,
            call_id=call_id,
            tags={"kind": "support-case", "status": "open"},
        )
        return receipt("finding_added", record, saved.etag)

    async def save_resolution_summary(params: SaveSummary, _invocation) -> str:
        item = await read(params.case_id)
        if item.value["version"] != params.expected_version:
            raise FoundryStoragePreconditionError(
                "Case changed since it was read. Read it again and regenerate the summary.",
                status_code=412,
                current_etag=item.etag,
            )
        record = copy.deepcopy(item.value)
        timestamp = now()
        record["resolution_summary"] = params.summary
        record["history"].append(
            {
                "action": "summary_saved",
                "at": timestamp,
                "text": params.summary,
                "source_version": params.expected_version,
            }
        )
        record["version"] += 1
        record["updated_at"] = timestamp
        record["status"] = "summarized"
        saved = await store.set_item(
            params.case_id,
            record,
            if_match=item.etag,
            call_id=call_id,
            tags={"kind": "support-case", "status": "summarized"},
        )
        return receipt("summary_saved", record, saved.etag)

    async def list_cases(params: ListCases, _invocation) -> str:
        page = await store.list_keys(
            tags={"kind": "support-case"}, limit=20, after=params.after, call_id=call_id
        )
        result = {
            "case_ids": [entry.key for entry in page.keys],
            "next_after": page.last_id if page.has_more else None,
        }
        operations.append({"action": "listed", **result})
        return json.dumps(result)

    def tool(name: str, description: str, handler, params_type) -> Tool:
        async def logged(params, invocation):
            try:
                return await handler(params, invocation)
            except Exception as error:
                operations.append(
                    {"action": "error", "tool": name, "message": str(error)}
                )
                logger.exception("CASE_STORE_TOOL_FAILED tool=%s", name)
                raise

        return define_tool(
            name, description=description, handler=logged, params_type=params_type
        )

    return [
        tool(
            "open_case",
            "Create a NEW synthetic support case. Returns the generated case ID and saved record. Do not retry creation automatically.",
            open_case,
            OpenCase,
        ),
        tool(
            "get_case",
            "Load a case, its findings, saved summary, version and full history from state storage. Required before summarizing.",
            get_case,
            CaseId,
        ),
        tool(
            "add_finding",
            "Append a finding to an existing case with an ETag-conditional write. Reopens the case and clears its current summary; old summaries remain in history.",
            add_finding,
            AddFinding,
        ),
        tool(
            "save_resolution_summary",
            "Persist your generated summary using the version returned by get_case. This is a synthetic summary, not a real support-ticket closure.",
            save_resolution_summary,
            SaveSummary,
        ),
        tool(
            "list_cases",
            "List saved case IDs for this caller, 20 per page. Pass next_after as after to get another page.",
            list_cases,
            ListCases,
        ),
    ]
