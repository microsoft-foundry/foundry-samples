"""Generic managed-compute quota and platform-capacity matching."""

from __future__ import annotations

import re
from typing import Any, Optional

NOT_FOUND_PATTERN = re.compile(r"not[\s_-]*found|\b404\b", re.IGNORECASE)


class PreflightError(RuntimeError):
    """Raised when a response cannot be matched unambiguously."""


def is_not_found_error(message: str) -> bool:
    """Return whether an Azure error represents HTTP/resource not found."""

    return bool(NOT_FOUND_PATTERN.search(message))


def _records(response: dict[str, Any], response_name: str) -> list[dict[str, Any]]:
    values = response.get("value")
    if not isinstance(values, list):
        raise PreflightError(f"{response_name} response doesn't contain a value array.")
    if not all(isinstance(value, dict) for value in values):
        raise PreflightError(f"{response_name} response contains a non-object value.")
    return values


def resolve_quota_record(
    usage_response: dict[str, Any],
    accelerator_type: str,
    offer_scope: str,
) -> dict[str, Any]:
    """Return the one quota record matching accelerator, scope, and unit."""

    suffix = f".{accelerator_type}".casefold()
    matches: list[dict[str, Any]] = []
    for record in _records(usage_response, "Usage"):
        name = record.get("name")
        metric_name = name.get("value") if isinstance(name, dict) else None
        if (
            isinstance(metric_name, str)
            and metric_name.casefold().endswith(suffix)
            and str(record.get("offerScope", "")).casefold() == offer_scope.casefold()
            and record.get("unit") == "AcceleratorCount"
        ):
            matches.append(record)

    if not matches:
        raise PreflightError(
            f"No quota record matched accelerator '{accelerator_type}' "
            f"and offer scope '{offer_scope}'."
        )
    if len(matches) > 1:
        names = ", ".join(str(record["name"]["value"]) for record in matches)
        raise PreflightError(
            f"Multiple quota records matched accelerator '{accelerator_type}' "
            f"and offer scope '{offer_scope}': {names}."
        )
    return matches[0]


def resolve_capacity_record(
    capacity_response: dict[str, Any],
    accelerator_type: str,
    offer_scope: str,
    scope_id: str = "",
) -> dict[str, Any]:
    """Return the one capacity record matching accelerator and offer scope."""

    values = _records(capacity_response, "Capacity")
    typed_records: list[tuple[dict[str, Any], str]] = []
    for record in values:
        properties = record.get("properties")
        if not isinstance(properties, dict):
            continue
        returned_accelerator = properties.get("acceleratorType")
        if returned_accelerator is None or not str(returned_accelerator).strip():
            continue
        typed_records.append((record, str(returned_accelerator)))

    accelerator_matches = [
        record
        for record, returned_accelerator in typed_records
        if returned_accelerator.casefold() == accelerator_type.casefold()
    ]
    if not accelerator_matches:
        if not values:
            raise PreflightError(
                f"No capacity records were returned for accelerator '{accelerator_type}'."
            )
        distinct_returned_types: dict[str, str] = {}
        for _, returned_accelerator in typed_records:
            distinct_returned_types.setdefault(
                returned_accelerator.casefold(),
                returned_accelerator,
            )
        if len(distinct_returned_types) > 1:
            returned_types = ", ".join(
                sorted(distinct_returned_types.values(), key=str.casefold)
            )
            raise PreflightError(
                f"No capacity record matched accelerator '{accelerator_type}'. "
                f"Returned accelerator types: {returned_types}."
            )
        accelerator_matches = (
            [record for record, _ in typed_records] if typed_records else values
        )

    scope_matches = [
        record
        for record in accelerator_matches
        if isinstance(record.get("properties"), dict)
        and str(record["properties"].get("offerScope", "")).casefold()
        == offer_scope.casefold()
    ]
    if not scope_matches:
        records_without_scope = [
            record
            for record in accelerator_matches
            if isinstance(record.get("properties"), dict)
            and not record["properties"].get("offerScope")
        ]
        if len(accelerator_matches) == 1 and len(records_without_scope) == 1:
            scope_matches = records_without_scope
        else:
            raise PreflightError(
                f"No unambiguous capacity record matched offer scope '{offer_scope}'."
            )

    if scope_id:
        scope_matches = [
            record
            for record in scope_matches
            if str(record["properties"].get("scopeId", "")).casefold()
            == scope_id.casefold()
        ]
    elif offer_scope.casefold() == "global":
        global_matches = [
            record
            for record in scope_matches
            if not record["properties"].get("scopeId")
        ]
        if global_matches:
            scope_matches = global_matches

    if not scope_matches:
        raise PreflightError(
            f"No capacity record matched offer scope '{offer_scope}' "
            f"and scope ID '{scope_id}'."
        )
    if len(scope_matches) > 1:
        names = ", ".join(str(record.get("name", "")) for record in scope_matches)
        raise PreflightError(
            f"Multiple capacity records matched accelerator '{accelerator_type}' "
            f"and scope '{offer_scope}': {names}."
        )
    return scope_matches[0]


def resolve_deployment_size(
    capacity_record: dict[str, Any],
    accelerators_per_instance: int,
) -> dict[str, Any]:
    """Return the deployment-size row for the exact accelerator topology."""

    properties = capacity_record.get("properties")
    if not isinstance(properties, dict):
        raise PreflightError("Capacity record doesn't contain a properties object.")
    sizes = properties.get("deploymentSizeCapacities")
    if not isinstance(sizes, list):
        raise PreflightError(
            "Capacity record doesn't contain a deploymentSizeCapacities array."
        )

    matches = [
        size
        for size in sizes
        if isinstance(size, dict)
        and int(size.get("modelInstanceAcceleratorCount", 0))
        == accelerators_per_instance
    ]
    if not matches:
        raise PreflightError(
            "No deployment-size capacity row matched "
            f"{accelerators_per_instance} accelerator(s) per model instance."
        )
    if len(matches) > 1:
        raise PreflightError(
            "Multiple deployment-size capacity rows matched "
            f"{accelerators_per_instance} accelerator(s) per model instance."
        )
    return matches[0]


def get_preflight_result(
    usage_response: dict[str, Any],
    capacity_response: dict[str, Any],
    accelerator_type: str,
    capacity_offer_scope: str,
    target_capacity: int,
    accelerators_per_instance: int,
    current_capacity: int = 0,
    quota_offer_scope: Optional[str] = None,
    scope_id: str = "",
) -> dict[str, Any]:
    """Calculate advisory quota and capacity sufficiency."""

    resolved_quota_scope = quota_offer_scope or capacity_offer_scope
    quota_record = resolve_quota_record(
        usage_response,
        accelerator_type,
        resolved_quota_scope,
    )
    capacity_record = resolve_capacity_record(
        capacity_response,
        accelerator_type,
        capacity_offer_scope,
        scope_id,
    )
    deployment_size = resolve_deployment_size(
        capacity_record,
        accelerators_per_instance,
    )

    additional_instances = max(0, target_capacity - current_capacity)
    additional_accelerators = additional_instances * accelerators_per_instance
    quota_current = int(quota_record["currentValue"])
    quota_limit = int(quota_record["limit"])
    quota_available = max(0, quota_limit - quota_current)
    quota_sufficient = quota_available >= additional_accelerators

    properties = capacity_record["properties"]
    available_accelerators = int(properties["availableAccelerators"])
    total_available_capacity = int(deployment_size["totalAvailableCapacity"])
    largest_deployment_capacity = int(deployment_size["largestDeploymentCapacity"])
    capacity_sufficient = (
        available_accelerators >= additional_accelerators
        and total_available_capacity >= additional_instances
        and largest_deployment_capacity >= additional_instances
    )

    failure_reasons: list[str] = []
    if not quota_sufficient:
        failure_reasons.append(
            f"Quota has {quota_available} accelerator(s) available but "
            f"{additional_accelerators} additional accelerator(s) are required."
        )
    if available_accelerators < additional_accelerators:
        failure_reasons.append(
            f"Platform capacity has {available_accelerators} accelerator(s) "
            f"available but {additional_accelerators} additional accelerator(s) "
            "are required."
        )
    if total_available_capacity < additional_instances:
        failure_reasons.append(
            f"The deployment-size pool has {total_available_capacity} model "
            f"instance(s) available but {additional_instances} additional "
            "instance(s) are required."
        )
    if largest_deployment_capacity < additional_instances:
        failure_reasons.append(
            "The largest contiguous deployment capacity is "
            f"{largest_deployment_capacity} but {additional_instances} additional "
            "instance(s) are required."
        )

    return {
        "acceleratorType": accelerator_type,
        "capacityOfferScope": capacity_offer_scope,
        "quotaOfferScope": resolved_quota_scope,
        "scopeId": scope_id,
        "targetCapacity": target_capacity,
        "currentCapacity": current_capacity,
        "acceleratorsPerInstance": accelerators_per_instance,
        "additionalInstancesRequired": additional_instances,
        "additionalAcceleratorsRequired": additional_accelerators,
        "quota": {
            "metricName": quota_record["name"]["value"],
            "current": quota_current,
            "limit": quota_limit,
            "available": quota_available,
            "sufficient": quota_sufficient,
        },
        "platformCapacity": {
            "resourceName": capacity_record.get("name"),
            "returnedAcceleratorType": properties.get("acceleratorType"),
            "availableAccelerators": available_accelerators,
            "totalAvailableCapacity": total_available_capacity,
            "largestDeploymentCapacity": largest_deployment_capacity,
            "modelInstanceAcceleratorCount": int(
                deployment_size["modelInstanceAcceleratorCount"]
            ),
            "sufficient": capacity_sufficient,
        },
        "sufficient": quota_sufficient and capacity_sufficient,
        "failureReasons": failure_reasons,
        "advisory": True,
    }
