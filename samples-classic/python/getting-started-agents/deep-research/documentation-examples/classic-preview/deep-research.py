# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_009():
    # <doc_deep_research_samples_run_the_python_sample>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        import time
        from typing import Optional
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential
        from azure.ai.agents import AgentsClient
        from azure.ai.agents.models import DeepResearchTool, MessageRole, ThreadMessage

        def fetch_and_print_new_agent_response(
            thread_id: str,
            agents_client: AgentsClient,
            last_message_id: Optional[str] = None,
        ) -> Optional[str]:
            response = agents_client.messages.get_last_message_by_role(
                thread_id=thread_id, role=MessageRole.AGENT
            )
            if not response or response.id == last_message_id:
                return last_message_id
            print("\nAgent response:")
            print("\n".join((t.text.value for t in response.text_messages)))
            for ann in response.url_citation_annotations:
                print(
                    f"URL Citation: [{ann.url_citation.title}]({ann.url_citation.url})"
                )
            return response.id

        def create_research_summary(
            message: ThreadMessage, filepath: str = "research_summary.md"
        ) -> None:
            if not message:
                print("No message content provided, cannot create research summary.")
                return
            with open(filepath, "w", encoding="utf-8") as fp:
                text_summary = "\n\n".join(
                    [t.text.value.strip() for t in message.text_messages]
                )
                fp.write(text_summary)
                if message.url_citation_annotations:
                    fp.write("\n\n## References\n")
                    seen_urls = set()
                    for ann in message.url_citation_annotations:
                        url = ann.url_citation.url
                        title = ann.url_citation.title or url
                        if url not in seen_urls:
                            fp.write(f"- [{title}]({url})\n")
                            seen_urls.add(url)
            print(f"Research summary written to '{filepath}'.")

        project_client = _resources.enter_context(
            AIProjectClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        conn_id = project_client.connections.get(
            name=os.environ["FOUNDRY_BING_RESOURCE_NAME"]
        ).id
        deep_research_tool = DeepResearchTool(
            bing_grounding_connection_id=conn_id,
            deep_research_model=os.environ[
                "FOUNDRY_DEEP_RESEARCH_MODEL_DEPLOYMENT_NAME"
            ],
        )
        agents_client = _resources.enter_context(
            AgentsClient(
                endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        agent = agents_client.create_agent(
            model=os.environ["FOUNDRY_MODEL_NAME"],
            name="my-agent",
            instructions="You are a helpful Agent that assists in researching scientific topics.",
            tools=deep_research_tool.definitions,
        )
        print(f"Created agent, ID: {agent.id}")
        thread = agents_client.threads.create()
        print(f"Created thread, ID: {thread.id}")
        message = agents_client.messages.create(
            thread_id=thread.id,
            role="user",
            content="Assess the UK outlook for 2026 economic growth and inflation from IMF sources. Provide a detailed report.",
        )
        print(f"Created message, ID: {message.id}")
        print(
            "Start processing the message... this might take a few minutes to finish."
        )
        run = agents_client.runs.create(thread_id=thread.id, agent_id=agent.id)
        last_message_id = None
        while run.status in ("queued", "in_progress"):
            time.sleep(1)
            run = agents_client.runs.get(thread_id=thread.id, run_id=run.id)
            last_message_id = fetch_and_print_new_agent_response(
                thread_id=thread.id,
                agents_client=agents_client,
                last_message_id=last_message_id,
            )
            print(f"Run status: {run.status}")
        print(f"Run finished with status: {run.status}, ID: {run.id}")
        if run.status == "failed":
            print(f"Run failed: {run.last_error}")
        final_message = agents_client.messages.get_last_message_by_role(
            thread_id=thread.id, role=MessageRole.AGENT
        )
        if final_message:
            create_research_summary(final_message)
        agents_client.threads.delete(thread.id)
        agents_client.delete_agent(agent.id)
        agents_client.close()
        project_client.close()
        print("Deleted thread and agent, and closed the clients")
    # </doc_deep_research_samples_run_the_python_sample>


def main():
    examples = {"aip-python-009": example_009}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-009")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
