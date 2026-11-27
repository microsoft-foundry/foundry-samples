"""Step 6: Define shared quality criteria with a generated rubric.

Task-level rubrics (step 5) check specific cases. A shared rubric applies the
same criteria to every response. Foundry generates one from a description of the
agent's job that you write, plus its production traces. You can also pass
dimensions you've already approved; Foundry keeps them and generates the rest.

Here the team adds one criterion of its own: policy answers must come from
policy_lookup. That carries the carry-on lesson over to fees and seat rules.

    python 06_generate_shared_rubric.py

Run it again later to regenerate: Foundry keeps the dimensions you pass and
adds a new evaluator version.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

from azure.ai.projects.models import (
    Dimension,
    EvaluatorGenerationInputs,
    PromptEvaluatorGenerationJobSource,
    RubricBasedEvaluatorDefinition,
    TracesEvaluatorGenerationJobSource,
)

from tutorial_utils import AGENT_NAME, JUDGE_MODEL, TutorialState, project_client

EVALUATOR_NAME = f"{AGENT_NAME}-shared-rubric"
AGENT_JOB_DESCRIPTION = (
    "Contoso Travel's trip planner helps travelers book flights and hotels. It searches flights per leg "
    "with search_flights and hotels with search_hotels, and answers policy questions about bags, fees, "
    "changes, and seats. Policies change often, so it must answer policy questions only from the "
    "policy_lookup tool. Answers should be short, list concrete options with prices, and cover every "
    "leg of a multi-city trip in travel order."
)
APPROVED_DIMENSIONS = [
    Dimension(
        id="policy_from_lookup",
        description="Every bag, fee, change, or seat rule in the answer comes from a policy_lookup result "
        "in the same turn, not from memory or instructions.",
    ),
]


def main() -> None:
    """Generate (or regenerate) the shared rubric evaluator."""
    sys.stdout.reconfigure(encoding="utf-8")
    now = datetime.now(UTC)
    with project_client() as project:
        print(
            f"Generating shared rubric {EVALUATOR_NAME!r} from the job description and recent traces..."
        )
        poller = project.evaluators.begin_create_generation_job(
            job=EvaluatorGenerationInputs(
                model=JUDGE_MODEL,
                evaluator_name=EVALUATOR_NAME,
                evaluator_display_name="Contoso trip planner quality",
                evaluator_description="Shared rubric for the trip planner.",
                dimensions=APPROVED_DIMENSIONS,
                sources=[
                    PromptEvaluatorGenerationJobSource(
                        description="The agent's job.", prompt=AGENT_JOB_DESCRIPTION
                    ),
                    TracesEvaluatorGenerationJobSource(
                        description="Production traces.",
                        agent_name=AGENT_NAME,
                        start_time=now - timedelta(days=7),
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
    TutorialState.update(
        shared_rubric={"name": evaluator.name, "version": evaluator.version}
    )
    print(f"Created {evaluator.name} version {evaluator.version}:")
    for dimension in definition.dimensions:
        print(f"- {dimension.id}: {dimension.description}")
    print(
        "Edit the dimensions in the Foundry portal (Evaluation > Evaluators) to match your standards."
    )


if __name__ == "__main__":
    main()
