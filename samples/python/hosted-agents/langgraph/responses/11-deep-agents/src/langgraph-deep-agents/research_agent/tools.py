"""Research tools loaded from Microsoft Foundry."""

import os

from langchain_azure_ai.tools import AzureAIProjectToolbox
from langchain_core.tools import BaseTool


async def load_tools() -> list[BaseTool]:
    """Load all tools exposed by the configured Foundry Toolbox."""
    toolbox = AzureAIProjectToolbox(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        toolbox_name=os.environ["TOOLBOX_NAME"],
    )
    return await toolbox.get_tools()
