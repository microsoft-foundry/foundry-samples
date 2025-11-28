# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------
from azure.ai.agentserver.agentframework import from_agent_framework
from dotenv import load_dotenv


def main() -> None:
    from spec_to_agents.container import AppContainer
    from spec_to_agents.workflow.core import build_event_planning_workflow

    load_dotenv()

    container = AppContainer()
    container.wire(modules=[__name__])

    from_agent_framework(lambda _: build_event_planning_workflow().as_agent("event_planning_agent")).run()


if __name__ == "__main__":
    main()
