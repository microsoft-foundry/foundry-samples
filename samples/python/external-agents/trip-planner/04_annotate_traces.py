"""Step 4 (preview): Annotate traces the way a domain expert would.

In the Foundry portal, a reviewer opens a trace, rates it, adds tags and a
comment, and writes the answer they expected. Each annotation is stored as a
``gen_ai.evaluation.result`` event in the agent's Application Insights
resource, linked to the trace. This script writes the same events, so you can
reproduce the review without clicking through the portal. There's no SDK or
REST API for annotations yet; the README lists the event fields.

It annotates the carry-on answers from the launch version (v1) as incorrect,
with the current rule as the expected answer, and one v2 carry-on answer as
correct. It reads trace IDs from traffic_log.jsonl (written by step 2).

    python 04_annotate_traces.py

Open a trace in Foundry and select Annotation to see the result.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime

import requests

from tutorial_utils import AGENT_NAME, TutorialState, read_traffic_log

CURRENT_CARRY_ON_RULE = (
    "One carry-on bag up to 55 x 35 x 20 cm and 7 kg, plus one personal item up to "
    "40 x 30 x 15 cm. Check with policy_lookup before answering."
)


class AnnotationWriter:
    """Writes human annotations to Application Insights, in the format the Foundry portal uses."""

    def __init__(self, connection_string: str) -> None:
        parts = dict(
            part.split("=", 1) for part in connection_string.split(";") if "=" in part
        )
        self._ikey = parts["InstrumentationKey"]
        self._endpoint = parts.get(
            "IngestionEndpoint", "https://dc.services.visualstudio.com"
        ).rstrip("/")

    def annotate(
        self,
        trace_id: str,
        *,
        good: bool,
        comment: str,
        tags: list[str],
        expected: str | None,
    ) -> None:
        """Send one turn-level annotation for a trace."""
        properties = {
            "gen_ai.evaluation.name": "overall_quality",
            "gen_ai.evaluation.score.label": "pass" if good else "fail",
            "gen_ai.evaluation.score.value": "1.0" if good else "0.0",
            "gen_ai.evaluation.explanation": comment,
            "gen_ai.agent.id": os.environ.get("OTEL_AGENT_ID", "contoso-trip-planner"),
            "gen_ai.agent.name": AGENT_NAME,
            "microsoft.gen_ai.evaluation.actor.type": "human",
            "microsoft.gen_ai.human_evaluation.source": "builder",
            "microsoft.gen_ai.human_evaluation.id": str(uuid.uuid4()),
            "microsoft.gen_ai.human_evaluation.tags": json.dumps(tags),
            "event.name": "gen_ai.evaluation.result",
            "microsoft.custom_event.name": "gen_ai.evaluation.result",
            "internal_properties": json.dumps({"gen_ai.evaluation.level": "turn"}),
        }
        if expected:
            properties["microsoft.gen_ai.human_evaluation.expected_output"] = expected
        envelope = {
            "name": "Microsoft.ApplicationInsights.Event",
            "time": datetime.now(UTC).isoformat(),
            "iKey": self._ikey,
            "tags": {"ai.operation.id": trace_id},
            "data": {
                "baseType": "EventData",
                "baseData": {
                    "ver": 2,
                    "name": "gen_ai.evaluation.result",
                    "properties": properties,
                },
            },
        }
        response = requests.post(
            f"{self._endpoint}/v2/track", json=[envelope], timeout=30
        )
        response.raise_for_status()
        if response.json().get("itemsAccepted") != 1:
            raise RuntimeError(
                f"Application Insights rejected the annotation: {response.text}"
            )


def main() -> None:
    """Annotate v1 carry-on traces as incorrect and one v2 carry-on trace as correct."""
    sys.stdout.reconfigure(encoding="utf-8")
    log = [
        r for r in read_traffic_log() if r.get("trace_id") and r["category"] == "policy"
    ]
    carry_on = [r for r in log if "fee" not in r["question"].lower()]
    # The log is append-only; take the newest traces so step 5's lookback window still covers them.
    bad = [r for r in carry_on if r["instructions"] == "v1"][-3:]
    good = [r for r in carry_on if r["instructions"] == "v2"][-1:]
    if not bad:
        raise SystemExit(
            "No v1 carry-on traces in traffic_log.jsonl. Run 02_send_traffic.py --instructions v1."
        )

    writer = AnnotationWriter(os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"])
    for row in bad:
        writer.annotate(
            row["trace_id"],
            good=False,
            tags=["policy", "outdated"],
            expected=CURRENT_CARRY_ON_RULE,
            comment="Quotes the old carry-on limit from memory instead of calling policy_lookup.",
        )
        print(f"Marked incorrect: {row['trace_id']}  {row['question']}")
    for row in good:
        writer.annotate(
            row["trace_id"],
            good=True,
            tags=["policy"],
            expected=None,
            comment="Calls policy_lookup and quotes the current limit.",
        )
        print(f"Marked correct:   {row['trace_id']}  {row['question']}")

    TutorialState.update(annotated_trace_ids=[r["trace_id"] for r in bad + good])
    print("Annotations appear on the traces within a few minutes.")


if __name__ == "__main__":
    main()
