# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_007():
    # <doc_browser_automation_samples_example_code>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.ai.agents.models import (
            MessageRole,
            RunStepToolCallDetails,
            BrowserAutomationTool,
            RunStepBrowserAutomationToolCall,
        )
        from azure.identity import DefaultAzureCredential

        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        connection_id = os.environ["AZURE_PLAYWRIGHT_CONNECTION_ID"]
        browser_automation = BrowserAutomationTool(connection_id=connection_id)
        with project_client:
            agents_client = project_client.agents
            agent = agents_client.create_agent(
                model=os.environ["FOUNDRY_MODEL_NAME"],
                name="my-agent",
                instructions="\n            You are an Agent helping with browser automation tasks. \n            You can answer questions, provide information, and assist with various tasks \n            related to web browsing using the Browser Automation tool available to you.\n            ",
                tools=browser_automation.definitions,
            )
            print(f"Created agent, ID: {agent.id}")
            thread = agents_client.threads.create()
            print(f"Created thread, ID: {thread.id}")
            message = agents_client.messages.create(
                thread_id=thread.id,
                role=MessageRole.USER,
                content="\n            Your goal is to report the percent of Microsoft year-to-date stock price change.\n            To do that, go to the website finance.yahoo.com.\n            At the top of the page, you will find a search bar.\n            Enter the value 'MSFT', to get information about the Microsoft stock price.\n            At the top of the resulting page you will see a default chart of Microsoft stock price.\n            Click on 'YTD' at the top of that chart, and report the percent value that shows up just below it.\n            ",
            )
            print(f"Created message, ID: {message.id}")
            print(f"Waiting for Agent run to complete. Please wait...")
            run = agents_client.runs.create_and_process(
                thread_id=thread.id, agent_id=agent.id
            )
            print(f"Run finished with status: {run.status}")
            if run.status == "failed":
                print(f"Run failed: {run.last_error}")
            run_steps = agents_client.run_steps.list(thread_id=thread.id, run_id=run.id)
            for step in run_steps:
                print(f"Step {step.id} status: {step.status}")
                if isinstance(step.step_details, RunStepToolCallDetails):
                    print("  Tool calls:")
                    tool_calls = step.step_details.tool_calls
                    for call in tool_calls:
                        print(f"    Tool call ID: {call.id}")
                        print(f"    Tool call type: {call.type}")
                        if isinstance(call, RunStepBrowserAutomationToolCall):
                            print(
                                f"    Browser automation input: {call.browser_automation.input}"
                            )
                            print(
                                f"    Browser automation output: {call.browser_automation.output}"
                            )
                            print("    Steps:")
                            for tool_step in call.browser_automation.steps:
                                print(
                                    f"      Last step result: {tool_step.last_step_result}"
                                )
                                print(f"      Current state: {tool_step.current_state}")
                                print(f"      Next step: {tool_step.next_step}")
                                print()
                        print()
                print()
            agents_client.delete_agent(agent.id)
            print("Deleted agent")
            response_message = agents_client.messages.get_last_message_by_role(
                thread_id=thread.id, role=MessageRole.AGENT
            )
            if response_message:
                for text_message in response_message.text_messages:
                    print(f"Agent response: {text_message.text.value}")
                for annotation in response_message.url_citation_annotations:
                    print(
                        f"URL Citation: [{annotation.url_citation.title}]({annotation.url_citation.url})"
                    )
    # </doc_browser_automation_samples_example_code>


def main():
    examples = {"aip-python-007": example_007}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-007")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
