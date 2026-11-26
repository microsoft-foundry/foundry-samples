"""Step 3: Give a Foundry project keyless access to the gateway's models.

1. Grants the project's managed identity the AI Gateway Models User role on the gateway's default workspace.
2. Creates a project connection that signs in to the gateway with the project's managed identity.

Agents in the project can then use the alias as <connection-name>/<alias>. No gateway key is stored in Foundry.
"""

import json

from azure.core.exceptions import ResourceNotFoundError

from common import (
    AI_GATEWAY_MODELS_USER_ROLE_ID,
    CONNECTION_MARKER,
    authorization_client,
    credential,
    foundry_client,
    gateway_client,
    get_gateway,
    grant_role,
    is_sample_connection,
    runtime_base_url,
    setting,
)

GATEWAY_AUDIENCE = "https://azure-api.net/aigateway"


def main() -> None:
    cred = credential()
    gateway = get_gateway(gateway_client(cred))

    resource_group = setting("FOUNDRY_RESOURCE_GROUP")
    account_name = setting("FOUNDRY_ACCOUNT_NAME")
    project_name = setting("FOUNDRY_PROJECT_NAME")
    connection_name = setting("AI_GATEWAY_CONNECTION_NAME", "ai-gateway")
    deployment_name = setting("FOUNDRY_MODEL_DEPLOYMENT")
    alias = setting("AI_GATEWAY_ALIAS", deployment_name)

    foundry = foundry_client(cred)
    project = foundry.projects.get(resource_group, account_name, project_name)
    if project.identity is None or not project.identity.principal_id:
        raise SystemExit(f"Project '{project_name}' has no system-assigned managed identity.")
    model = foundry.deployments.get(resource_group, account_name, deployment_name).properties.model

    grant_role(
        authorization_client(cred),
        scope=f"{gateway.id}/workspaces/default",
        principal_id=project.identity.principal_id,
        role_id=AI_GATEWAY_MODELS_USER_ROLE_ID,
        label=f"AI Gateway Models User to project '{project_name}'",
    )

    target = runtime_base_url(gateway)
    try:
        existing = foundry.project_connections.get(resource_group, account_name, project_name, connection_name)
        if not is_sample_connection(existing, gateway):
            raise SystemExit(
                f"Connection '{connection_name}' already exists and this sample didn't create it for this gateway. "
                "Choose another name."
            )
    except ResourceNotFoundError:
        pass

    gateway_url = f"https://{gateway.properties.frontend.default_hostname}"
    # azure-mgmt-cognitiveservices 15.0.0 has no typed model for connections that sign in with the project's
    # managed identity, or for their audience, so the body is passed as JSON. The typed operation sends it unchanged.
    connection = {
        "properties": {
            "category": "ApiManagement",
            "target": target,
            "authType": "ProjectManagedIdentity",
            "audience": GATEWAY_AUDIENCE,
            "isSharedToAll": False,
            "metadata": {
                "apimResourceKind": "AiGateway",
                "apimResource": json.dumps(
                    {
                        "id": gateway.id,
                        "name": gateway.name,
                        "gatewayUrl": gateway_url,
                        "location": gateway.location,
                        "subscriptionId": setting("AZURE_SUBSCRIPTION_ID"),
                        "resourceGroup": setting("AI_GATEWAY_RESOURCE_GROUP"),
                    }
                ),
                "deploymentInPath": "false",
                "inferenceAPIVersion": "",
                **CONNECTION_MARKER,
                "models": json.dumps(
                    [
                        {
                            "name": alias,
                            "properties": {
                                "model": {"name": model.name, "version": model.version, "format": model.format}
                            },
                        }
                    ]
                ),
            },
        }
    }
    foundry.project_connections.create(resource_group, account_name, project_name, connection_name, connection)
    print(f"Connection '{connection_name}' is ready.")

    print(f"Agents in project '{project_name}' can use model '{connection_name}/{alias}'.")


if __name__ == "__main__":
    main()
