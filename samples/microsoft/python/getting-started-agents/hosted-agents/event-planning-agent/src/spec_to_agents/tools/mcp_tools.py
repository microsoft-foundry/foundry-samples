# Copyright (c) Microsoft. All rights reserved.

"""MCP (Model Context Protocol) tools integration."""

from agent_framework import MCPStdioTool, ToolProtocol


def create_mcp_tool_instances() -> dict[str, ToolProtocol]:
    """
    Create MCP tool instances for framework-managed lifecycle.

    Tools are NOT connected when created. They connect lazily on first use
    via __aenter__() and cleanup automatically via:
    - DevUI mode: DevUI's _cleanup_entities() calls tool.close()
    - Console mode: ChatAgent's exit stack manages __aenter__/__aexit__

    Returns
    -------
    dict[str, ToolProtocol]
        Dictionary of MCP tool instances (not connected yet)
        Keys:
        - "sequential-thinking": MCP sequential thinking tool for advanced reasoning

    Example
    -------
    Used with Singleton provider in DI container::

        class AppContainer(containers.DeclarativeContainer):
            global_tools = providers.Singleton(create_mcp_tool_instances)


        container = AppContainer()
        tools = container.global_tools()  # Get tool instances
        # Framework manages lifecycle from here

    Notes
    -----
    The MCP tools require async context management (__aenter__/__aexit__)
    for connection establishment and cleanup. This function creates the
    tool instances but does NOT connect them. The framework (Agent Framework
    or DevUI) handles the connection lifecycle automatically.
    """
    # Create MCP tool instance (not connected)
    sequential_thinking_tool = MCPStdioTool(
        name="sequential-thinking", command="npx", args=["-y", "@modelcontextprotocol/server-sequential-thinking"]
    )

    # Return tools dict for injection (framework manages lifecycle)
    return {"sequential-thinking": sequential_thinking_tool}


__all__ = ["create_mcp_tool_instances"]
