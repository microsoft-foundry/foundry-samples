"""Run Agent Insights on the external weather agent's recent traces.

Agent Insights analyzes the agent's traces with a model you choose, groups
recurring issues, and suggests a next step for each one. This script creates a
monitor for the agent (or reuses an existing one), starts one on-demand run,
and prints the active insights. Agent Insights is generally available through
``project_client.agent_insight_monitors``.

The monitor is kept so you can review the insights in the Foundry portal
(Agents -> <agent> -> Insights). Pass ``--delete`` to remove it.

Usage:
    python run_agent_insights.py
    python run_agent_insights.py --lookback-hours 6
    python run_agent_insights.py --delete
"""

from __future__ import annotations

import argparse
import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"), override=True)

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import AgentInsightStatus
from azure.core.exceptions import ResourceExistsError
from azure.identity import DefaultAzureCredential

AGENT_NAME = os.environ.get("AGENT_NAME", "weather-agent")


def analysis_model() -> str:
    """Return the Insights model. Agent Insights needs a GPT-5 or later deployment."""
    model = os.environ.get("INSIGHTS_MODEL_DEPLOYMENT")
    if not model:
        raise SystemExit(
            "Set INSIGHTS_MODEL_DEPLOYMENT to a GPT-5 or later deployment."
        )
    return model


def get_or_create_monitor(project_client: AIProjectClient, model: str):
    """Return the agent's monitor using `model`, creating a disabled (on-demand) one if needed."""
    monitors = project_client.agent_insight_monitors
    for existing in monitors.list(agent_name=AGENT_NAME):
        if existing.model_deployment_name != model:
            return monitors.update(existing.id, model_deployment_name=model)
        return existing
    # enabled=False: runs only when started explicitly, not on a schedule.
    return monitors.create(
        agent_name=AGENT_NAME, model_deployment_name=model, enabled=False
    )


def delete_monitor(monitors, monitor_id: str, attempts: int = 20) -> None:
    """Delete a monitor, waiting for any active run to finish first (the service returns a conflict until then)."""
    for _ in range(attempts):
        try:
            monitors.delete(monitor_id)
            print(f"Deleted monitor {monitor_id}")
            return
        except ResourceExistsError:
            print(f"Monitor {monitor_id} has a run in progress; retrying in 30s...")
            time.sleep(30)
    raise SystemExit(
        f"Monitor {monitor_id} still has an active run. Try --delete later."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookback-hours", type=float, default=24)
    parser.add_argument(
        "--delete", action="store_true", help="Delete the agent's monitor and exit."
    )
    args = parser.parse_args()

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential
        ) as project_client,
    ):
        monitors = project_client.agent_insight_monitors
        if args.delete:
            for existing in monitors.list(agent_name=AGENT_NAME):
                delete_monitor(monitors, existing.id)
            return

        monitor = get_or_create_monitor(project_client, analysis_model())
        print(f"Using monitor {monitor.id} for agent {AGENT_NAME!r}")

        poller = monitors.begin_create_run(
            monitor.id,
            lookback_hours=args.lookback_hours,
            operation_id=str(uuid.uuid4()),
        )
        print(
            f"Started run {poller.details['run_id']} over the last {args.lookback_hours}h; waiting..."
        )
        result = poller.result()
        print(
            f"Traces analyzed: {result.traces_analyzed} of {result.traces_in_window}; "
            f"insights created={result.insights_created}, updated={result.insights_updated}"
        )

        insights = list(
            monitors.list_insights(
                monitor.id, statuses=[AgentInsightStatus.ACTIVE], include_details=True
            )
        )
        print(f"\nActive insights: {len(insights)}")
        for insight in insights:
            print(
                f"- [{insight.severity}] {insight.title} ({insight.trace_count} traces)"
            )
            if insight.details:
                print(
                    f"  Proposed next step: {insight.details.recommended_actions.proposed_fix.text}"
                )


if __name__ == "__main__":
    main()
