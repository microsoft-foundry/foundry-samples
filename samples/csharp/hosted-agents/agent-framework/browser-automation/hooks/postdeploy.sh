#!/bin/sh
set -e

echo "========================================"
echo "  Playwright Workspace Role Assignment"
echo "========================================"

_AZD_ENV_CACHE=$(azd env get-values 2>/dev/null || true)

_azd_get() {
    printf '%s' "$_AZD_ENV_CACHE" | grep "^${1}=" | head -1 | sed 's/^[^=]*="//' | sed 's/"$//'
}

AUTH_TYPE=$(_azd_get PLAYWRIGHT_AUTH_TYPE)
PLAYWRIGHT_RESOURCE_ID=$(_azd_get PLAYWRIGHT_SERVICE_RESOURCE_ID)

if [ -z "$PLAYWRIGHT_RESOURCE_ID" ] || [ -z "$AUTH_TYPE" ]; then
    echo "Necessary params not configured - skipping role assignment."
    exit 0
fi

if [ "$AUTH_TYPE" = "ApiKey" ]; then
    echo "Auth type is API Key - no role assignment needed."
    exit 0
fi

PRINCIPAL_ID=""
PRINCIPAL_TYPE="ServicePrincipal"

if [ "$AUTH_TYPE" = "ProjectManagedIdentity" ]; then
    echo "Assigning role to Project Managed Identity..."
    PROJECT_ID=$(_azd_get AZURE_AI_PROJECT_ID)
    if [ -z "$PROJECT_ID" ]; then
        echo "AZURE_AI_PROJECT_ID not found - skipping role assignment."
        exit 0
    fi
    PRINCIPAL_ID=$(az resource show --id "$PROJECT_ID" --query "identity.principalId" -o tsv 2>/dev/null)

elif [ "$AUTH_TYPE" = "AgenticIdentityToken" ]; then
    echo "Assigning role to Agent Identity..."
    PROJECT_ENDPOINT=$(_azd_get AZURE_AI_PROJECT_ENDPOINT)
    if [ -z "$PROJECT_ENDPOINT" ]; then
        PROJECT_ENDPOINT=$(_azd_get FOUNDRY_PROJECT_ENDPOINT)
    fi
    if [ -z "$PROJECT_ENDPOINT" ]; then
        echo "Could not determine project endpoint - skipping role assignment."
        exit 0
    fi

    AGENT_NAME=$(azd env get-values 2>/dev/null | grep -E '^AGENT_.*_NAME=' | head -1 | sed 's/^[^=]*="//' | sed 's/"$//')
    if [ -z "$AGENT_NAME" ]; then
        echo "Could not determine agent name - skipping role assignment."
        exit 0
    fi

    PRINCIPAL_ID=$(az rest \
        --method GET \
        --url "${PROJECT_ENDPOINT}/agents/${AGENT_NAME}?api-version=v1" \
        --resource https://ai.azure.com \
        --query "instance_identity.principal_id" \
        --output tsv)
fi

if [ -z "$PRINCIPAL_ID" ]; then
    echo "Could not determine principal ID - skipping role assignment."
    exit 0
fi

echo "  Principal ID: $PRINCIPAL_ID"

ROLE_DEFINITION_ID="78cf819f-0969-4ebe-8759-015c6efcd5bf"
echo "Assigning Playwright Workspace Contributor role on: $PLAYWRIGHT_RESOURCE_ID"

EXISTING=$(az role assignment list \
    --assignee "$PRINCIPAL_ID" \
    --role "$ROLE_DEFINITION_ID" \
    --scope "$PLAYWRIGHT_RESOURCE_ID" \
    --query "[0].id" -o tsv 2>/dev/null || echo "")

if [ -n "$EXISTING" ]; then
    echo "Role already assigned."
    exit 0
fi

MAX_RETRIES=3
RETRY_DELAY=10
ASSIGNED=false

for i in $(seq 1 $MAX_RETRIES); do
    if az role assignment create \
        --assignee-object-id "$PRINCIPAL_ID" \
        --assignee-principal-type "$PRINCIPAL_TYPE" \
        --role "$ROLE_DEFINITION_ID" \
        --scope "$PLAYWRIGHT_RESOURCE_ID" \
        --only-show-errors > /dev/null 2>&1; then
        ASSIGNED=true
        break
    fi

    if [ "$i" -lt "$MAX_RETRIES" ]; then
        echo "  Attempt $i failed, retrying in ${RETRY_DELAY}s..."
        sleep "$RETRY_DELAY"
    fi
done

if [ "$ASSIGNED" = true ]; then
    echo "Playwright Workspace Contributor role assigned successfully."
else
    echo "Could not assign role after $MAX_RETRIES attempts. Assign 'Playwright Workspace Contributor' manually to principal '$PRINCIPAL_ID' on the workspace." >&2
fi
