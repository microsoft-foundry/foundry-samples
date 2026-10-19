"""Provision or delete the Azure AI Foundry Prompt Agent with the OpenAI Computer Tool (`ComputerTool`).

Follows the separate provisioning script pattern in `samples/python/prompt-agents/`:
    python provision_agent.py          # Create a new Prompt Agent version with ComputerTool()
    python provision_agent.py create   # Same as above
    python provision_agent.py delete   # Delete all versions of the Prompt Agent

Can also be invoked automatically after `azd provision` via `hooks/postprovision.*`.
"""

import argparse
import os

import dotenv
from azure.ai.projects.models import ComputerTool, PromptAgentDefinition

from sample_config import (
    AGENT_NAME,
    INSTRUCTIONS_PATH,
    get_model_deployment_name,
    get_project_client,
    get_project_endpoint,
    load_agent_instructions,
)

dotenv.load_dotenv()


def cmd_create(_args: argparse.Namespace) -> None:
    """Create a new Prompt Agent version in Azure AI Foundry with `ComputerTool()` (`{"type": "computer"}`)."""
    endpoint = get_project_endpoint()
    model = get_model_deployment_name()
    instructions = load_agent_instructions()

    definition = PromptAgentDefinition(
        model=model,
        instructions=instructions,
        tools=[ComputerTool()],
    )

    print(f"Provisioning Prompt Agent '{AGENT_NAME}' on {endpoint} ...")
    print(f"  Model        : {model}")
    print(f"  Tool         : {ComputerTool().as_dict()}")
    print(f"  Instructions : {INSTRUCTIONS_PATH.relative_to(INSTRUCTIONS_PATH.parent.parent.parent)}")

    if os.environ.get("OPENAI_API_KEY"):
        print(f"Agent definition ready (name={AGENT_NAME}, model={model}, tool=ComputerTool).")
        return

    with get_project_client() as client:
        agent = client.agents.create_version(
            agent_name=AGENT_NAME,
            definition=definition,
        )
        print(f"Agent created (id={agent.id}, name={agent.name}, version={agent.version})")


def cmd_delete(_args: argparse.Namespace) -> None:
    """Delete all versions of the Prompt Agent from the Azure AI Foundry project."""
    with get_project_client() as client:
        versions = list(client.agents.list_versions(agent_name=AGENT_NAME))
        for v in versions:
            client.agents.delete_version(agent_name=AGENT_NAME, agent_version=v.version)
        print(f"Deleted {len(versions)} version(s) of '{AGENT_NAME}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="cmd")
    subparsers.add_parser("create", help="Create a new Prompt Agent version").set_defaults(func=cmd_create)
    subparsers.add_parser("delete", help="Delete all versions of the Prompt Agent").set_defaults(func=cmd_delete)

    args = parser.parse_args()
    func = getattr(args, "func", cmd_create)
    func(args)


if __name__ == "__main__":
    main()
