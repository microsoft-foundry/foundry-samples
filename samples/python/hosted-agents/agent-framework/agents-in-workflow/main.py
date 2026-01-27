# Copyright (c) Microsoft. All rights reserved.

from agent_framework import ConcurrentBuilder
from agent_framework.azure import AzureOpenAIChatClient
from azure.ai.agentserver.agentframework import from_agent_framework
from azure.identity import DefaultAzureCredential  # pyright: ignore[reportUnknownVariableType]


def create_workflow_builder():
    # Create agents
    researcher = AzureOpenAIChatClient(credential=DefaultAzureCredential()).create_agent(
        instructions=(
            "You're an expert market and product researcher. "
            "Given a prompt, provide concise, factual insights, opportunities, and risks."
        ),
        name="researcher",
    )
    marketer = AzureOpenAIChatClient(credential=DefaultAzureCredential()).create_agent(
        instructions=(
            "You're a creative marketing strategist. "
            "Craft compelling value propositions and target messaging aligned to the prompt."
        ),
        name="marketer",
    )
    legal = AzureOpenAIChatClient(credential=DefaultAzureCredential()).create_agent(
        instructions=(
            "You're a cautious legal/compliance reviewer. "
            "Highlight constraints, disclaimers, and policy concerns based on the prompt."
        ),
        name="legal",
    )

    # Build a concurrent workflow
    workflow_builder = ConcurrentBuilder().participants([researcher, marketer, legal])

    return workflow_builder

def main():
    # Run the agent as a hosted agent
    from_agent_framework(create_workflow_builder().build).run()


if __name__ == "__main__":
    main()
