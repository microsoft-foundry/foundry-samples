"""Interim REST calls for AI Gateway resources that the typed SDK doesn't cover yet.

azure-mgmt-aigateway 1.0.0b1 targets API version 2026-09-01-preview, which defines only the gateway resource.
Model providers, models, aliases, and API keys are published in the stable 2026-11-01 API, which doesn't have an
SDK yet. These helpers send those requests through the AI Gateway SDK client's own pipeline with send_request, so
they reuse its credential, retry, and logging policies. Replace them with typed operations when the SDK adds them.
"""

from __future__ import annotations

import time
from typing import Any

from azure.core.exceptions import HttpResponseError
from azure.core.rest import HttpRequest, HttpResponse
from azure.mgmt.aigateway import AIGatewayMgmtClient
from azure.mgmt.core.exceptions import ARMErrorFormat

from common import SAMPLE_MARKER

API_VERSION = "2026-11-01"
POLL_SECONDS = 5
TIMEOUT_SECONDS = 600


def _send(
    client: AIGatewayMgmtClient,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    allow_not_found: bool = False,
) -> HttpResponse:
    response = client.send_request(HttpRequest(method, f"{path}?api-version={API_VERSION}", json=body))
    if response.status_code >= 400 and not (allow_not_found and response.status_code == 404):
        raise HttpResponseError(response=response, error_format=ARMErrorFormat)
    return response


def get(client: AIGatewayMgmtClient, resource_id: str) -> dict[str, Any] | None:
    """Return the resource, or None if it doesn't exist."""
    response = _send(client, "GET", resource_id, allow_not_found=True)
    return None if response.status_code == 404 else response.json()


def is_sample_owned(resource: dict[str, Any]) -> bool:
    properties = resource.get("properties", {})
    return SAMPLE_MARKER in (properties.get("description") or properties.get("displayName") or "")


def _provisioning_state(resource: dict[str, Any] | None) -> str | None:
    if resource is None:
        return None
    # Resources that don't report a provisioning state are ready as soon as they can be read.
    return str(resource.get("properties", {}).get("provisioningState", "Succeeded")).lower()


def create_or_update(client: AIGatewayMgmtClient, resource_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Create or update a resource that this sample owns, then wait until it's provisioned."""
    existing = get(client, resource_id)
    if existing is not None and not is_sample_owned(existing):
        raise SystemExit(f"{resource_id} already exists and wasn't created by this sample. Choose another name.")

    response = _send(client, "PUT", resource_id, body)
    resource = response.json() if response.content else None
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while (state := _provisioning_state(resource)) != "succeeded":
        if state in ("failed", "canceled"):
            raise RuntimeError(f"Provisioning {resource_id} ended in state '{state}'.")
        if time.monotonic() > deadline:
            raise TimeoutError(f"Timed out waiting for {resource_id} to be provisioned.")
        time.sleep(POLL_SECONDS)
        resource = get(client, resource_id)
    return resource


def delete(client: AIGatewayMgmtClient, resource_id: str) -> None:
    """Delete a resource, if it exists, and wait until it's gone."""
    if _send(client, "DELETE", resource_id, allow_not_found=True).status_code == 404:
        return
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while get(client, resource_id) is not None:
        if time.monotonic() > deadline:
            raise TimeoutError(f"Timed out waiting for {resource_id} to be deleted.")
        time.sleep(POLL_SECONDS)


def list_secrets(client: AIGatewayMgmtClient, api_key_id: str) -> dict[str, str]:
    """Return a runtime API key's values. Keep them in memory; never print, log, or save them."""
    return _send(client, "POST", f"{api_key_id}/listSecrets").json()
