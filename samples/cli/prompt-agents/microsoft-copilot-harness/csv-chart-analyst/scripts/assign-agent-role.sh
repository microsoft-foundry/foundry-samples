#!/usr/bin/env sh

set -eu

project_endpoint="$(azd env get-value FOUNDRY_PROJECT_ENDPOINT)"
project_id="$(azd env get-value AZURE_AI_PROJECT_ID)"
agent_name="$(azd env get-value AGENT_CSV_CHART_ANALYST_NAME)"

agent_principal_id="$(az rest \
  --method GET \
  --url "${project_endpoint}/agents/${agent_name}?api-version=v1" \
  --resource https://ai.azure.com \
  --query instance_identity.principal_id \
  --output tsv)"

assignment_count="$(az role assignment list \
  --assignee-object-id "$agent_principal_id" \
  --role "Foundry User" \
  --scope "$project_id" \
  --fill-principal-name false \
  --query 'length(@)' \
  --output tsv)"

if [ "$assignment_count" = "0" ]; then
  az role assignment create \
    --assignee-object-id "$agent_principal_id" \
    --assignee-principal-type ServicePrincipal \
    --role "Foundry User" \
    --scope "$project_id" \
    --output none
fi

printf 'Foundry User is assigned to agent identity %s at project scope.\n' "$agent_principal_id"