"""Submit and monitor a SchemaRAFT fine-tuning job on Microsoft Foundry.

    python submit_finetune.py --train-file data/schemaraft_train.jsonl \
                              --val-file   data/schemaraft_val.jsonl

State is written to `finetune_job.json`, so `--resume` reattaches to a running
job instead of paying for a second one.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from eval_jga import load_dotenv_if_present
from foundry_client import make_client

HERE = Path(__file__).resolve().parent
STATE_PATH = HERE / "finetune_job.json"
TERMINAL = {"succeeded", "failed", "cancelled"}


def upload(client, path: Path) -> str:
    print(f"[upload] {path.name} ({path.stat().st_size / 1e6:.1f} MB)")
    with path.open("rb") as f:
        resp = client.files.create(file=f, purpose="fine-tune")
    print(f"         id={resp.id} status={resp.status}")
    return resp.id


def wait_processed(client, file_ids: list[str], timeout: int = 900) -> None:
    deadline = time.time() + timeout
    pending = set(file_ids)
    while pending and time.time() < deadline:
        for fid in list(pending):
            info = client.files.retrieve(fid)
            if info.status == "processed":
                pending.discard(fid)
            elif info.status == "error":
                raise RuntimeError(f"file {fid} failed validation: {info}")
        if pending:
            print(f"[wait] {len(pending)} file(s) still processing")
            time.sleep(10)
    if pending:
        raise TimeoutError(f"files not processed within {timeout}s: {pending}")
    print("[ok] files processed")


def poll(client, job_id: str, interval: int = 60) -> str | None:
    print(f"[poll] watching {job_id} (every {interval}s; Ctrl-C is safe, use --resume)")
    t0 = time.time()
    while True:
        job = client.fine_tuning.jobs.retrieve(job_id)
        print(
            f"  t={(time.time() - t0) / 60:5.1f}m  status={job.status}  "
            f"trained_tokens={getattr(job, 'trained_tokens', None)}"
        )
        if job.status in TERMINAL:
            if job.status != "succeeded":
                raise RuntimeError(
                    f"job ended with status={job.status}: "
                    f"{getattr(job, 'error', None)}"
                )
            return job.fine_tuned_model
        time.sleep(interval)


def main() -> None:
    load_dotenv_if_present()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--train-file", type=Path, default=HERE / "data" / "schemaraft_train.jsonl"
    )
    ap.add_argument("--val-file", type=Path, default=None)
    ap.add_argument(
        "--base-model", default=os.environ.get("BASE_MODEL", "gpt-4.1-mini-2025-04-14")
    )
    ap.add_argument("--suffix", default="schemaraft")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--endpoint", default=None)
    ap.add_argument(
        "--resume", action="store_true", help="reattach to the saved job id"
    )
    args = ap.parse_args()

    client = make_client(args.endpoint)
    state = (
        json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if STATE_PATH.exists()
        else {}
    )

    if args.resume and state.get("job_id"):
        job_id = state["job_id"]
    else:
        ids = [upload(client, args.train_file)]
        kwargs = {"training_file": ids[0]}
        if args.val_file:
            ids.append(upload(client, args.val_file))
            kwargs["validation_file"] = ids[1]
        wait_processed(client, ids)

        print(f"[job] base={args.base_model} suffix={args.suffix} epochs={args.epochs}")
        job = client.fine_tuning.jobs.create(
            model=args.base_model,
            suffix=args.suffix,
            method={
                "type": "supervised",
                "supervised": {"hyperparameters": {"n_epochs": args.epochs}},
            },
            **kwargs,
        )
        job_id = job.id
        state = {"job_id": job_id, "base_model": args.base_model}
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(f"      job_id={job_id}  (saved to {STATE_PATH.name})")

    model = poll(client, job_id)
    state["fine_tuned_model"] = model
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

    print(f"\n[done] fine-tuned model: {model}")
    print("Deploy it in the Foundry portal, then re-run:")
    print(
        "  python eval_jga.py --mode retrieved_distractor --deployment <deployment-name>"
    )


if __name__ == "__main__":
    main()
