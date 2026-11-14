"""Step 2: Send production-like traffic to the trip planner.

Each request becomes one trace in Application Insights. The mix covers ordinary
trips, carry-on and fee questions, and three- or four-city trips. Start with the
launch instructions (v1), which have two problems on purpose:

    python 02_send_traffic.py --instructions v1 --repeat 2

Each request is also appended to traffic_log.jsonl with its trace ID, so later
steps can find the traces to annotate.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime

from agent import ask, build_agent, configure_telemetry, flush_telemetry
from tutorial_utils import TRAFFIC_LOG

SCENARIOS: list[tuple[str, str]] = [
    (
        "simple",
        "Find me a flight from Seattle to Denver on 2026-12-05 and a hotel for 2 nights.",
    ),
    ("simple", "What's the cheapest flight from Boston to Chicago on 2026-12-12?"),
    (
        "simple",
        "I need a hotel in Austin for 3 nights starting 2026-12-18. Something rated 4 or higher.",
    ),
    ("policy", "What's the carry-on size limit? I have a 55 x 40 x 23 cm roller bag."),
    ("policy", "Can I bring a 9 kg backpack as my carry-on?"),
    ("policy", "How big can my cabin bag be on a Saver fare?"),
    ("policy", "Is there a fee to change my flight if I booked a Saver fare?"),
    (
        "multi-city",
        (
            "Plan a trip: Seattle -> San Francisco on 2026-12-03, then Los Angeles on 2026-12-06, "
            "then back to Seattle on 2026-12-09."
        ),
    ),
    (
        "multi-city",
        (
            "I want to visit Chicago, New York and Boston. Leaving from Denver on 2026-12-10, "
            "3 nights in each city, then fly home to Denver."
        ),
    ),
    (
        "multi-city",
        (
            "Help me plan London -> Paris -> Rome -> Barcelona starting 2027-01-15, 2 nights each, "
            "then return to London."
        ),
    ),
]


async def run_all(
    instructions: str, skills: str | None, categories: set[str], repeat: int
) -> None:
    """Send the selected scenarios and append each request to the traffic log."""
    agent = build_agent(instructions, skills)
    with TRAFFIC_LOG.open("a", encoding="utf-8") as log:
        for _ in range(repeat):
            for category, question in SCENARIOS:
                if categories and category not in categories:
                    continue
                started = datetime.now(UTC).isoformat()
                try:
                    answer = await ask(agent, question)
                    text, trace_id, error = answer.text, answer.trace_id, None
                # Keep going so one failure doesn't stop the batch.
                except Exception as ex:  # noqa: BLE001
                    text, trace_id, error = "", None, repr(ex)
                record = {
                    "started": started,
                    "instructions": instructions,
                    "skills": skills,
                    "category": category,
                    "question": question,
                    "answer": text,
                    "trace_id": trace_id,
                    "error": error,
                }
                log.write(json.dumps(record) + "\n")
                print(f"[{category}] {question}\n  -> {(text or error or '')[:200]}\n")
                await asyncio.sleep(1)


def main() -> None:
    """Parse arguments and send the scenario batch."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--instructions", choices=["v1", "v2"], default="v1")
    parser.add_argument(
        "--skills", help="Folder with SKILL.md skills to load, such as ./skills."
    )
    parser.add_argument(
        "--category", action="append", choices=["simple", "policy", "multi-city"]
    )
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    configure_telemetry()
    try:
        asyncio.run(
            run_all(
                args.instructions, args.skills, set(args.category or []), args.repeat
            )
        )
    finally:
        flush_telemetry()
    print(
        f"Logged requests to {TRAFFIC_LOG.name}. Traces appear in Foundry within a few minutes."
    )


if __name__ == "__main__":
    main()
