# Copyright (c) Microsoft. All rights reserved.
"""Flight Agent's synthetic round-trip inventory; amounts are USD cents."""

from datetime import date, datetime

CATALOG_VERSION = "synthetic-seattle-2027-01-v1"
FLIGHTS = [
    {
        "id": "FLIGHT-101",
        "origin": "SFO",
        "destination": "SEA",
        "departure_date": "2027-01-10",
        "return_date": "2027-01-13",
        "arrival": "2027-01-10T20:00:00-08:00",
        "refundable": False,
        "seats": 4,
        "fare_cents": 25000,
        "tax_cents": 4500,
        "baggage_cents": 3000,
    },
    {
        "id": "FLIGHT-102",
        "origin": "SFO",
        "destination": "SEA",
        "departure_date": "2027-01-10",
        "return_date": "2027-01-13",
        "arrival": "2027-01-10T18:00:00-08:00",
        "refundable": True,
        "seats": 4,
        "fare_cents": 39000,
        "tax_cents": 5000,
        "baggage_cents": 0,
    },
    {
        "id": "FLIGHT-103",
        "origin": "SFO",
        "destination": "SEA",
        "departure_date": "2027-01-10",
        "return_date": "2027-01-13",
        "arrival": "2027-01-11T10:30:00-08:00",
        "refundable": True,
        "seats": 4,
        "fare_cents": 18000,
        "tax_cents": 4000,
        "baggage_cents": 3500,
    },
]
EXAMPLE = {
    "origin": "SFO",
    "destination": "SEA",
    "departure_date": "2027-01-10",
    "return_date": "2027-01-13",
    "arrive_by": "2027-01-11T09:00:00-08:00",
    "travelers": 1,
    "refundable": True,
}


def search_flights(query: dict) -> dict:
    if not isinstance(query, dict) or set(query) != set(EXAMPLE):
        raise ValueError(
            "Flight query must contain exactly: " + ", ".join(sorted(EXAMPLE))
        )
    if type(query["travelers"]) is not int or not 1 <= query["travelers"] <= 4:
        raise ValueError("travelers must be an integer between 1 and 4")
    if type(query["refundable"]) is not bool:
        raise ValueError("refundable must be a boolean")
    for key in ("origin", "destination"):
        code = query[key]
        if (
            not isinstance(code, str)
            or len(code) != 3
            or not code.isascii()
            or not code.isalpha()
        ):
            raise ValueError(f"{key} must be a three-letter airport/city code")
    for key in ("departure_date", "return_date", "arrive_by"):
        if not isinstance(query[key], str):
            raise TypeError(f"{key} must be an ISO string")
    first, last = date.fromisoformat(query["departure_date"]), date.fromisoformat(
        query["return_date"]
    )
    if not first < last or (last - first).days > 14:
        raise ValueError("Trip must last between 1 and 14 nights")
    deadline = datetime.fromisoformat(query["arrive_by"])
    if deadline.utcoffset() is None or not first <= deadline.date() <= last:
        raise ValueError(
            "arrive_by must have a timezone and fall within the trip dates"
        )
    options = []
    for item in FLIGHTS:
        if (
            item["origin"] == query["origin"].upper()
            and item["destination"] == query["destination"].upper()
            and item["departure_date"] == query["departure_date"]
            and item["return_date"] == query["return_date"]
            and item["seats"] >= query["travelers"]
            and (not query["refundable"] or item["refundable"])
            and datetime.fromisoformat(item["arrival"]) <= deadline
        ):
            options.append(
                {
                    **item,
                    "total_cents": query["travelers"]
                    * (item["fare_cents"] + item["tax_cents"] + item["baggage_cents"]),
                }
            )
    return {
        "kind": "flights",
        "catalog_version": CATALOG_VERSION,
        "query": query,
        "status": "options_found" if options else "no_options",
        "options": options,
    }
