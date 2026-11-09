#!/usr/bin/env python3
"""Local validation and evidence helpers for the prompt-agent CI shell runner."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
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


def owned_skill_name(context: dict) -> str:
    name = context.get("skill_name")
    agent_name = context.get("agent_name")
    if (context.get("execution_profile") != "managed"
            or not isinstance(agent_name, str) or not re.fullmatch(r"ci-prompt-[A-Za-z0-9-]+", agent_name)
            or name != "ci-e2e-sk-" + agent_name.removeprefix("ci-prompt-")):
        raise LifecycleError("context must identify the managed agent's owned skill")
    return name


def toolbox_connection_name(toolbox_name: str, version: str, endpoint: str) -> str:
    digest = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:8]
    prefix = re.sub(r"[^A-Za-z0-9_-]", "-", f"{toolbox_name}-v{version}").lstrip("-_")[:20]
    return f"{prefix}-{digest}-mcp"


def _validate_project_endpoint(context: dict) -> str:
    project_endpoint = context.get("project_endpoint")
    if not isinstance(project_endpoint, str):
        raise LifecycleError("context must contain the project endpoint")
    project = urlsplit(project_endpoint)
    if (project.scheme != "https" or not project.hostname or project.query or project.fragment
            or project.username is not None or any(c.isspace() for c in project_endpoint)):
        raise LifecycleError("context project endpoint must be an HTTPS URL without credentials/query/fragment")
    return project_endpoint.rstrip("/")


def _expected_connection_name(context: dict) -> tuple[str, str]:
    name = owned_toolbox_name(context)
    project_endpoint = _validate_project_endpoint(context)
    toolbox_endpoint = context.get("toolbox_endpoint")
    connection_name = context.get("connection_name")
    prefix = project_endpoint + "/toolboxes/" + quote(name, safe="") + "/versions/"
    suffix = "/mcp?api-version=v1"
    if (not isinstance(toolbox_endpoint, str) or not toolbox_endpoint.startswith(prefix)
            or not toolbox_endpoint.endswith(suffix)):
        raise LifecycleError("context must contain the owned toolbox MCP endpoint")
    version = toolbox_endpoint[len(prefix):-len(suffix)]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", version):
        raise LifecycleError("context toolbox endpoint must contain a valid toolbox version")
    expected = toolbox_connection_name(name, version, toolbox_endpoint)
    if not isinstance(connection_name, str) or connection_name != expected:
        raise LifecycleError("context must identify the owned toolbox connection")
    return expected, toolbox_endpoint


def _extract_skill_frontmatter(content: str) -> tuple[str, str]:
    trimmed = content.lstrip("\ufeff \t\r\n")
    if not trimmed.startswith("---"):
        raise LifecycleError("SKILL.md must begin with a YAML front matter block")
    rest = trimmed[3:].lstrip("\r\n")
    before, sep, after = rest.partition("\n---")
    if not sep:
        raise LifecycleError("SKILL.md front matter is missing its closing delimiter")
    nl = after.find("\n")
    body = after[nl + 1:] if nl >= 0 else ""
    return before, body


def _validate_skill_archive(archive: str) -> str:
    if not isinstance(archive, str) or not archive.strip():
        raise LifecycleError("skill service must declare a nonempty archive path")
    normalized = archive.strip().replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if len(parts) != 2 or parts[0] != "skills" or ".." in parts or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", parts[1]):
        raise LifecycleError("skill archive must be ./skills/<skill-name>")
    return parts[1]


def _validate_managed_tools(tools: object, toolbox_key: str) -> None:
    if not isinstance(tools, list) or any(not isinstance(tool, dict) for tool in tools):
        raise LifecycleError("managed agent tools must be an array of mappings")
    mcp_count = 0
    for tool in tools:
        tool_type = tool.get("type")
        if tool_type == "web_search":
            if set(tool) != {"type"}:
                raise LifecycleError("managed web_search tool cannot have extra properties")
        elif tool_type in ("microsoft_copilot_toolset_preview", "github_copilot_toolset_preview"):
            if set(tool) - {"type", "defaultConfig"}:
                raise LifecycleError("managed copilot toolset supports only defaultConfig")
            default_config = tool.get("defaultConfig", {})
            if (not isinstance(default_config, dict) or set(default_config) - {"enabled"}
                    or not isinstance(default_config.get("enabled", False), bool)):
                raise LifecycleError("managed copilot toolset defaultConfig.enabled must be a boolean")
        elif tool_type == "mcp" and toolbox_key:
            mcp_count += 1
            if mcp_count > 1 or tool != {
                "type": "mcp", "server_label": toolbox_key, "require_approval": "never",
            }:
                raise LifecycleError("managed toolbox MCP tool must target only the owned toolbox with require_approval: never")
        else:
            raise LifecycleError("managed agents support only web_search, copilot toolset, and owned toolbox MCP tools")


def _validate_agent_toolboxes(agent: dict, toolbox_key: str) -> None:
    has_legacy = "toolbox" in agent
    has_plural = "toolboxes" in agent
    if has_legacy == has_plural:
        raise LifecycleError("managed toolbox agent must declare either toolboxes or legacy toolbox")
    if has_legacy and agent.get("toolbox") != {"name": toolbox_key}:
        raise LifecycleError("managed agent legacy toolbox must match the owned toolbox")
    if has_plural and agent.get("toolboxes") not in ([toolbox_key], [{"name": toolbox_key}]):
        raise LifecycleError("managed agent toolboxes must reference only the owned toolbox")


def validate_manifest(document: dict, service_key: str) -> str:
    if not isinstance(document, dict):
        raise LifecycleError("manifest must be a mapping")
    services = document.get("services")
    if not isinstance(services, dict) or any(not isinstance(service, dict) for service in services.values()):
        raise LifecycleError("services must be a mapping of service mappings")
    if "hooks" in document or any("hooks" in service for service in services.values()):
        raise LifecycleError("lifecycle hooks are not supported by the prompt CI adapter")
    if any(service.get("host") == "azure.ai.connection" for service in services.values()) or any(
        "connections" in item for item in [document, *services.values()]
    ):
        raise LifecycleError("connections are not supported by the prompt CI adapter")
    projects = [key for key, service in services.items() if service.get("host") == "azure.ai.project"]
    agent = services.get(service_key, {})
    if agent.get("host") != "azure.ai.agent" or agent.get("kind") != "prompt":
        raise LifecycleError("expected the original prompt agent service")
    profile = execution_profile(agent)
    if profile == "managed":
        toolboxes = [key for key, service in services.items() if service.get("host") == "azure.ai.toolbox"]
        skills = [key for key, service in services.items() if service.get("host") == "azure.ai.skill"]
        if len(projects) != 1 or len(toolboxes) + len(skills) != 1 or len(services) != 3:
            raise LifecycleError("managed agents require exactly one borrowed project and either one toolbox or one skill")
        if any(key in agent for key in ("codeConfiguration", "image", "memory", "policies")):
            raise LifecycleError("managed agents cannot have code, image, memory, or policy dependencies")
        if agent.get("project", ".") != ".":
            raise LifecycleError("managed agent must use project: .")
        if toolboxes:
            if "skills" in document or any("skills" in service for service in services.values()):
                raise LifecycleError("managed toolbox agents cannot also declare skills")
            toolbox_key = toolboxes[0]
            toolbox = services[toolbox_key]
            if (set(toolbox) - {"host", "uses", "description", "tools"}
                    or toolbox.get("uses") != projects or toolbox.get("tools") != [{"type": "web_search"}]):
                raise LifecycleError("managed toolbox must use only the borrowed project and contain only web_search")
            if agent.get("uses") not in (projects + toolboxes, toolboxes + projects):
                raise LifecycleError("managed agent must reference the project and toolbox once")
            _validate_agent_toolboxes(agent, toolbox_key)
            _validate_managed_tools(agent.get("tools", []), toolbox_key)
            return projects[0]
        if any(key in agent for key in ("toolbox", "toolboxes")):
            raise LifecycleError("managed skill agents cannot declare toolboxes")
        skill_key = skills[0]
        skill = services[skill_key]
        if set(skill) != {"host", "uses", "archive"} or skill.get("uses") != projects:
            raise LifecycleError("managed skill must use only the borrowed project and declare archive")
        if _validate_skill_archive(skill["archive"]) != skill_key:
            raise LifecycleError("managed skill archive directory must match the skill service key")
        if agent.get("uses") not in (projects + skills, skills + projects):
            raise LifecycleError("managed agent must reference the project and skill once")
        if "skills" in agent and agent["skills"] not in ([skill_key], [{"name": skill_key}]):
            raise LifecycleError("managed agent skills must reference only the owned skill")
        _validate_managed_tools(agent.get("tools", []), "")
        return projects[0]
    if len(projects) != 1 or len(services) != 2:
        raise LifecycleError("only an agent and one borrowed project are supported; skills, toolboxes and connections are not supported by this adapter")
    if agent.get("uses") != projects or agent.get("project", ".") != ".":
        raise LifecycleError("agent must consume only the borrowed project and use project: .")
    if any(key in agent for key in ("skills", "toolbox", "toolboxes", "codeConfiguration", "image")):
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


def _validate_source_skill_bundle(sample_dir: Path, original_skill: str) -> tuple[dict, str]:
    if sample_dir.is_symlink() or not sample_dir.is_dir():
        raise LifecycleError("sample directory must be a real directory")
    skills_dir = sample_dir / "skills"
    if skills_dir.is_symlink() or not skills_dir.is_dir():
        raise LifecycleError("skill archive directory is missing or is a symlink")
    skills_root = skills_dir.resolve()
    for root, dirs, files in os.walk(skills_dir, followlinks=False):
        root_path = Path(root)
        for item in (*dirs, *files):
            entry = root_path / item
            if entry.is_symlink() or not (entry.is_file() or entry.is_dir()):
                raise LifecycleError("skill bundle cannot contain symlinks or special files")
            if not entry.resolve().is_relative_to(skills_root):
                raise LifecycleError("skill bundle entry resolves outside skills directory")
    original_dir = skills_dir / original_skill
    entries = [entry for entry in skills_dir.iterdir() if not entry.name.startswith(".")]
    if entries != [original_dir] or not original_dir.is_dir() or original_dir.is_symlink():
        raise LifecycleError("skills directory must contain only the declared skill bundle")
    skill_md = original_dir / "SKILL.md"
    if skill_md.is_symlink() or not skill_md.is_file():
        raise LifecycleError("skill archive directory must contain a regular SKILL.md file")
    front, body = _extract_skill_frontmatter(skill_md.read_text(encoding="utf-8"))
    if not body.strip():
        raise LifecycleError("SKILL.md must contain nonempty instructions")
    metadata = yaml.load(front, Loader=ManifestLoader)
    if not isinstance(metadata, dict) or not str(metadata.get("description", "")).strip():
        raise LifecycleError("SKILL.md front matter must declare a nonempty description")
    if metadata.get("name", original_skill) != original_skill:
        raise LifecycleError("SKILL.md front matter name must match the skill service key")
    return metadata, body


def _rewrite_skill_bundle(source_dir: Path, original_skill: str, owned_skill: str) -> None:
    metadata, body = _validate_source_skill_bundle(source_dir, original_skill)
    skills_dir = source_dir / "skills"
    original_dir = skills_dir / original_skill
    owned_dir = skills_dir / owned_skill
    if owned_dir.exists() or owned_dir.is_symlink():
        raise LifecycleError("skill archive directory is missing or conflicts with owned skill directory")
    skill_md = original_dir / "SKILL.md"
    metadata["name"] = owned_skill
    skill_md.write_text(
        "---\n" + yaml.safe_dump(metadata, sort_keys=False).strip() + "\n---\n" + body,
        encoding="utf-8", newline="\n",
    )
    original_dir.rename(owned_dir)


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
        toolboxes = [key for key, service in document["services"].items() if service.get("host") == "azure.ai.toolbox"]
        skills = [key for key, service in document["services"].items() if service.get("host") == "azure.ai.skill"]
        if toolboxes:
            original_toolbox = toolboxes[0]
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
            if "toolbox" in agent:
                agent["toolbox"] = {"name": toolbox_name}
            else:
                agent["toolboxes"] = [
                    {"name": toolbox_name} if isinstance(item, dict) else toolbox_name
                    for item in agent["toolboxes"]
                ]
            for tool in agent.get("tools", []):
                if tool.get("type") == "mcp" and tool.get("server_label") == original_toolbox:
                    tool["server_label"] = toolbox_name
        else:
            original_skill = skills[0]
            _validate_source_skill_bundle(sample, original_skill)
            skill_name = owned_skill_name({
                "execution_profile": "managed", "agent_name": name,
                "skill_name": "ci-e2e-sk-" + name.removeprefix("ci-prompt-"),
            })
            if any(key.casefold() == skill_name.casefold() for key in document["services"] if key != original_skill):
                raise LifecycleError("owned skill name conflicts with an existing service")
            document["services"] = {
                skill_name if key == original_skill else key: service
                for key, service in document["services"].items()
            }
            document["services"][skill_name]["archive"] = f"./skills/{skill_name}"
            agent["uses"] = [skill_name if key == original_skill else key for key in agent["uses"]]
            if "skills" in agent:
                agent["skills"] = [
                    {"name": skill_name} if isinstance(item, dict) else skill_name
                    for item in agent["skills"]
                ]
    document["services"][project_key].pop("deployments", None)
    if isinstance(document.get("infra"), dict) and set(document["infra"]) == {"provider", "path"} and document["infra"].get("provider") == "microsoft.foundry":
        document["infra"] = {"provider": "microsoft.foundry"}
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
    original_doc = yaml.load((sample / "azure.yaml").read_text(encoding="utf-8"), Loader=ManifestLoader)
    original_skills = [
        key for key, svc in (original_doc.get("services") or {}).items()
        if isinstance(svc, dict) and svc.get("host") == "azure.ai.skill"
    ] if isinstance(original_doc, dict) else []
    name = "ci-prompt-" + uuid.uuid4().hex
    document, service_key = prepare_manifest(repo, sample, args.model_deployment, name)
    agent = document["services"][service_key]
    profile = execution_profile(agent)
    toolboxes = [key for key, svc in document["services"].items() if svc.get("host") == "azure.ai.toolbox"]
    skills = [key for key, svc in document["services"].items() if svc.get("host") == "azure.ai.skill"]
    toolbox_name = toolboxes[0] if profile == "managed" and toolboxes else ""
    skill_name = skills[0] if profile == "managed" and skills else ""
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
    shutil.copytree(sample, source, symlinks=True, ignore=shutil.ignore_patterns(
        ".azure", ".env", ".env.*", ".git", ".venv", "__pycache__",
    ))
    if skill_name:
        _rewrite_skill_bundle(source, original_skills[0], skill_name)
    (source / "azure.yaml").write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8", newline="\n")
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
        "toolbox_endpoint": "",
        "skill_name": skill_name,
        "connection_name": "",
        "project_endpoint": args.project_endpoint,
    })
    write_json(artifacts / "ownership.json", {
        "agent_name": name, "agent_service": service_key,
        "toolbox_name": toolbox_name, "toolbox_endpoint": "", "toolbox_deployment_attempted": False,
        "skill_name": skill_name, "skill_deployment_attempted": False,
        "connection_name": "", "connection_deployment_attempted": False,
        "project_id": args.project_id, "project_endpoint": args.project_endpoint,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "working_directory": str(work),
        "deployment_attempted": False, "cleanup": {},
        "response_retention": "not verified: azd does not expose prompt response deletion",
    })
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
    services = document["services"]
    agent = services[context["agent_service"]]
    profile = execution_profile(agent)
    if profile != context.get("execution_profile", "prompt"):
        raise LifecycleError("init changed the requested execution profile")
    has_toolbox = bool(context.get("toolbox_name"))
    has_skill = bool(context.get("skill_name"))
    if profile == "managed":
        if has_toolbox == has_skill:
            raise LifecycleError("managed context must identify an owned toolbox or skill")
        if has_toolbox:
            if context.get("skill_name", "") != "":
                raise LifecycleError("managed toolbox context cannot declare a skill")
            expected_tb = owned_toolbox_name(context)
            if (expected_tb not in services
                    or services[expected_tb].get("host") != "azure.ai.toolbox"
                    or "skills" in agent
                    or any(svc.get("host") == "azure.ai.skill" for svc in services.values())):
                raise LifecycleError("init changed the owned toolbox service")
            try:
                _validate_agent_toolboxes(agent, expected_tb)
            except LifecycleError as exc:
                raise LifecycleError("init changed the owned toolbox reference") from exc
            if context.get("connection_name") or context.get("toolbox_endpoint"):
                _expected_connection_name(context)
        else:
            if (context.get("toolbox_name", "") != ""
                    or context.get("connection_name", "") != ""
                    or context.get("toolbox_endpoint", "") != ""):
                raise LifecycleError("managed skill context cannot declare a toolbox or connection")
            expected_sk = owned_skill_name(context)
            if (expected_sk not in services
                    or services[expected_sk].get("host") != "azure.ai.skill"
                    or services[expected_sk].get("archive") != f"./skills/{expected_sk}"
                    or "toolbox" in agent or "toolboxes" in agent
                    or any(svc.get("host") == "azure.ai.toolbox" for svc in services.values())):
                raise LifecycleError("init changed the owned skill service")
            if "skills" in agent and agent["skills"] not in ([expected_sk], [{"name": expected_sk}]):
                raise LifecycleError("init changed the owned skills reference")
    elif (context.get("toolbox_name", "") != ""
          or context.get("skill_name", "") != ""
          or context.get("connection_name", "") != ""
          or context.get("toolbox_endpoint", "") != ""):
        raise LifecycleError("prompt context cannot declare managed resources")
    if agent.get("name") != context["agent_name"] or agent.get("model") != model_deployment:
        raise LifecycleError("init changed the requested agent identity, model, or kind")


def verify_connection(metadata: Path | None, context: dict) -> None:
    expected_name, expected_target = _expected_connection_name(context)
    if metadata is None:
        return
    document = json.loads(metadata.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise LifecycleError("connection show metadata must be an object")
    kind = document.get("kind")
    auth_type = document.get("authType")
    if (document.get("name") != expected_name
            or document.get("target") != expected_target
            or not isinstance(kind, str) or kind.casefold() != "remotetool"
            or not isinstance(auth_type, str)
            or auth_type.replace("-", "").replace("_", "").casefold() != "userentratoken"):
        raise LifecycleError("connection show returned unexpected owned name, target, kind, or authType")


def verify_deployed(
    metadata: Path,
    context: dict,
    model_deployment: str,
    toolbox_metadata: Path | None = None,
    skill_metadata: Path | None = None,
    connection_metadata: Path | None = None,
) -> None:
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
        if bool(context.get("toolbox_name")) == bool(context.get("skill_name")):
            raise LifecycleError("managed context must identify an owned toolbox or skill")
        if context.get("toolbox_name"):
            name = owned_toolbox_name(context)
            tools = definition.get("tools")
            mcp_tools = [tool for tool in (tools or []) if isinstance(tool, dict) and tool.get("type") == "mcp"]
            if (not isinstance(tools, list) or len(mcp_tools) != 1
                    or mcp_tools[0].get("server_label") != name
                    or not isinstance(mcp_tools[0].get("server_url"), str)):
                raise LifecycleError("managed agent must attach exactly the owned toolbox MCP server")
            if toolbox_metadata is None or connection_metadata is None:
                raise LifecycleError("managed agent verification requires toolbox and connection metadata")
            version = verify_toolbox(toolbox_metadata, context, mcp_tools[0]["server_url"])
            expected_conn = toolbox_connection_name(name, version, mcp_tools[0]["server_url"])
            connection_id = mcp_tools[0].get("project_connection_id")
            if (not isinstance(connection_id, str)
                    or connection_id != context.get("connection_name")
                    or connection_id != expected_conn
                    or mcp_tools[0]["server_url"] != context.get("toolbox_endpoint")):
                raise LifecycleError("managed agent toolbox connection ID does not match the owned toolbox endpoint")
            verify_connection(connection_metadata, context)
        else:
            name = owned_skill_name(context)
            skills = definition.get("skills")
            if skill_metadata is None:
                raise LifecycleError("managed skill agent verification requires skill metadata")
            version = verify_skill(skill_metadata, context)
            if (not isinstance(skills, list) or len(skills) != 1 or not isinstance(skills[0], dict)
                    or skills[0].get("name") != name or skills[0].get("version") != version
                    or skills[0].get("type", "skill_reference") != "skill_reference"):
                raise LifecycleError("managed agent must attach the owned skill and version")


def verify_toolbox(metadata: Path, context: dict, endpoint: str) -> str:
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
    project_endpoint = _validate_project_endpoint(context)
    expected = (project_endpoint + "/toolboxes/" + quote(name, safe="")
                + "/versions/" + quote(version["version"], safe="") + "/mcp?api-version=v1")
    if not isinstance(endpoint, str) or endpoint != expected or document.get("endpoint") != expected:
        raise LifecycleError("toolbox MCP endpoint must exactly match the owned project, toolbox, and version")
    return version["version"]


def verify_skill(metadata: Path, context: dict, version: str | None = None) -> str:
    name = owned_skill_name(context)
    document = json.loads(metadata.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise LifecycleError("skill show metadata must be an object")
    default_version = document.get("default_version")
    latest_version = document.get("latest_version")
    if (document.get("name") != name or not isinstance(default_version, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", default_version)
            or (latest_version is not None and latest_version != default_version)
            or (version is not None and default_version != version)):
        raise LifecycleError("skill show returned unexpected owned name or version")
    return default_version


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


def skill_absent(metadata: Path, context: dict) -> bool:
    name = owned_skill_name(context)
    skills = json.loads(metadata.read_text(encoding="utf-8"))
    if not isinstance(skills, list) or any(
        not isinstance(skill, dict) or not isinstance(skill.get("name"), str) or not skill["name"].strip()
        for skill in skills
    ):
        raise LifecycleError("skill list metadata must contain an array of nonempty skill names")
    return all(skill["name"].casefold() != name.casefold() for skill in skills)


def connection_absent(metadata: Path, context: dict) -> bool:
    name, _ = _expected_connection_name(context)
    connections = json.loads(metadata.read_text(encoding="utf-8"))
    if connections is None:
        return True
    if not isinstance(connections, list) or any(
        not isinstance(conn, dict) or not isinstance(conn.get("name"), str) or not conn["name"].strip()
        for conn in connections
    ):
        raise LifecycleError("connection list metadata must contain an array of nonempty connection names")
    return all(conn["name"].casefold() != name.casefold() for conn in connections)


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
    deployed.add_argument("--skill-metadata", type=Path)
    deployed.add_argument("--connection-metadata", type=Path)
    for verification in (adopted, deployed):
        verification.add_argument("--context", type=Path, required=True)
        verification.add_argument("--model-deployment", required=True)
    toolbox = commands.add_parser("verify-toolbox")
    toolbox.add_argument("--endpoint", required=True)
    toolbox_absence = commands.add_parser("toolbox-absent")
    skill = commands.add_parser("verify-skill")
    skill.add_argument("--version", required=True)
    skill_absence = commands.add_parser("skill-absent")
    connection = commands.add_parser("verify-connection")
    connection.add_argument("--metadata", type=Path)
    connection.add_argument("--context", type=Path, required=True)
    connection_absence = commands.add_parser("connection-absent")
    for verification in (toolbox, toolbox_absence, skill, skill_absence, connection_absence):
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
                verify_deployed(
                    args.metadata, context, args.model_deployment,
                    args.toolbox_metadata, args.skill_metadata, args.connection_metadata,
                )
            elif args.command == "verify-toolbox":
                version = verify_toolbox(args.metadata, context, args.endpoint)
                print(toolbox_connection_name(owned_toolbox_name(context), version, args.endpoint))
            elif args.command == "toolbox-absent":
                return 0 if toolbox_absent(args.metadata, context) else 1
            elif args.command == "verify-skill":
                verify_skill(args.metadata, context, args.version)
            elif args.command == "skill-absent":
                return 0 if skill_absent(args.metadata, context) else 1
            elif args.command == "verify-connection":
                verify_connection(args.metadata, context)
            elif args.command == "connection-absent":
                return 0 if connection_absent(args.metadata, context) else 1
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
