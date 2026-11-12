# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Explicitly remove only caller-selected, sample-owned resources."""

import argparse
import os

KINDS = (
    "agent",
    "agent-version",
    "conversation",
    "file",
    "vector-store",
    "toolbox-version",
    "memory-store",
    "skill",
    "dataset-version",
    "eval",
)
VERSIONED = {"agent-version", "toolbox-version", "dataset-version"}


def delete_resource(
    kind: str, identifier: str, version: str | None, force: bool
) -> None:
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    if kind not in KINDS or not identifier.strip():
        raise ValueError(
            "Provide a supported resource kind and a non-empty identifier."
        )
    if kind in VERSIONED and not version:
        raise ValueError("A version is required for this resource kind.")
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=endpoint, credential=credential, allow_preview=True
        ) as project,
    ):
        if kind == "agent":
            project.agents.delete(agent_name=identifier, force=force)
        elif kind == "agent-version":
            if version is None:
                raise ValueError("An agent version is required.")
            project.agents.delete_version(
                agent_name=identifier, agent_version=version, force=force
            )
        elif kind == "toolbox-version":
            if version is None:
                raise ValueError("A toolbox version is required.")
            project.toolboxes.delete_version(name=identifier, version=version)
        elif kind == "dataset-version":
            if version is None:
                raise ValueError("A dataset version is required.")
            project.datasets.delete(name=identifier, version=version)
        elif kind == "memory-store":
            project.beta.memory_stores.delete(name=identifier)
        elif kind == "skill":
            project.beta.skills.delete(name=identifier)
        else:
            with project.get_openai_client() as openai:
                if kind == "conversation":
                    deleted = openai.conversations.delete(identifier)
                elif kind == "file":
                    deleted = openai.files.delete(identifier)
                elif kind == "vector-store":
                    deleted = openai.vector_stores.delete(identifier)
                elif kind == "eval":
                    deleted = openai.evals.delete(identifier)
                else:
                    raise ValueError("Unsupported OpenAI-compatible resource kind.")
                if not deleted.deleted:
                    raise RuntimeError(
                        f"The service did not delete {kind} {identifier}."
                    )
    print(f"Cleanup request completed for {kind}: {identifier}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=KINDS)
    parser.add_argument("identifier")
    parser.add_argument("--version")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow deleting an active agent or agent version.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        required=True,
        help="Confirm that you own the selected sample resource.",
    )
    options = parser.parse_args()
    if options.kind in VERSIONED and not options.version:
        parser.error("--version is required for this resource kind.")
    if options.force and options.kind not in {"agent", "agent-version"}:
        parser.error("--force applies only to agents and agent versions.")
    delete_resource(options.kind, options.identifier, options.version, options.force)


if __name__ == "__main__":
    main()
