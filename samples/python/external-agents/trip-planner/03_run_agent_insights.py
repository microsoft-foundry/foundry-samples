"""Step 3: Find recurring issues with Agent Insights.

Agent Insights analyzes the agent's recent traces with a model you choose,
groups recurring issues, and shows each one with its severity, the linked
traces, and a proposed next step. Foundry doesn't have an external agent's code,
so proposed next steps are general guidance to apply in your own code.

    python 03_run_agent_insights.py --lookback-hours 24

Expect an insight about multi-city trips that repeat the same searches.
"""

from __future__ import annotations

import argparse
import sys
import uuid

from azure.ai.projects.models import AgentInsightStatus

from tutorial_utils import AGENT_NAME, JUDGE_MODEL, TutorialState, project_client


def get_or_create_monitor(monitors):
    """Return the agent's monitor, or create one that runs only on demand."""
    for existing in monitors.list(agent_name=AGENT_NAME):
        return existing
    return monitors.create(
        agent_name=AGENT_NAME, model_deployment_name=JUDGE_MODEL, enabled=False
    )


def main() -> None:
    """Start one Agent Insights run and print the active insights."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--lookback-hours", type=float, default=24)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    with project_client() as project:
        monitors = project.agent_insight_monitors
        monitor = get_or_create_monitor(monitors)
        TutorialState.update(insights_monitor_id=monitor.id)
        poller = monitors.begin_create_run(
            monitor.id,
            lookback_hours=args.lookback_hours,
            operation_id=str(uuid.uuid4()),
        )
        print(
            f"Analyzing traces from the last {args.lookback_hours}h (monitor {monitor.id})..."
        )
        result = poller.result()
        print(
            f"Analyzed {result.traces_analyzed} of {result.traces_in_window} traces; "
            f"{result.insights_created} new and {result.insights_updated} updated insights.\n"
        )

        insights = monitors.list_insights(
            monitor.id, statuses=[AgentInsightStatus.ACTIVE], include_details=True
        )
        for insight in insights:
            print(
                f"[{insight.severity}] {insight.title} ({insight.trace_count} traces)"
            )
            if insight.details:
                print(
                    f"  Proposed next step: {insight.details.recommended_actions.proposed_fix.text}\n"
                )
    print("Review the insights in the Foundry portal: Agents > your agent > Insights.")


if __name__ == "__main__":
    main()
