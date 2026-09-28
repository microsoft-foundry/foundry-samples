#!/usr/bin/env bash
#
# Enable incoming A2A on the executor agent (data plane). After this runs,
# the agent answers both Responses and A2A at the same endpoint.
#
#   PATCH the executor agent: publish an `agent_card` and add `a2a` to
#   its `agent_endpoint.protocols`.
#   See: https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint
#
# The matching `RemoteA2A` connection and `a2a_preview` toolbox are declared
# in the caller's azure.yaml and created by `azd provision` on the caller.
# They are not created here.
#
# Defaults (filled in from ../.env so you can usually run with no args):
#   - FOUNDRY_PROJECT_ENDPOINT : read from ../.env
#   - AGENT_NAME               : "agent-framework-a2a-executor-responses-dotnet"
#                                (the executor's default name from azure.yaml)
#
# Override any default by exporting the env var of the same name before
# running, or by passing the agent name as a positional arg.
#
# Usage:
#   ./setup-a2a.sh
#   ./setup-a2a.sh <agent-name>
#
# Requirements:
#   * Azure CLI (az) installed and authenticated (`az login`).
#   * Foundry User role (or higher) on the Foundry project.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

DEFAULT_AGENT_NAME="agent-framework-a2a-executor-responses-dotnet"

case "$#" in
  0) ;;
  1) AGENT_NAME="$1" ;;
  *)
    echo "Usage: $0 [<agent-name>]" >&2
    exit 1
    ;;
esac

if [[ -z "${FOUNDRY_PROJECT_ENDPOINT:-}" ]]; then
  echo "Error: FOUNDRY_PROJECT_ENDPOINT is not set (expected in $ENV_FILE)." >&2
  exit 1
fi

: "${AGENT_NAME:=$DEFAULT_AGENT_NAME}"

BASE_URL="${FOUNDRY_PROJECT_ENDPOINT%/}"
TARGET_A2A_URL="$BASE_URL/agents/$AGENT_NAME/endpoint/protocols/a2a/"
DISPLAY_A2A_URL="${TARGET_A2A_URL%/}"

echo "Project endpoint: $BASE_URL"
echo "Agent name:       $AGENT_NAME"
echo "Target A2A URL:   $DISPLAY_A2A_URL"
echo

echo "Enabling incoming A2A on agent '$AGENT_NAME'..."

az rest \
  --method PATCH \
  --url "$BASE_URL/agents/$AGENT_NAME?api-version=v1" \
  --resource https://ai.azure.com \
  --headers "Content-Type=application/json" \
  --body '{
    "agent_card": {
      "description": "A math expert that performs arithmetic operations and explains the steps.",
      "version": "1.0",
      "skills": [
        {
          "id": "arithmetic",
          "name": "Arithmetic and math expert",
          "description": "Performs arithmetic operations (addition, subtraction, multiplication, division, exponentiation) and returns concise numeric answers."
        }
      ]
    },
    "agent_endpoint": {
      "protocols": ["responses", "a2a"]
    }
  }' \
  --output none

echo "done."
echo
echo "Incoming A2A enabled."
echo "  A2A endpoint:  $DISPLAY_A2A_URL"
echo "  Agent card:    $DISPLAY_A2A_URL/agentCard/v0.3"
echo
echo "Next: when running 'azd ai agent init' on the caller, paste the A2A endpoint"
echo "above as the 'a2a_executor_endpoint' parameter. 'azd provision' on the caller"
echo "will then create the RemoteA2A connection + a2a_preview toolbox automatically."
