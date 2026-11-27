"""Step 5 (preview): Turn annotated traces into test cases for a golden dataset.

A data generation job reads the annotated traces and creates one dataset row per
captured turn: the user's question, the agent's answer, and the reviewer's
expected answer. With ``generate_test_case_rubric=True`` (preview), Foundry also
writes a task-level rubric for each row: pass/fail criteria for that specific
case, such as "calls policy_lookup before giving a bag rule".

    python 05_create_test_cases.py

The rows are also saved to golden_dataset.generated.jsonl so that you can
review them. Edit any row that is too strict, then merge the rows you trust into
golden_dataset.jsonl, the reviewed set that step 8 re-runs.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta

from azure.ai.projects.models import (
    DataGenerationModelOptions,
    DatasetDataGenerationJobOutput,
    EvaluationDataGenerationJobInputs,
    EvaluationDataGenerationJobOutputConfiguration,
    TracesDataGenerationJobConfiguration,
    TracesDataGenerationJobSource,
)

from tutorial_utils import (
    AGENT_NAME,
    HERE,
    JUDGE_MODEL,
    TutorialState,
    download_dataset_rows,
    project_client,
)

GENERATED_FILE = HERE / "golden_dataset.generated.jsonl"


def main() -> None:
    """Generate test cases from the annotated traces and save them locally for review."""
    sys.stdout.reconfigure(encoding="utf-8")
    trace_ids = TutorialState.require("annotated_trace_ids", "04_annotate_traces.py")
    now = datetime.now(UTC)
    dataset_name = f"{AGENT_NAME}-test-cases-{now.strftime('%y%m%d%H%M%S')}"

    with project_client() as project:
        print(f"Generating test cases from {len(trace_ids)} annotated traces...")
        poller = project.datasets.begin_create_generation_job(
            job=EvaluationDataGenerationJobInputs(
                name=dataset_name,
                sources=[
                    TracesDataGenerationJobSource(
                        description="Traces reviewed by the support lead.",
                        agent_name=AGENT_NAME,
                        trace_ids=trace_ids,
                        start_time=now - timedelta(days=7),
                        end_time=now,
                    )
                ],
                generation_configuration=TracesDataGenerationJobConfiguration(
                    generate_test_case_rubric=True,  # preview
                    model_options=DataGenerationModelOptions(model=JUDGE_MODEL),
                ),
                output_configuration=EvaluationDataGenerationJobOutputConfiguration(
                    name=dataset_name
                ),
            ),
            polling_interval=10,
        )
        result = poller.result()
        output = next(
            (
                o
                for o in result.outputs or []
                if isinstance(o, DatasetDataGenerationJobOutput)
            ),
            None,
        )
        if output is None:
            raise SystemExit(f"The job finished without a dataset: {result}")
        print(
            f"Created dataset {output.name} version {output.version} ({result.generated_samples} rows)."
        )
        TutorialState.update(
            test_case_dataset={"name": output.name, "version": output.version}
        )

        rows = download_dataset_rows(project, output.name, output.version)
    GENERATED_FILE.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    print(
        f"Saved {len(rows)} rows to {GENERATED_FILE.name}. Columns: {', '.join(rows[0]) if rows else '(none)'}"
    )


if __name__ == "__main__":
    main()
