import base64
import os
from dotenv import load_dotenv

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, ImageGenTool

load_dotenv()

project_client = AIProjectClient(
    endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(),
)

openai_client = project_client.get_openai_client()

with project_client:
    # <create_agent_with_image_gen_tool>
    agent = project_client.agents.create_version(
        agent_name="MyAgent",
        definition=PromptAgentDefinition(
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            instructions="Generate images based on user prompts",
            tools=[ImageGenTool(quality="low", size="1024x1024")],
        ),
        description="Agent for image generation.",
    )
    # </create_agent_with_image_gen_tool>
    print(f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})")
    response = openai_client.responses.create(
        input="Generate an image of Microsoft logo.",
        extra_headers={
            "x-ms-oai-image-generation-deployment": "gpt-image-1"
        },  # this is required at the moment for image generation
        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    )
    print(f"Response created: {response.id}")
    # Save the image to a file
    # <download_generated_image>
    image_data = [output.result for output in response.output if output.type == "image_generation_call"]

    if image_data and image_data[0]:
        print("Downloading generated image...")
        filename = "microsoft.png"
        file_path = os.path.abspath(filename)

        with open(file_path, "wb") as f:
            f.write(base64.b64decode(image_data[0]))
    # </download_generated_image>
        print(f"Image downloaded and saved to: {file_path}")
    # uncomment the following lines to clean up the created agent after running the sample
    #print("\nCleaning up...")
    #project_client.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
    #print("Agent deleted")