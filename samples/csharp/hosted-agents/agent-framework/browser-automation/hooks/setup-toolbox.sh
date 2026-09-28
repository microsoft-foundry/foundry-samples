#!/bin/sh
set -e

# ── Setup Browser Automation Toolbox ──────────────────────────────────────────
# This script creates a new version of the browser-automation-tools toolbox.
# Called by postprovision.sh after connection setup.
# Always creates a new version to pick up any connection changes, then publishes it.

_AZD_ENV_CACHE=$(azd env get-values 2>/dev/null || true)

_azd_get() {
    printf '%s' "$_AZD_ENV_CACHE" | grep "^${1}=" | head -1 | sed 's/^[^=]*="//' | sed 's/"$//'
}

echo ""
echo "Creating browser-automation-tools toolbox..."

PROJECT_ENDPOINT=$(_azd_get AZURE_AI_PROJECT_ENDPOINT)
if [ -z "$PROJECT_ENDPOINT" ]; then
    PROJECT_ENDPOINT=$(_azd_get FOUNDRY_PROJECT_ENDPOINT)
fi
if [ -z "$PROJECT_ENDPOINT" ]; then
    echo "Error: Could not determine project endpoint." >&2
    exit 1
fi

PROJECT_ID=$(_azd_get AZURE_AI_PROJECT_ID)
if [ -z "$PROJECT_ID" ]; then
    echo "Error: Could not determine project ID. Set AZURE_AI_PROJECT_ID." >&2
    exit 1
fi

CONNECTION_ID="${PROJECT_ID}/connections/browserautomation"
TOOLBOX_NAME="browser-automation-tools"
TOOLBOX_BODY=$(printf '{
  "tools": [{
    "type": "browser_automation_preview",
    "browser_automation_preview": {
      "connection": { "project_connection_id": "%s" }
    }
  }]
}' "$CONNECTION_ID")

RESPONSE=$(az rest \
    --method POST \
    --url "${PROJECT_ENDPOINT}/toolboxes/${TOOLBOX_NAME}/versions?api-version=v1" \
    --resource https://ai.azure.com \
    --headers "Content-Type=application/json" "Foundry-Features=Toolboxes=V1Preview" \
    --body "$TOOLBOX_BODY" \
    --output json)

VERSION_ID=$(printf '%s' "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version',''))" 2>/dev/null || echo "")
if [ -z "$VERSION_ID" ]; then
    echo "Error: Toolbox creation did not return a version ID." >&2
    exit 1
fi

echo "  Created version: $VERSION_ID"

azd ai toolbox publish "$TOOLBOX_NAME" "$VERSION_ID"
azd env set TOOLBOX_NAME "$TOOLBOX_NAME"

echo "Toolbox '$TOOLBOX_NAME' v${VERSION_ID} created and published."
