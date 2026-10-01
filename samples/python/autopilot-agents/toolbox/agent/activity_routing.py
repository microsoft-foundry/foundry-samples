"""Activity selectors for the Microsoft Teams surfaces supported by this agent."""

from __future__ import annotations

from collections.abc import Callable

from microsoft_agents.activity import Activity
from microsoft_agents.hosting.core import TurnContext

ActivityMatcher = Callable[[Activity], bool]


def selector(matcher: ActivityMatcher) -> Callable[[TurnContext], bool]:
    """Adapt an activity predicate for ``AgentApplication.add_route``."""
    return lambda context: matcher(context.activity)


def teams_direct_message(activity: Activity) -> bool:
    return (
        _is_message_on(activity, "msteams")
        and activity.conversation is not None
        and activity.conversation.conversation_type == "personal"
    )


def teams_group_chat_message(activity: Activity) -> bool:
    return (
        _is_message_on(activity, "msteams")
        and activity.conversation is not None
        and activity.conversation.conversation_type == "groupChat"
    )


def teams_tagged_channel_message(activity: Activity) -> bool:
    return (
        _is_message_on(activity, "msteams")
        and activity.conversation is not None
        and activity.conversation.conversation_type == "channel"
        and _agent_is_mentioned(activity)
    )


def _is_message_on(activity: Activity, channel: str) -> bool:
    return (
        activity.type == "message"
        and activity.channel_id is not None
        and activity.channel_id.channel == channel
    )


def _agent_is_mentioned(activity: Activity) -> bool:
    if activity.recipient is None:
        return False

    return any(
        mention.mentioned is not None
        and mention.mentioned.id == activity.recipient.id
        for mention in activity.get_mentions()
    )
