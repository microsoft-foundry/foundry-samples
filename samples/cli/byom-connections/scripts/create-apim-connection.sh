#!/usr/bin/env bash
# Create an ApiManagement connection on a Microsoft Foundry project with azd.
# The connection reaches an API in Azure API Management with either the APIM
# subscription key (AUTH_TYPE=api-key, the default) or the project's managed
# identity (AUTH_TYPE=project-managed-identity).
# Agents then use the model as <CONNECTION_NAME>/<MODEL_DEPLOYMENT_NAME>.
set -euo pipefail

: "${FOUNDRY_PROJECT_ENDPOINT:?Set FOUNDRY_PROJECT_ENDPOINT to your project endpoint.}"
: "${CONNECTION_NAME:?Set CONNECTION_NAME to the name of the new connection.}"
: "${APIM_API_URL:?Set APIM_API_URL to the APIM gateway URL plus the API path.}"
: "${MODEL_DEPLOYMENT_NAME:?Set MODEL_DEPLOYMENT_NAME to the model deployment name behind APIM.}"

model_name="${MODEL_NAME:-$MODEL_DEPLOYMENT_NAME}"
model_format="${MODEL_FORMAT:-OpenAI}"
version_field=""
if [ -n "${MODEL_VERSION:-}" ]; then
  version_field=",\"version\":\"${MODEL_VERSION}\""
fi
models="[{\"name\":\"${MODEL_DEPLOYMENT_NAME}\",\"properties\":{\"model\":{\"name\":\"${model_name}\"${version_field},\"format\":\"${model_format}\"}}}]"

args=(ai connection create "$CONNECTION_NAME"
  --kind ApiManagement
  --target "$APIM_API_URL"
  --metadata "deploymentInPath=${DEPLOYMENT_IN_PATH:-true}"
  --metadata "models=${models}"
  --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
  --no-prompt)

case "${AUTH_TYPE:-api-key}" in
  api-key)
    : "${APIM_SUBSCRIPTION_KEY:?Set APIM_SUBSCRIPTION_KEY to an APIM subscription key for the API.}"
    args+=(--auth-type api-key --key "$APIM_SUBSCRIPTION_KEY")
    ;;
  project-managed-identity)
    args+=(--auth-type project-managed-identity --audience "${TOKEN_AUDIENCE:-https://cognitiveservices.azure.com}")
    ;;
  *)
    echo "AUTH_TYPE must be api-key or project-managed-identity." >&2
    exit 1
    ;;
esac

if [ -n "${INFERENCE_API_VERSION:-}" ]; then
  args+=(--metadata "inferenceAPIVersion=${INFERENCE_API_VERSION}")
fi

azd "${args[@]}"
