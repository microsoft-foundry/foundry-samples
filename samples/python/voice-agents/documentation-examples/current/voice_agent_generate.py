# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_127():
    # <doc_prompt_voice_agent_generate_from_natural_language>
    import os
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        AgentKind,
        GenerateVoiceAgentRequest,
        VoiceAgentDefinition,
    )
    from azure.identity import DefaultAzureCredential

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    agent_name = os.environ["FOUNDRY_VOICE_AGENT_NAME"]
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint, credential=credential, allow_preview=True
        ) as project_client,
    ):
        generated = project_client.beta.agents.create_from_prompt(
            GenerateVoiceAgentRequest(
                kind=AgentKind.VOICE,
                name=agent_name,
                goal="Create a friendly voice assistant that answers general questions. Keep replies to one or two sentences.",
            )
        )
        definition = generated.versions.latest.definition
        if not isinstance(definition, VoiceAgentDefinition):
            raise TypeError("The generated agent must have a voice definition.")
        print(f"Generated instructions:\n{definition.instructions}")
        definition.store = True
        created = project_client.agents.create_version(
            agent_name=agent_name, definition=definition
        )
        print(f"Created voice agent '{agent_name}', version {created.version}")
    # </doc_prompt_voice_agent_generate_from_natural_language>


def main():
    examples = {"aip-python-127": example_127}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-127")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
