#!/usr/bin/env python3
"""Enforce reproducible locks for new or dependency-updated Python hosted agents."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import posixpath
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import tomllib
from typing import Iterable, Mapping, Sequence

import yaml
from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

SCOPE = PurePosixPath("samples/python/hosted-agents")
POLICY_PATH = SCOPE / "DEPENDENCY_POLICY.md"
DEFAULT_EXCEPTIONS = PurePosixPath(
    ".azure-pipelines/hosted-agent-tests/python-requirements-exceptions.toml"
)
DEPENDENCY_FILENAMES = {
    "Pipfile",
    "Pipfile.lock",
    "environment.yaml",
    "environment.yml",
    "pdm.lock",
    "poetry.lock",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "uv.lock",
    "uv.toml",
}
REQUIREMENTS_NAME = re.compile(r"^requirements(?:[-.][^/]*)?\.(?:in|txt)$")
NON_RUNTIME_REQUIREMENTS = re.compile(r"^requirements-(?:dev|test|tests)\.(?:in|txt)$")
REQUIREMENTS_ARTIFACT = "requirements.txt"
UV_MANIFEST = "pyproject.toml"
UV_LOCK = "uv.lock"
HASH_OPTION = re.compile(r"(?:^|\s)--hash(?:=|\s+)\S+")
INLINE_COMMENT = re.compile(r"\s+#.*$")
VCS_PREFIXES = ("git+", "hg+", "svn+", "bzr+")
VALID_CODES = {f"PYREQ{number:03d}" for number in range(1, 13)}


@dataclasses.dataclass(frozen=True)
class ServiceRoot:
    path: PurePosixPath
    manifest: PurePosixPath
    service: str


@dataclasses.dataclass(frozen=True)
class ChangedPath:
    status: str
    old: PurePosixPath | None
    new: PurePosixPath | None

    @property
    def paths(self) -> tuple[PurePosixPath, ...]:
        return tuple(path for path in (self.old, self.new) if path is not None)


@dataclasses.dataclass(frozen=True)
class Finding:
    code: str
    message: str
    root: PurePosixPath
    trigger: PurePosixPath
    source: PurePosixPath | None = None
    line: int | None = None
    detail: str | None = None


@dataclasses.dataclass(frozen=True)
class ExceptionRule:
    path: PurePosixPath
    code: str
    reason: str
    owner: str
    issue: str
    expires: dt.date


class CheckError(RuntimeError):
    """A fatal checker/configuration error."""


def git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=text,
    )
    if result.returncode:
        stderr = result.stderr if text else result.stderr.decode(errors="replace")
        raise CheckError(f"git {' '.join(args)} failed: {stderr.strip()}")
    return result.stdout


def tree_files(repo: Path, revision: str) -> set[PurePosixPath]:
    output = git(
        repo,
        "ls-tree",
        "-r",
        "--name-only",
        "-z",
        revision,
        "--",
        str(SCOPE),
        text=False,
    )
    assert isinstance(output, bytes)
    return {PurePosixPath(raw.decode()) for raw in output.split(b"\0") if raw}


def read_tree_file(repo: Path, revision: str, path: PurePosixPath) -> bytes:
    output = git(repo, "show", f"{revision}:{path}", text=False)
    assert isinstance(output, bytes)
    return output


def changed_paths(repo: Path, base: str, head: str) -> list[ChangedPath]:
    output = git(
        repo,
        "diff",
        "--name-status",
        "-z",
        "--find-renames",
        f"{base}..{head}",
        "--",
        str(SCOPE),
        text=False,
    )
    assert isinstance(output, bytes)
    fields = [field.decode() for field in output.split(b"\0") if field]
    changes: list[ChangedPath] = []
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        if status.startswith(("R", "C")):
            old = PurePosixPath(fields[index])
            new = PurePosixPath(fields[index + 1])
            index += 2
        elif status.startswith("D"):
            old = PurePosixPath(fields[index])
            new = None
            index += 1
        else:
            old = None
            new = PurePosixPath(fields[index])
            index += 1
        changes.append(ChangedPath(status=status, old=old, new=new))
    return changes


def is_under(path: PurePosixPath, parent: PurePosixPath) -> bool:
    return path == parent or parent in path.parents


def discover_services(
    repo: Path, revision: str, files: set[PurePosixPath]
) -> dict[PurePosixPath, ServiceRoot]:
    roots: dict[PurePosixPath, ServiceRoot] = {}
    for manifest in sorted(path for path in files if path.name == "azure.yaml"):
        try:
            document = yaml.safe_load(read_tree_file(repo, revision, manifest)) or {}
        except (yaml.YAMLError, UnicodeDecodeError) as exc:
            raise CheckError(f"Cannot parse {manifest} at {revision}: {exc}") from exc
        if not isinstance(document, Mapping):
            continue
        services = document.get("services", {})
        if not isinstance(services, Mapping):
            continue
        for service_name, raw_service in services.items():
            if not isinstance(raw_service, Mapping):
                continue
            language = str(raw_service.get("language", "")).lower()
            project = raw_service.get("project")
            if (
                language != "python"
                or not isinstance(project, str)
                or not project.strip()
            ):
                continue
            root = PurePosixPath(posixpath.normpath(str(manifest.parent / project)))
            if not is_under(root, SCOPE):
                raise CheckError(
                    f"Python service {service_name!r} in {manifest} resolves outside {SCOPE}: {root}"
                )
            existing = roots.get(root)
            if existing and existing.manifest != manifest:
                raise CheckError(
                    f"Python runtime root {root} is declared by both {existing.manifest} and {manifest}"
                )
            roots[root] = ServiceRoot(root, manifest, str(service_name))
    return roots


def is_dependency_input(path: PurePosixPath) -> bool:
    if NON_RUNTIME_REQUIREMENTS.match(path.name):
        return False
    return path.name in DEPENDENCY_FILENAMES or bool(REQUIREMENTS_NAME.match(path.name))


def closest_service(
    path: PurePosixPath, services: Mapping[PurePosixPath, ServiceRoot]
) -> PurePosixPath | None:
    candidates = [root for root in services if is_under(path, root)]
    return max(candidates, key=lambda item: len(item.parts), default=None)


def closest_manifest_sample(
    path: PurePosixPath, services: Mapping[PurePosixPath, ServiceRoot]
) -> list[PurePosixPath]:
    manifests = {service.manifest.parent for service in services.values()}
    candidates = [root for root in manifests if is_under(path, root)]
    if not candidates:
        return []
    sample = max(candidates, key=lambda item: len(item.parts))
    return sorted(
        root for root, service in services.items() if service.manifest.parent == sample
    )


def runtime_root_for_input(
    path: PurePosixPath,
    services: Mapping[PurePosixPath, ServiceRoot],
    files: set[PurePosixPath],
) -> PurePosixPath | None:
    service = closest_service(path, services)
    if service is not None:
        # A nested project is independently installable only when that directory
        # owns a supported lock artifact. Tests and vendored pyprojects otherwise
        # remain part of the declared service runtime.
        nested_requirements = path.parent / REQUIREMENTS_ARTIFACT
        nested_uv_lock = path.parent / UV_LOCK
        nested_uv_manifest = path.parent / UV_MANIFEST
        if path.parent != service and (
            nested_requirements in files
            or (nested_uv_lock in files and nested_uv_manifest in files)
        ):
            return path.parent
        return service
    sample_services = closest_manifest_sample(path, services)
    if len(sample_services) == 1:
        return sample_services[0]
    return None


def logical_requirement_lines(content: str) -> list[tuple[int, str]]:
    logical: list[tuple[int, str]] = []
    pending = ""
    start = 0
    for number, raw in enumerate(content.splitlines(), start=1):
        stripped = raw.strip()
        if not pending and (not stripped or stripped.startswith("#")):
            continue
        if not pending:
            start = number
        continued = stripped.endswith("\\")
        fragment = stripped[:-1].rstrip() if continued else stripped
        pending = f"{pending} {fragment}".strip()
        if not continued:
            logical.append((start, pending))
            pending = ""
    if pending:
        logical.append((start, pending))
    return logical


def strip_hashes(line: str) -> str:
    return HASH_OPTION.sub("", line).strip()


def parse_requirements(
    content: str,
    root: PurePosixPath,
    trigger: PurePosixPath,
    source: PurePosixPath,
) -> tuple[list[Requirement], list[Finding]]:
    requirements: list[Requirement] = []
    findings: list[Finding] = []
    for line_number, logical in logical_requirement_lines(content):
        line = INLINE_COMMENT.sub("", strip_hashes(logical)).strip()
        if not line or line.startswith("#"):
            continue
        lowered = line.lower()
        if lowered.startswith(("-r ", "--requirement ", "-c ", "--constraint ")):
            findings.append(
                Finding(
                    "PYREQ005",
                    "requirements.txt must be a standalone artifact and cannot include another requirements or constraints file",
                    root,
                    trigger,
                    source,
                    line_number,
                    logical,
                )
            )
            continue
        if lowered.startswith(("-e ", "--editable ")) or lowered.startswith(
            (".", "/", "file:")
        ):
            findings.append(
                Finding(
                    "PYREQ004",
                    "editable and local-path dependencies are not portable consumer requirements",
                    root,
                    trigger,
                    source,
                    line_number,
                    logical,
                )
            )
            continue
        if lowered.startswith("-"):
            findings.append(
                Finding(
                    "PYREQ009",
                    "index, host, and other pip options are not allowed in the portable requirements artifact",
                    root,
                    trigger,
                    source,
                    line_number,
                    logical,
                )
            )
            continue
        try:
            requirement = Requirement(line)
        except InvalidRequirement as exc:
            findings.append(
                Finding(
                    "PYREQ010",
                    f"invalid requirement: {exc}",
                    root,
                    trigger,
                    source,
                    line_number,
                    logical,
                )
            )
            continue
        if requirement.url:
            url = requirement.url.lower()
            code = "PYREQ003" if url.startswith(VCS_PREFIXES) else "PYREQ011"
            message = (
                "VCS dependencies are not portable consumer requirements; publish and pin a package or request a narrow exception"
                if code == "PYREQ003"
                else "direct URL dependencies are not allowed in the portable requirements artifact"
            )
            findings.append(
                Finding(code, message, root, trigger, source, line_number, logical)
            )
            continue
        specifiers = list(requirement.specifier)
        if (
            len(specifiers) != 1
            or specifiers[0].operator not in {"==", "==="}
            or "*" in specifiers[0].version
        ):
            findings.append(
                Finding(
                    "PYREQ002",
                    "each package must use exactly one immutable == or === version; extras and environment markers are allowed",
                    root,
                    trigger,
                    source,
                    line_number,
                    logical,
                )
            )
            continue
        requirements.append(requirement)
    return requirements, findings


def active_pins(requirements: Iterable[Requirement]) -> dict[str, str]:
    environment = default_environment()
    pins: dict[str, str] = {}
    for requirement in requirements:
        if requirement.marker and not requirement.marker.evaluate(environment):
            continue
        specifier = next(iter(requirement.specifier))
        pins[canonicalize_name(requirement.name)] = specifier.version
    return pins


def resolve_requirements(
    content: str,
    source: PurePosixPath,
    requirements: Sequence[Requirement],
    root: PurePosixPath,
    trigger: PurePosixPath,
    python: str,
) -> list[Finding]:
    with tempfile.TemporaryDirectory(prefix="hosted-agent-requirements-") as directory:
        temp_root = Path(directory)
        report = temp_root / "pip-report.json"
        requirement_file = temp_root / "requirements.txt"
        requirement_file.write_text(content, encoding="utf-8")
        command = [
            python,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--dry-run",
            "--ignore-installed",
            "--only-binary=:all:",
            "--no-cache-dir",
            "--index-url",
            "https://pypi.org/simple",
            "--retries",
            "2",
            "--timeout",
            "30",
            "--report",
            str(report),
            "-r",
            str(requirement_file),
        ]
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired as exc:
            raise CheckError(
                f"pip timed out while resolving {source} after {exc.timeout} seconds"
            ) from exc
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()[-4000:]
            infrastructure_signals = (
                "connection error",
                "connection reset",
                "connection timed out",
                "max retries exceeded",
                "read timed out",
                "remote end closed",
                "temporary failure",
                "tls",
            )
            if any(signal in detail.lower() for signal in infrastructure_signals):
                raise CheckError(
                    f"pip infrastructure failure while resolving {source}: {detail}"
                )
            return [
                Finding(
                    "PYREQ012",
                    "pip could not resolve the committed requirements artifact from binary distributions",
                    root,
                    trigger,
                    source,
                    detail=detail,
                )
            ]
        payload = json.loads(report.read_text(encoding="utf-8"))
    declared = active_pins(requirements)
    resolved: dict[str, str] = {}
    for item in payload.get("install", []):
        metadata = item.get("metadata", {})
        name = metadata.get("name")
        version = metadata.get("version")
        if name and version:
            resolved[canonicalize_name(name)] = str(version)
    findings: list[Finding] = []
    for name, version in sorted(resolved.items()):
        if name not in declared:
            findings.append(
                Finding(
                    "PYREQ007",
                    f"pip resolved transitive dependency {name}=={version}, but requirements.txt does not pin it",
                    root,
                    trigger,
                    source,
                )
            )
        elif declared[name] != version:
            findings.append(
                Finding(
                    "PYREQ008",
                    f"pip resolved {name}=={version}, which differs from the committed pin {name}=={declared[name]}",
                    root,
                    trigger,
                    source,
                )
            )
    return findings


def parse_uv_lock(
    lock_content: str,
    project_content: str,
    root: PurePosixPath,
    trigger: PurePosixPath,
    source: PurePosixPath,
) -> list[Finding]:
    try:
        lock = tomllib.loads(lock_content)
        project = tomllib.loads(project_content)
    except tomllib.TOMLDecodeError as exc:
        return [
            Finding(
                "PYREQ010",
                f"invalid uv project or lock TOML: {exc}",
                root,
                trigger,
                source,
            )
        ]

    project_table = project.get("project")
    project_name = (
        canonicalize_name(str(project_table.get("name")))
        if isinstance(project_table, Mapping) and project_table.get("name")
        else None
    )
    packages = lock.get("package")
    if not isinstance(packages, list):
        return [
            Finding(
                "PYREQ010",
                "uv.lock must contain a package array",
                root,
                trigger,
                source,
            )
        ]

    findings: list[Finding] = []
    for package in packages:
        if not isinstance(package, Mapping):
            findings.append(
                Finding(
                    "PYREQ010",
                    "uv.lock contains an invalid package entry",
                    root,
                    trigger,
                    source,
                )
            )
            continue
        name = str(package.get("name", "<unnamed>"))
        if not package.get("version"):
            findings.append(
                Finding(
                    "PYREQ002",
                    f"uv.lock package {name} does not pin an immutable version",
                    root,
                    trigger,
                    source,
                )
            )
        raw_source = package.get("source")
        if not isinstance(raw_source, Mapping):
            findings.append(
                Finding(
                    "PYREQ010",
                    f"uv.lock package {name} has no valid source",
                    root,
                    trigger,
                    source,
                )
            )
            continue
        if "git" in raw_source:
            findings.append(
                Finding(
                    "PYREQ003",
                    f"uv.lock package {name} uses a VCS source; publish and pin a package or request a narrow exception",
                    root,
                    trigger,
                    source,
                )
            )
        elif "url" in raw_source:
            findings.append(
                Finding(
                    "PYREQ011",
                    f"uv.lock package {name} uses a direct URL source",
                    root,
                    trigger,
                    source,
                )
            )
        elif any(
            key in raw_source for key in ("directory", "path", "editable", "virtual")
        ):
            local_project_source = raw_source.get("editable", raw_source.get("virtual"))
            is_project = (
                local_project_source == "."
                and project_name is not None
                and canonicalize_name(name) == project_name
            )
            if not is_project:
                findings.append(
                    Finding(
                        "PYREQ004",
                        f"uv.lock package {name} uses a local-path or editable source",
                        root,
                        trigger,
                        source,
                    )
                )
        elif raw_source.get("registry") != "https://pypi.org/simple":
            findings.append(
                Finding(
                    "PYREQ009",
                    f"uv.lock package {name} does not use the portable PyPI registry",
                    root,
                    trigger,
                    source,
                )
            )
    return findings


def validate_uv_resolution(
    repo: Path,
    revision: str,
    files: set[PurePosixPath],
    root: PurePosixPath,
    trigger: PurePosixPath,
    uv: str,
) -> list[Finding]:
    source = root / UV_LOCK
    with tempfile.TemporaryDirectory(prefix="hosted-agent-uv-lock-") as directory:
        project_root = Path(directory)
        for name in (UV_MANIFEST, UV_LOCK):
            (project_root / name).write_bytes(
                read_tree_file(repo, revision, root / name)
            )
        uv_config = root / "uv.toml"
        if uv_config in files:
            (project_root / uv_config.name).write_bytes(
                read_tree_file(repo, revision, uv_config)
            )
        commands = [
            [uv, "lock", "--check", "--project", str(project_root)],
            [
                uv,
                "export",
                "--frozen",
                "--no-dev",
                "--no-emit-project",
                "--no-hashes",
                "--no-annotate",
                "--format",
                "requirements-txt",
                "--project",
                str(project_root),
            ],
        ]
        for command in commands:
            try:
                result = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
            except FileNotFoundError as exc:
                raise CheckError(
                    f"uv executable not found while validating {source}: {uv}"
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise CheckError(
                    f"uv timed out while validating {source} after {exc.timeout} seconds"
                ) from exc
            if result.returncode:
                detail = (result.stderr or result.stdout).strip()[-4000:]
                return [
                    Finding(
                        "PYREQ012",
                        "uv could not validate or export the committed lock",
                        root,
                        trigger,
                        source,
                        detail=detail,
                    )
                ]
    return []


def load_exceptions(path: Path) -> list[ExceptionRule]:
    if not path.exists():
        return []
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    raw_rules = payload.get("exceptions", [])
    if not isinstance(raw_rules, list):
        raise CheckError(f"{path}: 'exceptions' must be an array of tables")
    rules: list[ExceptionRule] = []
    for index, raw in enumerate(raw_rules, start=1):
        if not isinstance(raw, Mapping):
            raise CheckError(f"{path}: exception {index} must be a table")
        missing = {"path", "code", "reason", "owner", "issue", "expires"} - raw.keys()
        if missing:
            raise CheckError(f"{path}: exception {index} is missing {sorted(missing)}")
        for field in ("path", "code", "reason", "owner", "issue"):
            if not isinstance(raw[field], str) or not raw[field].strip():
                raise CheckError(
                    f"{path}: exception {index} {field} must be a non-empty string"
                )
        if not re.fullmatch(
            r"https://github\.com/microsoft-foundry/foundry-samples/issues/[1-9][0-9]*",
            raw["issue"],
        ):
            raise CheckError(
                f"{path}: exception {index} issue must be an HTTPS issue URL "
                "under github.com/microsoft-foundry/foundry-samples/issues/"
            )
        expires = raw["expires"]
        if isinstance(expires, str):
            expires = dt.date.fromisoformat(expires)
        if type(expires) is not dt.date:
            raise CheckError(f"{path}: exception {index} has an invalid expiration")
        rule_path = PurePosixPath(raw["path"])
        code = raw["code"]
        if not is_under(rule_path, SCOPE):
            raise CheckError(f"{path}: exception {index} path must be under {SCOPE}")
        if code not in VALID_CODES:
            raise CheckError(f"{path}: exception {index} uses unknown code {code!r}")
        rules.append(
            ExceptionRule(
                rule_path,
                code,
                raw["reason"],
                raw["owner"],
                raw["issue"],
                expires,
            )
        )
    return rules


def apply_exceptions(
    findings: Sequence[Finding], rules: Sequence[ExceptionRule]
) -> tuple[list[Finding], list[ExceptionRule]]:
    today = dt.datetime.now(dt.timezone.utc).date()
    active_rules = [rule for rule in rules if rule.expires >= today]
    used: list[ExceptionRule] = []
    remaining: list[Finding] = []
    for finding in findings:
        match = next(
            (
                rule
                for rule in active_rules
                if rule.code == finding.code and rule.path == finding.root
            ),
            None,
        )
        if match:
            used.append(match)
        else:
            remaining.append(finding)
    return remaining, used


def collect_findings(
    repo: Path,
    base: str,
    head: str,
    resolve: bool,
    python: str,
    uv: str = "uv",
) -> list[Finding]:
    base_files = tree_files(repo, base)
    head_files = tree_files(repo, head)
    base_services = discover_services(repo, base, base_files)
    head_services = discover_services(repo, head, head_files)
    changes = changed_paths(repo, base, head)

    triggers: dict[PurePosixPath, set[PurePosixPath]] = {}
    new_roots = set(head_services) - set(base_services)
    # A newly declared Python service is always checked, even when no dependency
    # file was added.
    for root in sorted(new_roots):
        triggers.setdefault(root, set()).add(head_services[root].manifest)

    head_side_paths = {change.new for change in changes if change.new is not None}
    sample_directories = {service.manifest.parent for service in head_services.values()}
    for change in changes:
        for path in change.paths:
            if not is_dependency_input(path):
                continue
            if path in head_files:
                root = runtime_root_for_input(path, head_services, head_files)
            else:
                root = runtime_root_for_input(path, base_services, base_files)
            if root is None:
                continue
            belongs_to_head_sample = root in head_services or any(
                is_under(root, sample) for sample in sample_directories
            )
            if belongs_to_head_sample:
                triggers.setdefault(root, set()).add(path)

    findings: list[Finding] = []
    for root, root_triggers in sorted(triggers.items(), key=lambda item: str(item[0])):
        requirements_source = root / REQUIREMENTS_ARTIFACT
        uv_manifest = root / UV_MANIFEST
        uv_source = root / UV_LOCK
        if uv_manifest in head_files and uv_source in head_files:
            source = uv_source
            artifact_kind = "uv"
        elif requirements_source in head_files:
            source = requirements_source
            artifact_kind = "requirements"
        else:
            source = requirements_source
            artifact_kind = "missing"
        requirements_triggers = sorted(path for path in root_triggers if path == source)
        trigger = (
            requirements_triggers[0]
            if requirements_triggers
            else sorted(root_triggers)[0]
        )
        if artifact_kind == "missing":
            findings.append(
                Finding(
                    "PYREQ001",
                    "new or dependency-updated Python hosted-agent runtime must commit requirements.txt or both pyproject.toml and uv.lock",
                    root,
                    trigger,
                    source,
                )
            )
            continue
        # If a separate authoring input changed, require an updated export in
        # the same PR. requirements.txt itself is already the trigger otherwise.
        authoring_changed = any(
            path != source
            and not (artifact_kind == "uv" and path.name == REQUIREMENTS_ARTIFACT)
            for path in root_triggers
        )
        if (
            root not in new_roots
            and authoring_changed
            and source not in head_side_paths
        ):
            artifact_description = (
                "requirements.txt export"
                if artifact_kind == "requirements"
                else "uv.lock"
            )
            findings.append(
                Finding(
                    "PYREQ006",
                    f"a dependency authoring input changed without updating the committed {artifact_description}",
                    root,
                    trigger,
                    source,
                )
            )
        if artifact_kind == "requirements":
            content = read_tree_file(repo, head, source).decode("utf-8")
            requirements, parse_findings = parse_requirements(
                content, root, trigger, source
            )
            findings.extend(parse_findings)
            if resolve and not parse_findings:
                findings.extend(
                    resolve_requirements(
                        content, source, requirements, root, trigger, python
                    )
                )
        else:
            lock_content = read_tree_file(repo, head, uv_source).decode("utf-8")
            project_content = read_tree_file(repo, head, uv_manifest).decode("utf-8")
            uv_findings = parse_uv_lock(
                lock_content, project_content, root, trigger, uv_source
            )
            findings.extend(uv_findings)
            if resolve and not uv_findings:
                findings.extend(
                    validate_uv_resolution(repo, head, head_files, root, trigger, uv)
                )
    return findings


def annotation(finding: Finding, policy_url: str) -> str:
    properties: list[str] = ["type=error"]
    if finding.source:
        properties.append(f"sourcepath={finding.source}")
    if finding.line:
        properties.append(f"linenumber={finding.line}")
    message = f"{finding.code}: {finding.message}. Policy: {policy_url}"
    message = message.replace("\r", " ").replace("\n", " ")
    return f"##vso[task.logissue {';'.join(properties)};]{message}"


def print_findings(findings: Sequence[Finding], policy_url: str, ado: bool) -> None:
    for finding in findings:
        print(f"\n{finding.code} {finding.message}")
        print(f"  Runtime root: {finding.root}")
        print(f"  Trigger: {finding.trigger}")
        if finding.source:
            location = (
                f"{finding.source}:{finding.line}"
                if finding.line
                else str(finding.source)
            )
            print(f"  Source: {location}")
        if finding.detail:
            print(f"  Found: {finding.detail}")
        print(f"  Policy and remediation: {policy_url}")
        if ado:
            print(annotation(finding, policy_url))
    if findings:
        print(f"\nPython Hosted Agent dependency policy: {policy_url}")
        print(f"Repository path: {POLICY_PATH}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Base Git revision")
    parser.add_argument("--head", default="HEAD", help="Head Git revision")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument(
        "--resolve",
        action="store_true",
        help="Use pip or uv to verify the committed dependency artifact",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable used for pip resolution",
    )
    parser.add_argument(
        "--uv",
        default="uv",
        help="uv executable used for native uv lock validation",
    )
    parser.add_argument(
        "--exceptions",
        type=Path,
        help=f"Exception file (default: {DEFAULT_EXCEPTIONS})",
    )
    parser.add_argument(
        "--policy-url",
        default=str(POLICY_PATH),
        help="Policy URL shown in diagnostics",
    )
    parser.add_argument(
        "--ado", action="store_true", help="Emit Azure Pipelines annotations"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo = args.repo.resolve()
    exception_path = args.exceptions or repo / DEFAULT_EXCEPTIONS
    try:
        findings = collect_findings(
            repo, args.base, args.head, args.resolve, args.python, args.uv
        )
        rules = load_exceptions(exception_path)
        findings, used = apply_exceptions(findings, rules)
    except (CheckError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Dependency policy checker error: {exc}", file=sys.stderr)
        return 2
    if used:
        for rule in used:
            print(
                f"Applied exception {rule.code} for {rule.path} until {rule.expires}: {rule.reason}"
            )
    print_findings(findings, args.policy_url, args.ado)
    if findings:
        print(
            f"\nFound {len(findings)} dependency-policy violation(s).", file=sys.stderr
        )
        return 1
    print("Python Hosted Agent dependency-policy check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
