#!/usr/bin/env python3
"""Manage a Microsoft Foundry managed-compute deployment."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
from collections.abc import Sequence
from typing import Any, Optional

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient

API_VERSION = "2026-07-15-preview"
DEFAULT_DEPLOYMENT_NAME_PREFIX = "gemma-4-31b-it-a100"
DEFAULT_MODEL_ID = (
    "azureml://registries/azure-huggingface/models/" "google--gemma-4-31b-it/versions/5"
)
DEFAULT_DEPLOYMENT_TEMPLATE_ID = (
    "azureml://registries/azure-huggingface/deploymenttemplates/"
    "google--gemma-4-31b-it--16k-nvidia-a100/labels/latest"
)
DEFAULT_ACCELERATOR_TYPE = "A100_80GB"
DEFAULT_CAPACITY = 1
SKU_NAME = "GlobalManagedCompute"
DEFAULT_VERSION_UPGRADE_OPTION = "OnceNewDefaultVersionAvailable"
VERSION_UPGRADE_OPTIONS = (
    "NoAutoUpgrade",
    "OnceCurrentVersionExpired",
    "OnceNewDefaultVersionAvailable",
)
DEPLOYMENT_NAME_PATTERN = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,56}-[a-zA-Z0-9]{6}$"
)
ACCOUNT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$")
SUBSCRIPTION_ID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def configuration_default(
    environment_variable: str,
    default: str,
    include_default: bool,
) -> str:
    if include_default:
        return os.getenv(environment_variable, default)
    if environment_variable in os.environ:
        return os.environ[environment_variable]
    return argparse.SUPPRESS


def add_expected_configuration_arguments(
    parser: argparse.ArgumentParser,
    *,
    include_defaults: bool,
) -> None:
    parser.add_argument(
        "--model-id",
        default=configuration_default("MODEL_ID", DEFAULT_MODEL_ID, include_defaults),
        help="Foundry catalog model asset ID.",
    )
    parser.add_argument(
        "--deployment-template-id",
        default=configuration_default(
            "DEPLOYMENT_TEMPLATE_ID",
            DEFAULT_DEPLOYMENT_TEMPLATE_ID,
            include_defaults,
        ),
        help="Foundry catalog deployment-template asset ID.",
    )
    parser.add_argument(
        "--accelerator-type",
        default=configuration_default(
            "ACCELERATOR_TYPE",
            DEFAULT_ACCELERATOR_TYPE,
            include_defaults,
        ),
        choices=("A100_80GB",),
        help="Managed-compute accelerator family.",
    )
    parser.add_argument(
        "--version-upgrade-option",
        default=configuration_default(
            "VERSION_UPGRADE_OPTION",
            DEFAULT_VERSION_UPGRADE_OPTION,
            include_defaults,
        ),
        choices=VERSION_UPGRADE_OPTIONS,
        help="Deployment-template upgrade policy.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage a Microsoft Foundry managed-compute deployment."
    )
    parser.add_argument(
        "--subscription-id",
        default=os.getenv("AZURE_SUBSCRIPTION_ID"),
        help="Azure subscription ID (or set AZURE_SUBSCRIPTION_ID).",
    )
    parser.add_argument(
        "--resource-group",
        default=os.getenv("RESOURCE_GROUP"),
        help="Resource group containing the Foundry account (or set RESOURCE_GROUP).",
    )
    parser.add_argument(
        "--account-name",
        default=os.getenv("FOUNDRY_ACCOUNT_NAME"),
        help="Existing Foundry AIServices account name (or set FOUNDRY_ACCOUNT_NAME).",
    )
    parser.add_argument(
        "--deployment-name",
        default=os.getenv("DEPLOYMENT_NAME"),
        help=(
            "Managed-compute deployment name. Create generates a six-character "
            "alphanumeric suffix when omitted."
        ),
    )

    subparsers = parser.add_subparsers(dest="action", required=True)

    create_parser = subparsers.add_parser(
        "create", help="Create the deployment and verify its final state."
    )
    add_expected_configuration_arguments(create_parser, include_defaults=True)
    create_parser.add_argument(
        "--capacity",
        type=positive_integer,
        default=os.getenv("CAPACITY", str(DEFAULT_CAPACITY)),
        help="Number of model instances.",
    )

    subparsers.add_parser("show", help="Show one deployment.")
    subparsers.add_parser("list", help="List deployments under the Foundry account.")

    scale_parser = subparsers.add_parser(
        "scale", help="Change only SKU capacity and verify the final state."
    )
    add_expected_configuration_arguments(scale_parser, include_defaults=False)
    scale_parser.add_argument(
        "--capacity",
        type=positive_integer,
        default=os.getenv("CAPACITY", str(DEFAULT_CAPACITY)),
        help="Target number of model instances.",
    )

    subparsers.add_parser("delete", help="Delete the deployment.")
    return parser


def validate_arguments(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> None:
    if not args.subscription_id:
        parser.error("set --subscription-id or AZURE_SUBSCRIPTION_ID")
    if not SUBSCRIPTION_ID_PATTERN.fullmatch(args.subscription_id):
        parser.error("subscription ID must be a UUID")
    if not args.resource_group:
        parser.error("set --resource-group or RESOURCE_GROUP")
    if not args.account_name:
        parser.error("set --account-name or FOUNDRY_ACCOUNT_NAME")
    if not ACCOUNT_NAME_PATTERN.fullmatch(args.account_name):
        parser.error(
            "account name must be 2-64 characters and contain only letters, "
            "numbers, periods, underscores, and hyphens"
        )
    if args.action == "create" and not args.deployment_name:
        args.deployment_name = (
            f"{DEFAULT_DEPLOYMENT_NAME_PREFIX}-{secrets.token_hex(3)}"
        )
        print(f"Generated deployment name: {args.deployment_name}", file=sys.stderr)
    elif args.action != "list" and not args.deployment_name:
        parser.error(
            "set --deployment-name or DEPLOYMENT_NAME to the suffixed name "
            "returned by create"
        )
    if args.action != "list" and not DEPLOYMENT_NAME_PATTERN.fullmatch(
        args.deployment_name
    ):
        parser.error(
            "deployment name must end in a six-character alphanumeric suffix "
            "and be at most 64 characters"
        )


def deployment_summary(deployment: Any) -> dict[str, Any]:
    return {
        "id": deployment.id,
        "name": deployment.name,
        "provisioningState": deployment.properties.provisioning_state,
        "model": deployment.properties.model,
        "deploymentTemplate": deployment.properties.deployment_template,
        "acceleratorType": deployment.properties.accelerator_type,
        "versionUpgradeOption": deployment.properties.version_upgrade_option,
        "sku": {
            "name": deployment.sku.name,
            "capacity": deployment.sku.capacity,
        },
    }


def immutable_configuration(deployment: Any) -> dict[str, Any]:
    return {
        "model": deployment.properties.model,
        "deploymentTemplate": deployment.properties.deployment_template,
        "acceleratorType": deployment.properties.accelerator_type,
        "versionUpgradeOption": deployment.properties.version_upgrade_option,
        "computeId": getattr(deployment.properties, "compute_id", None),
        "priority": getattr(deployment.properties, "priority", None),
    }


def verify_deployment(
    deployment: Any,
    *,
    model_id: str,
    deployment_template_id: str,
    accelerator_type: str,
    capacity: int,
    version_upgrade_option: str,
) -> None:
    actual = deployment_summary(deployment)
    expected = {
        "provisioningState": "Succeeded",
        "model": model_id,
        "deploymentTemplate": deployment_template_id,
        "acceleratorType": accelerator_type,
        "versionUpgradeOption": version_upgrade_option,
        "sku": {"name": SKU_NAME, "capacity": capacity},
    }
    mismatches = {
        field: {"expected": expected[field], "actual": actual[field]}
        for field in expected
        if actual[field] != expected[field]
    }
    if mismatches:
        raise RuntimeError(
            "Deployment verification failed:\n"
            + json.dumps(mismatches, indent=2, sort_keys=True)
        )


def verify_scale_source(deployment: Any, args: argparse.Namespace) -> None:
    mismatches: dict[str, dict[str, Any]] = {}
    if deployment.properties.provisioning_state != "Succeeded":
        mismatches["provisioningState"] = {
            "expected": "Succeeded",
            "actual": deployment.properties.provisioning_state,
        }
    if deployment.sku.name != SKU_NAME:
        mismatches["sku.name"] = {
            "expected": SKU_NAME,
            "actual": deployment.sku.name,
        }

    expectations = (
        ("model_id", "model", deployment.properties.model),
        (
            "deployment_template_id",
            "deploymentTemplate",
            deployment.properties.deployment_template,
        ),
        (
            "accelerator_type",
            "acceleratorType",
            deployment.properties.accelerator_type,
        ),
        (
            "version_upgrade_option",
            "versionUpgradeOption",
            deployment.properties.version_upgrade_option,
        ),
    )
    for argument_name, property_name, actual in expectations:
        if hasattr(args, argument_name):
            expected = getattr(args, argument_name)
            if actual != expected:
                mismatches[property_name] = {
                    "expected": expected,
                    "actual": actual,
                }

    if mismatches:
        raise RuntimeError(
            "Deployment cannot be scaled because it isn't healthy or doesn't "
            "match explicitly supplied expectations:\n"
            + json.dumps(mismatches, indent=2, sort_keys=True)
        )


def verify_scaled_deployment(
    deployment: Any,
    capacity: int,
    immutable_before: dict[str, Any],
) -> None:
    actual = deployment_summary(deployment)
    mismatches: dict[str, dict[str, Any]] = {}
    expected_fields = {
        "provisioningState": "Succeeded",
        "sku": {"name": SKU_NAME, "capacity": capacity},
    }
    for field, expected in expected_fields.items():
        if actual[field] != expected:
            mismatches[field] = {"expected": expected, "actual": actual[field]}

    immutable_after = immutable_configuration(deployment)
    if immutable_after != immutable_before:
        mismatches["immutableConfiguration"] = {
            "expected": immutable_before,
            "actual": immutable_after,
        }

    if mismatches:
        raise RuntimeError(
            "Scaled deployment verification failed:\n"
            + json.dumps(mismatches, indent=2, sort_keys=True)
        )


def get_deployment(
    client: CognitiveServicesManagementClient, args: argparse.Namespace
) -> Any:
    return client.managed_compute_deployments.get(
        resource_group_name=args.resource_group,
        account_name=args.account_name,
        deployment_name=args.deployment_name,
    )


def create_deployment(
    client: CognitiveServicesManagementClient, args: argparse.Namespace
) -> None:
    client.managed_compute_deployments.begin_create_or_update(
        resource_group_name=args.resource_group,
        account_name=args.account_name,
        deployment_name=args.deployment_name,
        resource={
            "sku": {"name": SKU_NAME, "capacity": args.capacity},
            "properties": {
                "model": args.model_id,
                "deploymentTemplate": args.deployment_template_id,
                "acceleratorType": args.accelerator_type,
                "versionUpgradeOption": args.version_upgrade_option,
            },
        },
    ).result()
    deployment = get_deployment(client, args)
    verify_deployment(
        deployment,
        model_id=args.model_id,
        deployment_template_id=args.deployment_template_id,
        accelerator_type=args.accelerator_type,
        capacity=args.capacity,
        version_upgrade_option=args.version_upgrade_option,
    )
    print(json.dumps(deployment_summary(deployment), indent=2))


def show_deployment(
    client: CognitiveServicesManagementClient, args: argparse.Namespace
) -> None:
    print(json.dumps(deployment_summary(get_deployment(client, args)), indent=2))


def list_deployments(
    client: CognitiveServicesManagementClient, args: argparse.Namespace
) -> None:
    deployments = client.managed_compute_deployments.list(
        resource_group_name=args.resource_group,
        account_name=args.account_name,
    )
    print(
        json.dumps(
            [deployment_summary(deployment) for deployment in deployments], indent=2
        )
    )


def scale_deployment(
    client: CognitiveServicesManagementClient, args: argparse.Namespace
) -> None:
    current = get_deployment(client, args)
    verify_scale_source(current, args)
    immutable_before = immutable_configuration(current)
    client.managed_compute_deployments.begin_update(
        resource_group_name=args.resource_group,
        account_name=args.account_name,
        deployment_name=args.deployment_name,
        properties={"sku": {"name": SKU_NAME, "capacity": args.capacity}},
    ).result()
    deployment = get_deployment(client, args)
    verify_scaled_deployment(deployment, args.capacity, immutable_before)
    print(json.dumps(deployment_summary(deployment), indent=2))


def delete_deployment(
    client: CognitiveServicesManagementClient, args: argparse.Namespace
) -> None:
    client.managed_compute_deployments.begin_delete(
        resource_group_name=args.resource_group,
        account_name=args.account_name,
        deployment_name=args.deployment_name,
    ).result()
    try:
        get_deployment(client, args)
    except ResourceNotFoundError:
        print(f"Deleted managed-compute deployment {args.deployment_name}.")
        return
    raise RuntimeError(
        f"Deployment {args.deployment_name} still exists after delete completed."
    )


def run(client: CognitiveServicesManagementClient, args: argparse.Namespace) -> None:
    actions = {
        "create": create_deployment,
        "show": show_deployment,
        "list": list_deployments,
        "scale": scale_deployment,
        "delete": delete_deployment,
    }
    actions[args.action](client, args)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_arguments(parser, args)

    credential = DefaultAzureCredential()
    client: Optional[CognitiveServicesManagementClient] = None
    try:
        client = CognitiveServicesManagementClient(
            credential=credential,
            subscription_id=args.subscription_id,
            api_version=API_VERSION,
        )
        run(client, args)
    finally:
        if client is not None:
            client.close()
        credential.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
