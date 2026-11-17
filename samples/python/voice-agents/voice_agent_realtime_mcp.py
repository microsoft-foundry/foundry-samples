"""Invoke a read-only MCP tool and explicitly approve or reject its request.

Set FOUNDRY_PROJECT_ENDPOINT. Optional: FOUNDRY_VOICE_AGENT_MODEL,
FOUNDRY_VOICE_MCP_SERVER_URL (defaults to the public Microsoft Learn server),
and FOUNDRY_VOICE_MCP_TOOL_NAME (defaults to microsoft_docs_search).
Run: python voice_agent_realtime_mcp.py --approval approve
Use --approval reject to deny execution, or never for a trusted read-only server.
"""

import argparse
import os
import time
from uuid import uuid4

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    RealtimeConversationItemMessageUser,
    RealtimeConversationItemMessageUserContent,
    RealtimeConversationItemType,
    RealtimeMCPApprovalRequest,
    RealtimeMCPApprovalResponse,
    RealtimeMCPListTools,
    RealtimeMCPToolCall,
    RealtimeServerEventConversationItemCreated,
    RealtimeServerEventConversationItemDone,
    RealtimeServerEventError,
    RealtimeServerEventMCPListToolsFailed,
    RealtimeServerEventResponseDone,
    RealtimeServerEventResponseCreated,
    RealtimeServerEventResponseMCPCallFailed,
    RealtimeServerEventResponseOutputItemDone,
    RealtimeServerEventResponseTextDone,
    VoiceAgentDefinition,
    VoiceAgentMcpTool,
    VoiceModelType,
    VoiceOutputModality,
)
from azure.ai.projects.operations import RealtimeConnection
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from voice_agent_util import require_new_agent, safe_print, sample_agent_name

DEFAULT_MCP_URL = "https://learn.microsoft.com/api/mcp"
DEFAULT_TOOL_NAME = "microsoft_docs_search"
SERVER_LABEL = "sample-docs"
PROMPT = "Search Microsoft Learn for Azure Functions triggers, then summarize one result in one sentence."


def wait_for_tool(
    connection: RealtimeConnection, server_label: str, tool_name: str
) -> None:
    """Wait for the service's asynchronous tool discovery before asking the model."""
    deadline = time.monotonic() + 60
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("The MCP tool catalog did not finish loading.")
        event = connection.recv(timeout=remaining)
        if isinstance(event, RealtimeServerEventError):
            raise RuntimeError(event.error.message)
        if isinstance(event, RealtimeServerEventMCPListToolsFailed):
            raise RuntimeError(f"MCP tool discovery failed for item {event.item_id}.")
        if isinstance(event, RealtimeServerEventConversationItemDone):
            item = event.item
            if (
                isinstance(item, RealtimeMCPListTools)
                and item.server_label == server_label
            ):
                if tool_name not in [tool.name for tool in item.tools]:
                    raise RuntimeError(
                        f"The advertised catalog does not contain {tool_name}."
                    )
                return


def run_tool_turn(
    connection: RealtimeConnection,
    *,
    approval: str,
    tool_name: str,
    server_label: str = SERVER_LABEL,
) -> None:
    """Require a real completed tool call, or a confirmed approval denial."""
    if approval not in ("approve", "reject", "never"):
        raise ValueError("Choose approve, reject, or never.")
    wait_for_tool(connection, server_label, tool_name)
    connection.conversation.item.create(
        item=RealtimeConversationItemMessageUser(
            type=RealtimeConversationItemType.MESSAGE,
            content=[
                RealtimeConversationItemMessageUserContent(
                    type="input_text", text=PROMPT
                )
            ],
        )
    )
    connection.response.create()
    approvals: dict[str, RealtimeMCPApprovalRequest] = {}
    answered_approvals: set[str] = set()
    completed_calls: set[str] = set()
    requested_calls: set[str] = set()
    response_texts: dict[str, str] = {}
    response_count = 0
    response_active = True
    deadline = time.monotonic() + 120

    def collect_approval(item: RealtimeMCPApprovalRequest) -> None:
        if item.server_label != server_label or item.name != tool_name:
            raise RuntimeError(
                "Refusing approval for an unexpected MCP server or tool."
            )
        approvals[item.id] = item

    def submit_approvals() -> None:
        for request in approvals.values():
            if request.id in answered_approvals:
                continue
            if approval == "never":
                raise RuntimeError(
                    "The trusted-server scenario unexpectedly requested approval."
                )
            connection.conversation.item.create(
                item=RealtimeMCPApprovalResponse(
                    id=f"item_{uuid4().hex[:12]}",
                    approval_request_id=request.id,
                    approve=approval == "approve",
                    reason="Explicit sample approval."
                    if approval == "approve"
                    else "Sample denied execution.",
                )
            )
            answered_approvals.add(request.id)

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("The MCP tool/approval round trip did not finish.")
        event = connection.recv(timeout=remaining)
        if isinstance(event, RealtimeServerEventError):
            raise RuntimeError(event.error.message)
        if isinstance(event, RealtimeServerEventMCPListToolsFailed):
            raise RuntimeError(
                f"MCP operation failed: {event.type}, item {event.item_id}."
            )
        if isinstance(event, RealtimeServerEventResponseMCPCallFailed):
            if (
                approval == "reject"
                and answered_approvals
                and event.item_id in requested_calls
            ):
                continue
            raise RuntimeError(f"MCP invocation failed for item {event.item_id}.")
        if isinstance(event, RealtimeServerEventResponseCreated):
            response_active = True
        if isinstance(
            event,
            (
                RealtimeServerEventResponseOutputItemDone,
                RealtimeServerEventConversationItemDone,
                RealtimeServerEventConversationItemCreated,
            ),
        ):
            item = event.item
            if isinstance(item, RealtimeMCPApprovalRequest):
                collect_approval(item)
                # The service can emit the request after its response.done.
                if not response_active:
                    submit_approvals()
            elif isinstance(item, RealtimeMCPApprovalResponse):
                if (
                    approval == "reject"
                    and item.approval_request_id in answered_approvals
                    and not item.approve
                ):
                    if completed_calls:
                        raise RuntimeError("A denied MCP request still executed.")
                    print("Approval rejected and acknowledged; no MCP tool executed.")
                    return
            elif isinstance(item, RealtimeMCPToolCall):
                if item.error is not None:
                    if (
                        approval == "reject"
                        and answered_approvals
                        and item.id in requested_calls
                    ):
                        continue
                    raise RuntimeError(f"MCP tool {item.name} returned an error.")
                if item.server_label != server_label or item.name != tool_name:
                    raise RuntimeError("An unexpected MCP tool executed.")
                if item.output:
                    if approval == "reject":
                        raise RuntimeError("A denied MCP request still executed.")
                    first_completion = item.id not in completed_calls
                    completed_calls.add(item.id)
                    if first_completion:
                        print(f"Completed MCP tool: {item.name}, item {item.id}")
        elif isinstance(event, RealtimeServerEventResponseTextDone):
            response_texts[event.response_id] = event.text
        elif isinstance(event, RealtimeServerEventResponseDone):
            response_active = False
            response_count += 1
            response_id = event.response.id
            if not response_id:
                raise RuntimeError("The MCP response omitted its response ID.")
            if event.response.status != "completed":
                raise RuntimeError(
                    f"MCP response ended with status {event.response.status}."
                )
            for item in event.response.output or []:
                if isinstance(item, RealtimeMCPApprovalRequest):
                    collect_approval(item)
            text = response_texts.pop(response_id, "")
            current_calls = {
                item.id
                for item in event.response.output or []
                if isinstance(item, RealtimeMCPToolCall)
            }
            requested_calls.update(current_calls)
            submit_approvals()
            if (
                completed_calls
                and requested_calls <= completed_calls
                and not current_calls
                and text.strip()
            ):
                if approval == "approve" and not answered_approvals:
                    raise RuntimeError(
                        "The service omitted the required approval request."
                    )
                safe_print(f"Agent: {text}")
                return
            elif requested_calls or answered_approvals:
                # MCP completion and its automatically scheduled answer can follow response.done.
                if response_count >= 4:
                    raise RuntimeError("The sample exceeded four MCP response cycles.")
            else:
                raise RuntimeError(
                    "The model answered without a completed MCP tool result."
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--approval", choices=("approve", "reject", "never"), default="reject"
    )
    args = parser.parse_args()
    load_dotenv()
    model = os.environ.get("FOUNDRY_VOICE_AGENT_MODEL") or "gpt-realtime"
    tool_name = os.environ.get("FOUNDRY_VOICE_MCP_TOOL_NAME") or DEFAULT_TOOL_NAME
    agent_name = sample_agent_name("sample-realtime-mcp")
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential
        ) as client,
    ):
        require_new_agent(client, agent_name)
        created = client.agents.create_version(
            agent_name=agent_name,
            definition=VoiceAgentDefinition(
                model_type=VoiceModelType.MANAGED,
                model=model,
                instructions=f"Use {tool_name} before answering. Do not invent search results.",
                output_modalities=[VoiceOutputModality.TEXT],
                tools=[
                    VoiceAgentMcpTool(
                        server_label=SERVER_LABEL,
                        server_url=os.environ.get("FOUNDRY_VOICE_MCP_SERVER_URL")
                        or DEFAULT_MCP_URL,
                        allowed_tools=[tool_name],
                        require_approval="never"
                        if args.approval == "never"
                        else "always",
                    )
                ],
            ),
        )
        try:
            print(f"Created owned agent {agent_name}, version {created.version}.")
            with client.voice_agents.realtime.connect(
                agent_name=agent_name
            ) as connection:
                run_tool_turn(connection, approval=args.approval, tool_name=tool_name)
        finally:
            client.agents.delete_version(
                agent_name=agent_name, agent_version=created.version
            )


if __name__ == "__main__":
    main()
