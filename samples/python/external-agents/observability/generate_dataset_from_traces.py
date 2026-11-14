"""Generate an evaluation dataset from the external weather agent's traces.

A data generation job reads the agent's recent traces from the connected
Application Insights resource and turns each captured turn into a dataset row
(query, response, and tool context) that you can review and re-run as a test.
Turn-level dataset generation from traces is generally available through
``project_client.datasets.begin_create_generation_job``.

Test-case rubrics (``generate_test_case_rubric=True``) and conversation-level
jobs are still in preview, so this script doesn't use them.

Prerequisite: the Foundry project's managed identity needs the Reader role on
the connected Application Insights resource so the job can query traces.

Usage:
    python generate_dataset_from_traces.py
    python generate_dataset_from_traces.py --lookback-hours 6 --max-samples 20
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
    DatasetDataGenerationJobOutput,
    EvaluationDataGenerationJobInputs,
    EvaluationDataGenerationJobOutputConfiguration,
    TracesDataGenerationJobConfiguration,
    TracesDataGenerationJobSource,
)
from azure.identity import DefaultAzureCredential

AGENT_NAME = os.environ.get("AGENT_NAME", "weather-agent")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--max-samples", type=int, default=15)
    args = parser.parse_args()

    end_time = datetime.now(tz=timezone.utc)
    start_time = end_time - timedelta(hours=args.lookback_hours)
    run_suffix = end_time.strftime("%y%m%d%H%M%S")
    dataset_name = f"{AGENT_NAME}-traces-{run_suffix}"

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential
        ) as project_client,
    ):
        print(
            f"Generating dataset {dataset_name!r} from {AGENT_NAME!r} traces (last {args.lookback_hours}h)..."
        )
        poller = project_client.datasets.begin_create_generation_job(
            job=EvaluationDataGenerationJobInputs(
                name=f"{AGENT_NAME}-traces-{run_suffix}",
                sources=[
                    TracesDataGenerationJobSource(
                        description="Production traces of the external weather agent.",
                        agent_name=AGENT_NAME,
                        start_time=start_time,
                        end_time=end_time,
                    )
                ],
                # max_samples caps the dataset size. Private content is redacted by default.
                generation_configuration=TracesDataGenerationJobConfiguration(
                    max_samples=args.max_samples
                ),
                output_configuration=EvaluationDataGenerationJobOutputConfiguration(
                    name=dataset_name
                ),
            ),
            polling_interval=10,
        )
        result = poller.result()

        dataset = next(
            (
                o
                for o in result.outputs or []
                if isinstance(o, DatasetDataGenerationJobOutput)
            ),
            None,
        )
        if dataset is None:
            raise SystemExit(f"The job finished without a dataset output: {result}")
        print(
            f"Generated dataset {dataset.name!r} version {dataset.version} ({result.generated_samples} samples)."
        )
        print(
            "Review it in the Foundry portal under Data, then use it in an evaluation."
        )


if __name__ == "__main__":
    main()
