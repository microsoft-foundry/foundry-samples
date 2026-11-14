"""Register the externally hosted weather agent in Foundry.

After this runs successfully, open the Foundry portal -> your project ->
Agents -> ``weather-agent`` to see the trace view light up with spans
emitted by the running agent.

Prereqs:
    * FOUNDRY_PROJECT_ENDPOINT env var
    * AAD credentials with permission to create agents in the project
    * The external runtime (weather_agent.py) is already emitting OTel
      spans to the Application Insights connected to the Foundry project
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"), override=True)

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import ExternalAgentDefinition
from azure.identity import DefaultAzureCredential

AGENT_NAME = os.environ.get("AGENT_NAME", "weather-agent")
AGENT_ID = f"{AGENT_NAME}-v1"


def main() -> None:
    project_client = AIProjectClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
    )

    # create_version creates the agent if needed and adds a registration revision.
    agent = project_client.agents.create_version(
        agent_name=AGENT_NAME,
        description="Weather agent hosted outside Foundry.",
        definition=ExternalAgentDefinition(
            # Must match gen_ai.agent.id emitted by weather_agent.py.
            otel_agent_id=AGENT_ID,
        ),
    )

    print(f"Registered external agent: {agent.name}  (version {agent.version})")
    print(f"Resolved otel_agent_id  : {agent.definition.otel_agent_id}")
    print()
    print("Open the Foundry portal and navigate to:")
    print(f"  Project -> Agents -> {agent.name} -> Traces")
    print("to see traces emitted by the external runtime.")


if __name__ == "__main__":
    main()
