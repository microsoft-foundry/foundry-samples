# Copyright (c) Microsoft. All rights reserved.
"""Fixed synthetic travel inventory; prices are USD cents, never live quotes."""

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
FLIGHT_FIELDS = {
    "origin",
    "destination",
    "departure_date",
    "return_date",
    "arrive_by",
    "travelers",
    "refundable",
}
HOTEL_FIELDS = {
    "destination",
    "check_in",
    "check_out",
    "travelers",
    "refundable",
    "max_office_distance_meters",
}
TRIP_FIELDS = (FLIGHT_FIELDS - {"refundable"}) | {
    "flight_refundable",
    "hotel_refundable",
    "budget_cents",
    "max_office_distance_meters",
}
FLIGHT_EXAMPLE = {
    "origin": "SFO",
    "destination": "SEA",
    "departure_date": "2027-01-10",
    "return_date": "2027-01-13",
    "arrive_by": "2027-01-11T09:00:00-08:00",
    "travelers": 1,
    "refundable": True,
}
HOTEL_EXAMPLE = {
    "destination": "SEA",
    "check_in": "2027-01-10",
    "check_out": "2027-01-13",
    "travelers": 1,
    "refundable": True,
    "max_office_distance_meters": 3000,
}


def require_fields(query: dict, fields: set[str]) -> None:
    if not isinstance(query, dict) or set(query) != fields:
        raise ValueError(
            "Travel query must contain exactly these fields: "
            + ", ".join(sorted(fields))
        )
    if type(query["travelers"]) is not int or not 1 <= query["travelers"] <= 4:
        raise ValueError("travelers must be an integer between 1 and 4")
    if type(query["refundable"]) is not bool:
        raise ValueError("refundable must be a boolean")
    for key in ("origin", "destination"):
        if key in fields and (
            not isinstance(query[key], str)
            or len(query[key]) != 3
            or not query[key].isalpha()
        ):
            raise ValueError(f"{key} must be a three-letter airport/city code")


def validate_dates(start: str, end: str) -> tuple[date, date]:
    if not isinstance(start, str) or not isinstance(end, str):
        raise TypeError("Travel dates must be ISO date strings")
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if not first < last or (last - first).days > 14:
        raise ValueError("Trip must last between 1 and 14 nights")
    return first, last


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


def search_flights(query: dict) -> dict:
    require_fields(query, FLIGHT_FIELDS)
    first, last = validate_dates(query["departure_date"], query["return_date"])
    if not isinstance(query["arrive_by"], str):
        raise TypeError("arrive_by must be an ISO timestamp with timezone")
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


def search_hotels(query: dict) -> dict:
    require_fields(query, HOTEL_FIELDS)
    first, last = validate_dates(query["check_in"], query["check_out"])
    if (
        type(query["max_office_distance_meters"]) is not int
        or query["max_office_distance_meters"] < 0
    ):
        raise ValueError("max_office_distance_meters must be a nonnegative integer")
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


def validate_trip(trip: dict) -> dict:
    if not isinstance(trip, dict) or set(trip) != TRIP_FIELDS:
        raise ValueError(
            "Trip requirements are incomplete or contain unsupported fields"
        )
    if (
        type(trip["budget_cents"]) is not int
        or not 0 <= trip["budget_cents"] <= 10000000
    ):
        raise ValueError("budget_cents must be an integer between 0 and 10000000")
    search_flights(flight_query(trip))
    search_hotels(hotel_query(trip))
    return trip


def verify_options(result: dict, trip: dict) -> None:
    """Check remote options against this synthetic fixture, not model assertions."""
    kind = result.get("kind")
    expected = (
        search_flights(flight_query(trip))
        if kind == "flights"
        else search_hotels(hotel_query(trip)) if kind == "hotels" else None
    )
    if expected is None or any(
        result.get(key) != value for key, value in expected.items()
    ):
        raise ValueError("Remote result does not match the requested catalog query")


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
        if selection.get("status") != "no_match":
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
