"""Shared settings, clients, and helpers for the AI Gateway admin-setup scripts."""

from __future__ import annotations

import os
import re
import sys
import uuid
from pathlib import Path

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.mgmt.aigateway import AIGatewayMgmtClient
from azure.mgmt.aigateway.models import AiGatewayResource
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.authorization.models import RoleAssignmentCreateParameters
from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
from dotenv import load_dotenv

# Values already set in the environment take precedence over .env.
load_dotenv(Path(__file__).with_name(".env"), override=False)

# Reruns update, and cleanup deletes, only resources that carry these markers.
SAMPLE_MARKER = "AI Gateway admin-setup sample"
SAMPLE_DESCRIPTION = f"Created by the {SAMPLE_MARKER}."
SAMPLE_TAGS = {"created-by": "foundry-samples-ai-gateway-admin-setup"}

# Built-in role definition IDs.
FOUNDRY_USER_ROLE_ID = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
AI_GATEWAY_MODELS_USER_ROLE_ID = "a6b68e3d-a1f0-4c60-8678-237c050cf4ea"


def setting(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, "").strip() or default
    if not value:
        sys.exit(f"Set {name} in .env or in your environment. See .env.example.")
    return value


def optional_setting(name: str) -> str | None:
    return os.environ.get(name, "").strip() or None


def arm_name(value: str) -> str:
    """Convert a name to the lowercase letters, digits, and hyphens that gateway child resources allow."""
    name = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9-]", "-", value.lower())).strip("-")
    if not name:
        sys.exit(f"Can't derive a resource name from {value!r}.")
    return name


def credential() -> DefaultAzureCredential:
    return DefaultAzureCredential()


def gateway_client(cred: DefaultAzureCredential) -> AIGatewayMgmtClient:
    return AIGatewayMgmtClient(cred, setting("AZURE_SUBSCRIPTION_ID"))


def foundry_client(cred: DefaultAzureCredential) -> CognitiveServicesManagementClient:
    return CognitiveServicesManagementClient(cred, setting("AZURE_SUBSCRIPTION_ID"))


def authorization_client(cred: DefaultAzureCredential) -> AuthorizationManagementClient:
    return AuthorizationManagementClient(cred, setting("AZURE_SUBSCRIPTION_ID"))


def get_gateway(client: AIGatewayMgmtClient) -> AiGatewayResource:
    name = setting("AI_GATEWAY_NAME")
    try:
        gateway = client.ai_gateway_resources.get(setting("AI_GATEWAY_RESOURCE_GROUP"), name)
    except ResourceNotFoundError:
        sys.exit(f"Gateway '{name}' wasn't found. Run create-gateway.py first.")
    if gateway.identity is None or not gateway.identity.principal_id:
        sys.exit(f"Gateway '{name}' has no system-assigned managed identity.")
    return gateway


def runtime_base_url(gateway: AiGatewayResource) -> str:
    # Use the hostname the service assigned; don't build it from the gateway name.
    return f"https://{gateway.properties.frontend.default_hostname}/default/models/openai/v1"


def role_assignment_name(scope: str, principal_id: str, role_id: str) -> str:
    # A deterministic name lets reruns reuse the assignment and lets cleanup find it.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{scope.lower()}|{principal_id}|{role_id}"))


def grant_role(
    client: AuthorizationManagementClient, scope: str, principal_id: str, role_id: str, label: str
) -> None:
    # Check first, so reruns don't need permission to write role assignments once the role is granted.
    for assignment in client.role_assignments.list_for_scope(scope, filter=f"principalId eq '{principal_id}'"):
        inherited_or_same = f"{scope.lower()}/".startswith(f"{assignment.scope.lower().rstrip('/')}/")
        if inherited_or_same and assignment.role_definition_id.lower().endswith(role_id):
            print(f"{label} was already granted.")
            return

    subscription_id = setting("AZURE_SUBSCRIPTION_ID")
    parameters = RoleAssignmentCreateParameters(
        role_definition_id=f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization/roleDefinitions/{role_id}",
        principal_id=principal_id,
        # Skips a directory lookup that can fail for a managed identity created moments ago.
        principal_type="ServicePrincipal",
    )
    try:
        client.role_assignments.create(scope, role_assignment_name(scope, principal_id, role_id), parameters)
        print(f"Granted {label}.")
    except ResourceExistsError:
        print(f"{label} was already granted.")


def revoke_role(
    client: AuthorizationManagementClient, scope: str, principal_id: str, role_id: str, label: str
) -> None:
    name = role_assignment_name(scope, principal_id, role_id)
    try:
        client.role_assignments.get(scope, name)
    except ResourceNotFoundError:
        print(f"Skipped {label}: this sample didn't grant it.")
        return
    client.role_assignments.delete(scope, name)
    print(f"Removed {label}.")
