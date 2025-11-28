# Copyright (c) Microsoft. All rights reserved.

"""
Shared constants for the spec-to-agents application.

This module contains configuration constants used across multiple modules
to avoid duplication and ensure consistency.
"""

# Agent color mappings for Rich console styling
# Maps agent name prefixes (case-insensitive) to Rich color names
AGENT_COLORS: dict[str, str] = {
    "venue": "blue",
    "budget": "green",
    "catering": "yellow",
    "logistics": "cyan",
    "coordinator": "magenta",
}
