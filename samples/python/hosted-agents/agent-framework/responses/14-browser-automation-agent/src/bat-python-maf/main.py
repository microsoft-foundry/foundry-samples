# ruff: noqa: E402
from __future__ import annotations

import logging
import warnings

from dotenv import load_dotenv

from utils.agent_factory import build_agent
from utils.settings import make_settings
from utils.tool_catalog import ToolCatalogResponsesHostServer

warnings.filterwarnings("ignore", message=r"\[SKILLS\].*")

logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()
    settings = make_settings()
    if settings.verbose:
        logging.basicConfig(level=logging.INFO)
        logger.info("Foundry project endpoint: %s", settings.project_endpoint)
        logger.info("Model: %s", settings.model)
        logger.info("Toolbox: %s", settings.toolbox_name)
    agent, _ = build_agent(settings)
    ToolCatalogResponsesHostServer(agent).run()


if __name__ == "__main__":
    main()
