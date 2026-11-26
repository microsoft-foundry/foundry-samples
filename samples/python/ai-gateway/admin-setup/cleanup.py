"""Delete what the admin-setup scripts created, and nothing else.

Removes the project connection if this sample created it for this gateway, the role assignments these scripts granted,
and the runtime key, alias, model registration, and model provider that this sample created. Deletes the gateway itself
only if create-gateway.py created it.
"""

import argparse

from azure.core import MatchConditions
from azure.core.exceptions import ResourceNotFoundError

import gateway_rest
from common import (
    AI_GATEWAY_MODELS_USER_ROLE_ID,
    FOUNDRY_USER_ROLE_ID,
    SAMPLE_TAGS,
    arm_name,
    authorization_client,
    credential,
    foundry_client,
    gateway_client,
    is_sample_connection,
    optional_setting,
    revoke_role,
    setting,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete the resources the admin-setup scripts created.")
    parser.add_argument("--yes", action="store_true", help="Delete without asking for confirmation.")
    args = parser.parse_args()

    cred = credential()
    gateways = gateway_client(cred)
    gateway_resource_group = setting("AI_GATEWAY_RESOURCE_GROUP")
    gateway_name = setting("AI_GATEWAY_NAME")
    try:
        gateway = gateways.ai_gateway_resources.get(gateway_resource_group, gateway_name)
    except ResourceNotFoundError:
        raise SystemExit(f"Gateway '{gateway_name}' wasn't found. Nothing to clean up.")

    resource_group = setting("FOUNDRY_RESOURCE_GROUP")
    account_name = setting("FOUNDRY_ACCOUNT_NAME")
    project_name = optional_setting("FOUNDRY_PROJECT_NAME")
    owns_gateway = all((gateway.tags or {}).get(key) == value for key, value in SAMPLE_TAGS.items())

    print("This deletes:")
    if project_name:
        print(f"- The project connection in '{project_name}', if this sample created it, and the project's gateway role")
    print(f"- The gateway identity's Foundry User role on '{account_name}', if this sample granted it")
    if owns_gateway:
        print(f"- Gateway '{gateway_name}' and everything in it")
    else:
        print(f"- The runtime key, alias, model, and provider that this sample created in gateway '{gateway_name}'")
    if not args.yes and input("Continue? [y/N] ").strip().lower() != "y":
        raise SystemExit("Canceled.")

    foundry = foundry_client(cred)
    authorization = authorization_client(cred)
    workspace_id = f"{gateway.id}/workspaces/default"

    if project_name:
        connection_name = setting("AI_GATEWAY_CONNECTION_NAME", "ai-gateway")
        try:
            connection = foundry.project_connections.get(resource_group, account_name, project_name, connection_name)
            if is_sample_connection(connection, gateway):
                foundry.project_connections.delete(resource_group, account_name, project_name, connection_name)
                print(f"Deleted connection '{connection_name}'.")
            else:
                print(f"Skipped connection '{connection_name}': this sample didn't create it for this gateway.")
        except ResourceNotFoundError:
            print(f"Connection '{connection_name}' wasn't found.")
        project = foundry.projects.get(resource_group, account_name, project_name)
        if project.identity is not None and project.identity.principal_id:
            revoke_role(
                authorization,
                workspace_id,
                project.identity.principal_id,
                AI_GATEWAY_MODELS_USER_ROLE_ID,
                f"AI Gateway Models User from project '{project_name}'",
            )

    account = foundry.accounts.get(resource_group, account_name)
    revoke_role(
        authorization,
        account.id,
        gateway.identity.principal_id,
        FOUNDRY_USER_ROLE_ID,
        f"Foundry User on '{account_name}' from the gateway identity",
    )

    if owns_gateway:
        print(f"Deleting gateway '{gateway_name}'. This can take several minutes...")
        # The SDK requires etag and match_condition; Unconditionally skips the etag check.
        gateways.ai_gateway_resources.begin_delete(
            gateway_resource_group, gateway_name, etag=None, match_condition=MatchConditions.Unconditionally
        ).result()
        print(f"Deleted gateway '{gateway_name}'.")
        return

    deployment_name = setting("FOUNDRY_MODEL_DEPLOYMENT")
    alias = setting("AI_GATEWAY_ALIAS", deployment_name)
    provider_id = f"{workspace_id}/modelProviders/{arm_name(account_name)}"
    for resource_id in (
        f"{gateway.id}/apiKeys/{arm_name(setting('AI_GATEWAY_API_KEY_NAME', 'external-app'))}",
        f"{workspace_id}/aliases/{arm_name(alias)}",
        f"{provider_id}/models/{arm_name(deployment_name)}",
        provider_id,
    ):
        name = resource_id.rsplit("/", 2)[-2:]
        resource = gateway_rest.get(gateways, resource_id)
        if resource is None:
            continue
        if not gateway_rest.is_sample_owned(resource):
            print(f"Skipped {'/'.join(name)}: this sample didn't create it.")
            continue
        gateway_rest.delete(gateways, resource_id)
        print(f"Deleted {'/'.join(name)}.")


if __name__ == "__main__":
    main()
