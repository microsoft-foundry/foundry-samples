#!/usr/bin/env sh

set -eu

project_endpoint=$(azd env get-value FOUNDRY_PROJECT_ENDPOINT)
if [ -z "$project_endpoint" ]; then
  echo 'FOUNDRY_PROJECT_ENDPOINT is missing after provisioning.' >&2
  exit 1
fi

azd env set AZURE_AI_PROJECT_ENDPOINT "$project_endpoint"