# Copyright (c) Microsoft. All rights reserved.

"""Custom message types for workflow human-in-the-loop interactions."""

from dataclasses import dataclass, field
from typing import Any

from agent_framework import ChatMessage
from pydantic import BaseModel, Field
from typing_extensions import Literal


@dataclass
class HumanFeedbackRequest:
    """
    Request for human input during event planning workflow.

    This dataclass is used with ctx.request_info() to pause the workflow
    and request clarification, selection, or approval from the user.

    Attributes
    ----------
    prompt : str
        Clear question or instruction for the user
    context : dict[str, Any]
        Supporting information such as options, data, constraints
    request_type : str
        Category of request (e.g., "clarification", "selection", "approval")
    requesting_agent : str
        ID of the specialist agent that requested this input
    conversation : list[ChatMessage]
        Full conversation history up to this point, used to restore context
        when routing back to the requesting agent after human feedback

    Examples
    --------
    >>> HumanFeedbackRequest(
    ...     prompt="Which venue do you prefer?",
    ...     context={"venues": [{"name": "Venue A", "capacity": 50}]},
    ...     request_type="selection",
    ...     requesting_agent="venue",
    ...     conversation=[ChatMessage(Role.USER, text="Plan a party")],
    ... )
    """

    prompt: str
    context: dict[str, Any]
    request_type: str
    requesting_agent: str
    conversation: list[ChatMessage] = field(default_factory=list)  # type: ignore


class SpecialistOutput(BaseModel):
    """
    Structured output from each specialist agent.

    This model enforces that specialists provide:
    1. A concise summary of their work
    2. Routing decision (next_agent or user_input_needed)
    3. Optional user prompt if input is needed

    Examples
    --------
    Route to next agent:
    >>> SpecialistOutput(summary="Researched 3 venues: A ($2k), B ($3k), C ($4k)", next_agent="budget")

    Request user input:
    >>> SpecialistOutput(
    ...     summary="Found 3 venue options",
    ...     next_agent=None,
    ...     user_input_needed=True,
    ...     user_prompt="Which venue do you prefer: A, B, or C?",
    ... )
    """

    summary: str = Field(description="Concise summary of this specialist's recommendations (max 200 words)")
    next_agent: Literal["venue", "budget", "catering", "logistics"] | None = Field(
        description=(
            "ID of next agent to route to ('venue', 'budget', 'catering', 'logistics'), or None if done/need user input, requests to other sub-agents from a sub-agent should always go through the coordinator (e.g. venue → event_coordinator → budget)"  # noqa: E501
        )
    )
    user_input_needed: bool = Field(default=False, description="Whether user input is required before proceeding")
    user_prompt: str | None = Field(default=None, description="Question to ask user if user_input_needed=True")


__all__ = ["HumanFeedbackRequest", "SpecialistOutput"]
