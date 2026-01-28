# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
"""
DESCRIPTION:
    This sample demonstrates how to evaluate the Modern Workplace Assistant
    using the cloud evaluation API with built-in evaluators.

USAGE:
    python evaluate.py

    Before running:
    pip install "azure-ai-projects>=2.0.0b1" python-dotenv

    Set these environment variables:
    1) AZURE_AI_PROJECT_ENDPOINT - Your Foundry project endpoint
    2) AZURE_AI_MODEL_DEPLOYMENT_NAME - Model deployment name (e.g., gpt-4o-mini)
    3) AZURE_AI_AGENT_NAME - (Optional) Agent name to use
"""

import os
import time
from typing import Union
from pprint import pprint
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from openai.types.eval_create_params import DataSourceConfigCustom
from openai.types.evals.run_create_response import RunCreateResponse
from openai.types.evals.run_retrieve_response import RunRetrieveResponse

# <configure_evaluation>
load_dotenv()
endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
model_deployment_name = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    project_client.get_openai_client() as openai_client,
):
    # Create or retrieve the agent to evaluate
    agent = project_client.agents.create_version(
        agent_name=os.environ.get("AZURE_AI_AGENT_NAME", "Modern Workplace Assistant"),
        definition=PromptAgentDefinition(
            model=model_deployment_name,
            instructions="You are a helpful Modern Workplace Assistant that answers questions about company policies and technical guidance.",
        ),
    )
    print(f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})")

    # Define the data schema for evaluation
    data_source_config = DataSourceConfigCustom(
        type="custom",
        item_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        },
        include_sample_schema=True,
    )

    # Define testing criteria with built-in evaluators
    # data_mapping: sample.output_text = agent string response, sample.output_items = structured JSON with tool calls
    testing_criteria = [
        {
            "type": "azure_ai_evaluator",
            "name": "violence_detection",
            "evaluator_name": "builtin.violence",
            "data_mapping": {"query": "{{item.query}}", "response": "{{sample.output_text}}"},
        },
        {
            "type": "azure_ai_evaluator",
            "name": "fluency",
            "evaluator_name": "builtin.fluency",
            "initialization_parameters": {"deployment_name": f"{model_deployment_name}"},
            "data_mapping": {"query": "{{item.query}}", "response": "{{sample.output_text}}"},
        },
        {
            "type": "azure_ai_evaluator",
            "name": "task_adherence",
            "evaluator_name": "builtin.task_adherence",
            "initialization_parameters": {"deployment_name": f"{model_deployment_name}"},
            "data_mapping": {"query": "{{item.query}}", "response": "{{sample.output_items}}"},
        },
    ]

    # Create the evaluation object
    eval_object = openai_client.evals.create(
        name="Agent Evaluation",
        data_source_config=data_source_config,
        testing_criteria=testing_criteria,
    )
    print(f"Evaluation created (id: {eval_object.id}, name: {eval_object.name})")
# </configure_evaluation>

# <run_cloud_evaluation>
    # Define the data source for the evaluation run
    # This targets the agent with test queries
    data_source = {
        "type": "azure_ai_target_completions",
        "source": {
            "type": "file_content",
            "content": [
                {"item": {"query": "What is Contoso's remote work policy?"}},
                {"item": {"query": "What are the security requirements for remote employees?"}},
                {"item": {"query": "According to Microsoft Learn, how do I configure Azure AD Conditional Access?"}},
                {"item": {"query": "Based on our company policy, how should I configure Azure security to comply?"}},
            ],
        },
        "input_messages": {
            "type": "template",
            "template": [
                {"type": "message", "role": "user", "content": {"type": "input_text", "text": "{{item.query}}"}}
            ],
        },
        "target": {
            "type": "azure_ai_agent",
            "name": agent.name,
            "version": agent.version,
        },
    }

    # Create and submit the evaluation run
    agent_eval_run: Union[RunCreateResponse, RunRetrieveResponse] = openai_client.evals.runs.create(
        eval_id=eval_object.id,
        name=f"Evaluation Run for Agent {agent.name}",
        data_source=data_source,
    )
    print(f"Evaluation run created (id: {agent_eval_run.id})")
# </run_cloud_evaluation>

# <retrieve_evaluation_results>
    # Poll until the evaluation run completes
    while agent_eval_run.status not in ["completed", "failed"]:
        agent_eval_run = openai_client.evals.runs.retrieve(
            run_id=agent_eval_run.id,
            eval_id=eval_object.id
        )
        print(f"Waiting for eval run to complete... current status: {agent_eval_run.status}")
        time.sleep(5)

    if agent_eval_run.status == "completed":
        print("\n✓ Evaluation run completed successfully!")
        print(f"Result Counts: {agent_eval_run.result_counts}")

        # Retrieve detailed output items
        output_items = list(
            openai_client.evals.runs.output_items.list(
                run_id=agent_eval_run.id,
                eval_id=eval_object.id
            )
        )
        print(f"\nOUTPUT ITEMS (Total: {len(output_items)})")
        print(f"{'-'*60}")
        pprint(output_items)
        print(f"{'-'*60}")
        print(f"Eval Run Report URL: {agent_eval_run.report_url}")
    else:
        print("\n✗ Evaluation run failed.")

    # Cleanup
    openai_client.evals.delete(eval_id=eval_object.id)
    print("Evaluation deleted")

    project_client.agents.delete(agent_name=agent.name)
    print("Agent deleted")
# </retrieve_evaluation_results>
