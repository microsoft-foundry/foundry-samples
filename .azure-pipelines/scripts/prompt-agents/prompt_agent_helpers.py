#!/usr/bin/env python3
"""Local validation and evidence helpers for the prompt-agent CI shell runner."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import quote, urlsplit
import uuid

import yaml

from discover_samples import ManifestLoader, SAMPLE_ROOTS, sample_record
from hosted_agent_fixture import fixture_dir_for_sample
from hosted_agent_test_spec import build_plan, load_spec


class LifecycleError(RuntimeError):
    pass


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def execution_profile(agent: dict) -> str:
    if "harness" not in agent:
        return "prompt"
    harness = agent["harness"]
    if (
        not isinstance(harness, dict)
        or set(harness) != {"type"}
        or not isinstance(harness.get("type"), str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", harness["type"])
    ):
        raise LifecycleError("managed harness.type must be a nonempty identifier")
    return "managed"


def owned_toolbox_name(context: dict) -> str:
    name = context.get("toolbox_name")
    agent_name = context.get("agent_name")
    if (context.get("execution_profile") != "managed"
            or not isinstance(agent_name, str) or not re.fullmatch(r"ci-prompt-[A-Za-z0-9-]+", agent_name)
            or name != "ci-e2e-tb-" + agent_name.removeprefix("ci-prompt-")):
        raise LifecycleError("context must identify the managed agent's owned toolbox")
    return name


def validate_manifest(document: dict, service_key: str) -> str:
    if not isinstance(document, dict):
        raise LifecycleError("manifest must be a mapping")
    services = document.get("services")
    if not isinstance(services, dict) or any(not isinstance(service, dict) for service in services.values()):
        raise LifecycleError("services must be a mapping of service mappings")
    if "hooks" in document or any("hooks" in service for service in services.values()):
        raise LifecycleError("lifecycle hooks are not supported by the prompt CI adapter")
    projects = [key for key, service in services.items() if service.get("host") == "azure.ai.project"]
    agent = services.get(service_key, {})
    if agent.get("host") != "azure.ai.agent" or agent.get("kind") != "prompt":
        raise LifecycleError("expected the original prompt agent service")
    profile = execution_profile(agent)
    if profile == "managed":
        toolboxes = [key for key, service in services.items() if service.get("host") == "azure.ai.toolbox"]
        if len(projects) != 1 or len(toolboxes) != 1 or len(services) != 3:
            raise LifecycleError("managed agents require exactly one borrowed project, one toolbox, and one agent")
        if any(key in item for item in [document, *services.values()] for key in ("skills", "connections")):
            raise LifecycleError("managed skills and connections are not supported")
        toolbox_key = toolboxes[0]
        toolbox = services[toolbox_key]
        if (set(toolbox) - {"host", "uses", "description", "tools"}
                or toolbox.get("uses") != projects or toolbox.get("tools") != [{"type": "web_search"}]):
            raise LifecycleError("managed toolbox must use only the borrowed project and contain only web_search")
        if (agent.get("uses") not in (projects + toolboxes, toolboxes + projects)
                or agent.get("project", ".") != "."
                or agent.get("toolbox") != {"name": toolbox_key}):
            raise LifecycleError("managed agent must reference the project and toolbox once, with only toolbox.name")
        if agent.get("tools", []) != [] or any(key in agent for key in ("codeConfiguration", "image")):
            raise LifecycleError("managed agents cannot have direct tools or other dependencies")
        return projects[0]
    if len(projects) != 1 or len(services) != 2:
        raise LifecycleError("only an agent and one borrowed project are supported; skills, toolboxes and connections are not supported by this adapter")
    if agent.get("uses") != projects or agent.get("project", ".") != ".":
        raise LifecycleError("agent must consume only the borrowed project and use project: .")
    if any(key in agent for key in ("skills", "toolbox", "codeConfiguration", "image")):
        raise LifecycleError("agent has dependencies outside the prompt CLI adapter")
    tools = agent.get("tools", [])
    if not isinstance(tools, list):
        raise LifecycleError("tools must be an array")
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") not in ("function", "mcp"):
            raise LifecycleError("only client function schemas and public MCP tools are supported")
        if tool["type"] == "mcp" and (
            tool.get("require_approval") != "never"
            or any(key in tool for key in ("project_connection_id", "headers", "authorization"))
        ):
            raise LifecycleError("MCP tools must be public and require_approval: never")
    return projects[0]


def prepare_manifest(repo: Path, sample: Path, model: str, name: str) -> tuple[dict, str]:
    record = sample_record(repo, sample / "azure.yaml")
    document = yaml.load((sample / "azure.yaml").read_text(encoding="utf-8"), Loader=ManifestLoader)
    service_key = record["agentService"]
    project_key = validate_manifest(document, service_key)
    agent = document["services"][service_key]
    agent["name"] = name
    agent["description"] = f"Temporary prompt-agent CI resource: {name}"
    agent["model"] = model
    if execution_profile(agent) == "managed":
        original_toolbox = agent["toolbox"]["name"]
        toolbox_name = owned_toolbox_name({
            "execution_profile": "managed", "agent_name": name,
            "toolbox_name": "ci-e2e-tb-" + name.removeprefix("ci-prompt-"),
        })
        if any(key.casefold() == toolbox_name.casefold() for key in document["services"] if key != original_toolbox):
            raise LifecycleError("owned toolbox name conflicts with an existing service")
        document["services"] = {
            toolbox_name if key == original_toolbox else key: service
            for key, service in document["services"].items()
        }
        agent["uses"] = [toolbox_name if key == original_toolbox else key for key in agent["uses"]]
        agent["toolbox"]["name"] = toolbox_name
    document["services"][project_key].pop("deployments", None)
    validate_manifest(document, service_key)
    return document, service_key


def plan_contract(spec: Path, profile: str) -> dict:
    contract = load_spec(spec)
    # Check filtered-out tests too, before creating artifacts or allowing cloud work.
    for test in contract["tests"]:
        for turn in test["turns"]:
            if not isinstance(turn["input"], str):
                raise LifecycleError("azd prompt invoke supports only string input, not structured message arrays")
            if any(assertion["source"] == "raw" for assertion in turn.get("assertions", [])):
                raise LifecycleError("azd prompt invoke does not expose raw response evidence; use assistant_text")
    plan = build_plan(contract, profile=profile)
    if not plan["turn_count"]:
        raise LifecycleError("contract must contain at least one applicable turn")
    if not any(turn["assertions"] for test in plan["tests"] for turn in test["turns"]):
        raise LifecycleError("contract must assert observable output in an applicable turn")
    return plan


def prepare(args) -> None:
    if not re.fullmatch(r"/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.CognitiveServices/accounts/[^/]+/projects/[^/]+", args.project_id, re.I):
        raise LifecycleError("project-id must be a Foundry project ARM ID")
    endpoint = urlsplit(args.project_endpoint)
    if endpoint.scheme != "https" or not endpoint.hostname or endpoint.query or endpoint.fragment or endpoint.username is not None:
        raise LifecycleError("project-endpoint must be an HTTPS project URL without credentials/query/fragment")
    if not args.model_deployment.strip():
        raise LifecycleError("model-deployment must be nonempty")
    repo = args.repo.resolve()
    sample = (repo / args.sample).resolve()
    if Path(args.sample).is_absolute() or not any(
        sample != repo / root and sample.is_relative_to(repo / root) for root in SAMPLE_ROOTS
    ):
        raise LifecycleError("sample must be a repository-relative directory below a configured prompt sample root")
    name = "ci-prompt-" + uuid.uuid4().hex
    document, service_key = prepare_manifest(repo, sample, args.model_deployment, name)
    agent = document["services"][service_key]
    profile = execution_profile(agent)
    toolbox_name = agent["toolbox"]["name"] if profile == "managed" else ""
    spec = args.spec or repo / fixture_dir_for_sample(sample.relative_to(repo).as_posix()) / "test-spec.yml"
    plan = plan_contract(spec, profile)
    artifacts = args.artifacts.resolve()
    work = args.work.resolve()
    if artifacts.is_relative_to(sample):
        raise LifecycleError("artifacts directory must be outside the sample tree")
    if artifacts.exists():
        raise FileExistsError(f"artifacts directory already exists: {artifacts}")
    if not work.is_dir() or work.is_relative_to(sample):
        raise LifecycleError("work must be an existing temporary directory outside the sample tree")
    source = work / "input"
    if source.exists() or artifacts.is_relative_to(source):
        raise LifecycleError("work/input must be new and separate from artifacts")
    artifacts.mkdir(parents=True, exist_ok=False)
    evidence = artifacts / "evidence"
    evidence.mkdir()
    write_json(artifacts / "plan.json", plan)
    write_json(artifacts / "context.json", {
        "agent_name": name,
        "agent_service": service_key,
        "service_env_key": service_key.replace("-", "_").replace(" ", "_").upper(),
        "account_name": args.project_id.split("/")[-3],
        "execution_profile": profile,
        "toolbox_name": toolbox_name,
        "project_endpoint": args.project_endpoint,
    })
    write_json(artifacts / "ownership.json", {
        "agent_name": name, "agent_service": service_key,
        "toolbox_name": toolbox_name, "toolbox_deployment_attempted": False,
        "project_id": args.project_id, "project_endpoint": args.project_endpoint,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "working_directory": str(work),
        "deployment_attempted": False, "cleanup": {},
        "response_retention": "not verified: azd does not expose prompt response deletion",
    })
    shutil.copytree(sample, source, ignore=shutil.ignore_patterns(
        ".azure", ".env", ".env.*", ".git", ".venv", "__pycache__",
    ))
    (source / "azure.yaml").write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8", newline="\n")
    turns = []
    for test in plan["tests"]:
        for index, turn in enumerate(test["turns"]):
            (evidence / f"turn-{turn['global_turn']}-input.txt").write_text(
                turn["input"], encoding="utf-8", newline="\n",
            )
            turns.append({"global_turn": turn["global_turn"], "new_conversation": index == 0})
    write_json(artifacts / "turns.json", turns)


def verify_adopted(manifest: Path, context: dict, model_deployment: str) -> None:
    document = yaml.load(manifest.read_text(encoding="utf-8"), Loader=ManifestLoader)
    if not isinstance(document, dict):
        raise LifecycleError("adopted manifest must be a mapping")
    validate_manifest(document, context["agent_service"])
    agent = document["services"][context["agent_service"]]
    profile = execution_profile(agent)
    if profile != context.get("execution_profile", "prompt"):
        raise LifecycleError("init changed the requested execution profile")
    if profile == "managed" and agent["toolbox"] != {"name": owned_toolbox_name(context)}:
        raise LifecycleError("init changed the owned toolbox reference")
    if agent.get("name") != context["agent_name"] or agent.get("model") != model_deployment:
        raise LifecycleError("init changed the requested agent identity, model, or kind")


def verify_deployed(metadata: Path, context: dict, model_deployment: str, toolbox_metadata: Path | None = None) -> None:
    document = json.loads(metadata.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise LifecycleError("azd show metadata must be an object")
    versions = document.get("versions")
    latest = versions.get("latest") if isinstance(versions, dict) else None
    definition = latest.get("definition") if isinstance(latest, dict) else None
    if (document.get("name") != context["agent_name"] or not isinstance(latest, dict)
            or not latest.get("version") or not isinstance(definition, dict)
            or definition.get("kind") != "prompt" or definition.get("model") != model_deployment):
        raise LifecycleError("azd show returned unexpected agent identity, model, kind, or version")
    profile = execution_profile(definition)
    if profile != context.get("execution_profile", "prompt"):
        raise LifecycleError("azd show returned an unexpected execution profile")
    if profile == "managed":
        name = owned_toolbox_name(context)
        tools = definition.get("tools")
        if (not isinstance(tools, list) or len(tools) != 1 or not isinstance(tools[0], dict)
                or tools[0].get("type") != "mcp" or tools[0].get("server_label") != name
                or not isinstance(tools[0].get("server_url"), str)):
            raise LifecycleError("managed agent must attach exactly the owned toolbox MCP server")
        if toolbox_metadata is None:
            raise LifecycleError("managed agent verification requires toolbox metadata")
        verify_toolbox(toolbox_metadata, context, tools[0]["server_url"])


def verify_toolbox(metadata: Path, context: dict, endpoint: str) -> None:
    name = owned_toolbox_name(context)
    document = json.loads(metadata.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise LifecycleError("toolbox show metadata must be an object")
    toolbox = document.get("toolbox")
    version = document.get("version")
    if (not isinstance(toolbox, dict) or toolbox.get("name") != name
            or not isinstance(version, dict) or version.get("name") != name
            or not isinstance(version.get("version"), str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", version["version"])
            or version.get("tools") != [{"type": "web_search"}]):
        raise LifecycleError("toolbox show returned unexpected owned name, version, or tools")
    project_endpoint = context.get("project_endpoint")
    if not isinstance(project_endpoint, str):
        raise LifecycleError("context must contain the project endpoint")
    project = urlsplit(project_endpoint)
    if (project.scheme != "https" or not project.hostname or project.query or project.fragment
            or project.username is not None or any(c.isspace() for c in project_endpoint)):
        raise LifecycleError("context project endpoint must be an HTTPS URL without credentials/query/fragment")
    expected = (project_endpoint.rstrip("/") + "/toolboxes/" + quote(name, safe="")
                + "/versions/" + quote(version["version"], safe="") + "/mcp?api-version=v1")
    if not isinstance(endpoint, str) or endpoint != expected or document.get("endpoint") != expected:
        raise LifecycleError("toolbox MCP endpoint must exactly match the owned project, toolbox, and version")


def toolbox_absent(metadata: Path, context: dict) -> bool:
    name = owned_toolbox_name(context)
    document = json.loads(metadata.read_text(encoding="utf-8"))
    toolboxes = document.get("toolboxes") if isinstance(document, dict) else None
    if not isinstance(toolboxes, list) or any(
        not isinstance(toolbox, dict) or not isinstance(toolbox.get("name"), str) or not toolbox["name"].strip()
        for toolbox in toolboxes
    ):
        raise LifecycleError("toolbox list metadata must contain an array of nonempty toolbox names")
    return all(toolbox["name"].casefold() != name.casefold() for toolbox in toolboxes)


def agent_absent(stderr: str, exit_code: int, name: str, endpoint: str) -> bool:
    """Fail closed unless azd reports an exact-target prompt GET with HTTP 404."""
    if exit_code in (0, 124, 137):
        return False
    messages = [stderr]
    for line in stderr.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "consoleMessage":
            data = event.get("data")
            if isinstance(data, dict) and isinstance(data.get("message"), str):
                messages.append(data["message"])
    target = endpoint.rstrip("/") + "/agents/" + name
    pattern = (
        re.escape(f'failed to get prompt agent "{name}": GET {target}')
        + r"(?:\?api-version=v1)?\r?\n(?:-+\r?\n)?RESPONSE 404: 404 Not Found(?:\r?\n|$)"
    )
    return any(re.search(pattern, message) for message in messages)


def record_turn(prefix: Path, exit_code: int) -> None:
    stdout = Path(f"{prefix}-stdout.txt").read_text(encoding="utf-8")
    Path(f"{prefix}-stderr.txt").read_text(encoding="utf-8")
    # read_text normalizes CRLF; remove only the CLI's one display newline.
    Path(f"{prefix}-assistant-text.txt").write_text(stdout.removesuffix("\n"), encoding="utf-8", newline="\n")
    write_json(Path(f"{prefix}-status.json"), {
        "exit_code": exit_code, "evidence_source": "azd-cli",
        "mcp_approvals": {
            "automatic": False, "pending": 0, "error": None, "steps": [],
            "observed": False,
        },
    })


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preparation = commands.add_parser("prepare")
    preparation.add_argument("--repo", type=Path, required=True)
    preparation.add_argument("--sample", required=True)
    preparation.add_argument("--project-id", required=True)
    preparation.add_argument("--project-endpoint", required=True)
    preparation.add_argument("--model-deployment", required=True)
    preparation.add_argument("--artifacts", type=Path, required=True)
    preparation.add_argument("--work", type=Path, required=True)
    preparation.add_argument("--spec", type=Path)
    adopted = commands.add_parser("verify-adopted")
    adopted.add_argument("--manifest", type=Path, required=True)
    deployed = commands.add_parser("verify-deployed")
    deployed.add_argument("--metadata", type=Path, required=True)
    deployed.add_argument("--toolbox-metadata", type=Path)
    for verification in (adopted, deployed):
        verification.add_argument("--context", type=Path, required=True)
        verification.add_argument("--model-deployment", required=True)
    toolbox = commands.add_parser("verify-toolbox")
    toolbox.add_argument("--endpoint", required=True)
    toolbox_absence = commands.add_parser("toolbox-absent")
    for verification in (toolbox, toolbox_absence):
        verification.add_argument("--metadata", type=Path, required=True)
        verification.add_argument("--context", type=Path, required=True)
    absence = commands.add_parser("absent")
    absence.add_argument("--stderr", type=Path, required=True)
    absence.add_argument("--stdout", type=Path)
    absence.add_argument("--exit-code", type=int, required=True)
    absence.add_argument("--context", type=Path, required=True)
    absence.add_argument("--project-endpoint", required=True)
    recording = commands.add_parser("record-turn")
    recording.add_argument("--prefix", type=Path, required=True)
    recording.add_argument("--exit-code", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            prepare(args)
        elif args.command == "record-turn":
            record_turn(args.prefix, args.exit_code)
        else:
            context = json.loads(args.context.read_text(encoding="utf-8"))
            if not isinstance(context, dict):
                raise LifecycleError("context must be an object")
            if args.command == "verify-adopted":
                verify_adopted(args.manifest, context, args.model_deployment)
            elif args.command == "verify-deployed":
                verify_deployed(args.metadata, context, args.model_deployment, args.toolbox_metadata)
            elif args.command == "verify-toolbox":
                verify_toolbox(args.metadata, context, args.endpoint)
            elif args.command == "toolbox-absent":
                return 0 if toolbox_absent(args.metadata, context) else 1
            else:
                streams = [args.stderr] + ([args.stdout] if args.stdout else [])
                return 0 if any(agent_absent(
                    stream.read_text(encoding="utf-8"), args.exit_code,
                    context["agent_name"], args.project_endpoint,
                ) for stream in streams) else 1
        return 0
    except (LifecycleError, OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
