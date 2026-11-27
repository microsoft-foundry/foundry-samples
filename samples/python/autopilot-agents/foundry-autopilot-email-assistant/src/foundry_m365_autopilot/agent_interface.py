# Copyright (c) Microsoft. All rights reserved.

"""Agent base class.

Defines the abstract base class that agents must inherit from to work with the
generic host (``host_agent_server.py``). Python port of the
``AgentInterface`` from the Agent365 reference sample.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from microsoft_agents.hosting.core import Authorization, TurnContext


class AgentInterface(ABC):
    """Abstract base class that any hosted agent must inherit from.

    This ensures agents implement the required methods at class definition
    time, providing stronger guarantees than a :class:`typing.Protocol`.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the agent and any required resources."""

    @abstractmethod
    async def process_user_message(
        self,
        message: str,
        auth: Authorization,
        auth_handler_name: Optional[str],
        context: TurnContext,
    ) -> str:
        """Process a user message and return a response."""

    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up any resources used by the agent."""


def check_agent_inheritance(agent_class) -> bool:
    """Check that ``agent_class`` inherits from :class:`AgentInterface`."""

    if not issubclass(agent_class, AgentInterface):
        print(f"❌ Agent {agent_class.__name__} does not inherit from AgentInterface")
        return False
    return True
