import os
from pathlib import Path
from uuid import uuid4

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv


def main():
    load_dotenv(Path(__file__).with_name(".env"))
    project_endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"].strip()
    connection_name = os.environ["CONNECTED_MODEL_CONNECTION_NAME"].strip()
    model_name = os.environ["CONNECTED_MODEL_NAME"].strip()
    if not all((project_endpoint, connection_name, model_name)):
        raise ValueError("Set all three settings from .env-template before running.")

    connected_model = f"{connection_name}/{model_name}"

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=project_endpoint, credential=credential
        ) as project_client,
    ):
        agent = project_client.agents.create_version(
            agent_name=f"connected-model-responses-{uuid4().hex[:8]}",
            definition=PromptAgentDefinition(
                model=connected_model,
                instructions="You are a helpful assistant. Answer clearly and concisely.",
            ),
        )
        print(f"Connected model: {connected_model}")
        print(f"Temporary agent: {agent.name} (version {agent.version})")

        try:
            with project_client.get_openai_client(agent_name=agent.name) as openai_client:
                response = openai_client.responses.create(
                    input="Explain how a rainbow forms in three short steps.",
                )
                if not response.output_text or not response.output_text.strip():
                    raise RuntimeError("The connected model returned no output text.")
                print(f"Response output: {response.output_text}")
        finally:
            project_client.agents.delete_version(
                agent_name=agent.name, agent_version=agent.version
            )
            print("Temporary agent version deleted.")


if __name__ == "__main__":
    main()
