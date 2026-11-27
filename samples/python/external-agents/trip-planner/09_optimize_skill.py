"""Step 9 (preview): Learn from past traces with skill optimization.

Skill optimization analyzes the agent's past traces, along with any annotations
and evaluation results, and proposes a new or updated skill: a versioned folder
of instructions (a SKILL.md file plus optional scripts and reference files) that
an agent can load when it needs it.

    python 09_optimize_skill.py --lookback-hours 72

A successful run means the run finished, not that the proposal is better.
Review the findings and the proposed skill. Because the agent runs outside
Foundry, the script downloads the skill into ./skills, which agent.py loads
with --skills. Then re-run the golden dataset (step 8) to compare.
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
import uuid
import zipfile
from datetime import UTC, datetime, timedelta

from azure.ai.projects.models import (
    AgentOptimizationFixedTraceWindow,
    AgentOptimizationFoundryAgentTargetConfiguration,
    AgentOptimizationJob,
    AgentOptimizationModelConfiguration,
    AgentTracesOptimizationContext,
    SkillOptimizationConfiguration,
    SteeringPromptOptimizationContext,
)

from tutorial_utils import AGENT_NAME, HERE, JUDGE_MODEL, TutorialState, project_client

SKILLS_DIR = HERE / "skills"
FOCUS = "Improve multi-city trip planning: search each requested leg exactly once, in travel order."


def start_job(project, lookback_hours: float):
    """Start a skill optimization job over the agent's recent traces, wait for it, and return its ID."""
    now = datetime.now(UTC)
    job = AgentOptimizationJob(
        display_name=f"{AGENT_NAME} multi-city skill",
        target_configuration=AgentOptimizationFoundryAgentTargetConfiguration(
            name=AGENT_NAME
        ),
        optimization_model_configuration=AgentOptimizationModelConfiguration(
            model=JUDGE_MODEL
        ),
        optimization_configuration=SkillOptimizationConfiguration(
            context=[
                AgentTracesOptimizationContext(
                    trace_window=AgentOptimizationFixedTraceWindow(
                        start_time=now - timedelta(hours=lookback_hours),
                        end_time=now,
                        max_traces=50,
                    )
                ),
                SteeringPromptOptimizationContext(prompt=FOCUS),
            ]
        ),
    )
    poller = project.agents.begin_create_optimization_job(
        job=job, operation_id=str(uuid.uuid4())
    )
    print(
        f"Started skill optimization over the last {lookback_hours}h of traces; this takes several minutes..."
    )
    poller.result()
    return poller.details["job_id"]


def download_skills(project, job_id: str) -> list[str]:
    """Print each proposed skill's rationale and download it into ./skills."""
    downloaded = []
    for candidate in project.agents.list_optimization_candidates(job_id=job_id):
        details = project.agents.get_optimization_candidate(
            job_id=job_id, candidate_id=candidate.candidate_id
        )
        for skill in getattr(details.output, "skill_results", None) or []:
            print(
                f"\n[{skill.status}] {skill.output_skill.name}\n  Why: {skill.rationale or skill.error}"
            )
            version = getattr(skill.output_skill, "version", None)
            if not version:
                continue
            archive = b"".join(
                project.beta.skills.download_version(
                    name=skill.output_skill.name, version=version
                )
            )
            target = SKILLS_DIR / skill.output_skill.name
            shutil.rmtree(target, ignore_errors=True)
            zipfile.ZipFile(io.BytesIO(archive)).extractall(target)
            downloaded.append(str(target.relative_to(HERE)))
    return downloaded


def main() -> None:
    """Run skill optimization and download the proposed skills."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--lookback-hours", type=float, default=72)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    with project_client() as project:
        job_id = start_job(project, args.lookback_hours)
        TutorialState.update(skill_optimization_job_id=job_id)
        print(f"Job {job_id} finished.")
        downloaded = download_skills(project, job_id)
    if downloaded:
        print(f"\nDownloaded: {', '.join(downloaded)}. Review SKILL.md, then run:")
        print("  python 08_run_golden_dataset.py --instructions v2 --skills ./skills")
    else:
        print(
            "\nNo new skill was proposed. Review the job in the Foundry portal (Agents > your agent > Optimize)."
        )


if __name__ == "__main__":
    main()
