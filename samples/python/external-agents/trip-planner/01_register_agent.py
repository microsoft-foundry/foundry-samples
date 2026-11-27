"""Step 1: Register the trip planner in Foundry as an external agent.

The agent keeps running where it is. Registration tells Foundry which traces in
the connected Application Insights resource belong to it: the ones whose
gen_ai.agent.id matches otel_agent_id.
"""

import os

from azure.ai.projects.models import ExternalAgentDefinition

from tutorial_utils import AGENT_NAME, project_client


def main() -> None:
    """Register the agent with the same ID its traces carry."""
    with project_client() as project:
        agent = project.agents.create_version(
            agent_name=AGENT_NAME,
            description="Contoso Travel trip planner, running outside Foundry (fictional).",
            definition=ExternalAgentDefinition(
                otel_agent_id=os.environ.get("OTEL_AGENT_ID", "contoso-trip-planner")
            ),
        )
    print(f"Registered external agent {agent.name} (version {agent.version}).")


if __name__ == "__main__":
    main()
