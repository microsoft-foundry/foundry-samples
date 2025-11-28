# Copyright (c) Microsoft. All rights reserved.

"""Calendar management tools using iCalendar files."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Final

import pytz
from agent_framework import ai_function
from icalendar import Calendar, Event
from pydantic import Field

# Get calendar storage path from environment
CALENDAR_PATH: Final[Path] = Path(os.getenv("CALENDAR_STORAGE_PATH", "./data/calendars"))
CALENDAR_PATH.mkdir(parents=True, exist_ok=True)


@ai_function  # type: ignore[arg-type]
async def create_calendar_event(  # noqa: RUF029
    event_title: Annotated[str, Field(description="Title of the calendar event")],
    start_date: Annotated[str, Field(description="Start date in ISO format (YYYY-MM-DD)")],
    start_time: Annotated[str, Field(description="Start time in HH:MM format (24-hour)")],
    duration_hours: Annotated[int, Field(description="Duration in hours", ge=1, le=24)] = 1,
    location: Annotated[str, Field(description="Event location")] = "",
    description: Annotated[str, Field(description="Event description")] = "",
    calendar_name: Annotated[str, Field(description="Calendar name (filename without .ics)")] = "event_planning",
) -> str:
    """
    Create a new calendar event in an iCalendar file.

    Parameters
    ----------
    event_title : str
        Title of the calendar event
    start_date : str
        Start date in ISO format (YYYY-MM-DD)
    start_time : str
        Start time in HH:MM format (24-hour)
    duration_hours : int, optional
        Duration in hours (1-24), default is 1
    location : str, optional
        Event location
    description : str, optional
        Event description
    calendar_name : str, optional
        Calendar name (filename without .ics), default is "event_planning"

    Returns
    -------
    str
        Success message with event details or error message

    Notes
    -----
    Events are stored in iCalendar (.ics) files in the configured calendar storage path.
    If the calendar file doesn't exist, it will be created automatically.
    """
    try:
        # Parse date and time
        start_datetime_str = f"{start_date} {start_time}"
        start_dt = datetime.strptime(start_datetime_str, "%Y-%m-%d %H:%M")
        start_dt = pytz.UTC.localize(start_dt)
        end_dt = start_dt + timedelta(hours=duration_hours)

        # Load or create calendar
        calendar_file = CALENDAR_PATH / f"{calendar_name}.ics"
        if calendar_file.exists():
            with open(calendar_file, "rb") as f:  # noqa: ASYNC230
                cal = Calendar.from_ical(f.read())  # type: ignore
        else:
            cal = Calendar()  # type: ignore[no-untyped-call]
            cal.add("prodid", "-//Event Planning Agent//EN")  # type: ignore
            cal.add("version", "2.0")  # type: ignore

        # Create event
        event = Event()  # type: ignore[no-untyped-call]
        event.add("summary", event_title)  # type: ignore
        event.add("dtstart", start_dt)  # type: ignore
        event.add("dtend", end_dt)  # type: ignore
        event.add("dtstamp", datetime.now(pytz.UTC))  # type: ignore
        if location:
            event.add("location", location)  # type: ignore
        if description:
            event.add("description", description)  # type: ignore

        # Add event to calendar
        cal.add_component(event)  # type: ignore

        # Save calendar
        with open(calendar_file, "wb") as f:  # noqa: ASYNC230
            f.write(cal.to_ical())  # type: ignore

        return (
            f"Successfully created event '{event_title}' on {start_date} at {start_time} in calendar '{calendar_name}'"
        )

    except ValueError as e:
        return f"Error parsing date/time: {e!s}. Use YYYY-MM-DD for date and HH:MM for time."
    except Exception as e:
        return f"Error creating calendar event: {e!s}"


@ai_function  # type: ignore[arg-type]
async def list_calendar_events(  # noqa: RUF029
    calendar_name: Annotated[str, Field(description="Calendar name (filename without .ics)")] = "event_planning",
    start_date: Annotated[str | None, Field(description="Optional: Filter events from this date (YYYY-MM-DD)")] = None,
    end_date: Annotated[str | None, Field(description="Optional: Filter events until this date (YYYY-MM-DD)")] = None,
) -> str:
    """
    List events from an iCalendar file.

    Parameters
    ----------
    calendar_name : str, optional
        Calendar name (filename without .ics), default is "event_planning"
    start_date : str | None, optional
        Optional: Filter events from this date (YYYY-MM-DD)
    end_date : str | None, optional
        Optional: Filter events until this date (YYYY-MM-DD)

    Returns
    -------
    str
        Formatted list of events or error message

    Notes
    -----
    Events are listed with their date, time, and location (if specified).
    Date filters are inclusive.
    """
    try:
        calendar_file = CALENDAR_PATH / f"{calendar_name}.ics"
        if not calendar_file.exists():
            return f"Calendar '{calendar_name}' does not exist"

        with open(calendar_file, "rb") as f:  # noqa: ASYNC230
            cal = Calendar.from_ical(f.read())  # type: ignore

        # Parse date filters
        start_filter = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
        end_filter = datetime.strptime(end_date, "%Y-%m-%d") if end_date else None

        # Extract events
        events = []
        for component in cal.walk():  # type: ignore
            if component.name == "VEVENT":  # type: ignore
                summary = str(component.get("summary", "Untitled"))  # type: ignore
                dtstart = component.get("dtstart").dt  # type: ignore
                dtend = component.get("dtend").dt  # type: ignore
                location_val = component.get("location")  # type: ignore
                location_str = str(location_val) if location_val else ""  # type: ignore

                # Apply date filters
                if start_filter and dtstart.date() < start_filter.date():  # type: ignore
                    continue
                if end_filter and dtstart.date() > end_filter.date():  # type: ignore
                    continue

                # Format event
                event_str = f"- {summary}"
                event_str += f"\n  Date: {dtstart.strftime('%Y-%m-%d %H:%M')}"  # type: ignore
                if dtend:
                    event_str += f" to {dtend.strftime('%H:%M')}"  # type: ignore
                if location_str:
                    event_str += f"\n  Location: {location_str}"
                events.append(event_str)  # type: ignore

        if not events:
            return f"No events found in calendar '{calendar_name}'"

        return f"Events in '{calendar_name}':\n" + "\n\n".join(events)  # type: ignore

    except Exception as e:
        return f"Error listing calendar events: {e!s}"


@ai_function  # type: ignore[arg-type]
async def delete_calendar_event(  # noqa: RUF029
    event_title: Annotated[str, Field(description="Title of the event to delete")],
    calendar_name: Annotated[str, Field(description="Calendar name (filename without .ics)")] = "event_planning",
) -> str:
    """
    Delete a calendar event by title.

    Parameters
    ----------
    event_title : str
        Title of the event to delete
    calendar_name : str, optional
        Calendar name (filename without .ics), default is "event_planning"

    Returns
    -------
    str
        Success message with count of deleted events or error message

    Notes
    -----
    If multiple events with the same title exist, all will be deleted.
    """
    try:
        calendar_file = CALENDAR_PATH / f"{calendar_name}.ics"
        if not calendar_file.exists():
            return f"Calendar '{calendar_name}' does not exist"

        with open(calendar_file, "rb") as f:  # noqa: ASYNC230
            cal = Calendar.from_ical(f.read())  # type: ignore

        # Find and remove event
        events_removed = 0
        for component in cal.walk():  # type: ignore
            if component.name == "VEVENT":  # type: ignore
                summary = str(component.get("summary", ""))  # type: ignore
                if summary == event_title:
                    cal.subcomponents.remove(component)  # type: ignore
                    events_removed += 1

        if events_removed == 0:
            return f"Event '{event_title}' not found in calendar '{calendar_name}'"

        # Save updated calendar
        with open(calendar_file, "wb") as f:  # noqa: ASYNC230
            f.write(cal.to_ical())  # type: ignore

        return (
            f"Successfully deleted {events_removed} event(s) with title '{event_title}' from calendar '{calendar_name}'"
        )

    except Exception as e:
        return f"Error deleting calendar event: {e!s}"


__all__ = ["create_calendar_event", "delete_calendar_event", "list_calendar_events"]
