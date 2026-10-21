#!/usr/bin/env bash
# Fail closed: a missing or untagged ledger is never authority to delete a resource group.
set -euo pipefail
case "${OSTYPE:-}" in msys*|cygwin*) export MSYS_NO_PATHCONV=1; jq() { command jq --binary "$@"; } ;; esac
artifacts= work= subscription=
while [ "$#" -gt 0 ]; do
  [ "$#" -ge 2 ] || { echo 'Missing option value' >&2; exit 2; }
  case "$1" in
    --artifacts) artifacts=$2 ;; --work) work=$2 ;; --subscription-id) subscription=$2 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift 2
done
[ -n "$artifacts" ] && [ -n "$work" ] && [ -n "$subscription" ] || {
  echo 'Required: --artifacts --work --subscription-id' >&2; exit 2;
}
artifacts=$(realpath -m "$artifacts")
work=$(realpath -m "$work")
ledger="$artifacts/provision-ledger.json"
[ -f "$ledger" ] || { echo 'No provisioning ledger; nothing is authorized for deletion' >&2; exit 0; }
teardown_status=failed
trap 'jq -n --arg status "$teardown_status" "{status:\$status}" > "$artifacts/teardown-result.json"' EXIT
[[ "$work/" != "$artifacts/"* && "$artifacts/" != "$work/"* ]] || { echo 'Work must be separate from artifacts' >&2; exit 1; }
jq -e --arg work "$work" --arg sub "$subscription" '
  .previously_absent == true and .work == $work and .subscription == $sub and
  (.nonce | type == "string" and test("^[0-9a-f]{32}$")) and
  .environment == ("ci-prompt-" + .nonce) and
  .resource_group == ("rg-ci-prompt-" + .nonce) and
  (.location | type == "string" and test("^[a-z0-9]+$"))
' "$ledger" >/dev/null || { echo 'Invalid ownership ledger; refusing deletion' >&2; exit 1; }
environment=$(jq -r .environment "$ledger")
resource_group=$(jq -r .resource_group "$ledger")
nonce=$(jq -r .nonce "$ledger")
location=$(jq -r .location "$ledger")
if [ "$(jq -r .tagged "$ledger")" != true ]; then
  # Provision may have failed before ownership could be verified. Never delete an untagged group.
  if [ "$(az group exists --name "$resource_group" --subscription "$subscription" -o tsv)" = false ]; then
    echo 'No owned resource group was created'
    teardown_status=passed
    exit 0
  fi
  echo 'Unverified resource group exists; manual investigation required' >&2
  exit 1
fi
[ -f "$work/project/azure.yaml" ] && [ -d "$work/project/.azure/$environment" ] || {
  echo 'Recorded azd workspace is missing; refusing deletion' >&2; exit 1;
}
manifest_hash=$(sha256sum "$work/project/azure.yaml")
manifest_hash=${manifest_hash%% *}
jq -e --arg hash "$manifest_hash" '.manifest_sha256 == $hash' "$ledger" >/dev/null || {
  echo 'Adopted manifest changed; refusing deletion' >&2; exit 1;
}
cd "$work/project"
for pair in "AZURE_ENV_NAME:$environment" "AZURE_SUBSCRIPTION_ID:$subscription" \
  "AZURE_RESOURCE_GROUP:$resource_group" "AZURE_LOCATION:$location"; do
  key=${pair%%:*}
  [ "$(azd env get-value "$key" -e "$environment")" = "${pair#*:}" ] || {
    echo "azd $key differs from ledger; refusing deletion" >&2; exit 1;
  }
done
if jq -e 'has("project_id")' "$ledger" >/dev/null; then
  project_id=$(azd env get-value AZURE_AI_PROJECT_ID -e "$environment")
  endpoint=$(azd env get-value FOUNDRY_PROJECT_ENDPOINT -e "$environment" 2>/dev/null ||
    azd env get-value AZURE_AI_PROJECT_ENDPOINT -e "$environment")
  jq -e --arg id "$project_id" --arg endpoint "$endpoint" \
    '.project_id == $id and .project_endpoint == $endpoint' "$ledger" >/dev/null || {
      echo 'Project identity differs from ledger; refusing deletion' >&2; exit 1;
    }
  [[ "${project_id,,}" =~ ^/subscriptions/${subscription,,}/resourcegroups/${resource_group,,}/providers/microsoft\.cognitiveservices/accounts/[a-z0-9][a-z0-9_-]*/projects/[a-z0-9][a-z0-9_-]*$ ]] || {
    echo 'Project does not belong to recorded group' >&2; exit 1;
  }
else
  # azd can publish outputs before provision fails. Accept only an ID inside this owned group.
  project_id=$(azd env get-value AZURE_AI_PROJECT_ID -e "$environment" 2>/dev/null) || project_id=
  endpoints=()
  for key in FOUNDRY_PROJECT_ENDPOINT AZURE_AI_PROJECT_ENDPOINT AZURE_AIPROJECT_ENDPOINT; do
    endpoint=$(azd env get-value "$key" -e "$environment" 2>/dev/null) || endpoint=
    [ -z "$endpoint" ] || endpoints+=("$endpoint")
  done
  if [ -n "$project_id" ] || [ "${#endpoints[@]}" -gt 0 ]; then
    [[ "${project_id,,}" =~ ^/subscriptions/${subscription,,}/resourcegroups/${resource_group,,}/providers/microsoft\.cognitiveservices/accounts/[a-z0-9][a-z0-9_-]*/projects/[a-z0-9][a-z0-9_-]*$ ]] || {
      echo 'Unrecorded project does not belong to recorded group' >&2; exit 1;
    }
    if [ "${#endpoints[@]}" -gt 0 ]; then
      arm_endpoint=$(az resource show --ids "$project_id" --subscription "$subscription" \
        --query 'properties.endpoints."AI Foundry API"' -o tsv) || {
          echo 'Cannot verify unrecorded project endpoint with ARM' >&2; exit 1;
        }
      for endpoint in "${endpoints[@]}"; do
        [[ "$endpoint" == https://* ]] && [ -n "$arm_endpoint" ] &&
          [ "${endpoint%/}" = "${arm_endpoint%/}" ] || {
            echo 'Unrecorded project endpoint differs from ARM' >&2; exit 1;
          }
      done
    fi
  fi
fi
group=$(az group show --name "$resource_group" --subscription "$subscription" -o json) || {
  echo 'Cannot establish owned group identity; refusing deletion' >&2; exit 1;
}
jq -e --arg id "/subscriptions/$subscription/resourceGroups/$resource_group" --arg nonce "$nonce" --arg env "$environment" \
  '(.id | ascii_downcase) == ($id | ascii_downcase) and
   (.tags.ciPromptOwner == $nonce or .tags["azd-env-name"] == $env)' <<< "$group" >/dev/null || {
    echo 'Resource group ownership tag/ID differs; refusing deletion' >&2; exit 1;
  }
azd down --force --purge --no-prompt -e "$environment"
exists=$(az group exists --name "$resource_group" --subscription "$subscription" -o tsv)
[ "$exists" = false ] || { echo 'Resource group deletion not verified' >&2; exit 1; }
teardown_status=passed
