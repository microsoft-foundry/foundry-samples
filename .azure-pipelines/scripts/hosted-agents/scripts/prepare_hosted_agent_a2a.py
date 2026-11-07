#!/usr/bin/env python3
"""Prepare job-local native A2A services without collapsing specialist services."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".github" / "scripts"))
from hosted_agent_test_spec import load_spec


def prepare(
    manifest: dict[str, Any], sample: dict[str, Any], sample_dir: Path, agent_name: str
) -> dict[str, Any]:
    manifest = copy.deepcopy(manifest)
    services = manifest["services"]
    agents = {
        key: service
        for key, service in services.items()
        if service.get("host") == "azure.ai.agent"
    }
    selected = sample.get("service")
    if selected is None and len(agents) == 1:
        selected = next(iter(agents))
    if selected not in agents:
        raise ValueError(
            "Multi-agent A2A fixtures must select sample.service from azure.yaml"
        )
    if any(
        not any(
            entry.get("protocol") == "a2a" for entry in service.get("protocols", [])
        )
        for service in agents.values()
    ):
        raise ValueError("Native A2A preparation requires A2A agent services")
    names = {
        key: agent_name if key == selected else f"{agent_name}-{key}" for key in agents
    }
    for key, service in agents.items():
        service["name"] = names[key]
    endpoints = sample.get("endpoints", {})
    for variable, specialist in endpoints.items():
        if specialist not in agents:
            raise ValueError(f"Unknown A2A endpoint service: {specialist}")
        endpoint = (
            "${AZURE_AI_PROJECT_ENDPOINT}/agents/"
            + names[specialist]
            + "/endpoint/protocols/a2a?api-version=v1"
        )
        consumers = [
            service
            for service in agents.values()
            if service.get("env", {}).get(variable) == "${" + variable + "}"
        ]
        if not consumers:
            raise ValueError(f"No agent consumes endpoint variable {variable}")
        for consumer in consumers:
            if consumer is agents[specialist]:
                raise ValueError("An A2A service cannot depend on its own endpoint")
            consumer["env"][variable] = endpoint
            consumer.setdefault("uses", []).append(specialist)
    if "toolbox" in sample:
        toolbox_path = (sample_dir / sample["toolbox"]).resolve()
        if not toolbox_path.is_relative_to(sample_dir.resolve()):
            raise ValueError("Toolbox definition must be inside the sample")
        toolbox = json.loads(toolbox_path.read_text(encoding="utf-8"))
        if not isinstance(toolbox.get("tools"), list) or not toolbox["tools"]:
            raise ValueError("Toolbox definition must contain tools")
        key = "ci-a2a-toolbox"
        if key in services:
            raise ValueError(f"Reserved CI service already exists: {key}")
        services[key] = {
            "host": "azure.ai.toolbox",
            "uses": [
                name
                for name, service in services.items()
                if service.get("host") == "azure.ai.project"
            ],
            "tools": toolbox["tools"],
        }
        consumers = [
            service
            for service in agents.values()
            if service.get("env", {}).get("TOOLBOX_ENDPOINT") == "${TOOLBOX_ENDPOINT}"
        ]
        if not consumers:
            raise ValueError("No agent consumes TOOLBOX_ENDPOINT")
        for consumer in consumers:
            consumer["env"][
                "TOOLBOX_ENDPOINT"
            ] = "${TOOLBOX_CI_A2A_TOOLBOX_MCP_ENDPOINT}"
            consumer.setdefault("uses", []).append(key)
    for service in services.values():
        if "uses" in service:
            service["uses"] = list(
                dict.fromkeys(names.get(key, key) for key in service["uses"])
            )
    renamed = {names.get(key, key): value for key, value in services.items()}
    if len(renamed) != len(services):
        raise ValueError("CI agent name collides with another service")
    manifest["services"] = renamed
    manifest["name"] = agent_name
    return manifest


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        raise ValueError(
            "Expected manifest, fixture spec, sample directory and CI agent name"
        )
    path, spec, sample_dir = map(Path, argv[:3])
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    prepared = prepare(document, load_spec(spec)["sample"], sample_dir, argv[3])
    path.write_text(yaml.safe_dump(prepared, sort_keys=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
