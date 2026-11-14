"""Generate a rubric evaluator from the weather agent's job description and traces.

An evaluator generation job turns a description of what the agent should do,
plus its production traces, into a rubric evaluator with named pass/fail
dimensions. You can edit the dimensions and use the evaluator in any
evaluation. Rubric evaluator generation is generally available through
``project_client.evaluators.begin_create_generation_job``.

The service rejects a traces-only source list, so the traces are paired with a
prompt that describes the agent's job.

Usage:
    python generate_rubric_evaluator.py
    python generate_rubric_evaluator.py --lookback-hours 72
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"), override=True)

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    EvaluatorGenerationInputs,
    PromptEvaluatorGenerationJobSource,
    RubricBasedEvaluatorDefinition,
    TracesEvaluatorGenerationJobSource,
)
from azure.identity import DefaultAzureCredential

AGENT_NAME = os.environ.get("AGENT_NAME", "weather-agent")
MODEL = os.environ["AZURE_OPENAI_DEPLOYMENT"]

AGENT_JOB_DESCRIPTION = (
    "A weather assistant that answers questions about current conditions and forecasts "
    "for a city. It must call its weather tool for every city it reports on, never "
    "invent temperatures or conditions, state units, and ask which city the user means "
    "when the request is ambiguous."
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookback-hours", type=int, default=24)
    args = parser.parse_args()

    now = datetime.now(tz=timezone.utc)
    evaluator_name = f"{AGENT_NAME}-rubric-{now.strftime('%y%m%d%H%M%S')}"

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential
        ) as project_client,
    ):
        print(f"Generating rubric evaluator {evaluator_name!r}...")
        poller = project_client.evaluators.begin_create_generation_job(
            job=EvaluatorGenerationInputs(
                model=MODEL,
                evaluator_name=evaluator_name,
                evaluator_display_name=f"{AGENT_NAME} quality rubric",
                evaluator_description="Generated from the agent's job description and production traces.",
                sources=[
                    PromptEvaluatorGenerationJobSource(
                        description="What the agent is for and how it should behave.",
                        prompt=AGENT_JOB_DESCRIPTION,
                    ),
                    TracesEvaluatorGenerationJobSource(
                        description="Production traces of the external weather agent.",
                        agent_name=AGENT_NAME,
                        start_time=now - timedelta(hours=args.lookback_hours),
                        end_time=now,
                    ),
                ],
            ),
            polling_interval=10,
        )
        evaluator = poller.result()

        definition = evaluator.definition
        if not isinstance(definition, RubricBasedEvaluatorDefinition):
            raise SystemExit(f"Expected a rubric evaluator, got: {definition}")
        print(
            f"Created evaluator {evaluator.name!r} version {evaluator.version} with dimensions:"
        )
        for dimension in definition.dimensions:
            print(f"- {dimension.id}: {dimension.description}")
        print(
            "\nUse it in an evaluation as testing criterion evaluator_name="
            f"{evaluator.name!r}, or edit it in the Foundry portal."
        )


if __name__ == "__main__":
    main()
