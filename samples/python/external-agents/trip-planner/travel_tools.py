"""Mock Contoso Travel tools. All data is fictional and deterministic."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated

from pydantic import Field

# Current policy, returned only by policy_lookup. The v1 instructions carry an older copy.
_POLICIES: dict[str, str] = {
    "carry-on": (
        "Carry-on (effective 2026-10-01): one bag up to 55 x 35 x 20 cm and 7 kg, "
        "plus one personal item up to 40 x 30 x 15 cm that fits under the seat."
    ),
    "checked-bag": "Checked bag: first bag USD 35, second bag USD 45, max 23 kg and 158 cm total dimensions.",
    "change-fee": "Changes: free up to 24 hours before departure on Flex fares; USD 75 on Saver fares.",
    "seat": "Seat selection: free on Flex fares; USD 15-40 on Saver fares depending on row.",
}

_AIRLINES = ["Contoso Air", "Fabrikam Airways", "Northwind Jet"]


def _seed(*parts: str) -> int:
    """Return a stable integer derived from the inputs so results repeat across runs."""
    return int(
        hashlib.sha256("|".join(p.lower() for p in parts).encode()).hexdigest()[:8], 16
    )


def search_flights(
    origin: Annotated[str, Field(description="Departure city")],
    destination: Annotated[str, Field(description="Arrival city")],
    date: Annotated[str, Field(description="Travel date, YYYY-MM-DD")],
) -> str:
    """Search one-way flights for a single leg."""
    seed = _seed(origin, destination, date)
    options = [
        {
            "flight": f"{_AIRLINES[(seed + i) % 3][:2].upper()}{100 + (seed >> i) % 800}",
            "airline": _AIRLINES[(seed + i) % 3],
            "from": origin,
            "to": destination,
            "date": date,
            "depart": f"{6 + (seed >> (i + 2)) % 12:02d}:{(seed >> i) % 4 * 15:02d}",
            "price_usd": 89 + (seed >> (i + 4)) % 260,
        }
        for i in range(3)
    ]
    return json.dumps(options)


def search_hotels(
    city: Annotated[str, Field(description="City to stay in")],
    check_in: Annotated[str, Field(description="Check-in date, YYYY-MM-DD")],
    nights: Annotated[int, Field(description="Number of nights")],
) -> str:
    """Search hotels in a city."""
    seed = _seed(city, check_in, str(nights))
    names = ["Harbor View", "Old Town Inn", "Central Suites"]
    options = [
        {
            "hotel": f"{names[i]} {city}",
            "check_in": check_in,
            "nights": nights,
            "price_per_night_usd": 95 + (seed >> (i * 3)) % 180,
            "rating": round(3.6 + ((seed >> i) % 14) / 10, 1),
        }
        for i in range(3)
    ]
    return json.dumps(options)


def policy_lookup(
    topic: Annotated[
        str, Field(description="One of: carry-on, checked-bag, change-fee, seat")
    ],
) -> str:
    """Return the current Contoso Travel partner-airline policy for a topic."""
    key = topic.strip().lower().replace(" ", "-").replace("_", "-")
    if key in ("carryon", "carry-on-bag", "cabin-bag", "hand-luggage"):
        key = "carry-on"
    return _POLICIES.get(
        key, f"No policy found for '{topic}'. Known topics: {', '.join(_POLICIES)}."
    )


TOOLS = [search_flights, search_hotels, policy_lookup]
