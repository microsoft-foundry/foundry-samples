"""Exercise handled publication failures through the native graph and host."""

from __future__ import annotations

import json
import os
import sys
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from azure.core.exceptions import HttpResponseError, ServiceRequestError
from langchain_azure_ai.agents.hosting import ResponsesHostServer
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import build_agent
from report_export import create_report_export_tool

REPORT = "# Report v1\nEvidence [1].\n\n[1] https://example.org/source"
REVISION = REPORT + "\n\n## Recovery limitations\nOnly saved state is restored."
FAILURE = (
    "Publishing /report-v1.md failed. No download link was created. "
    "The saved report remains available for editing."
)


class ScriptedModel(GenericFakeChatModel):
    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> ScriptedModel:
        return self

    def get_num_tokens_from_messages(
        self, messages: list[BaseMessage], tools: Sequence[Any] | None = None
    ) -> int:
        return sum(len(str(message.content)) // 4 for message in messages)


def call(name: str, arguments: dict[str, Any], identifier: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": arguments, "id": identifier, "type": "tool_call"}
        ],
    )


def response(client: TestClient, stream: bool, **request: Any) -> dict[str, Any]:
    result = client.post("/responses", json={"stream": stream, **request})
    result.raise_for_status()
    if not stream:
        return result.json()
    events = [
        json.loads(line.removeprefix("data: "))
        for line in result.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    if any(
        event.get("type") in {"error", "response.failed", "response.incomplete"}
        for event in events
    ):
        raise AssertionError("Unexpected terminal error in native host stream")
    return next(
        event["response"]
        for event in events
        if event.get("type") == "response.completed"
    )


class PublicationFailureWorkflowTests(unittest.TestCase):
    def test_named_versions_publish_selected_saved_bytes_without_overwriting(
        self,
    ) -> None:
        for stream in (False, True):
            with (
                self.subTest(stream=stream),
                patch.dict(
                    os.environ,
                    {
                        "OTEL_SDK_DISABLED": "true",
                        "REPORT_STORAGE_ACCOUNT_URL": "https://reports.blob.core.windows.net",
                        "REPORT_STORAGE_CONTAINER": "reports",
                    },
                ),
            ):
                storage = MagicMock()
                storage.__enter__.return_value = storage
                storage.account_name = "reports"
                blobs: list[MagicMock] = []

                def create_blob(
                    container: str, name: str, saved: list[MagicMock] = blobs
                ) -> MagicMock:
                    blob = MagicMock(
                        url=f"https://reports.blob.core.windows.net/{container}/{name}"
                    )
                    saved.append(blob)
                    return blob

                storage.get_blob_client.side_effect = create_blob
                with (
                    patch("report_export.BlobServiceClient", return_value=storage),
                    patch(
                        "report_export.generate_blob_sas", return_value="sp=r&sig=test"
                    ),
                ):
                    model = ScriptedModel(
                        disable_streaming=True,
                        messages=iter(
                            [
                                call(
                                    "write_file",
                                    {"file_path": "/report-v1.md", "content": REPORT},
                                    "save",
                                ),
                                call(
                                    "publish_report",
                                    {"report_name": "report-v1.md"},
                                    "publish-v1",
                                ),
                                AIMessage(content=REPORT),
                                call(
                                    "write_file",
                                    {"file_path": "/report-v2.md", "content": REPORT},
                                    "copy",
                                ),
                                call(
                                    "edit_file",
                                    {
                                        "file_path": "/report-v2.md",
                                        "old_string": REPORT,
                                        "new_string": REVISION,
                                    },
                                    "revise",
                                ),
                                call(
                                    "publish_report",
                                    {"report_name": "report-v2.md"},
                                    "publish-v2",
                                ),
                                AIMessage(content=REVISION),
                                call(
                                    "publish_report",
                                    {"report_name": "report-v1.md"},
                                    "republish-original",
                                ),
                                AIMessage(content=REPORT),
                            ]
                        ),
                    )
                    graph = build_agent(
                        model,
                        InMemorySaver(),
                        [],
                        create_report_export_tool(MagicMock()),
                    )
                    with TestClient(ResponsesHostServer(graph).app) as client:
                        first = response(client, stream, input="Save and publish v1")
                        second = response(
                            client,
                            stream,
                            previous_response_id=first["id"],
                            input="Keep v1 and revise a copy as v2",
                        )
                        third = response(
                            client,
                            stream,
                            previous_response_id=second["id"],
                            input="Publish original v1 again",
                        )
                        self.assertTrue(
                            all(
                                result["status"] == "completed"
                                for result in (first, second, third)
                            )
                        )
                self.assertEqual(
                    [blob.upload_blob.call_args.args[0] for blob in blobs],
                    [REPORT.encode(), REVISION.encode(), REPORT.encode()],
                )
                names = [
                    invocation.args[1]
                    for invocation in storage.get_blob_client.call_args_list
                ]
                self.assertEqual(len(set(names)), 3)
                self.assertTrue(
                    names[0].endswith("/report-v1.md")
                    and names[2].endswith("/report-v1.md")
                )
                self.assertTrue(names[1].endswith("/report-v2.md"))

    def test_host_completes_and_preserves_editable_state_after_publication_error(
        self,
    ) -> None:
        for stream in (False, True):
            for error in (HttpResponseError("denied"), ServiceRequestError("offline")):
                with (
                    self.subTest(stream=stream, error=type(error).__name__),
                    patch.dict(
                        os.environ,
                        {
                            "OTEL_SDK_DISABLED": "true",
                            "REPORT_STORAGE_ACCOUNT_URL": "https://reports.blob.core.windows.net",
                            "REPORT_STORAGE_CONTAINER": "reports",
                        },
                    ),
                ):
                    storage = MagicMock()
                    storage.__enter__.return_value = storage
                    storage.account_name = "reports"
                    storage.get_user_delegation_key.side_effect = error
                    with patch("report_export.BlobServiceClient", return_value=storage):
                        model = ScriptedModel(
                            disable_streaming=True,
                            messages=iter(
                                [
                                    call(
                                        "write_file",
                                        {
                                            "file_path": "/report-v1.md",
                                            "content": REPORT,
                                        },
                                        "save",
                                    ),
                                    call(
                                        "publish_report",
                                        {"report_name": "report-v1.md"},
                                        "publish",
                                    ),
                                    AIMessage(content=FAILURE),
                                    call(
                                        "read_file",
                                        {"file_path": "/report-v1.md"},
                                        "read-original",
                                    ),
                                    call(
                                        "write_file",
                                        {
                                            "file_path": "/report-v2.md",
                                            "content": REPORT,
                                        },
                                        "copy",
                                    ),
                                    call(
                                        "edit_file",
                                        {
                                            "file_path": "/report-v2.md",
                                            "old_string": REPORT,
                                            "new_string": REVISION,
                                        },
                                        "edit",
                                    ),
                                    call(
                                        "read_file",
                                        {"file_path": "/report-v2.md"},
                                        "read-revised",
                                    ),
                                    AIMessage(content=REVISION),
                                ]
                            ),
                        )
                        graph = build_agent(
                            model,
                            InMemorySaver(),
                            [],
                            create_report_export_tool(MagicMock()),
                        )
                        with TestClient(ResponsesHostServer(graph).app) as client:
                            first = response(
                                client, stream, input="Save and publish report-v1.md"
                            )
                            self.assertEqual(first["status"], "completed")
                            self.assertIn(FAILURE, json.dumps(first))
                            self.assertNotIn("download_url", json.dumps(first))
                            revised = response(
                                client,
                                stream,
                                previous_response_id=first["id"],
                                input="Read v1, then revise a copy as v2",
                            )
                            self.assertEqual(revised["status"], "completed")
                            assert client.portal is not None
                            config: RunnableConfig = {
                                "configurable": {"thread_id": first["id"]}
                            }
                            state = client.portal.call(graph.aget_state, config)
                            self.assertEqual(
                                state.values["files"]["/report-v1.md"]["content"],
                                REPORT,
                            )
                            self.assertEqual(
                                state.values["files"]["/report-v2.md"]["content"],
                                REVISION,
                            )
                            errors = [
                                message
                                for message in state.values["messages"]
                                if isinstance(message, ToolMessage)
                                and message.name == "publish_report"
                            ]
                            self.assertEqual(len(errors), 1)
                            self.assertEqual(errors[0].status, "error")
                            self.assertIn("No download link", errors[0].content)
                    storage.get_blob_client.assert_not_called()
                    storage.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
