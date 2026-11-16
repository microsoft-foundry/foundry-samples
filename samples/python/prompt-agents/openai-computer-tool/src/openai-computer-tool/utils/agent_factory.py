"""Provision or delete the Azure AI Foundry Prompt Agent with the OpenAI Computer Tool (`ComputerTool`)."""

from azure.ai.projects.models import ComputerTool, PromptAgentDefinition

from utils.settings import (
    AGENT_NAME,
    PROMPTS_PATH,
    SRC_DIR,
    get_model_deployment_name,
    get_project_client,
    get_project_endpoint,
    load_agent_instructions,
)


def provision_agent(agent_name: str = AGENT_NAME) -> None:
    """Create a new Prompt Agent version in Azure AI Foundry with `ComputerTool()` (`{"type": "computer"}`)."""
    endpoint = get_project_endpoint()
    model = get_model_deployment_name()
    instructions = load_agent_instructions()

    definition = PromptAgentDefinition(
        model=model,
        instructions=instructions,
        tools=[ComputerTool()],
    )

    print(f"Provisioning Prompt Agent '{agent_name}' on {endpoint} ...")
    print(f"  Model        : {model}")
    print(f"  Tool         : {ComputerTool().as_dict()}")
    print(f"  Instructions : {PROMPTS_PATH.relative_to(SRC_DIR)}")

    with get_project_client() as client:
        agent = client.agents.create_version(
            agent_name=agent_name,
            definition=definition,
        )
        print(f"Agent created (id={agent.id}, name={agent.name}, version={agent.version})")


def delete_agent(agent_name: str = AGENT_NAME) -> None:
    """Delete all versions of the Prompt Agent from the Azure AI Foundry project."""
    with get_project_client() as client:
        versions = list(client.agents.list_versions(agent_name=agent_name))
        for version in versions:
            client.agents.delete_version(agent_name=agent_name, agent_version=version.version)
        print(f"Deleted {len(versions)} version(s) of '{agent_name}'.")
