#!/bin/sh
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
#
# Grants the deployed hosted agent identity access to Azure Managed Redis.

set -eu

main() {
  azd_values="$(azd env get-values)"
  project_endpoint="$(printf '%s\n' "${azd_values}" |
    sed -n 's/^\(AZURE_AI_PROJECT_ENDPOINT\|FOUNDRY_PROJECT_ENDPOINT\)="\(.*\)"$/\2/p' |
    head -n 1)"
  agent_name="$(printf '%s\n' "${azd_values}" |
    sed -n 's/^AGENT_.*_NAME="\(.*\)"$/\1/p' |
    head -n 1)"
  redis_database_id="$(printf '%s\n' "${azd_values}" |
    sed -n 's/^REDIS_DATABASE_RESOURCE_ID="\(.*\)"$/\1/p')"

  if [ -z "${project_endpoint}" ] || [ -z "${agent_name}" ] ||
    [ -z "${redis_database_id}" ]; then
    echo "ERROR: Required project, agent, or Redis deployment values are missing." >&2
    exit 1
  fi

  # 1. Get the deployed agent identity.
  foundry_token="$(az account get-access-token \
    --resource 'https://ai.azure.com' \
    --query accessToken \
    --output tsv)"
  principal_id="$(curl --fail --silent --show-error \
    --header "Authorization: Bearer ${foundry_token}" \
    "${project_endpoint%/}/agents/${agent_name}?api-version=v1" |
    python3 -c \
      "import json, sys; print(json.load(sys.stdin)['instance_identity']['principal_id'])")"

  # 2. Add the identity to Redis authentication.
  management_token="$(az account get-access-token \
    --resource 'https://management.azure.com/' \
    --query accessToken \
    --output tsv)"
  assignment_name="agent-${principal_id}"
  assignment_uri="https://management.azure.com${redis_database_id}/accessPolicyAssignments/${assignment_name}?api-version=2025-07-01"

  curl --fail --silent --show-error \
    --request PUT \
    --header "Authorization: Bearer ${management_token}" \
    --header 'Content-Type: application/json' \
    --data "{\"properties\":{\"accessPolicyName\":\"default\",\"user\":{\"objectId\":\"${principal_id}\"}}}" \
    "${assignment_uri}" >/dev/null

  echo "Granted Azure Managed Redis access to agent identity ${principal_id}."
}

main "$@"
