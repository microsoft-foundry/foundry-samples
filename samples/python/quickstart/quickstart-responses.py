import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

load_dotenv()

print(f"Using AZURE_AI_FOUNDRY_PROJECT_ENDPOINT: {os.environ['AZURE_AI_FOUNDRY_PROJECT_ENDPOINT']}")
print(f"Using AZURE_AI_FOUNDRY_MODEL_DEPLOYMENT_NAME: {os.environ['AZURE_AI_FOUNDRY_MODEL_DEPLOYMENT_NAME']}")

project_client = AIProjectClient(
    endpoint=os.environ["AZURE_AI_FOUNDRY_PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(),
)

openai_client = project_client.get_openai_client()

response = openai_client.responses.create(
    model=os.environ["AZURE_AI_FOUNDRY_MODEL_DEPLOYMENT_NAME"],
    input="What is the size of France in square miles?",
)
print(f"Response output: {response.output_text}")