"""Teams message selectors, matching the Hello World Autopilot."""

from collections.abc import Callable

from microsoft_agents.activity import Activity
from microsoft_agents.hosting.core import TurnContext

ActivityMatcher = Callable[[Activity], bool]


def selector(matcher: ActivityMatcher) -> Callable[[TurnContext], bool]:
    return lambda context: matcher(context.activity)


def teams_direct_message(activity: Activity) -> bool:
    return (
        _is_teams_message(activity)
        and activity.conversation is not None
        and activity.conversation.conversation_type == "personal"
    )


def teams_group_chat_message(activity: Activity) -> bool:
    return (
        _is_teams_message(activity)
        and activity.conversation is not None
        and activity.conversation.conversation_type == "groupChat"
    )


def teams_tagged_channel_message(activity: Activity) -> bool:
    return (
        _is_teams_message(activity)
        and activity.conversation is not None
        and activity.conversation.conversation_type == "channel"
        and activity.recipient is not None
        and any(
            mention.mentioned is not None
            and mention.mentioned.id == activity.recipient.id
            for mention in activity.get_mentions()
        )
    )


def _is_teams_message(activity: Activity) -> bool:
    return (
        activity.type == "message"
        and activity.channel_id is not None
        and activity.channel_id.channel == "msteams"
    )
