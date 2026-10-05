#!/usr/bin/env python3
"""Check managed-compute accelerator quota and platform capacity."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections.abc import Sequence
from typing import Any, Optional
from urllib.parse import quote

from managed_compute_preflight import (
    PreflightError,
    get_preflight_result,
    is_not_found_error,
)

API_VERSION = "2026-07-15-preview"
MANAGEMENT_ENDPOINT = "https://management.azure.com"
ACCOUNT_ID_PATTERN = re.compile(
    r"^/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/"
    r"Microsoft\.CognitiveServices/accounts/([^/]+)$",
    re.IGNORECASE,
)
TRANSIENT_PATTERN = re.compile(
    r"connection reset|connection aborted|temporarily unavailable|"
    r"too many requests|\b429\b|\b5\d\d\b",
    re.IGNORECASE,
)


class AzureCliError(PreflightError):
    """Raised when Azure CLI returns an error."""


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def non_negative_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value cannot be negative")
    return parsed


def invoke_az_json(arguments: Sequence[str]) -> dict[str, Any]:
    """Run Azure CLI with bounded retries for recognized transient failures."""

    for attempt in range(1, 4):
        try:
            completed = subprocess.run(
                ["az", *arguments],
                capture_output=True,
                check=False,
                text=True,
            )
        except FileNotFoundError as exc:
            raise AzureCliError(
                "Azure CLI wasn't found. Install Azure CLI and run 'az login'."
            ) from exc

        if completed.returncode == 0:
            try:
                result = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                raise AzureCliError("Azure CLI returned invalid JSON output.") from exc
            if not isinstance(result, dict):
                raise AzureCliError("Azure CLI returned a non-object JSON response.")
            return result

        details = completed.stderr.strip() or completed.stdout.strip()
        if not TRANSIENT_PATTERN.search(details) or attempt == 3:
            raise AzureCliError(f"Azure CLI failed: {details}")
        time.sleep(2 ** (attempt - 1))

    raise AzureCliError("Azure CLI failed after retrying.")


def resolve_capacity_offer_scope(
    requested_offer_scope: str,
    sku_name: str,
) -> str:
    if requested_offer_scope:
        return requested_offer_scope
    if sku_name == "GlobalManagedCompute":
        return "Global"
    raise PreflightError(
        f"No offer-scope mapping is defined for SKU '{sku_name}'. "
        "Supply --offer-scope explicitly."
    )


def resolve_quota_offer_scope(
    requested_quota_offer_scope: str,
    capacity_offer_scope: str,
    scope_id: str,
) -> str:
    if requested_quota_offer_scope:
        return requested_quota_offer_scope
    if capacity_offer_scope.casefold() == "global":
        return "Global"
    if capacity_offer_scope.casefold() == "datazone" and scope_id:
        return f"Datazone-{scope_id}"
    raise PreflightError(
        "Quota offer scope cannot be derived from capacity offer scope "
        f"'{capacity_offer_scope}' and scope ID '{scope_id}'. "
        "Supply --quota-offer-scope explicitly."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Perform advisory managed-compute accelerator quota and platform-"
            "capacity checks before create or scale."
        )
    )
    parser.add_argument(
        "--account-id",
        required=True,
        help="Full ARM ID of the existing Foundry AIServices account.",
    )
    parser.add_argument(
        "--accelerator-type",
        required=True,
        help="Managed-compute accelerator type, such as A100_80GB.",
    )
    parser.add_argument(
        "--target-capacity",
        required=True,
        type=positive_integer,
        help="Target number of model instances.",
    )
    parser.add_argument(
        "--accelerators-per-instance",
        type=non_negative_integer,
        default=0,
        help=(
            "Accelerators required by one model instance. Required for create; "
            "read from the existing deployment for scale."
        ),
    )
    parser.add_argument(
        "--deployment-id",
        default="",
        help="Existing managed-compute deployment ARM ID for a scale check.",
    )
    parser.add_argument(
        "--sku-name",
        default="GlobalManagedCompute",
        help="Managed-compute SKU name.",
    )
    parser.add_argument(
        "--offer-scope",
        default="",
        help="Capacity offer scope when it cannot be derived from the SKU.",
    )
    parser.add_argument(
        "--scope-id",
        default="",
        help="Optional Data Zone scope ID; empty for Global.",
    )
    parser.add_argument(
        "--quota-offer-scope",
        default="",
        help="Quota offer scope when it differs from the capacity offer scope.",
    )
    parser.add_argument(
        "--offer",
        default="MaaP",
        help="Capacity offer name.",
    )
    parser.add_argument(
        "--output-format",
        choices=("table", "json"),
        default="table",
        help="Output format.",
    )
    parser.add_argument(
        "--require-deployment-region-capacity",
        action="store_true",
        help=(
            "For scale, fail instead of falling back when Azure cannot return "
            "capacity for the deployment's hosting region."
        ),
    )
    return parser


def account_parts(account_id: str) -> Sequence[str]:
    match = ACCOUNT_ID_PATTERN.fullmatch(account_id)
    if not match:
        raise PreflightError(
            "Account ID is not a valid "
            "Microsoft.CognitiveServices/accounts ARM resource ID."
        )
    return match.groups()


def display_table(result: dict[str, Any]) -> None:
    print("Managed-compute preflight (advisory)")
    print(f"Account: {result['accountId']}")
    print(f"Location: {result['accountLocation']}")
    print(f"Accelerator: {result['acceleratorType']}")
    print(f"Capacity offer scope: {result['capacityOfferScope']}")
    print(f"Quota offer scope: {result['quotaOfferScope']}")
    print(f"Instances: {result['currentCapacity']} -> {result['targetCapacity']}")
    print(
        "Additional accelerators required: "
        f"{result['additionalAcceleratorsRequired']}"
    )
    print(f"Capacity lookup: {result['capacityLookup']}")
    print()
    quota = result["quota"]
    print(
        f"Quota: {quota['current']}/{quota['limit']} used; "
        f"{quota['available']} available"
    )
    capacity = result["platformCapacity"]
    print("Platform accelerators available: " f"{capacity['availableAccelerators']}")
    print(
        "Deployment-size instances available: " f"{capacity['totalAvailableCapacity']}"
    )
    print(
        "Largest contiguous deployment capacity: "
        f"{capacity['largestDeploymentCapacity']}"
    )
    print()
    if result["sufficient"]:
        print("[PASS] Quota and platform capacity are sufficient for this request.")
    else:
        for reason in result["failureReasons"]:
            print(f"[FAIL] {reason}")
    for warning in result["warnings"]:
        print(f"[WARN] {warning}", file=sys.stderr)
    print(
        "This check does not reserve quota or capacity; the deployment operation "
        "remains authoritative."
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    subscription_id, resource_group, account_name = account_parts(args.account_id)
    capacity_offer_scope = resolve_capacity_offer_scope(
        args.offer_scope,
        args.sku_name,
    )
    quota_offer_scope = resolve_quota_offer_scope(
        args.quota_offer_scope,
        capacity_offer_scope,
        args.scope_id,
    )

    account = invoke_az_json(
        [
            "cognitiveservices",
            "account",
            "show",
            "--subscription",
            subscription_id,
            "--resource-group",
            resource_group,
            "--name",
            account_name,
            "--only-show-errors",
            "--output",
            "json",
        ]
    )
    if account.get("kind") != "AIServices":
        raise PreflightError(
            f"Account '{account_name}' has kind '{account.get('kind')}', "
            "not AIServices."
        )
    properties = account.get("properties")
    if not isinstance(properties, dict):
        raise PreflightError("Foundry account response has no properties object.")
    if properties.get("provisioningState") != "Succeeded":
        raise PreflightError(
            f"Account '{account_name}' provisioning state is "
            f"'{properties.get('provisioningState')}', not Succeeded."
        )

    current_capacity = 0
    accelerators_per_instance = args.accelerators_per_instance
    if args.deployment_id:
        expected_prefix = f"{args.account_id}/managedComputeDeployments/"
        if not args.deployment_id.casefold().startswith(expected_prefix.casefold()):
            raise PreflightError(
                "Deployment ID must identify a managed-compute deployment "
                "under the account ID."
            )
        deployment_name = args.deployment_id[len(expected_prefix) :]
        if not deployment_name or "/" in deployment_name:
            raise PreflightError("Deployment ID contains unexpected path segments.")

        deployment_url = (
            f"{MANAGEMENT_ENDPOINT}{args.deployment_id}?api-version={API_VERSION}"
        )
        deployment = invoke_az_json(
            [
                "rest",
                "--method",
                "get",
                "--url",
                deployment_url,
                "--only-show-errors",
                "--output",
                "json",
            ]
        )
        deployment_properties = deployment.get("properties")
        deployment_sku = deployment.get("sku")
        if not isinstance(deployment_properties, dict) or not isinstance(
            deployment_sku, dict
        ):
            raise PreflightError(
                "Managed-compute deployment response is missing properties or SKU."
            )
        if deployment_properties.get("acceleratorType") != args.accelerator_type:
            raise PreflightError(
                f"Deployment accelerator "
                f"'{deployment_properties.get('acceleratorType')}' does not match "
                f"'{args.accelerator_type}'."
            )
        if deployment_sku.get("name") != args.sku_name:
            raise PreflightError(
                f"Deployment SKU '{deployment_sku.get('name')}' does not match "
                f"'{args.sku_name}'."
            )
        current_capacity = int(deployment_sku["capacity"])
        deployment_accelerators = int(deployment_properties["acceleratorsPerInstance"])
        if (
            accelerators_per_instance > 0
            and accelerators_per_instance != deployment_accelerators
        ):
            raise PreflightError(
                f"Accelerators per instance '{accelerators_per_instance}' "
                f"conflicts with deployment value '{deployment_accelerators}'."
            )
        accelerators_per_instance = deployment_accelerators
    elif accelerators_per_instance < 1:
        raise PreflightError(
            "Accelerators per instance is required and must be at least 1 "
            "for a create check."
        )

    location = str(account.get("location", ""))
    if not location:
        raise PreflightError("Foundry account response has no location.")
    usage_url = (
        f"{MANAGEMENT_ENDPOINT}/subscriptions/{subscription_id}/providers/"
        "Microsoft.CognitiveServices/locations/"
        f"{quote(location, safe='')}/managedComputeUsages"
        f"?api-version={API_VERSION}"
    )
    base_capacity_url = (
        f"{MANAGEMENT_ENDPOINT}/subscriptions/{subscription_id}/providers/"
        "Microsoft.CognitiveServices/managedComputeCapacities"
        f"?api-version={API_VERSION}"
        f"&offer={quote(args.offer, safe='')}"
        f"&acceleratorType={quote(args.accelerator_type, safe='')}"
    )
    capacity_url = base_capacity_url
    capacity_lookup = "bestAvailable"
    warnings: list[str] = []
    if args.deployment_id:
        capacity_url += f"&deploymentId={quote(args.deployment_id, safe='')}"
        capacity_lookup = "deploymentRegion"

    usage_response = invoke_az_json(
        [
            "rest",
            "--method",
            "get",
            "--url",
            usage_url,
            "--only-show-errors",
            "--output",
            "json",
        ]
    )
    try:
        capacity_response = invoke_az_json(
            [
                "rest",
                "--method",
                "get",
                "--url",
                capacity_url,
                "--only-show-errors",
                "--output",
                "json",
            ]
        )
    except AzureCliError as exc:
        if args.deployment_id and is_not_found_error(str(exc)):
            if args.require_deployment_region_capacity:
                raise PreflightError(
                    "Azure could not return capacity for the deployment's "
                    "hosting region and "
                    "--require-deployment-region-capacity was specified."
                ) from exc
            capacity_lookup = "bestAvailableFallback"
            warnings.append(
                "Azure could not return capacity for the deployment's hosting "
                "region. Platform capacity uses the broader "
                f"'{capacity_offer_scope}' offer/scope snapshot."
            )
            capacity_response = invoke_az_json(
                [
                    "rest",
                    "--method",
                    "get",
                    "--url",
                    base_capacity_url,
                    "--only-show-errors",
                    "--output",
                    "json",
                ]
            )
        else:
            raise

    result = get_preflight_result(
        usage_response=usage_response,
        capacity_response=capacity_response,
        accelerator_type=args.accelerator_type,
        capacity_offer_scope=capacity_offer_scope,
        quota_offer_scope=quota_offer_scope,
        scope_id=args.scope_id,
        target_capacity=args.target_capacity,
        current_capacity=current_capacity,
        accelerators_per_instance=accelerators_per_instance,
    )
    return {
        "accountId": args.account_id,
        "accountLocation": location,
        "deploymentId": args.deployment_id,
        "skuName": args.sku_name,
        "offer": args.offer,
        "capacityLookup": capacity_lookup,
        **result,
        "warnings": warnings,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run(args)
    except (AzureCliError, PreflightError, KeyError, TypeError, ValueError) as exc:
        print(f"Managed-compute preflight failed: {exc}", file=sys.stderr)
        return 2

    if args.output_format == "json":
        print(json.dumps(result, indent=2))
    else:
        display_table(result)
    return 0 if result["sufficient"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
