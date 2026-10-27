# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_013():
    # <doc_model_context_protocol_samples_create_an_agent_with_the_mcp_tool>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os, time
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential
        from azure.ai.agents.models import (
            ListSortOrder,
            McpTool,
            RequiredMcpToolCall,
            RunStepActivityDetails,
            SubmitToolApprovalAction,
            ToolApproval,
        )

        mcp_server_url = os.environ.get(
            "FOUNDRY_MCP_SERVER_URL", "https://gitmcp.io/Azure/azure-rest-api-specs"
        )
        mcp_server_label = os.environ.get("FOUNDRY_MCP_SERVER_LABEL", "github")
        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        mcp_tool = McpTool(
            server_label=mcp_server_label, server_url=mcp_server_url, allowed_tools=[]
        )
        search_api_code = "search_azure_rest_api_code"
        mcp_tool.allow_tool(search_api_code)
        print(f"Allowed tools: {mcp_tool.allowed_tools}")
        with project_client:
            agents_client = project_client.agents
            agent = agents_client.create_agent(
                model=os.environ["FOUNDRY_MODEL_NAME"],
                name="my-mcp-agent",
                instructions="You are a helpful agent that can use MCP tools to assist users. Use the available MCP tools to answer questions and perform tasks.",
                tools=mcp_tool.definitions,
            )
            print(f"Created agent, ID: {agent.id}")
            print(f"MCP Server: {mcp_tool.server_label} at {mcp_tool.server_url}")
            thread = agents_client.threads.create()
            print(f"Created thread, ID: {thread.id}")
            message = agents_client.messages.create(
                thread_id=thread.id,
                role="user",
                content="Please summarize the Azure REST API specifications Readme",
            )
            print(f"Created message, ID: {message.id}")
            mcp_tool.update_headers("SuperSecret", "123456")
            run = agents_client.runs.create(
                thread_id=thread.id,
                agent_id=agent.id,
                tool_resources=mcp_tool.resources,
            )
            print(f"Created run, ID: {run.id}")
            while run.status in ["queued", "in_progress", "requires_action"]:
                time.sleep(1)
                run = agents_client.runs.get(thread_id=thread.id, run_id=run.id)
                if run.status == "requires_action" and isinstance(
                    run.required_action, SubmitToolApprovalAction
                ):
                    tool_calls = run.required_action.submit_tool_approval.tool_calls
                    if not tool_calls:
                        print("No tool calls provided - cancelling run")
                        agents_client.runs.cancel(thread_id=thread.id, run_id=run.id)
                        break
                    tool_approvals = []
                    for tool_call in tool_calls:
                        if isinstance(tool_call, RequiredMcpToolCall):
                            try:
                                print(f"Approving tool call: {tool_call}")
                                tool_approvals.append(
                                    ToolApproval(
                                        tool_call_id=tool_call.id,
                                        approve=True,
                                        headers=mcp_tool.headers,
                                    )
                                )
                            except Exception as e:
                                print(f"Error approving tool_call {tool_call.id}: {e}")
                    print(f"tool_approvals: {tool_approvals}")
                    if tool_approvals:
                        agents_client.runs.submit_tool_outputs(
                            thread_id=thread.id,
                            run_id=run.id,
                            tool_approvals=tool_approvals,
                        )
                print(f"Current run status: {run.status}")
            print(f"Run completed with status: {run.status}")
            if run.status == "failed":
                print(f"Run failed: {run.last_error}")
            run_steps = agents_client.run_steps.list(thread_id=thread.id, run_id=run.id)
            for step in run_steps:
                print(f"Step {step['id']} status: {step['status']}")
                step_details = step.get("step_details", {})
                tool_calls = step_details.get("tool_calls", [])
                if tool_calls:
                    print("  MCP Tool calls:")
                    for call in tool_calls:
                        print(f"    Tool Call ID: {call.get('id')}")
                        print(f"    Type: {call.get('type')}")
                if isinstance(step_details, RunStepActivityDetails):
                    for activity in step_details.activities:
                        for (
                            function_name,
                            function_definition,
                        ) in activity.tools.items():
                            print(
                                f'  The function {function_name} with description "{function_definition.description}" will be called.:'
                            )
                            if len(function_definition.parameters) > 0:
                                print("  Function parameters:")
                                for (
                                    argument,
                                    func_argument,
                                ) in function_definition.parameters.properties.items():
                                    print(f"      {argument}")
                                    print(f"      Type: {func_argument.type}")
                                    print(
                                        f"      Description: {func_argument.description}"
                                    )
                            else:
                                print("This function has no parameters")
                print()
            messages = agents_client.messages.list(
                thread_id=thread.id, order=ListSortOrder.ASCENDING
            )
            print("\nConversation:")
            print("-" * 50)
            for msg in messages:
                if msg.text_messages:
                    last_text = msg.text_messages[-1]
                    print(f"{msg.role.upper()}: {last_text.text.value}")
                    print("-" * 50)
            print(f"\nDemonstrating dynamic tool management:")
            print(f"Current allowed tools: {mcp_tool.allowed_tools}")
            try:
                mcp_tool.disallow_tool(search_api_code)
                print(f"After removing {search_api_code}: {mcp_tool.allowed_tools}")
            except ValueError as e:
                print(f"Error removing tool: {e}")
            agents_client.delete_agent(agent.id)
            print("Deleted agent")
    # </doc_model_context_protocol_samples_create_an_agent_with_the_mcp_tool>


def main():
    examples = {"aip-python-013": example_013}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-013")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
