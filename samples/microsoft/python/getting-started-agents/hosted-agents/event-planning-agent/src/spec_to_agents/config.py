# Copyright (c) Microsoft. All rights reserved.
from typing import Any


def get_default_model_config() -> dict[str, Any]:
    """
    Get the default model configuration for agents.

    Returns
    -------
    dict[str, Any]
        Default model configuration settings
    """
    return {
        "additional_chat_options": {
            "reasoning": {"effort": "minimal"}  # Use "minimal" for minimal reasoning
        },
        "store": True,  # use service managed threads
    }
