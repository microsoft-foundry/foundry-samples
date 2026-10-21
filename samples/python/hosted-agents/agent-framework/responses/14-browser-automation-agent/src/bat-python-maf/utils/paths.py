from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_skill_path() -> Path:
    return project_root() / "skills"


def skill_paths() -> list[Path]:
    return [default_skill_path()]


def prompts_root() -> Path:
    return project_root() / "prompts"
