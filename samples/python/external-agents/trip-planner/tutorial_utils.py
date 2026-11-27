"""Shared helpers for the tutorial steps: Foundry clients, settings, and a small state file.

Each step saves the names it creates (dataset, evaluators, rule) in
``.tutorial_state.json`` so that later steps can use them.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

HERE = Path(__file__).parent
STATE_FILE = HERE / ".tutorial_state.json"
TRAFFIC_LOG = HERE / "traffic_log.jsonl"
AGENT_NAME = os.environ.get("FOUNDRY_AGENT_NAME", "contoso-trip-planner")
# Judge and analysis model: Agent Insights and skill optimization need a GPT-5 or later deployment.
JUDGE_MODEL = (
    os.environ.get("JUDGE_MODEL_DEPLOYMENT") or os.environ["AZURE_OPENAI_DEPLOYMENT"]
)


class TutorialState:
    """Read and update the names saved by earlier steps."""

    @staticmethod
    def load() -> dict[str, Any]:
        """Return the saved state, or an empty dict before the first step."""
        return (
            json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if STATE_FILE.exists()
            else {}
        )

    @staticmethod
    def update(**values: Any) -> None:
        """Merge values into the saved state."""
        state = TutorialState.load()
        state.update(values)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    @staticmethod
    def require(key: str, step: str) -> Any:
        """Return a saved value, or stop with a pointer to the step that creates it."""
        value = TutorialState.load().get(key)
        if value is None:
            raise SystemExit(f"Missing '{key}'. Run {step} first.")
        return value


def project_client():
    """Return an AIProjectClient for FOUNDRY_PROJECT_ENDPOINT."""
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    return AIProjectClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
    )


def read_traffic_log() -> list[dict[str, Any]]:
    """Return the requests recorded by 02_send_traffic.py."""
    if not TRAFFIC_LOG.exists():
        raise SystemExit("No traffic log found. Run 02_send_traffic.py first.")
    return [
        json.loads(line)
        for line in TRAFFIC_LOG.read_text(encoding="utf-8").splitlines()
        if line
    ]


def download_dataset_rows(project, name: str, version: str) -> list[dict[str, Any]]:
    """Download a JSONL dataset from Foundry and return its rows."""
    from azure.storage.blob import ContainerClient

    reference = project.datasets.get_credentials(
        name=name, version=version
    ).blob_reference
    container = ContainerClient.from_container_url(reference.credential.sas_uri)
    # blob_uri points at this version's file or folder; read only that, not the whole container.
    path = unquote(urlparse(reference.blob_uri).path).split("/", 2)[2]
    blob_names = (
        [path]
        if path.endswith(".jsonl")
        else [
            blob
            for blob in container.list_blob_names(
                name_starts_with=path.rstrip("/") + "/"
            )
            if blob.endswith(".jsonl")
        ]
    )
    rows: list[dict[str, Any]] = []
    for blob_name in blob_names:
        text = container.download_blob(blob_name).readall().decode("utf-8")
        rows.extend(json.loads(line) for line in text.splitlines() if line.strip())
    return rows


def wait_for_eval_run(
    openai_client, eval_id: str, run_id: str, timeout_seconds: int = 1800
):
    """Poll an evaluation run until it finishes and return it."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        run = openai_client.evals.runs.retrieve(run_id=run_id, eval_id=eval_id)
        if run.status in ("completed", "failed", "canceled"):
            return run
        print(f"  status={run.status} ...")
        time.sleep(15)
    raise TimeoutError(
        f"Evaluation run {run_id} didn't finish within {timeout_seconds}s"
    )
