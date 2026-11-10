"""Run hosted-agent runtime regressions outside the lightweight policy suite."""

from __future__ import annotations

import subprocess
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    project = root / (
        "samples/python/hosted-agents/langgraph/responses/07-human-in-the-loop/"
        "src/langgraph-human-in-the-loop-responses"
    )
    subprocess.run(
        ["uv", "sync", "--frozen", "--python", "3.13", "--project", str(project)],
        cwd=root,
        check=True,
    )
    subprocess.run(
        [
            "uv",
            "run",
            "--no-sync",
            "--project",
            str(project),
            "python",
            "-m",
            "unittest",
            "discover",
            "-s",
            ".github/scripts/runtime-tests",
            "-p",
            "test_*.py",
        ],
        cwd=root,
        check=True,
    )


if __name__ == "__main__":
    main()
