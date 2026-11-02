# Copyright (c) Microsoft. All rights reserved.
"""Hotel Agent's synthetic stay inventory; amounts are USD cents."""

from datetime import date

CATALOG_VERSION = "synthetic-seattle-2027-01-v1"
HOTELS = [
    {
        "id": "HOTEL-201",
        "name": "Budget Central",
        "destination": "SEA",
        "office_distance_meters": 900,
        "refundable": False,
        "rooms": 2,
        "night_cents": 14500,
        "tax_per_night_cents": 1500,
        "stay_fee_cents": 1500,
    },
    {
        "id": "HOTEL-202",
        "name": "Office Flex",
        "destination": "SEA",
        "office_distance_meters": 1200,
        "refundable": True,
        "rooms": 2,
        "night_cents": 21000,
        "tax_per_night_cents": 2500,
        "stay_fee_cents": 2000,
    },
    {
        "id": "HOTEL-203",
        "name": "Airport Flex",
        "destination": "SEA",
        "office_distance_meters": 14000,
        "refundable": True,
        "rooms": 2,
        "night_cents": 15000,
        "tax_per_night_cents": 1500,
        "stay_fee_cents": 1500,
    },
    {
        "id": "HOTEL-204",
        "name": "Premium Center",
        "destination": "SEA",
        "office_distance_meters": 500,
        "refundable": True,
        "rooms": 2,
        "night_cents": 30000,
        "tax_per_night_cents": 3000,
        "stay_fee_cents": 3000,
    },
]
EXAMPLE = {
    "destination": "SEA",
    "check_in": "2027-01-10",
    "check_out": "2027-01-13",
    "travelers": 1,
    "refundable": True,
    "max_office_distance_meters": 3000,
}


def validate_query(query: dict) -> None:
    if not isinstance(query, dict) or set(query) != set(EXAMPLE):
        raise ValueError(
            "Hotel query must contain exactly: " + ", ".join(sorted(EXAMPLE))
        )
    if type(query["travelers"]) is not int or not 1 <= query["travelers"] <= 4:
        raise ValueError("travelers must be an integer between 1 and 4")
    if type(query["refundable"]) is not bool:
        raise ValueError("refundable must be a boolean")
    code = query["destination"]
    if (
        not isinstance(code, str)
        or len(code) != 3
        or not code.isascii()
        or not code.isalpha()
    ):
        raise ValueError("destination must be a three-letter airport/city code")
    for key in ("check_in", "check_out"):
        if not isinstance(query[key], str):
            raise TypeError(f"{key} must be an ISO date string")
    first, last = date.fromisoformat(query["check_in"]), date.fromisoformat(
        query["check_out"]
    )
    if not first < last or (last - first).days > 14:
        raise ValueError("Trip must last between 1 and 14 nights")
    if (
        type(query["max_office_distance_meters"]) is not int
        or query["max_office_distance_meters"] < 0
    ):
        raise ValueError("max_office_distance_meters must be a nonnegative integer")


def search_hotels(query: dict) -> dict:
    """Reference calculation used only to verify the model's answer."""
    validate_query(query)
    first, last = date.fromisoformat(query["check_in"]), date.fromisoformat(
        query["check_out"]
    )
    rooms_needed = (query["travelers"] + 1) // 2
    nights = (last - first).days
    options = []
    for item in HOTELS:
        if (
            item["destination"] == query["destination"].upper()
            and date(2027, 1, 1) <= first < last <= date(2027, 2, 1)
            and item["rooms"] >= rooms_needed
            and (not query["refundable"] or item["refundable"])
            and item["office_distance_meters"] <= query["max_office_distance_meters"]
        ):
            options.append(
                {
                    **item,
                    "nights": nights,
                    "rooms_needed": rooms_needed,
                    "total_cents": rooms_needed
                    * (
                        nights * (item["night_cents"] + item["tax_per_night_cents"])
                        + item["stay_fee_cents"]
                    ),
                }
            )
    return {
        "kind": "hotels",
        "catalog_version": CATALOG_VERSION,
        "query": query,
        "status": "options_found" if options else "no_options",
        "options": options,
    }


def verify_calculations(query: dict, answer: dict) -> dict:
    expected = search_hotels(query)
    options = answer.get("options")
    if not isinstance(options, list) or answer.get("status") != expected["status"]:
        raise ValueError("Hotel model returned an invalid options status")
    computed = {}
    for option in options:
        if not isinstance(option, dict) or set(option) != {
            "id",
            "nights",
            "rooms_needed",
            "total_cents",
        }:
            raise ValueError(
                "Hotel model must return ID, nights, rooms_needed and total_cents"
            )
        if not isinstance(option["id"], str) or option["id"] in computed:
            raise ValueError("Hotel model returned an invalid or duplicate ID")
        if any(
            type(option[key]) is not int
            for key in ("nights", "rooms_needed", "total_cents")
        ):
            raise ValueError("Hotel model calculations must be integers")
        computed[option["id"]] = (
            option["nights"],
            option["rooms_needed"],
            option["total_cents"],
        )
    if computed != {
        item["id"]: (item["nights"], item["rooms_needed"], item["total_cents"])
        for item in expected["options"]
    }:
        raise ValueError(
            "Hotel model filtering, room count or price calculation is incorrect"
        )
    assessment = answer.get("assessment")
    if not isinstance(assessment, str) or not assessment.strip():
        raise ValueError("Hotel model did not explain its assessment")
    inventory = {item["id"]: item for item in HOTELS}
    return {
        "kind": "hotels",
        "catalog_version": CATALOG_VERSION,
        "query": query,
        "status": answer["status"],
        "options": [{**inventory[item["id"]], **item} for item in options],
        "assessment": assessment,
        "calculations_verified": True,
    }
