"""Check local/hosted configuration parity for module-hosted Python agents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import posixpath
import re
import shlex

import yaml


HOSTING_MODULE = "langchain_azure_ai.agents.hosting.run"
SAMPLE_ROOT = Path("samples/python/hosted-agents")


class CommandParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def command_tokens(command: object) -> list[str]:
    if command is None:
        return []
    if isinstance(command, str):
        return shlex.split(command)
    if isinstance(command, list) and all(isinstance(part, str) for part in command):
        return command
    raise ValueError("command must be a string or an array of strings")


def hosting_settings(tokens: list[str], *, local: bool) -> dict:
    for index, token in enumerate(tokens[:-1]):
        if token in {"-m", "--module"} and tokens[index + 1] == HOSTING_MODULE:
            prefix = tokens[:index]
            executable = prefix[0].replace("\\", "/").rsplit("/", 1)[-1] if prefix else ""
            uv_run = executable in {"uv", "uv.exe"} and prefix[1:2] == ["run"]
            python = re.fullmatch(r"python(?:\d+(?:\.\d+)*)?(?:\.exe)?", executable)
            if not (
                uv_run
                or (python and token == "-m")
                or (not local and not prefix and token == "-m")
            ):
                raise ValueError("hosting module must be invoked by Python or uv run")
            arguments = tokens[index + 2:]
            break
    else:
        raise ValueError(f"must invoke the hosting module via -m {HOSTING_MODULE}")

    parser = CommandParser(add_help=False, allow_abbrev=False)
    parser.add_argument("agent", nargs="?")
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--config", default="langgraph.json")
    parser.add_argument("--option", action="append", default=[])
    parser.add_argument("--host")
    parser.add_argument("--port")
    args = parser.parse_args(arguments)
    options = {}
    for option in args.option:
        name, separator, value = option.partition("=")
        name, value = name.strip(), value.strip()
        if not separator or not name or not value:
            raise ValueError("--option must use NAME=VALUE")
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = value
        options[name] = json.dumps(parsed, sort_keys=True)
    return {
        "protocol": args.protocol,
        "options": options,
        "agent": args.agent,
        "config": posixpath.normpath(args.config.replace("\\", "/")),
    }


def check_manifest(path: Path) -> tuple[int, list[str]]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or not isinstance(document.get("services"), dict):
            raise ValueError("services must be a mapping")
    except (OSError, ValueError, yaml.YAMLError) as error:
        return 0, [f"{path}: {error}"]

    checked = 0
    errors = []
    for name, service in document["services"].items():
        if not isinstance(service, dict) or service.get("host") != "azure.ai.agent":
            continue
        label = f"{path}: services.{name}"
        try:
            configuration = service.get("codeConfiguration") or {}
            if not isinstance(configuration, dict):
                raise ValueError("codeConfiguration must be a mapping")
            hosted = command_tokens(configuration.get("entryPoint"))
            startup = command_tokens(service.get("startupCommand"))
            if HOSTING_MODULE not in hosted and HOSTING_MODULE not in startup:
                continue
            checked += 1
            if not startup:
                raise ValueError("startupCommand is required for a module-hosted agent")
            expected = hosting_settings(hosted, local=False)
            actual = hosting_settings(startup, local=True)
            for setting in expected:
                if actual[setting] != expected[setting]:
                    errors.append(f"{label}: startupCommand {setting} must match entryPoint")
            protocols = service.get("protocols")
            if not isinstance(protocols, list) or not any(
                isinstance(protocol, dict) and protocol.get("protocol") == expected["protocol"]
                for protocol in protocols
            ):
                raise ValueError("protocols must declare the hosting --protocol")
        except ValueError as error:
            errors.append(f"{label}: {error}")
    return checked, errors


def check_repository(repo: Path) -> tuple[int, list[str]]:
    root = repo / SAMPLE_ROOT
    if not root.is_dir():
        return 0, [f"Hosted-agent sample directory does not exist: {root}"]
    checked = 0
    errors = []
    for manifest in sorted(root.rglob("azure.yaml")):
        count, problems = check_manifest(manifest)
        checked += count
        errors.extend(problems)
    return checked, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    checked, errors = check_repository(args.repo_root.resolve())
    if errors:
        for error in errors:
            print(f"::error::{error}")
        return 1
    print(f"Validated local startup for {checked} module-hosted service(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
