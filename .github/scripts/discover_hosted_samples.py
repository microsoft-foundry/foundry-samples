#!/usr/bin/env python3
"""
Discover valid hosted agent samples for GitHub Actions matrix.

A valid hosted agent sample is a directory containing:
- agent.yaml (defines the hosted agent configuration)
- main.py (entry point)
- requirements.txt (dependencies)

Outputs JSON array of sample paths relative to repository root.
"""

import json
import sys
from pathlib import Path


def find_hosted_samples(base_path: Path) -> list[dict]:
    """Find all valid hosted agent sample directories.
    
    Args:
        base_path: Path to the hosted-agents directory
        
    Returns:
        List of dicts with sample info (path, name, framework)
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
            "framework": framework
        })
    
    return sorted(samples, key=lambda x: x["path"])


def main():
    # Default path relative to repo root
    repo_root = Path(__file__).parent.parent.parent
    hosted_agents_path = repo_root / "samples" / "python" / "hosted-agents"
    
    if not hosted_agents_path.exists():
        print(f"Error: Path not found: {hosted_agents_path}", file=sys.stderr)
        sys.exit(1)
    
    samples = find_hosted_samples(hosted_agents_path)
    
    if not samples:
        print("Warning: No valid hosted agent samples found", file=sys.stderr)
    
    # Output JSON for GitHub Actions
    print(json.dumps(samples))


if __name__ == "__main__":
    main()
