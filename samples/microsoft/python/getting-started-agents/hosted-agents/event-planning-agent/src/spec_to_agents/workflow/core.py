# Copyright (c) Microsoft. All rights reserved.

"""Event planning multi-agent workflow definition and lazy initialization."""

from agent_framework import (
    AgentExecutor,
    BaseChatClient,
    Workflow,
    WorkflowBuilder,
)
from dependency_injector.wiring import Provide, inject

from spec_to_agents.agents import (
    budget_analyst,
    catering_coordinator,
    event_coordinator,
    logistics_manager,
    venue_specialist,
)
from spec_to_agents.workflow.executors import EventPlanningCoordinator


@inject
def build_event_planning_workflow(
    client: BaseChatClient = Provide["client"],
) -> Workflow:
    """
    Build the multi-agent event planning workflow with human-in-the-loop capabilities.

    Architecture
    ------------
    Uses coordinator-centric star topology with 5 executors:
    - EventPlanningCoordinator: Manages routing and human-in-the-loop using service-managed threads
    - VenueSpecialist: Venue research via custom web_search tool
    - BudgetAnalyst: Financial planning via Code Interpreter
    - CateringCoordinator: Food planning via custom web_search tool
    - LogisticsManager: Scheduling, weather, calendar management

    Conversation history is managed automatically by service-managed threads (store=True).
    No manual message tracking or summarization overhead.

    Workflow Pattern
    ----------------
    Star topology with bidirectional edges:
    - Coordinator ←→ Venue Specialist
    - Coordinator ←→ Budget Analyst
    - Coordinator ←→ Catering Coordinator
    - Coordinator ←→ Logistics Manager

    Human-in-the-Loop
    ------------------
    Specialists can call request_user_input tool when they need clarification,
    selection, or approval. The coordinator intercepts these tool calls and uses
    ctx.request_info() + @response_handler to pause the workflow, emit
    RequestInfoEvent, and resume with user responses via DevUI.

    Parameters
    ----------
    client : AzureAIAgentClient
        Azure AI agent client for creating workflow agents.
        Should be managed via async context manager in calling code for automatic cleanup.
    mcp_tool : MCPStdioTool | None, optional
        Connected MCP tool for coordinator's sequential thinking capabilities.
        If None, coordinator operates without MCP tool assistance.
        Must be connected (within async context manager) before passing to workflow.

    Returns
    -------
    Workflow
        Configured workflow instance ready for execution via DevUI
        or programmatic invocation.

    Notes
    -----
    The workflow uses sequential orchestration managed by the coordinator.
    Human-in-the-loop is optional: the workflow can complete autonomously
    if agents have sufficient context and choose not to request user input.

    Requires Microsoft Foundry credentials configured via environment variables
    or Azure CLI authentication.

    The client parameter should be managed as an async context manager in the
    calling code to ensure proper cleanup of agents when the workflow is done.
    """
    # Create agents
    coordinator_agent = event_coordinator.create_agent()
    venue_agent = venue_specialist.create_agent()
    budget_agent = budget_analyst.create_agent()
    catering_agent = catering_coordinator.create_agent()
    logistics_agent = logistics_manager.create_agent()
    # Create coordinator executor with routing logic
    coordinator = EventPlanningCoordinator(coordinator_agent)

    # Create specialist executors
    venue_exec = AgentExecutor(agent=venue_agent, id="venue")
    budget_exec = AgentExecutor(agent=budget_agent, id="budget")
    catering_exec = AgentExecutor(agent=catering_agent, id="catering")
    logistics_exec = AgentExecutor(agent=logistics_agent, id="logistics")

    # Build workflow with bidirectional star topology
    workflow = (
        WorkflowBuilder(
            name="Event Planning Workflow",
            description=(
                "Multi-agent event planning workflow with venue selection, budgeting, "
                "catering, and logistics coordination. Supports human-in-the-loop for "
                "clarification and approval."
            ),
            max_iterations=30,  # Prevent infinite loops
        )
        # Set coordinator as start executor
        .set_start_executor(coordinator)
        # Bidirectional edges: Coordinator ←→ Each Specialist
        .add_edge(coordinator, venue_exec)
        .add_edge(venue_exec, coordinator)
        .add_edge(coordinator, budget_exec)
        .add_edge(budget_exec, coordinator)
        .add_edge(coordinator, catering_exec)
        .add_edge(catering_exec, coordinator)
        .add_edge(coordinator, logistics_exec)
        .add_edge(logistics_exec, coordinator)
        .build()
    )

    # Set stable ID to prevent URL issues on restart
    workflow.id = "event-planning-workflow"
    return workflow
