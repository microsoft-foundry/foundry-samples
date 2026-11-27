"""Step 1: Create an AI Gateway with the typed management SDK.

Creates a Microsoft.ApiManagement/aigateways resource with a system-assigned managed identity. The SKU is
omitted, so the service applies its default. If the gateway already exists, the script leaves it unchanged.
"""

from azure.core.exceptions import ResourceNotFoundError
from azure.mgmt.aigateway import models

from common import SAMPLE_TAGS, credential, gateway_client, runtime_base_url, setting


def main() -> None:
    resource_group = setting("AI_GATEWAY_RESOURCE_GROUP")
    name = setting("AI_GATEWAY_NAME")
    client = gateway_client(credential())

    try:
        gateway = client.ai_gateway_resources.get(resource_group, name)
        print(f"Gateway '{name}' already exists. Leaving it unchanged.")
    except ResourceNotFoundError:
        location = setting("AI_GATEWAY_LOCATION")
        print(f"Creating gateway '{name}' in {location}. This can take several minutes...")
        gateway = client.ai_gateway_resources.begin_create_or_update(
            resource_group,
            name,
            models.AiGatewayResource(
                location=location,
                tags=SAMPLE_TAGS,
                identity=models.ManagedServiceIdentity(type=models.ManagedServiceIdentityType.SYSTEM_ASSIGNED),
                properties=models.AiGatewayProperties(),
            ),
        ).result()

    if gateway.identity is None or not gateway.identity.principal_id:
        raise SystemExit(f"Gateway '{name}' has no system-assigned managed identity. Enable one, then continue.")

    state = gateway.properties.provisioning_state
    print(f"Gateway ID:         {gateway.id}")
    print(f"Provisioning state: {getattr(state, 'value', state)}")
    print(f"Managed identity:   {gateway.identity.principal_id}")
    print(f"Runtime base URL:   {runtime_base_url(gateway)}")
    print("Next: run publish-model.py.")


if __name__ == "__main__":
    main()
