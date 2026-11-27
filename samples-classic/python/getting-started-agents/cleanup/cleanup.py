# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Explicitly remove only caller-selected classic sample resources."""

import argparse
import os

KINDS = ("agent", "thread", "file", "vector-store")


def delete_resource(kind: str, identifier: str) -> None:
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    if kind not in KINDS or not identifier.strip():
        raise ValueError(
            "Provide a supported resource kind and a non-empty identifier."
        )
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project,
    ):
        if kind == "agent":
            project.agents.delete_agent(agent_id=identifier)
        elif kind == "thread":
            project.agents.threads.delete(thread_id=identifier)
        elif kind == "file":
            project.agents.files.delete(file_id=identifier)
        elif kind == "vector-store":
            project.agents.vector_stores.delete(vector_store_id=identifier)
    print(f"Cleanup request completed for {kind}: {identifier}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=KINDS)
    parser.add_argument("identifier")
    parser.add_argument(
        "--confirm",
        action="store_true",
        required=True,
        help="Confirm that you own the selected sample resource.",
    )
    options = parser.parse_args()
    delete_resource(options.kind, options.identifier)


if __name__ == "__main__":
    main()
