#!/usr/bin/env sh
# azd postprovision hook (POSIX / sh).
#
# Runs after `azd provision` and creates the Foundry Memory Store.
# It stores MEMORY_STORE_NAME so the agent can reach the store.

set -e

# Run from the sample directory; resolve the script from any azd cwd.
cd "$(CDPATH= cd "$(dirname "$0")/.." && pwd)"

# The manifest declares the embedding deployment.
if [ -z "$AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME" ]; then
  AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME="text-embedding-3-small"
  export AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME
  azd env set AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME \
    "$AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME"
fi

# Default and persist the store name for agent deployment.
if [ -z "$MEMORY_STORE_NAME" ]; then
  MEMORY_STORE_NAME="agent_framework_memory"
  export MEMORY_STORE_NAME
  azd env set MEMORY_STORE_NAME "$MEMORY_STORE_NAME"
fi

echo "Provisioning the Foundry Memory Store '$MEMORY_STORE_NAME'..."
# Install the locked runtime dependencies used by the provisioning script.
uv sync --frozen --no-dev --no-install-project
# Idempotent: an existing store with the same name is left untouched.
uv run --no-sync python provision_memory_store.py

# Ensure agent.yaml receives the name if init resolved it before this
# hook ran.
# This keeps the deployed agent connected to the provisioned store.
if [ -f agent.yaml ]; then
  awk -v val="$MEMORY_STORE_NAME" '
    prev ~ /name:[[:space:]]*MEMORY_STORE_NAME[[:space:]]*$/ && /value:/ {
      sub(/value:.*/, "value: " val)
    }
    { print; prev = $0 }
  ' agent.yaml > agent.yaml.tmp && mv agent.yaml.tmp agent.yaml
  echo "Set MEMORY_STORE_NAME in agent.yaml to '$MEMORY_STORE_NAME' for deploy."
fi

echo "Done. MEMORY_STORE_NAME = $MEMORY_STORE_NAME"
