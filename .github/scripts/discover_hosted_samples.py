#!/usr/bin/env python3
"""
Discover valid hosted agent samples for GitHub Actions matrix.

A valid Python hosted agent sample is a directory containing:
- agent.yaml (defines the hosted agent configuration)
- main.py (entry point)
- requirements.txt (dependencies)

A valid C# hosted agent sample is a directory containing:
- agent.yaml (defines the hosted agent configuration)
- *.csproj (C# project file)
- Program.cs (entry point)

Outputs JSON array of sample paths relative to repository root.
"""

import json
import sys
from pathlib import Path


def find_python_hosted_samples(base_path: Path) -> list[dict]:
    """Find all valid Python hosted agent sample directories.

    Args:
        base_path: Path to the python/hosted-agents directory

    Returns:
        List of dicts with sample info (path, name, framework, language)
    """
    samples = []

    for agent_yaml in base_path.rglob("agent.yaml"):
        sample_dir = agent_yaml.parent

        # Validate required files exist
        if not (sample_dir / "main.py").exists():
            continue
        if not (sample_dir / "requirements.txt").exists():
            continue

        # Determine framework based on parent directory
        rel_path = sample_dir.relative_to(base_path)
        parts = rel_path.parts
        framework = parts[0] if len(parts) > 1 else "unknown"

        # Get path relative to repo root
        repo_root = base_path.parent.parent.parent
        sample_path = str(sample_dir.relative_to(repo_root)).replace("\\", "/")

        samples.append({
            "path": sample_path,
            "name": sample_dir.name,
            "framework": framework,
            "language": "python"
        })

    return sorted(samples, key=lambda x: x["path"])


def find_csharp_hosted_samples(base_path: Path) -> list[dict]:
    """Find all valid C# hosted agent sample directories.

    Args:
        base_path: Path to the csharp/hosted-agents directory

    Returns:
        List of dicts with sample info (path, name, framework, language)
    """
    samples = []

    for agent_yaml in base_path.rglob("agent.yaml"):
        sample_dir = agent_yaml.parent

        # Validate required files exist
        csproj_files = list(sample_dir.glob("*.csproj"))
        if not csproj_files:
            continue
        if not (sample_dir / "Program.cs").exists():
            continue

        # Determine framework based on parent directory
        rel_path = sample_dir.relative_to(base_path)
        parts = rel_path.parts
        framework = parts[0] if len(parts) > 1 else "csharp"

        # Get path relative to repo root
        repo_root = base_path.parent.parent.parent
        sample_path = str(sample_dir.relative_to(repo_root)).replace("\\", "/")

        samples.append({
            "path": sample_path,
            "name": sample_dir.name,
            "framework": framework,
            "language": "csharp"
        })

    return sorted(samples, key=lambda x: x["path"])


def main():
    repo_root = Path(__file__).parent.parent.parent
    all_samples = []

    # Discover Python samples
    python_path = repo_root / "samples" / "python" / "hosted-agents"
    if python_path.exists():
        python_samples = find_python_hosted_samples(python_path)
        all_samples.extend(python_samples)

    # Discover C# samples
    csharp_path = repo_root / "samples" / "csharp" / "hosted-agents"
    if csharp_path.exists():
        csharp_samples = find_csharp_hosted_samples(csharp_path)
        all_samples.extend(csharp_samples)

    if not all_samples:
        print("Warning: No valid hosted agent samples found", file=sys.stderr)

    # Output JSON for GitHub Actions
    print(json.dumps(all_samples))


if __name__ == "__main__":
    main()
