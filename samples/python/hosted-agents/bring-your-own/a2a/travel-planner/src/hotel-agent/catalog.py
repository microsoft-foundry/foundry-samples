# Copyright (c) Microsoft. All rights reserved.
"""Raw dummy hotels for the LLM; no Python filtering or stay calculations."""

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
