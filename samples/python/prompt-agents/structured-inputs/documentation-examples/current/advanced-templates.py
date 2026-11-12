# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_067():
    # <doc_structured_inputs_advanced_template_syntax>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import (
            PromptAgentDefinition,
            StructuredInputDefinition,
        )
        from azure.identity import DefaultAzureCredential

        PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        AGENT_NAME = "weather-assistant"
        with AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=_resources.enter_context(DefaultAzureCredential()),
        ) as project:
            instructions = "You are a weather assistant. Provide a helpful weather summary for the user.\n\nThe user asked about: {{location}}\nUse the following units: {{units}}\n\n{{#if includeForecast}}\nInclude a brief multi-day forecast in your response.\n{{else}}\nFocus only on the current conditions.\n{{/if}}\n\n{{#if preferences}}\nThe user has these additional preferences:\n{{#each preferences}}\n- {{this}}\n{{/each}}\n{{/if}}\n\nKeep the final answer clear and easy to read."
            agent = project.agents.create_version(
                agent_name=AGENT_NAME,
                definition=PromptAgentDefinition(
                    model="gpt-5-mini",
                    instructions=instructions,
                    structured_inputs={
                        "location": StructuredInputDefinition(
                            description="City or region to check weather for",
                            required=True,
                            schema={"type": "string"},
                        ),
                        "units": StructuredInputDefinition(
                            description="Temperature units (Celsius or Fahrenheit)",
                            default_value="Celsius",
                            schema={"type": "string"},
                        ),
                        "includeForecast": StructuredInputDefinition(
                            description="Whether to include a multi-day forecast",
                            default_value="false",
                            schema={"type": "boolean"},
                        ),
                        "preferences": StructuredInputDefinition(
                            description="Additional user preferences",
                            schema={"type": "array"},
                        ),
                    },
                ),
            )
            with project.get_openai_client(agent_name=agent.name) as openai:
                conversation = openai.conversations.create()
                response = openai.responses.create(
                    conversation=conversation.id,
                    input="What's the weather like?",
                    extra_body={
                        "structured_inputs": {
                            "location": "Seattle, WA",
                            "units": "Fahrenheit",
                            "includeForecast": True,
                            "preferences": ["Highlight UV index", "Include wind speed"],
                        }
                    },
                )
                print(response.output_text)
    # </doc_structured_inputs_advanced_template_syntax>


def main():
    examples = {"aip-python-067": example_067}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-067")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
