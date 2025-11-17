# Copyright (c) Microsoft. All rights reserved.

"""Tools for event planning agents."""

from spec_to_agents.tools.bing_search import web_search
from spec_to_agents.tools.calendar import create_calendar_event, delete_calendar_event, list_calendar_events
from spec_to_agents.tools.weather import get_weather_forecast

__all__ = [
    "create_calendar_event",
    "delete_calendar_event",
    "get_weather_forecast",
    "list_calendar_events",
    "web_search",
]
