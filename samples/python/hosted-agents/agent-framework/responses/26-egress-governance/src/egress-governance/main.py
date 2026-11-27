# Copyright (c) Microsoft. All rights reserved.

"""Model-free Agent Framework host for the governance admission walkthrough."""

import logging

from agent_framework import Executor, Message, WorkflowBuilder, WorkflowContext, handler
from agent_framework_foundry_hosting import ResponsesHostServer


class GovernanceProbe(Executor):
    @handler
    async def respond(
        self, messages: list[Message], context: WorkflowContext[None, str]
    ) -> None:
        await context.yield_output("Governance sample ready.")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    probe = GovernanceProbe(id="governance-probe")
    agent = (
        WorkflowBuilder(start_executor=probe, output_from=[probe]).build().as_agent()
    )
    ResponsesHostServer(agent).run()


if __name__ == "__main__":
    main()
