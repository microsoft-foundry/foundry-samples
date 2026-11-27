# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_055():
    # <doc_mcp_authentication_flow_using_oauth_identity_passthrough>
    from contextlib import ExitStack

    with ExitStack() as _resources:
        import os
        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential

        project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        agent_name = os.environ["FOUNDRY_AGENT_NAME"]
        user_input = "Use the MCP tool to complete my request."
        project = _resources.enter_context(
            AIProjectClient(
                endpoint=project_endpoint,
                credential=_resources.enter_context(DefaultAzureCredential()),
            )
        )
        openai = _resources.enter_context(
            project.get_openai_client(agent_name=agent_name)
        )
        response = openai.responses.create(input=user_input, tool_choice="required")
        for item in response.output:
            if item.type == "oauth_consent_request":
                print(f"Open this URL to authorize access: {item.consent_link}")
    # </doc_mcp_authentication_flow_using_oauth_identity_passthrough>


def main():
    examples = {"aip-python-055": example_055}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-055")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
