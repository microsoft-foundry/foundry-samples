"""Tests for the Python managed-compute preflight logic."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = MODULE_DIR / "managed_compute_preflight.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "managed_compute_preflight",
    MODULE_PATH,
)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load {MODULE_PATH}")
managed_compute_preflight = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(managed_compute_preflight)

PreflightError = managed_compute_preflight.PreflightError
get_preflight_result = managed_compute_preflight.get_preflight_result
resolve_capacity_record = managed_compute_preflight.resolve_capacity_record


def usage_response(
    accelerator_type: str = "A100_80GB",
    current: int = 16,
    limit: int = 24,
    offer_scope: str = "Global",
):
    return {
        "value": [
            {
                "name": {"value": f"ManagedCompute.{offer_scope}.{accelerator_type}"},
                "offerScope": offer_scope,
                "currentValue": current,
                "limit": limit,
                "unit": "AcceleratorCount",
            }
        ]
    }


def capacity_response(
    accelerator_type: str = "A100_80GB",
    available_accelerators: int = 119,
    deployment_sizes=None,
    offer_scope: str = "Global",
    scope_id: str = "",
):
    if deployment_sizes is None:
        deployment_sizes = [
            {
                "modelInstanceAcceleratorCount": 1,
                "totalAvailableCapacity": 119,
                "largestDeploymentCapacity": 119,
            }
        ]
    return {
        "value": [
            {
                "name": f"{accelerator_type}.{offer_scope}",
                "properties": {
                    "acceleratorType": accelerator_type,
                    "availableAccelerators": available_accelerators,
                    "deploymentSizeCapacities": deployment_sizes,
                    "offerScope": offer_scope,
                    "scopeId": scope_id,
                },
            }
        ]
    }


class ManagedComputePreflightTests(unittest.TestCase):
    def test_create_calculates_full_target(self):
        result = get_preflight_result(
            usage_response(),
            capacity_response(),
            "A100_80GB",
            "Global",
            target_capacity=2,
            accelerators_per_instance=1,
        )
        self.assertEqual(result["additionalInstancesRequired"], 2)
        self.assertEqual(result["additionalAcceleratorsRequired"], 2)
        self.assertTrue(result["sufficient"])

    def test_scale_calculates_delta(self):
        result = get_preflight_result(
            usage_response(current=17),
            capacity_response(),
            "A100_80GB",
            "Global",
            target_capacity=2,
            current_capacity=1,
            accelerators_per_instance=1,
        )
        self.assertEqual(result["additionalInstancesRequired"], 1)
        self.assertEqual(result["additionalAcceleratorsRequired"], 1)
        self.assertTrue(result["sufficient"])

    def test_multi_accelerator_size(self):
        sizes = [
            {
                "modelInstanceAcceleratorCount": 1,
                "totalAvailableCapacity": 8,
                "largestDeploymentCapacity": 8,
            },
            {
                "modelInstanceAcceleratorCount": 2,
                "totalAvailableCapacity": 4,
                "largestDeploymentCapacity": 3,
            },
        ]
        result = get_preflight_result(
            usage_response("H100_80GB", current=2, limit=20),
            capacity_response("H100_80GB", 10, sizes),
            "H100_80GB",
            "Global",
            target_capacity=3,
            accelerators_per_instance=2,
        )
        self.assertEqual(result["additionalAcceleratorsRequired"], 6)
        self.assertEqual(result["platformCapacity"]["modelInstanceAcceleratorCount"], 2)
        self.assertTrue(result["sufficient"])

    def test_insufficient_quota(self):
        result = get_preflight_result(
            usage_response(current=23, limit=24),
            capacity_response(),
            "A100_80GB",
            "Global",
            target_capacity=2,
            accelerators_per_instance=1,
        )
        self.assertFalse(result["quota"]["sufficient"])
        self.assertFalse(result["sufficient"])

    def test_insufficient_capacity(self):
        result = get_preflight_result(
            usage_response(),
            capacity_response(available_accelerators=1),
            "A100_80GB",
            "Global",
            target_capacity=2,
            accelerators_per_instance=1,
        )
        self.assertFalse(result["platformCapacity"]["sufficient"])
        self.assertFalse(result["sufficient"])

    def test_scale_down_requires_no_additional_capacity(self):
        result = get_preflight_result(
            usage_response(current=24, limit=24),
            capacity_response(available_accelerators=0),
            "A100_80GB",
            "Global",
            target_capacity=1,
            current_capacity=2,
            accelerators_per_instance=1,
        )
        self.assertEqual(result["additionalAcceleratorsRequired"], 0)
        self.assertTrue(result["sufficient"])

    def test_missing_deployment_size_fails(self):
        with self.assertRaises(PreflightError):
            get_preflight_result(
                usage_response(),
                capacity_response(),
                "A100_80GB",
                "Global",
                target_capacity=1,
                accelerators_per_instance=2,
            )

    def test_ambiguous_capacity_fails(self):
        response = capacity_response()
        response["value"].append(dict(response["value"][0]))
        with self.assertRaises(PreflightError):
            resolve_capacity_record(response, "A100_80GB", "Global")

    def test_legacy_single_record_without_scope_is_accepted(self):
        response = capacity_response()
        response["value"][0]["properties"].pop("offerScope")
        response["value"][0]["properties"].pop("scopeId")
        record = resolve_capacity_record(response, "A100_80GB", "Global")
        self.assertEqual(record["name"], "A100_80GB.Global")

    def test_accelerator_alias_is_disambiguated_by_scope(self):
        sizes = [
            {
                "modelInstanceAcceleratorCount": 1,
                "totalAvailableCapacity": 10,
                "largestDeploymentCapacity": 10,
            }
        ]
        response = {
            "value": [
                {
                    "name": "Azure.A100.Global",
                    "properties": {
                        "acceleratorType": "Azure.A100",
                        "availableAccelerators": 10,
                        "deploymentSizeCapacities": sizes,
                        "offerScope": "Global",
                        "scopeId": "",
                    },
                },
                {
                    "name": "Azure.A100.DataZone.US",
                    "properties": {
                        "acceleratorType": "Azure.A100",
                        "availableAccelerators": 5,
                        "deploymentSizeCapacities": sizes,
                        "offerScope": "DataZone",
                        "scopeId": "US",
                    },
                },
            ]
        }
        record = resolve_capacity_record(response, "A100_80GB", "Global")
        self.assertEqual(record["name"], "Azure.A100.Global")

    def test_data_zone_uses_distinct_quota_scope(self):
        result = get_preflight_result(
            usage_response(offer_scope="Datazone-US"),
            capacity_response(offer_scope="DataZone", scope_id="US"),
            "A100_80GB",
            "DataZone",
            quota_offer_scope="Datazone-US",
            scope_id="US",
            target_capacity=1,
            accelerators_per_instance=1,
        )
        self.assertEqual(result["capacityOfferScope"], "DataZone")
        self.assertEqual(result["quotaOfferScope"], "Datazone-US")
        self.assertTrue(result["sufficient"])


if __name__ == "__main__":
    unittest.main()
