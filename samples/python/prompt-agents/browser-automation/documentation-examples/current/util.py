# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Temporarily select one created agent version without losing an existing endpoint."""

from contextlib import contextmanager
from azure.core.exceptions import ResourceNotFoundError
from azure.ai.projects.models import (
    AgentEndpointConfig,
    FixedRatioVersionSelectionRule,
    ProtocolConfiguration,
    ResponsesProtocolConfiguration,
    VersionSelector,
)


@contextmanager
def create_version_with_endpoint(project_client, agent_name, *, definition, **kwargs):
    agent_existed = True
    try:
        original_endpoint = project_client.agents.get(
            agent_name=agent_name
        ).agent_endpoint
    except ResourceNotFoundError:
        agent_existed = False
        original_endpoint = None
    if agent_existed and original_endpoint is None:
        raise ValueError(
            "Use a new agent name or an agent with an existing endpoint. "
            "This example cannot safely restore an unconfigured existing agent."
        )
    created = project_client.agents.create_version(
        agent_name=agent_name, definition=definition, **kwargs
    )
    print(f"Created agent {created.name}, version {created.version}")
    try:
        project_client.agents.update_details(
            agent_name=agent_name,
            agent_endpoint=AgentEndpointConfig(
                version_selector=VersionSelector(
                    version_selection_rules=[
                        FixedRatioVersionSelectionRule(
                            agent_version=created.version, traffic_percentage=100
                        )
                    ]
                ),
                protocol_configuration=ProtocolConfiguration(
                    responses=ResponsesProtocolConfiguration()
                ),
            ),
        )
        yield created
    finally:
        if agent_existed:
            project_client.agents.update_details(
                agent_name=agent_name, agent_endpoint=original_endpoint
            )
            project_client.agents.delete_version(
                agent_name=agent_name, agent_version=created.version, force=True
            )
        else:
            project_client.agents.delete(agent_name=agent_name, force=True)
