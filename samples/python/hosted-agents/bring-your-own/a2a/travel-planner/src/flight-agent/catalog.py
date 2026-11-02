# Copyright (c) Microsoft. All rights reserved.
"""Raw dummy flights for the LLM; no Python search or price calculation."""

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
