"""Run declared, credential-free checks for changed Python hosted runtimes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.util
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import tomllib

import yaml


def load_dependency_policy():
    path = Path(__file__).with_name("check-hosted-agent-python-requirements.py")
    spec = importlib.util.spec_from_file_location("hosted_runtime_dependencies", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


policy = load_dependency_policy()
SHARED_INPUTS = {
    ".github/scripts/check_hosted_agent_runtime.py",
    ".github/scripts/check-hosted-agent-python-requirements.py",
    ".github/scripts/test/test_hosted_agent_runtime.py",
    ".github/scripts/requirements.txt",
    ".github/workflows/hosted-agent-policies.yml",
}


@dataclass(frozen=True)
class RuntimeChecks:
    root: PurePosixPath
    commands: tuple[tuple[str, ...], ...]


def parse_checks(content: bytes, root: PurePosixPath) -> RuntimeChecks | None:
    try:
        project = tomllib.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"Invalid {root}/pyproject.toml: {error}") from error
    tools = project.get("tool", {})
    if not isinstance(tools, dict):
        raise ValueError(f"{root}: tool must be a table")
    declaration = tools.get("hosted-agent-validation")
    if declaration is None:
        return None
    if not isinstance(declaration, dict) or set(declaration) != {"commands"}:
        raise ValueError(f"{root}: validation must declare only commands")
    groups = project.get("dependency-groups", {})
    if not isinstance(groups, dict) or not isinstance(groups.get("dev"), list):
        raise ValueError(f"{root}: validation requires a locked dev dependency group")
    commands = declaration["commands"]
    if not isinstance(commands, list) or not commands:
        raise ValueError(
            f"{root}: commands must be a non-empty array of argument arrays"
        )
    for command in commands:
        if (
            not isinstance(command, list)
            or not command
            or not all(
                isinstance(argument, str) and argument.strip() and "\0" not in argument
                for argument in command
            )
        ):
            raise ValueError(
                f"{root}: every command must be a non-empty argument array"
            )
    return RuntimeChecks(root, tuple(tuple(command) for command in commands))


def discover_checks(repo: Path, base: str, head: str) -> list[RuntimeChecks]:
    files = policy.tree_files(repo, head)
    old_files = policy.tree_files(repo, base)
    output = policy.git(
        repo, "diff", "--name-only", "-z", f"{base}..{head}", text=False
    )
    changes = {PurePosixPath(path.decode()) for path in output.split(b"\0") if path}
    shared_changed = bool({str(path) for path in changes} & SHARED_INPUTS)
    selected = []
    for root, service in sorted(policy.discover_services(repo, head, files).items()):
        manifest = yaml.safe_load(policy.read_tree_file(repo, head, service.manifest))
        if manifest["services"][service.service].get("host") != "azure.ai.agent":
            continue
        project_file = root / "pyproject.toml"
        if project_file not in files:
            continue
        checks = parse_checks(policy.read_tree_file(repo, head, project_file), root)
        if checks is None:
            if project_file in changes and project_file in old_files:
                previous = parse_checks(
                    policy.read_tree_file(repo, base, project_file), root
                )
                if previous is not None:
                    raise ValueError(
                        f"{root}: cannot remove validation from an existing runtime"
                    )
            continue
        if root / "uv.lock" not in files:
            raise ValueError(f"{root}: validation requires uv.lock")
        if (
            shared_changed
            or service.manifest in changes
            or any(policy.is_under(path, root) for path in changes)
        ):
            selected.append(checks)
    return selected


def validate_runtime(repo: Path, checks: RuntimeChecks, uv: str = "uv") -> None:
    directory = (repo / str(checks.root)).resolve(strict=True)
    if not directory.is_relative_to((repo / str(policy.SCOPE)).resolve()):
        raise ValueError(f"Runtime escapes the Python hosted-agent tree: {checks.root}")
    if not (directory / "uv.lock").is_file():
        raise ValueError(f"{checks.root}: validation requires uv.lock")
    with tempfile.TemporaryDirectory(prefix="hosted-runtime-state-") as temporary:
        environment = dict(os.environ)
        environment.update(
            {
                "AGENTSERVER_STATE_ROOT": str(Path(temporary) / "agentserver"),
                "OTEL_SDK_DISABLED": "true",
                "AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED": "false",
                "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false",
                "LANGSMITH_TRACING": "false",
                "LANGSMITH_TRACING_V2": "false",
                "LANGCHAIN_TRACING": "false",
                "LANGCHAIN_TRACING_V2": "false",
            }
        )
        commands = [
            [uv, "sync", "--frozen", "--group", "dev"],
            *[
                [uv, "run", "--frozen", "--group", "dev", "--", *command]
                for command in checks.commands
            ],
        ]
        for command in commands:
            print(f"{checks.root}: {command!r}", flush=True)
            subprocess.run(
                command,
                cwd=directory,
                env=environment,
                check=True,
                timeout=600,
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--runtime", type=PurePosixPath)
    parser.add_argument("--uv", default="uv")
    arguments = parser.parse_args(argv)
    if bool(arguments.base) == bool(arguments.runtime):
        parser.error("choose either --base/--head or --runtime")
    try:
        if arguments.runtime:
            path = arguments.repo / str(arguments.runtime) / "pyproject.toml"
            checks = parse_checks(path.read_bytes(), arguments.runtime)
            if checks is None:
                raise ValueError(f"{arguments.runtime}: no validation declaration")
            selected = [checks]
        else:
            selected = discover_checks(arguments.repo, arguments.base, arguments.head)
        for checks in selected:
            validate_runtime(arguments.repo, checks, arguments.uv)
        print(f"Validated {len(selected)} declared hosted runtime(s).")
        return 0
    except (ValueError, OSError, policy.CheckError) as error:
        print(f"Hosted runtime validation error: {error}", file=sys.stderr)
        return 2
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(f"Hosted runtime check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
