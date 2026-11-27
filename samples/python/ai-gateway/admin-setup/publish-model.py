"""Step 2: Publish an existing Foundry model deployment through the gateway.

1. Grants the gateway's managed identity the Foundry User role on the Foundry account.
2. Registers the account as a model provider that signs in with that identity.
3. Registers the deployment as a backend model.
4. Publishes a callable alias that applies a per-caller token limit.

Step 1 uses the typed authorization SDK. The typed AI Gateway SDK doesn't cover steps 2-4 yet, so they use the
interim helpers in gateway_rest.py.
"""

import gateway_rest
from common import (
    FOUNDRY_USER_ROLE_ID,
    SAMPLE_DESCRIPTION,
    arm_name,
    authorization_client,
    credential,
    foundry_client,
    gateway_client,
    get_gateway,
    grant_role,
    runtime_base_url,
    setting,
)


def main() -> None:
    cred = credential()
    gateways = gateway_client(cred)
    gateway = get_gateway(gateways)

    resource_group = setting("FOUNDRY_RESOURCE_GROUP")
    account_name = setting("FOUNDRY_ACCOUNT_NAME")
    deployment_name = setting("FOUNDRY_MODEL_DEPLOYMENT")
    alias = setting("AI_GATEWAY_ALIAS", deployment_name)
    tokens_per_minute = int(setting("AI_GATEWAY_TOKENS_PER_MINUTE", "10000"))

    foundry = foundry_client(cred)
    account = foundry.accounts.get(resource_group, account_name)
    deployment = foundry.deployments.get(resource_group, account_name, deployment_name)

    grant_role(
        authorization_client(cred),
        scope=account.id,
        principal_id=gateway.identity.principal_id,
        role_id=FOUNDRY_USER_ROLE_ID,
        label=f"Foundry User on '{account_name}' to the gateway identity",
    )

    workspace_id = f"{gateway.id}/workspaces/default"
    provider_id = f"{workspace_id}/modelProviders/{arm_name(account_name)}"
    endpoint = account.properties.endpoint
    gateway_rest.create_or_update(
        gateways,
        provider_id,
        {
            "properties": {
                "modelProviderType": "Foundry",
                "displayName": account_name,
                "description": SAMPLE_DESCRIPTION,
                "foundry": {
                    "endpoint": {"url": endpoint if endpoint.endswith("/") else f"{endpoint}/"},
                    "resourceIds": [account.id],
                },
                # The gateway calls Foundry with its managed identity, so no Foundry key is stored in the gateway.
                "authentication": {"managedIdentity": {"resource": "https://cognitiveservices.azure.com/"}},
            }
        },
    )
    print(f"Model provider '{arm_name(account_name)}' is ready.")

    model_id = f"{provider_id}/models/{arm_name(deployment_name)}"
    gateway_rest.create_or_update(
        gateways,
        model_id,
        {
            "properties": {
                "displayName": deployment_name,
                "description": SAMPLE_DESCRIPTION,
                "deployment": {
                    "resourceId": deployment.id,
                    # Foundry expects the deployment name in the upstream request's model field.
                    "modelName": deployment_name,
                    "modelVersion": deployment.properties.model.version,
                },
                "supportedEndpoints": ["/openai/v1/chat/completions", "/openai/v1/responses"],
            }
        },
    )
    print(f"Model registration '{arm_name(deployment_name)}' is ready.")

    alias_id = f"{workspace_id}/aliases/{arm_name(alias)}"
    gateway_rest.create_or_update(
        gateways,
        alias_id,
        {
            "properties": {
                "aliasName": alias,
                "description": SAMPLE_DESCRIPTION,
                "backendModels": [{"resourceId": model_id}],
                # Each caller identity can use up to this many tokens per minute through the alias.
                "policies": [
                    {"type": "tokenLimit", "period": "minute", "count": tokens_per_minute, "counterKey": ["identity"]}
                ],
            }
        },
    )
    print(f"Alias '{alias}' is ready, limited to {tokens_per_minute} tokens per minute per caller.")

    print(f"Runtime base URL: {runtime_base_url(gateway)}")
    print(f"Callers send model '{alias}'. Next: run connect-foundry-project.py or create-api-key.py.")


if __name__ == "__main__":
    main()
