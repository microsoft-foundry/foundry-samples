#!/usr/bin/env python3
"""Prepare an existing Foundry project's Application Insights connection."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

ARM = "https://management.azure.com"
FOUNDRY_VERSION = "2025-10-01-preview"
PROJECT_PATTERN = re.compile(
    r"/subscriptions/[^/]+/resourceGroups/[^/]+/providers/"
    r"Microsoft\.CognitiveServices/accounts/[^/]+/projects/[^/]+",
    re.IGNORECASE,
)
INSIGHTS_PATTERN = re.compile(
    r"/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.Insights/components/[^/]+",
    re.IGNORECASE,
)
IDENTITY_PATTERN = re.compile(
    r"/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.ManagedIdentity/userAssignedIdentities/[^/]+",
    re.IGNORECASE,
)
SETUP_LOCK_TAG = "foundry-tracing-setup-lock"
PUBLISHER = "3913510d-42f4-4e42-8a64-420c390055eb"
READER = "73c42c96-874c-492b-b04d-ab87d138a893"
CONTENT_READER = "dbc9c667-e97f-4491-aee6-90b9cf960190"
NOT_FOUND = {"ResourceNotFound", "ResourceGroupNotFound", "NotFound", "RoleAssignmentNotFound", "ParentResourceNotFound"}
PRECONDITION_FAILED = {"PreconditionFailed", "IfMatchPreconditionFailed"}


class AzureError(RuntimeError):
    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class AzureCLI:
    def __init__(self, timeout: float = 300) -> None:
        self.timeout = timeout
        self.deadline: float | None = None

    def run(self, *arguments: str) -> Any:
        timeout = self.timeout
        if self.deadline is not None:
            timeout = min(timeout, self.deadline - time.monotonic())
            if timeout <= 0:
                raise AzureError("Azure operation deadline exceeded")
        try:
            result = subprocess.run(
                [shutil.which("az") or "az", *arguments, "--output", "json", "--only-show-errors"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AzureError(f"Azure CLI invocation failed: {exc}") from exc
        if result.returncode:
            # Do not echo response bodies: a connection operation can contain credentials.
            match = re.search(
                r'"code"\s*:\s*"([A-Za-z][A-Za-z0-9_.]+)"|\(([A-Za-z][A-Za-z0-9_.]+)\)',
                result.stderr,
            )
            plain_error = result.stderr.strip().removeprefix("ERROR: ").strip()
            status_codes = {
                "Not Found": "NotFound", "Forbidden": "Forbidden",
                "Unauthorized": "Unauthorized", "Bad Request": "BadRequest",
                "Conflict": "Conflict", "Gateway Timeout": "GatewayTimeout",
                "Too Many Requests": "TooManyRequests",
                "Precondition Failed": "PreconditionFailed",
            }
            code = next(group for group in match.groups() if group) if match else status_codes.get(plain_error, "AzureCLIError")
            guidance = "Check sign-in, resource IDs, policy, and permissions."
            if code in ("RequestDisallowedByPolicy", "PolicyDenied"):
                guidance = "Ask the policy owner to resolve the denial; do not recreate resources blindly."
            raise AzureError(
                f"{code}: Azure CLI {arguments[0]} failed (exit {result.returncode}). "
                f"{guidance}", code,
            )
        try:
            return json.loads(result.stdout) if result.stdout.strip() else {}
        except json.JSONDecodeError as exc:
            raise AzureError("Azure CLI returned malformed JSON") from exc

    def rest(
        self, method: str, resource_id: str, version: str, body: Any = None, *,
        headers: dict[str, str] | None = None,
    ) -> Any:
        arguments = ["rest", "--method", method, "--url", f"{ARM}{resource_id}?api-version={version}"]
        if body is None and not headers:
            return self.run(*arguments)
        with tempfile.TemporaryDirectory() as directory:
            if headers:
                path = Path(directory) / "headers.json"
                path.write_text(json.dumps(headers), encoding="utf-8")
                arguments.extend(("--headers", f"@{path}"))
            if body is not None:
                path = Path(directory) / "body.json"
                path.write_text(json.dumps(body), encoding="utf-8")
                arguments.extend(("--body", f"@{path}"))
            return self.run(*arguments)

    def list(self, resource_id: str, version: str) -> list[dict[str, Any]]:
        result = self.rest("get", resource_id, version)
        values: list[dict[str, Any]] = []
        visited: set[str] = set()
        while True:
            if not isinstance(result, dict) or not isinstance(result.get("value"), list):
                raise AzureError("Azure resource list has no value array")
            if not all(isinstance(value, dict) for value in result["value"]):
                raise AzureError("Azure resource list contains a non-object")
            values.extend(result["value"])
            next_link = result.get("nextLink")
            if not next_link:
                return values
            if not isinstance(next_link, str) or not next_link.startswith(f"{ARM}/"):
                raise AzureError("Azure resource list returned an invalid nextLink")
            if next_link in visited:
                raise AzureError("Azure resource list repeated a nextLink")
            visited.add(next_link)
            result = self.run("rest", "--method", "get", "--url", next_link)


def validate_project(project_id: str) -> str:
    project_id = project_id.rstrip("/")
    if not PROJECT_PATTERN.fullmatch(project_id):
        raise AzureError("--project-id must be a complete Foundry project ARM resource ID")
    return project_id


def insights_id(value: Any) -> str:
    if not isinstance(value, str) or not INSIGHTS_PATTERN.fullmatch(value):
        raise AzureError("The App Insights connection has no valid component resource ID")
    return value


def connection(cli: AzureCLI, project_id: str) -> dict[str, Any] | None:
    project_id = validate_project(project_id)
    matches = [
        item for item in cli.list(f"{project_id}/connections", FOUNDRY_VERSION)
        if item.get("properties", {}).get("category") == "AppInsights"
    ]
    if not matches:
        account_id = project_id[:project_id.lower().rindex("/projects/")]
        matches = [
            item for item in cli.list(f"{account_id}/connections", FOUNDRY_VERSION)
            if item.get("properties", {}).get("category") == "AppInsights"
            and item.get("properties", {}).get("isSharedToAll") is True
        ]
    if len(matches) > 1:
        raise AzureError("Multiple applicable App Insights connections; select the intended connection explicitly")
    if not matches:
        return None
    properties = matches[0]["properties"]
    target = insights_id(
        properties.get("metadata", {}).get("ResourceId") or properties.get("target")
    )
    return {
        "connection_id": matches[0]["id"],
        "application_insights_resource_id": target,
        "auth_type": properties.get("authType"),
    }


def _reuse_connection(
    project_id: str, existing: dict[str, Any], application_insights: str | None,
) -> dict[str, Any]:
    if application_insights and insights_id(application_insights).lower() != existing["application_insights_resource_id"].lower():
        raise AzureError("The project already has a different App Insights connection; it will not be replaced")
    return {"status": "reused", "project_id": project_id, **existing}


def _release_project_lock(cli: AzureCLI, project_id: str, owner: str) -> None:
    while True:
        project = cli.rest("get", project_id, FOUNDRY_VERSION)
        tags = dict(project.get("tags") or {})
        key = next((key for key in tags if key.lower() == SETUP_LOCK_TAG), None)
        if key is None or tags[key] != owner:
            return
        etag = project.get("etag")
        if not etag:
            raise AzureError("Project has no ETag; setup lock release could not be verified")
        del tags[key]
        try:
            cli.rest("patch", project_id, FOUNDRY_VERSION, {"tags": tags}, headers={"If-Match": etag})
            return
        except AzureError as exc:
            if exc.code not in PRECONDITION_FAILED:
                raise
        time.sleep(min(1, max(0, cli.deadline - time.monotonic())))


@contextmanager
def project_setup_lock(cli: AzureCLI, project_id: str, deadline: float) -> Iterator[None]:
    owner = uuid.uuid4().hex
    attempted = False
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AzureError(
                    f"Timed out waiting for project tracing setup. Inspect the {SETUP_LOCK_TAG} "
                    "tag; remove it only after confirming its setup process has stopped."
                )
            project = cli.rest("get", project_id, FOUNDRY_VERSION)
            tags = dict(project.get("tags") or {})
            if not any(key.lower() == SETUP_LOCK_TAG for key in tags):
                etag = project.get("etag")
                if not etag:
                    raise AzureError("Project has no ETag; refusing unsafe concurrent tracing setup")
                tags[SETUP_LOCK_TAG] = owner
                attempted = True
                try:
                    cli.rest("patch", project_id, FOUNDRY_VERSION, {"tags": tags}, headers={"If-Match": etag})
                    break
                except AzureError as exc:
                    if exc.code not in PRECONDITION_FAILED:
                        raise
            time.sleep(min(1, max(0, deadline - time.monotonic())))
        yield
    finally:
        if attempted:
            active_error = sys.exc_info()[0] is not None
            previous_deadline = cli.deadline
            cli.deadline = time.monotonic() + 60
            try:
                _release_project_lock(cli, project_id, owner)
            except AzureError as exc:
                print(f"WARNING: Project setup lock release unverified: {exc}", file=sys.stderr)
                if not active_error:
                    raise
            finally:
                cli.deadline = previous_deadline


def project_principal(
    cli: AzureCLI, project: dict[str, Any], user_assigned_identity: str | None = None,
) -> str:
    identity = project.get("identity") or {}
    assigned = identity.get("userAssignedIdentities") or {}
    if user_assigned_identity:
        selected = next(
            (resource_id for resource_id in assigned if resource_id.lower() == user_assigned_identity.rstrip("/").lower()),
            None,
        )
        if selected is None:
            raise AzureError("--user-assigned-identity-resource-id must select an identity attached to the project")
    elif identity.get("principalId"):
        return identity["principalId"]
    elif len(assigned) == 1:
        selected = next(iter(assigned))
    elif assigned:
        raise AzureError("Multiple user-assigned identities are attached; select --user-assigned-identity-resource-id explicitly")
    else:
        raise AzureError("Project managed identity is required; enable it before configuring tracing")
    if not IDENTITY_PATTERN.fullmatch(selected):
        raise AzureError("The project contains an invalid user-assigned identity resource ID")
    principal = (assigned[selected] or {}).get("principalId")
    if not principal:
        principal = cli.rest("get", selected, "2023-01-31").get("properties", {}).get("principalId")
    if not principal:
        raise AzureError("The selected user-assigned identity has no principal ID")
    return principal


def wait_ready(cli: AzureCLI, resource_id: str, version: str, deadline: float) -> dict[str, Any]:
    while True:
        result = cli.rest("get", resource_id, version)
        state = result.get("properties", {}).get("provisioningState")
        if state in (None, "Succeeded"):
            return result
        if state in ("Failed", "Canceled", "Cancelled"):
            raise AzureError(f"Resource provisioning reached {state}: {resource_id}")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AzureError(f"Timed out waiting for resource provisioning: {resource_id}")
        time.sleep(min(5, remaining))


def assign_role(
    cli: AzureCLI, resource_id: str, principal: str, role: str, *,
    owner: str | None = None, created: list[tuple[str, str]] | None = None,
) -> None:
    subscription = resource_id.split("/")[2]
    role_definition = f"/subscriptions/{subscription}/providers/Microsoft.Authorization/roleDefinitions/{role}"
    assignments = cli.list(
        f"{resource_id}/providers/Microsoft.Authorization/roleAssignments", "2022-04-01",
    )
    if any(
        item.get("properties", {}).get("principalId", "").lower() == principal.lower()
        and item.get("properties", {}).get("roleDefinitionId", "").lower() == role_definition.lower()
        for item in assignments
    ):
        return
    seed = f"{resource_id.lower()}/{principal.lower()}/{role.lower()}"
    name = uuid.uuid5(uuid.NAMESPACE_URL, seed + (f"/{owner}" if owner else ""))
    assignment_id = f"{resource_id}/providers/Microsoft.Authorization/roleAssignments/{name}"
    if created is not None:
        created.append((assignment_id, "2022-04-01"))
    cli.rest(
        "put", assignment_id,
        "2022-04-01",
        {"properties": {
            "principalId": principal,
            "roleDefinitionId": role_definition,
            "principalType": "ServicePrincipal",
        }},
    )


def delete_owned(
    cli: AzureCLI, resource_id: str, version: str, owner: str, timeout: float,
) -> None:
    cli.deadline = time.monotonic() + min(timeout, 60)
    try:
        resource = cli.rest("get", resource_id, version)
    except AzureError as exc:
        if exc.code in NOT_FOUND:
            return
        raise
    owned = resource.get("tags", {}).get("foundry-tracing-owner") == owner
    role_path = "/providers/Microsoft.Authorization/roleAssignments/"
    if role_path in resource_id:
        scope, name = resource_id.rsplit(role_path, 1)
        properties = resource.get("properties", {})
        principal = properties.get("principalId", "").lower()
        role = properties.get("roleDefinitionId", "").rsplit("/", 1)[-1].lower()
        expected = uuid.uuid5(uuid.NAMESPACE_URL, f"{scope.lower()}/{principal}/{role}/{owner}")
        owned = bool(principal and role and name.lower() == str(expected))
    if not owned:
        raise AzureError("Resource ownership could not be confirmed; resource retained")
    cli.rest("delete", resource_id, version)
    while True:
        try:
            cli.rest("get", resource_id, version)
        except AzureError as exc:
            if exc.code in NOT_FOUND:
                return
            raise
        remaining = cli.deadline - time.monotonic()
        if remaining <= 0:
            raise AzureError("Timed out verifying owned-resource deletion")
        time.sleep(min(5, remaining))


def prepare(
    cli: AzureCLI, project_id: str, *, disabled: bool = False,
    timeout: float = 300, application_insights: str | None = None,
    user_assigned_identity: str | None = None,
) -> dict[str, Any]:
    project_id = validate_project(project_id)
    if disabled:
        return {"status": "disabled", "project_id": project_id}
    deadline = time.monotonic() + timeout
    cli.deadline = deadline
    existing = connection(cli, project_id)
    if existing:
        return _reuse_connection(project_id, existing, application_insights)
    with project_setup_lock(cli, project_id, deadline):
        return _prepare_locked(
            cli, project_id, deadline=deadline, timeout=timeout,
            application_insights=application_insights, user_assigned_identity=user_assigned_identity,
        )


def _prepare_locked(
    cli: AzureCLI, project_id: str, *, deadline: float, timeout: float,
    application_insights: str | None, user_assigned_identity: str | None,
) -> dict[str, Any]:
    existing = connection(cli, project_id)
    if existing:
        return _reuse_connection(project_id, existing, application_insights)
    project = cli.rest("get", project_id, FOUNDRY_VERSION)
    principal = project_principal(cli, project, user_assigned_identity)
    location = project.get("location")
    if not location:
        raise AzureError("The project has no location")
    resource_group = project_id[:project_id.lower().index("/providers/")]
    owner = uuid.uuid4().hex
    suffix = owner[:12]
    tags = {"foundry-tracing-project": project_id, "foundry-tracing-owner": owner}
    workspace_id = f"{resource_group}/providers/Microsoft.OperationalInsights/workspaces/agent-traces-{suffix}"
    component_id = application_insights or f"{resource_group}/providers/Microsoft.Insights/components/agent-traces-{suffix}"
    insights_id(component_id)
    created: list[tuple[str, str]] = []
    attached = False
    attaching = False
    try:
        if application_insights:
            component = cli.rest("get", component_id, "2020-02-02")
            if not component.get("properties", {}).get("WorkspaceResourceId"):
                raise AzureError("BYO App Insights must be workspace-based")
            if component.get("properties", {}).get("DisableLocalAuth") is not True:
                raise AzureError("New managed-identity connections require BYO App Insights with local authentication disabled; existing resources will not be changed")
        else:
            # Never adopt or overwrite a same-named resource owned by somebody else.
            resources = cli.list(f"{resource_group}/resources", "2021-04-01")
            collisions = {item["id"].lower() for item in resources}
            if workspace_id.lower() in collisions or component_id.lower() in collisions:
                raise AzureError("Tracing resource name already exists without a project connection; inspect it before retrying")
            created.append((workspace_id, "2023-09-01"))
            cli.rest("put", workspace_id, "2023-09-01", {
                "location": location,
                "tags": tags,
                "properties": {"sku": {"name": "PerGB2018"}, "retentionInDays": 30},
            })
            wait_ready(cli, workspace_id, "2023-09-01", deadline)
            created.append((component_id, "2020-02-02"))
            cli.rest("put", component_id, "2020-02-02", {
                "location": location, "kind": "web",
                "tags": tags,
                "properties": {
                    "Application_Type": "web", "WorkspaceResourceId": workspace_id,
                    "DisableLocalAuth": True,
                },
            })
            component = wait_ready(cli, component_id, "2020-02-02", deadline)
        for role in (PUBLISHER, READER, CONTENT_READER):
            assign_role(cli, component_id, principal, role, owner=owner, created=created)
        # Recheck for connections created by tools that do not use this lock.
        existing = connection(cli, project_id)
        if existing:
            raise AzureError("A connection appeared during setup; it was not replaced. Rerun to reuse it")
        connection_id = f"{project_id}/connections/agent-traces-{suffix}"
        attaching = True
        cli.rest("put", connection_id, FOUNDRY_VERSION, {"properties": {
            "category": "AppInsights", "target": component_id,
            "authType": "ProjectManagedIdentity",
            "metadata": {
                "ApiType": "Azure", "ResourceId": component_id,
                "ApplicationInsightsConnectionString": component["properties"]["ConnectionString"],
            },
        }})
        attached = True
        wait_ready(cli, connection_id, FOUNDRY_VERSION, deadline)
        return {
            "status": "configured", "project_id": project_id,
            "connection_id": connection_id,
            "application_insights_resource_id": component_id,
            "auth_type": "ProjectManagedIdentity",
            "principal_id": principal,
        }
    except (AzureError, KeyError, KeyboardInterrupt):
        if not attached and (attaching or application_insights):
            # A timed-out PUT may have succeeded remotely; never delete its destination.
            cli.deadline = time.monotonic() + min(timeout, 60)
            try:
                linked = connection(cli, project_id)
                attached = bool(linked and linked["application_insights_resource_id"].lower() == component_id.lower())
            except AzureError:
                attached = True
                print("WARNING: Connection outcome is uncertain; owned resources retained for inspection.", file=sys.stderr)
        # Keep a successfully attached resource: deleting it would break the project connection.
        if not attached:
            for resource_id, version in reversed(created):
                try:
                    delete_owned(cli, resource_id, version, owner, timeout)
                except AzureError as exc:
                    print(f"WARNING: Cleanup unverified for {resource_id}: {exc}", file=sys.stderr)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--application-insights-resource-id")
    parser.add_argument("--user-assigned-identity-resource-id", help="Select an attached user-assigned identity for role assignments")
    parser.add_argument("--disable", action="store_true", help="Skip setup without disconnecting existing telemetry")
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    try:
        result = prepare(
            AzureCLI(args.timeout), args.project_id, disabled=args.disable,
            timeout=args.timeout, application_insights=args.application_insights_resource_id,
            user_assigned_identity=args.user_assigned_identity_resource_id,
        )
    except (AzureError, KeyError) as exc:
        print(
            f"WARNING: App Insights setup did not complete: {exc}\n"
            "The project is retained. Correct the reported prerequisite and rerun this "
            "command to configure tracing later. Tracing is not verified.",
            file=sys.stderr,
        )
        return 2
    except KeyboardInterrupt:
        print("App Insights setup interrupted; cleanup was attempted for owned resources.", file=sys.stderr)
        return 130
    if result["status"] == "configured":
        print(
            "Connection configured, not ingestion-verified. Allow 2-5 minutes for "
            "identity/connection propagation before the first agent conversation.",
            file=sys.stderr,
        )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
