# Copyright (c) Microsoft. All rights reserved.

"""Dependency injection container for application-wide dependencies."""

from dependency_injector import containers, providers

from spec_to_agents.config import get_default_model_config
from spec_to_agents.tools.mcp_tools import create_mcp_tool_instances  # Changed import
from spec_to_agents.utils.clients import create_agent_client_for_devui


class AppContainer(containers.DeclarativeContainer):
    """
    Application-wide dependency injection container.

    Manages lifecycle and injection of:
    - Azure AI agent client (singleton)
    - Global tools dictionary (MCP tools, framework-managed lifecycle)
    - Model configuration (singleton)

    The tools provider returns a dict[str, ToolProtocol] containing globally
    shared tools (currently just MCP sequential-thinking tool). Agent-specific
    tools (web search, code interpreter, weather, calendar) are initialized
    inside each agent's create_agent() factory function, not via DI injection.

    Agent factories can selectively access global tools by key:
        global_tools["sequential-thinking"]

    Usage in main.py (DevUI mode):
        container = AppContainer()
        container.wire(modules=[...])
        workflows = export_workflow()
        agents = export_agents()
        serve(entities=workflows + agents)
        # DevUI's _cleanup_entities() handles MCP tool cleanup

    Usage in console.py (CLI mode):
        container = AppContainer()
        container.wire(modules=[...])
        async with container.client():
            workflow = build_event_planning_workflow()
            # ChatAgent's exit stack handles MCP tool lifecycle

    Notes
    -----
    MCP tools connect lazily on first use via __aenter__() and cleanup
    automatically via framework's exit stack (console.py) or DevUI's
    _cleanup_entities() (main.py). No manual init_resources() or
    shutdown_resources() needed.
    """

    # Configuration
    config = providers.Configuration()

    # Client provider (singleton factory)
    # Uses non-context-managed client for DI compatibility
    client = providers.Singleton(
        create_agent_client_for_devui,
    )

    # Global tools provider (singleton factory, framework-managed lifecycle)
    # Provides dict[str, ToolProtocol] with MCP tool instances
    # Framework handles async context management (__aenter__/__aexit__)
    global_tools = providers.Singleton(
        create_mcp_tool_instances,
    )

    model_config = providers.Singleton(
        get_default_model_config,
    )

    # Wiring configuration: modules that use @inject
    wiring_config = containers.WiringConfiguration(
        packages=[
            "spec_to_agents.agents",
            "spec_to_agents.workflow",
        ]
    )
