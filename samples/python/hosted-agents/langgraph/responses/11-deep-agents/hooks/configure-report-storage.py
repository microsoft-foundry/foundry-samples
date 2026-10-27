"""Authorize the deployed agent to publish reports to the configured container."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

RECEIPT = Path(".azure/report-storage-role-assignments.json")


def run_cli(*arguments: str) -> str:
    executable = shutil.which(arguments[0])
    if executable is None:
        raise RuntimeError(f"Install {arguments[0]} before deploying this sample.")
    try:
        result = subprocess.run(
            [executable, *arguments[1:]],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as error:
        code = re.search(
            r"(?m)^ERROR:\s*\(([A-Za-z][A-Za-z0-9]{0,63})\)",
            error.stderr or "",
        )
        detail = f" ({code.group(1)})" if code else ""
        raise RuntimeError(
            f"Command failed: {' '.join(arguments[:4])}{detail}"
        ) from None
    return result.stdout.strip()


def configure() -> None:
    settings = {}
    for line in run_cli("azd", "env", "get-values").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.startswith("AZURE_"):
            settings[key] = value.strip().strip('"')
    account = settings.get("AZURE_STORAGE_ACCOUNT_NAME", "")
    container = settings.get("AZURE_STORAGE_CONTAINER_NAME", "")
    if re.fullmatch(r"[a-z0-9]{3,24}", account) is None:
        raise ValueError("Set AZURE_STORAGE_ACCOUNT_NAME to an existing account.")
    if (
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])", container) is None
        or "--" in container
    ):
        raise ValueError("Set AZURE_STORAGE_CONTAINER_NAME to a private container.")
    subscription = settings.get("AZURE_STORAGE_SUBSCRIPTION_ID") or settings.get(
        "AZURE_SUBSCRIPTION_ID", ""
    )
    UUID(subscription)
    account_id = run_cli(
        "az",
        "storage",
        "account",
        "list",
        "--subscription",
        subscription,
        "--query",
        f"[?name=='{account}'].id | [0]",
        "--output",
        "tsv",
    )
    expected_prefix = f"/subscriptions/{subscription}/resourceGroups/".lower()
    expected_suffix = f"/providers/Microsoft.Storage/storageAccounts/{account}".lower()
    if not (
        account_id.lower().startswith(expected_prefix)
        and account_id.lower().endswith(expected_suffix)
    ):
        raise ValueError("Storage lookup returned an unexpected resource scope.")
    container_id = f"{account_id}/blobServices/default/containers/{container}"
    run_cli("az", "resource", "show", "--ids", container_id, "--output", "none")
    agent = json.loads(run_cli("azd", "ai", "agent", "show", "--output", "json"))
    principal = agent.get("instance_identity", {}).get("principal_id", "")
    UUID(principal)
    receipt = {"principal": principal, "account_id": account_id, "assignments": []}
    if RECEIPT.is_file():
        previous = json.loads(RECEIPT.read_text(encoding="utf-8"))
        if (
            previous.get("principal") == principal
            and previous.get("account_id") == account_id
        ):
            receipt = previous
        elif previous.get("assignments"):
            raise ValueError(
                "Clean up recorded grants before changing the agent or Storage account."
            )
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt), encoding="utf-8")
    for role, scope in (
        ("Storage Blob Data Contributor", container_id),
        ("Storage Blob Delegator", account_id),
    ):
        role_id = run_cli(
            "az",
            "role",
            "definition",
            "list",
            "--name",
            role,
            "--subscription",
            subscription,
            "--query",
            "[0].id",
            "--output",
            "tsv",
        )
        if not role_id:
            raise ValueError(f"Could not resolve the {role} role.")
        assignments = json.loads(
            run_cli(
                "az",
                "role",
                "assignment",
                "list",
                "--scope",
                scope,
                "--include-inherited",
                "--output",
                "json",
            )
        )
        if any(
            assignment.get("principalId", "").lower() == principal.lower()
            and assignment.get("roleDefinitionId", "")
            .lower()
            .endswith("/" + role_id.rsplit("/", 1)[-1].lower())
            for assignment in assignments
        ):
            continue
        assignment_name = str(uuid5(NAMESPACE_URL, f"{scope}/{principal}/{role_id}"))
        run_cli(
            "az",
            "role",
            "assignment",
            "create",
            "--assignee-object-id",
            principal,
            "--assignee-principal-type",
            "ServicePrincipal",
            "--role",
            role_id,
            "--scope",
            scope,
            "--name",
            assignment_name,
            "--only-show-errors",
            "--output",
            "none",
        )
        identifier = f"{scope}/providers/Microsoft.Authorization/roleAssignments/{assignment_name}"
        if identifier not in receipt["assignments"]:
            receipt["assignments"].append(identifier)
        RECEIPT.write_text(json.dumps(receipt), encoding="utf-8")
    print("Report Storage roles configured for the deployed agent instance.")


def cleanup() -> None:
    if not RECEIPT.is_file():
        raise ValueError("Report Storage role receipt is missing.")
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    principal = receipt["principal"]
    UUID(principal)
    account_id = receipt["account_id"]
    for identifier in list(receipt["assignments"]):
        if not identifier.startswith(account_id + "/"):
            raise ValueError("Role cleanup escaped its recorded Storage account.")
        UUID(identifier.rsplit("/", 1)[-1])
        scope = identifier.rsplit(
            "/providers/Microsoft.Authorization/roleAssignments/", 1
        )[0]
        assignment = json.loads(
            run_cli(
                "az",
                "role",
                "assignment",
                "list",
                "--scope",
                scope,
                "--query",
                f"[?name=='{identifier.rsplit('/', 1)[-1]}'] | [0]",
                "--output",
                "json",
            )
        )
        if (
            assignment is not None
            and assignment["principalId"].lower() != principal.lower()
        ):
            raise ValueError(
                "Role cleanup principal does not match the deployed agent."
            )
        if assignment is not None:
            run_cli(
                "az",
                "role",
                "assignment",
                "delete",
                "--ids",
                identifier,
                "--output",
                "none",
            )
        receipt["assignments"].remove(identifier)
        RECEIPT.write_text(json.dumps(receipt), encoding="utf-8")
    print(
        "Only report Storage role assignments created by this deployment were removed."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    try:
        cleanup() if args.cleanup else configure()
    except (
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as error:
        detail = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print(
            f"Report Storage authorization failed ({detail}). Check account/container settings "
            "and the deployer's role-assignment permission; no account-key fallback is used.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
