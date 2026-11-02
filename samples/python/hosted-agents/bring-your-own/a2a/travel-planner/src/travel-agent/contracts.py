# Copyright (c) Microsoft. All rights reserved.
"""Validate remote travel contracts without importing specialist inventories."""

from datetime import date, datetime

FLIGHT_FIELDS = {
    "origin",
    "destination",
    "departure_date",
    "return_date",
    "arrive_by",
    "travelers",
    "refundable",
}
TRIP_FIELDS = (FLIGHT_FIELDS - {"refundable"}) | {
    "flight_refundable",
    "hotel_refundable",
    "budget_cents",
    "max_office_distance_meters",
}


def integer(value: object, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value


def flight_query(trip: dict) -> dict:
    return {
        key: trip["flight_refundable"] if key == "refundable" else trip[key]
        for key in FLIGHT_FIELDS
    }


def hotel_query(trip: dict) -> dict:
    return {
        "destination": trip["destination"],
        "check_in": trip["departure_date"],
        "check_out": trip["return_date"],
        "travelers": trip["travelers"],
        "refundable": trip["hotel_refundable"],
        "max_office_distance_meters": trip["max_office_distance_meters"],
    }


def validate_trip(trip: dict) -> dict:
    if not isinstance(trip, dict) or set(trip) != TRIP_FIELDS:
        raise ValueError(
            "Trip requirements are incomplete or contain unsupported fields"
        )
    if integer(trip["budget_cents"], "budget_cents") > 10000000:
        raise ValueError("budget_cents must not exceed 10000000")
    if integer(trip["travelers"], "travelers", 1) > 4:
        raise ValueError("travelers must not exceed 4")
    integer(trip["max_office_distance_meters"], "max_office_distance_meters")
    for key in ("flight_refundable", "hotel_refundable"):
        if type(trip[key]) is not bool:
            raise ValueError(f"{key} must be a boolean")
    for key in ("origin", "destination"):
        code = text(trip[key], key)
        if len(code) != 3 or not code.isascii() or not code.isalpha():
            raise ValueError(f"{key} must be a three-letter airport/city code")
    first = date.fromisoformat(text(trip["departure_date"], "departure_date"))
    last = date.fromisoformat(text(trip["return_date"], "return_date"))
    if not first < last or (last - first).days > 14:
        raise ValueError("Trip must last between 1 and 14 nights")
    deadline = datetime.fromisoformat(text(trip["arrive_by"], "arrive_by"))
    if deadline.utcoffset() is None or not first <= deadline.date() <= last:
        raise ValueError(
            "arrive_by must have a timezone and fall within the trip dates"
        )
    return trip


def verify_options(result: dict, trip: dict) -> None:
    """Validate returned constraints and arithmetic, not a local catalog copy."""
    kind = result.get("kind")
    if kind not in {"flights", "hotels"}:
        raise ValueError("Unknown specialist result kind")
    expected_query = flight_query(trip) if kind == "flights" else hotel_query(trip)
    query = result.get("query")
    if (
        not isinstance(query, dict)
        or query != expected_query
        or any(
            type(query[key]) is not type(value) for key, value in expected_query.items()
        )
    ):
        raise ValueError("Remote result changed the requested query")
    text(result.get("catalog_version"), "catalog_version")
    options = result.get("options")
    if not isinstance(options, list):
        raise TypeError("Remote options must be a list")
    if result.get("status") != ("options_found" if options else "no_options"):
        raise ValueError("Remote options status is inconsistent")
    ids = set()
    nights = (
        date.fromisoformat(trip["return_date"])
        - date.fromisoformat(trip["departure_date"])
    ).days
    rooms = (trip["travelers"] + 1) // 2
    for item in options:
        if not isinstance(item, dict):
            raise TypeError("Each remote option must be an object")
        option_id = text(item.get("id"), "option id")
        if option_id in ids:
            raise ValueError("Remote options contain duplicate IDs")
        ids.add(option_id)
        if type(item.get("refundable")) is not bool:
            raise ValueError("Remote refundability must be a boolean")
        if item.get("destination") != trip["destination"].upper() or (
            expected_query["refundable"] and not item["refundable"]
        ):
            raise ValueError("Remote option violates destination or refundability")
        total = integer(item.get("total_cents"), "total_cents")
        if kind == "flights":
            arrival = datetime.fromisoformat(text(item.get("arrival"), "arrival"))
            if (
                item.get("origin") != trip["origin"].upper()
                or item.get("departure_date") != trip["departure_date"]
                or item.get("return_date") != trip["return_date"]
                or integer(item.get("seats"), "seats") < trip["travelers"]
                or arrival.utcoffset() is None
                or not date.fromisoformat(trip["departure_date"])
                <= arrival.date()
                <= date.fromisoformat(trip["return_date"])
                or arrival > datetime.fromisoformat(trip["arrive_by"])
            ):
                raise ValueError("Remote flight violates travel constraints")
            expected_total = trip["travelers"] * sum(
                integer(item.get(key), key)
                for key in ("fare_cents", "tax_cents", "baggage_cents")
            )
        else:
            text(item.get("name"), "hotel name")
            if (
                integer(item.get("office_distance_meters"), "office_distance_meters")
                > trip["max_office_distance_meters"]
                or integer(item.get("rooms"), "rooms") < rooms
                or integer(item.get("nights"), "nights", 1) != nights
                or integer(item.get("rooms_needed"), "rooms_needed", 1) != rooms
            ):
                raise ValueError("Remote hotel violates stay constraints")
            expected_total = rooms * (
                nights
                * (
                    integer(item.get("night_cents"), "night_cents")
                    + integer(item.get("tax_per_night_cents"), "tax_per_night_cents")
                )
                + integer(item.get("stay_fee_cents"), "stay_fee_cents")
            )
        if total != expected_total:
            raise ValueError("Remote option has inconsistent price arithmetic")


def eligible_pairs(trip: dict, results: dict[str, dict]) -> list[tuple[dict, dict]]:
    if set(results) != {"flights", "hotels"}:
        raise ValueError("Both Toolbox specialist results are required")
    for role, result in results.items():
        if result.get("kind") != role:
            raise ValueError("Specialist result is attached to the wrong role")
        verify_options(result, trip)
    return [
        (flight, hotel)
        for flight in results["flights"]["options"]
        for hotel in results["hotels"]["options"]
        if flight["total_cents"] + hotel["total_cents"] <= trip["budget_cents"]
    ]


def choose_itinerary(trip: dict, results: dict[str, dict], selection: dict) -> dict:
    pairs = eligible_pairs(trip, results)
    if not pairs:
        if (
            selection.get("status") != "no_match"
            or selection.get("flight_id") is not None
            or selection.get("hotel_id") is not None
        ):
            raise ValueError(
                "Model proposed an itinerary when no eligible combination exists"
            )
        return {
            "status": "no_match",
            "budget_cents": trip["budget_cents"],
            "currency": "USD",
            "synthetic": True,
            "booking_created": False,
        }
    if selection.get("status") != "proposed":
        raise ValueError("Model rejected the trip despite eligible combinations")
    for flight, hotel in pairs:
        if flight["id"] == selection.get("flight_id") and hotel["id"] == selection.get(
            "hotel_id"
        ):
            total = flight["total_cents"] + hotel["total_cents"]
            if total != min(f["total_cents"] + h["total_cents"] for f, h in pairs):
                raise ValueError("Model did not select the cheapest eligible itinerary")
            return {
                "status": "proposed",
                "currency": "USD",
                "synthetic": True,
                "booking_created": False,
                "flight": flight,
                "hotel": hotel,
                "total_cents": total,
                "budget_cents": trip["budget_cents"],
                "remaining_cents": trip["budget_cents"] - total,
            }
    raise ValueError("Model selected unavailable or over-budget options")
