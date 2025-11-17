# Copyright (c) Microsoft. All rights reserved.

import os

from agent_framework.observability import setup_observability
from dotenv import load_dotenv

# Load environment variables at module import
load_dotenv()

# Enable observability (skip in container environments if not configured)
if not (os.getenv("CONTAINER_ENV") == "true" and not os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")):
    setup_observability()


def main() -> None:
    """Launch the branching workflow in DevUI with DI container."""
    import logging

    from agent_framework.devui import serve

    from spec_to_agents.agents import export_agents
    from spec_to_agents.container import AppContainer
    from spec_to_agents.workflow import export_workflow

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger(__name__)

    # Initialize DI container and wire modules for dependency injection
    container = AppContainer()
    container.wire(modules=[__name__])

    # MCP tools now work in DevUI mode - framework manages lifecycle
    # No override needed, no init_resources() needed

    # Get port from environment (for container deployments) or use default
    port = int(os.getenv("PORT", "8080"))
    # Disable auto_open in container environments
    auto_open = os.getenv("ENVIRONMENT") != "production"
    # Bind to 0.0.0.0 in container environments for external access
    host = "0.0.0.0" if os.getenv("CONTAINER_ENV") == "true" else "localhost"  # noqa: S104

    logger.info("Starting Agent Workflow DevUI...")
    logger.info(f"Available at: http://{host}:{port}")

    # Load entities synchronously (no async context needed)
    workflows = export_workflow()
    agents = export_agents()

    # DevUI's serve() handles MCP tool lifecycle via _cleanup_entities()
    # Use localhost for local dev security; 0.0.0.0 for container deployments
    # Dependencies (client, global_tools) are injected automatically into workflow/agent builders
    serve(entities=workflows + agents, port=port, host=host, auto_open=auto_open)


if __name__ == "__main__":
    main()
