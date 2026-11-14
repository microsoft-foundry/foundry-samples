"""Step 8: Measure and compare: run the golden dataset against an agent version.

The golden dataset lives in Foundry. The first run uploads golden_dataset.jsonl
as a dataset tagged `golden`; later runs reuse it. Foundry can't call an external
agent, so this script reads the golden rows, runs the agent locally on each one,
uploads the answers as a dataset, and scores them in Foundry with the same
evaluators every time:

- task_rubric: the row's own pass/fail criteria (builtin.task_level_rubric)
- shared_rubric: the shared rubric from step 6
- policy_accuracy: the custom policy evaluator from step 7

Run it before and after a change, then compare:

    python 08_run_golden_dataset.py --instructions v1
    python 08_run_golden_dataset.py --instructions v2
    python 08_run_golden_dataset.py --instructions v2 --skills ./skills   # after step 9

After you edit golden_dataset.jsonl, pass a new --golden-version so the change
is uploaded as a new version, and compare agent versions on the same one.

Each run's pass rates are saved, and the script prints every saved run side by side.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from azure.core.exceptions import ResourceNotFoundError

from agent import ask, build_agent
from travel_tools import TOOLS
from tutorial_utils import (
    AGENT_NAME,
    HERE,
    JUDGE_MODEL,
    TutorialState,
    download_dataset_rows,
    project_client,
    wait_for_eval_run,
)

GOLDEN_FILE = HERE / "golden_dataset.jsonl"
GOLDEN_DATASET = f"{AGENT_NAME}-golden"
ANSWERS_DATASET = f"{AGENT_NAME}-golden-answers"
CRITERIA = ["task_rubric", "shared_rubric", "policy_accuracy"]


def tool_definitions() -> list[dict]:
    """Describe the agent's tools in the format evaluators read."""
    from agent_framework import FunctionTool

    definitions = []
    for tool in TOOLS:
        function = FunctionTool(
            name=tool.__name__, description=tool.__doc__ or "", func=tool
        )
        definitions.append(
            {
                "type": "function",
                "name": function.name,
                "description": function.description,
                "parameters": function.parameters(),
            }
        )
    return definitions


async def answer_rows(
    instructions: str, skills: str | None, rows: list[dict]
) -> list[dict]:
    """Run the agent on each golden row and return one evaluation row per answer."""
    agent = build_agent(instructions, skills)
    definitions = tool_definitions()
    items = []
    for row in rows:
        answer = await ask(agent, row["query"])
        items.append(
            {
                "id": row["id"],
                "query": row["query"],
                "response": answer.messages,
                "tool_definitions": definitions,
                "expected": row["expected"],
                "rubric_dimensions": row["rubric_dimensions"],
            }
        )
        print(f"  answered {row['id']}")
    return items


def ensure_golden_dataset(project, version: str) -> list[dict]:
    """Upload golden_dataset.jsonl as a `golden` dataset version if needed, and return its rows."""
    try:
        project.datasets.get(name=GOLDEN_DATASET, version=version)
        print(f"Using golden dataset {GOLDEN_DATASET}:{version}")
    except ResourceNotFoundError:
        dataset = project.datasets.upload_file(
            name=GOLDEN_DATASET, version=version, file_path=str(GOLDEN_FILE)
        )
        dataset.tags = {"golden": "true"}
        project.datasets.create_or_update(
            name=GOLDEN_DATASET, version=version, dataset_version=dataset
        )
        print(f"Uploaded golden dataset {GOLDEN_DATASET}:{version}")
    return download_dataset_rows(project, GOLDEN_DATASET, version)


def upload_answers(project, items: list[dict]) -> str:
    """Upload the agent's answers as a new dataset version and return its ID."""
    version = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "answers.jsonl"
        lines = [json.dumps(item, ensure_ascii=False) for item in items]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        dataset = project.datasets.upload_file(
            name=ANSWERS_DATASET, version=version, file_path=str(path)
        )
    print(f"Uploaded answers as {ANSWERS_DATASET}:{version}")
    return dataset.id


def testing_criteria() -> list[dict]:
    """Return the three evaluators used for every golden-dataset run."""
    shared = TutorialState.require("shared_rubric", "06_generate_shared_rubric.py")
    policy = TutorialState.require("policy_evaluator", "07_evaluate_continuously.py")
    base = {"query": "{{item.query}}", "response": "{{item.response}}"}
    init = {"deployment_name": JUDGE_MODEL}
    return [
        {
            "type": "azure_ai_evaluator",
            "name": "task_rubric",
            "evaluator_name": "builtin.task_level_rubric",
            "data_mapping": {
                **base,
                "rubric_dimensions": "{{item.rubric_dimensions}}",
                "tool_definitions": "{{item.tool_definitions}}",
            },
            "initialization_parameters": init,
        },
        {
            "type": "azure_ai_evaluator",
            "name": "shared_rubric",
            "evaluator_name": shared["name"],
            "data_mapping": {**base, "tool_definitions": "{{item.tool_definitions}}"},
            "initialization_parameters": init,
        },
        {
            "type": "azure_ai_evaluator",
            "name": "policy_accuracy",
            "evaluator_name": policy["name"],
            "data_mapping": base,
            "initialization_parameters": {**init, "threshold": 3},
        },
    ]


def get_or_create_eval(openai_client) -> str:
    """Reuse one evaluation for every golden run so runs line up in the portal."""
    eval_id = TutorialState.load().get("golden_eval_id")
    if eval_id:
        return eval_id
    group = openai_client.evals.create(
        name="Contoso trip planner golden dataset",
        data_source_config={
            "type": "custom",
            "include_sample_schema": False,
            "item_schema": {
                "type": "object",
                "required": ["query", "response"],
                "properties": {
                    "query": {"type": "string"},
                    "response": {"type": "array"},
                    "tool_definitions": {"type": "array"},
                    "expected": {"type": "string"},
                    "rubric_dimensions": {"type": "array"},
                },
            },
        },
        testing_criteria=testing_criteria(),
    )
    TutorialState.update(golden_eval_id=group.id)
    return group.id


def pass_rates(run) -> dict[str, str]:
    """Return 'passed/total' per criterion for a finished run."""
    rates = {}
    for result in run.per_testing_criteria_results or []:
        total = result.passed + result.failed
        rates[result.testing_criteria] = f"{result.passed}/{total}"
    return rates


def print_comparison(results: dict[str, dict[str, str]]) -> None:
    """Print every saved golden run side by side."""
    labels = list(results)
    print("\n" + "criterion".ljust(18) + "".join(label.ljust(16) for label in labels))
    for criterion in CRITERIA:
        print(
            criterion.ljust(18)
            + "".join(results[label].get(criterion, "-").ljust(16) for label in labels)
        )


def main() -> None:
    """Answer the golden dataset with one agent version, score it, and compare with earlier runs."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--instructions", choices=["v1", "v2"], default="v1")
    parser.add_argument(
        "--skills", help="Folder with SKILL.md skills to load, such as ./skills."
    )
    parser.add_argument(
        "--golden-version",
        default="1",
        help="Golden dataset version to use. Use a new one after editing golden_dataset.jsonl.",
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    label = args.instructions + ("+skills" if args.skills else "")

    testing_criteria()  # fail fast if steps 6 and 7 haven't run
    with project_client() as project, project.get_openai_client() as openai_client:
        rows = ensure_golden_dataset(project, args.golden_version)
        print(f"Answering {len(rows)} golden rows with {label}...")
        items = asyncio.run(answer_rows(args.instructions, args.skills, rows))
        answers_id = upload_answers(project, items)

        eval_id = get_or_create_eval(openai_client)
        run = openai_client.evals.runs.create(
            eval_id=eval_id,
            name=f"golden-{label}",
            data_source={
                "type": "jsonl",
                "source": {"type": "file_id", "id": answers_id},
            },
        )
        print(f"Scoring in Foundry (run {run.id})...")
        run = wait_for_eval_run(openai_client, eval_id, run.id)
    if run.status != "completed":
        raise SystemExit(f"Evaluation run ended with status {run.status}: {run.error}")

    results = TutorialState.load().get("golden_results", {})
    results[label] = pass_rates(run)
    TutorialState.update(golden_results=results)
    print_comparison(results)


if __name__ == "__main__":
    main()
