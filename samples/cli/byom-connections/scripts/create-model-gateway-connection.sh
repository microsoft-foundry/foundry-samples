#!/usr/bin/env bash
# Create a ModelGateway connection on a Microsoft Foundry project with azd.
# The connection reaches a model gateway or provider with an API key.
# Agents then use the model as <CONNECTION_NAME>/<MODEL_DEPLOYMENT_NAME>.
set -euo pipefail

: "${FOUNDRY_PROJECT_ENDPOINT:?Set FOUNDRY_PROJECT_ENDPOINT to your project endpoint.}"
: "${CONNECTION_NAME:?Set CONNECTION_NAME to the name of the new connection.}"
: "${GATEWAY_URL:?Set GATEWAY_URL to the gateway base URL.}"
: "${GATEWAY_API_KEY:?Set GATEWAY_API_KEY to the gateway API key.}"
: "${MODEL_DEPLOYMENT_NAME:?Set MODEL_DEPLOYMENT_NAME to the model name the gateway exposes.}"

model_name="${MODEL_NAME:-$MODEL_DEPLOYMENT_NAME}"
model_format="${MODEL_FORMAT:-OpenAI}"
version_field=""
if [ -n "${MODEL_VERSION:-}" ]; then
  version_field=",\"version\":\"${MODEL_VERSION}\""
fi
models="[{\"name\":\"${MODEL_DEPLOYMENT_NAME}\",\"properties\":{\"model\":{\"name\":\"${model_name}\"${version_field},\"format\":\"${model_format}\"}}}]"

azd ai connection create "$CONNECTION_NAME" \
  --kind ModelGateway \
  --target "$GATEWAY_URL" \
  --auth-type api-key \
  --key "$GATEWAY_API_KEY" \
  --metadata "deploymentInPath=${DEPLOYMENT_IN_PATH:-false}" \
  --metadata "inferenceAPIVersion=${INFERENCE_API_VERSION:-}" \
  --metadata "models=${models}" \
  --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT" \
  --no-prompt
