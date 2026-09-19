# Copyright (c) Microsoft. All rights reserved.

"""Echo Agent using the Activity protocol, published as a Microsoft 365 Autopilot.

A minimal Activity protocol agent that echoes the user's message back. Hosted by
``azure-ai-agentserver-activity`` for the Foundry platform contract and bridged
to the M365 Agents SDK for activity processing and outbound channel delivery
(e.g. Microsoft Teams).

This sample uses the package's **digital-worker** auth model
(``digital_worker=True``): outbound Bot Connector tokens are minted from the
agent's managed identity **blueprint** via federated identity, matching the
Autopilot (Microsoft 365 Agent 365) publishing model, where the deployed
agent is published as a tenant-scoped digital worker rather than a
single-tenant Teams bot tied to the instance identity.

Demonstrates:
- The ``ActivityAgentServerHost(digital_worker=True)`` setup for Autopilot agents
- Routing by activity type (``message``, ``conversationUpdate``)
- Structured logging
"""

import logging

# Configure logging first
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger("echo-autopilot-agent")

from azure.ai.agentserver.activity import ActivityAgentServerHost

# Digital-worker auth model: outbound tokens are minted from the agent
# identity blueprint (federated identity), not the instance identity.
host = ActivityAgentServerHost(digital_worker=True)
app = host.agent_app


@app.activity("message")
async def on_message(context, state):
    """Echo the user's message back."""
    user_text = (context.activity.text or "").strip()

    if user_text:
        reply = f"Echo : {user_text}"
        # Outbound delivery goes to the Bot Connector (serviceUrl). Guard it so a
        # transient delivery failure is logged instead of surfacing as a 500 on
        # the inbound webhook (which would make the Bot Connector retry).
        try:
            await context.send_activity(reply)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("[ERROR] Could not send echo reply: %s", exc)


@app.activity("conversationUpdate")
async def on_members_added(context, state):
    """Welcome new members."""
    members = context.activity.members_added or []
    logger.info("[MEMBERS] CONVERSATION UPDATE | members_added=%d", len(members))

    for member in members:
        if member.id != context.activity.recipient.id:
            member_name = getattr(member, "name", "Guest")
            logger.info("[WAVE] MEMBER ADDED | name=%s | id=%s", member_name, getattr(member, "id", "?"))
            try:
                await context.send_activity("Welcome! I'm an Autopilot echo agent — say something.")
                logger.info("[OK] Welcome message sent")
            except Exception as exc:
                logger.warning("[ERROR] Could not send welcome: %s", exc)


@app.error
async def on_error(context, error):
    """Handle unhandled errors."""
    logger.error("[ERROR] HANDLER ERROR | error=%s", error, exc_info=True)
    await context.send_activity(f"Sorry, something went wrong: {error}")


if __name__ == "__main__":
    logger.info("Starting echo Autopilot agent (bring-your-own) ...")
    host.run()
