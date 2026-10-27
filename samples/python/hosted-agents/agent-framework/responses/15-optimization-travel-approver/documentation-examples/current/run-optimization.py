# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Run the selected documentation example explicitly with --run."""

import argparse
import logging
import sys


def example_138():
    # <doc_quickstart_optimize_hosted_agent_2_run_the_optimization_job>
    """
    DESCRIPTION:
        Create an optimization job for a hosted agent using the latest agent
        optimization API, poll the job to completion, and list its candidates.

    USAGE:
        python optimize_hosted_agent_v3.py

        Before running the sample:

        pip install azure-ai-projects azure-ai-agentserver-optimization python-dotenv

        Set these environment variables with your own values:
        1) FOUNDRY_PROJECT_ENDPOINT - Required. The Microsoft Foundry project endpoint.
        2) FOUNDRY_AGENT_NAME       - Required. The hosted agent name.
        3) DATASET_NAME             - Required. The registered training dataset name.
        4) EVALUATOR_NAME           - Required. The registered evaluator name.
        5) DATASET_VERSION          - Optional. The dataset version. Defaults to "1".
        6) EVAL_MODEL               - Optional. The evaluation model. Defaults to "gpt-4o".
        7) OPTIMIZATION_MODEL       - Optional. The optimization model. Defaults to "gpt-5".
        8) POLL_INTERVAL_SECONDS    - Optional. Seconds between status polls. Defaults to 10.
        9) OPTIMIZATION_JOB_ID      - Optional. An existing job ID to resume instead of creating a job.
       10) OPTIMIZATION_LOCAL_DIR   - Optional. Path to the local .agent_configs directory.
       11) CREDENTIAL_PROCESS_TIMEOUT_SECONDS
                                    - Optional. Credential subprocess timeout. Defaults to 60.
    """
    import os
    import time
    from pathlib import Path
    from azure.ai.agentserver.optimization import load_config, load_skills_from_dir
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        AgentOptimizationBaselineAgentConfiguration,
        AgentOptimizationCandidateExpand,
        AgentOptimizationCandidateSearchConfiguration,
        AgentOptimizationConfiguration,
        AgentOptimizationEvaluationConfiguration,
        AgentOptimizationEvaluator,
        AgentOptimizationFoundryAgentTargetConfiguration,
        AgentOptimizationJob,
        AgentOptimizationModelConfiguration,
        AgentOptimizationSkill,
        AgentOptimizationSpace,
        AgentOptimizationTargetCompletionDatasetReferenceDataSource,
        AgentOptimizationTargetCompletionEvaluationSet,
        EvaluationModelConfiguration,
        JobStatus,
        TargetAttribute,
    )
    from azure.identity import DefaultAzureCredential

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    agent_name = os.environ["FOUNDRY_AGENT_NAME"]
    dataset_name = os.environ["FOUNDRY_DATASET_NAME"]
    evaluator_name = os.environ["FOUNDRY_EVALUATOR_NAME"]
    dataset_version = os.environ.get("FOUNDRY_DATASET_VERSION", "1")
    eval_model = os.environ.get("FOUNDRY_EVAL_MODEL", "gpt-4o")
    optimization_model = os.environ.get("FOUNDRY_OPTIMIZATION_MODEL", "gpt-5")
    poll_interval_seconds = int(os.environ.get("FOUNDRY_POLL_INTERVAL_SECONDS", "10"))
    existing_job_id = os.environ.get("FOUNDRY_OPTIMIZATION_JOB_ID")
    credential_process_timeout_seconds = int(
        os.environ.get("FOUNDRY_CREDENTIAL_PROCESS_TIMEOUT_SECONDS", "60")
    )
    optimization_config = load_config()
    target_attributes = [TargetAttribute.INSTRUCTIONS]
    baseline_configuration = None
    if optimization_config:
        loaded_skills = optimization_config.skills
        if not loaded_skills and optimization_config.skills_dir:
            loaded_skills = load_skills_from_dir(Path(optimization_config.skills_dir))
        skills = [
            AgentOptimizationSkill(
                name=skill.name, description=skill.description, body=skill.body or None
            )
            for skill in loaded_skills
        ]
        if skills:
            target_attributes.append(TargetAttribute.SKILLS)
        if optimization_config.tool_definitions:
            target_attributes.append(TargetAttribute.TOOLS)
        baseline_configuration = AgentOptimizationBaselineAgentConfiguration(
            system_prompt=optimization_config.instructions,
            current_model=optimization_config.model,
            skills=skills or None,
            tools=optimization_config.tool_definitions or None,
        )
    with (
        DefaultAzureCredential(
            process_timeout=credential_process_timeout_seconds
        ) as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        job_request = AgentOptimizationJob(
            target_configuration=AgentOptimizationFoundryAgentTargetConfiguration(
                name=agent_name
            ),
            optimization_model_configuration=AgentOptimizationModelConfiguration(
                model=optimization_model
            ),
            optimization_configuration=AgentOptimizationConfiguration(
                evaluation_configuration=AgentOptimizationEvaluationConfiguration(
                    training_set=AgentOptimizationTargetCompletionEvaluationSet(
                        source=AgentOptimizationTargetCompletionDatasetReferenceDataSource(
                            name=dataset_name, version=dataset_version
                        )
                    ),
                    evaluators=[AgentOptimizationEvaluator(name=evaluator_name)],
                    evaluation_model=EvaluationModelConfiguration(model=eval_model),
                ),
                candidate_search_configuration=AgentOptimizationCandidateSearchConfiguration(
                    max_candidates=2
                ),
                baseline_agent_configuration=baseline_configuration,
                agent_optimization_space=AgentOptimizationSpace(
                    target_attributes=target_attributes
                ),
            ),
        )
        if existing_job_id:
            job_id = existing_job_id
        else:
            poller = project_client.agents.begin_create_optimization_job(
                job=job_request, polling=False
            )
            job_id = poller.details.get("job_id")
            if not isinstance(job_id, str):
                raise RuntimeError(
                    "The create operation did not return an optimization job ID."
                )
        print(f"Optimization job ID: {job_id}")
        terminal_statuses = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
        job = project_client.agents.get_optimization_job(job_id=job_id)
        print("Optimization job started, waiting for completion...")
        while job.status not in terminal_statuses:
            print(f"\tstatus=`{job.status}`")
            time.sleep(poll_interval_seconds)
            job = project_client.agents.get_optimization_job(job_id=job_id)
        print(f"\tstatus=`{job.status}`")
        for warning in job.warnings or []:
            print(f"[WARNING] {warning}")
        if job.status == JobStatus.FAILED:
            message = job.error.message if job.error else "<no error message>"
            raise RuntimeError(f"Optimization job `{job.id}` failed: {message}")
        if job.status == JobStatus.CANCELLED:
            raise RuntimeError(f"Optimization job `{job.id}` was cancelled.")
        if job.result is None:
            raise RuntimeError(
                f"Optimization job `{job.id}` completed without a result."
            )
        result = job.result
        summary = result.candidate_summary
        if summary:
            print(f"Baseline candidate: {summary.baseline_id}")
            print(f"Best candidate: {summary.best_id}")
            print(
                f"Completed optimized candidates: {summary.completed_candidate_count}"
            )
            if summary.baseline_score is not None:
                print(f"Baseline score: {summary.baseline_score:.4f}")
            if summary.best_score is not None:
                print(f"Best score: {summary.best_score:.4f}")
        if result.termination_reason:
            print(f"Termination reason: {result.termination_reason}")
        for candidate in project_client.agents.list_optimization_candidates(
            job_id=job_id, expand=[AgentOptimizationCandidateExpand.MUTATIONS]
        ):
            details = [
                f"{candidate.name}: candidate_id={candidate.candidate_id}",
                f"status={candidate.status}",
            ]
            if candidate.evaluation:
                if candidate.evaluation.score is not None:
                    details.append(f"score={candidate.evaluation.score:.4f}")
                if candidate.evaluation.avg_tokens is not None:
                    details.append(f"avg_tokens={candidate.evaluation.avg_tokens:.0f}")
            print(", ".join(details))
    # </doc_quickstart_optimize_hosted_agent_2_run_the_optimization_job>


def main():
    examples = {"aip-python-138": example_138}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        required=True,
        help="Execute the example; it can call Azure and create resources.",
    )
    parser.add_argument("--example", choices=examples, default="aip-python-138")
    options = parser.parse_args()
    logging.info("Running example %s", options.example)
    examples[options.example]()
    logging.info("Example %s completed", options.example)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
