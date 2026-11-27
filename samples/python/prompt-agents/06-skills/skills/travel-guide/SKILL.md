---
name: travel-guide
description: Produces a structured city travel guide with a day-by-day itinerary, neighborhoods, food picks, practical tips, and photo-worthy stops. Use when the user asks for a travel guide, city guide, itinerary, or trip plan for a destination.
---

# Travel guide skill

Use this skill when the user wants a city travel guide, itinerary, or trip plan.

## Workflow

1. Identify the destination city from the user's request.
2. Infer trip length and interests when provided; otherwise default to a 3-day guide with a balanced mix of culture, food, neighborhoods, views, and practical tips.
3. Produce a Markdown guide with these sections:
   - **Overview** — one paragraph on the city and the best time to visit.
   - **Day-by-day itinerary** — one section per day, split into morning / afternoon / evening.
   - **Neighborhoods** — 3–5 areas worth exploring and why.
   - **Food & drink** — signature dishes plus a few specific places or markets.
   - **Practical tips** — getting around, money, safety, and etiquette.
   - **Photo-worthy stops** — a short list of standout viewpoints or landmarks.
4. Keep the guide concrete and specific to the requested city; avoid generic filler.
