#!/usr/bin/env bash
# Provision a cell-owned Foundry project. The ledger is deliberately written before azd can create anything.
set -euo pipefail

sample= artifacts= subscription= location= work=
python=${PYTHON:-python3}
while [ "$#" -gt 0 ]; do
  [ "$#" -ge 2 ] || { echo 'Missing option value' >&2; exit 2; }
  case "$1" in
    --sample) sample=$2 ;; --artifacts) artifacts=$2 ;;
    --subscription-id) subscription=$2 ;; --location) location=$2 ;; --work) work=$2 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift 2
done
[ -n "$sample" ] && [ -n "$artifacts" ] && [ -n "$subscription" ] &&
  [ -n "$location" ] && [ -n "$work" ] || { echo 'Required: --sample --artifacts --subscription-id --location --work' >&2; exit 2; }
[[ "$subscription" =~ ^[0-9a-fA-F-]{36}$ && "$location" =~ ^[a-z0-9]+$ ]] || { echo 'Invalid subscription or location' >&2; exit 2; }
for tool in az azd jq "$python" realpath sha256sum; do command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 1; }; done
case "${OSTYPE:-}" in msys*|cygwin*) export MSYS_NO_PATHCONV=1; jq() { command jq --binary "$@"; } ;; esac
native_path() {
  case "${OSTYPE:-}" in msys*|cygwin*) cygpath -m "$1" ;; *) printf '%s\n' "$1" ;; esac
}
sample=$(realpath "$sample")
artifacts=$(realpath -m "$artifacts")
work=$(realpath -m "$work")
[ -f "$sample/azure.yaml" ] && [ -d "$artifacts" ] && [ ! -e "$artifacts/provision-ledger.json" ] &&
  [ ! -e "$work" ] && [[ "$work/" != "$artifacts/"* && "$artifacts/" != "$work/"* ]] &&
  [[ "$work/" != "$sample/"* && "$sample/" != "$work/"* ]] || {
    echo 'Sample, fresh work directory, and separate existing artifacts directory required' >&2; exit 1;
  }

nonce=$("$python" -c 'import uuid; print(uuid.uuid4().hex)')
environment="ci-prompt-$nonce"
resource_group="rg-ci-prompt-$nonce"
ledger="$artifacts/provision-ledger.json"
exists=$(az group exists --name "$resource_group" --subscription "$subscription" -o tsv)
[ "$exists" = false ] || { echo 'Resource group exists or absence cannot be established' >&2; exit 1; }
jq -n --arg nonce "$nonce" --arg env "$environment" --arg rg "$resource_group" \
  --arg sub "$subscription" --arg loc "$location" --arg work "$work" \
  '{nonce:$nonce, environment:$env, resource_group:$rg, subscription:$sub,
    location:$loc, work:$work, previously_absent:true, tagged:false}' > "$ledger"

# Only sample source (not .azure/.env credentials or prior azd state) enters the disposable workspace.
SAMPLE="$(native_path "$sample")" WORK="$(native_path "$work")" "$python" - <<'PY'
import os
from pathlib import Path
import shutil
import yaml

sample = Path(os.environ['SAMPLE'])
work = Path(os.environ['WORK'])
doc = yaml.safe_load((sample / 'azure.yaml').read_text(encoding='utf-8'))
services = doc.get('services') if isinstance(doc, dict) else None
if not isinstance(doc, dict) or doc.get('infra') != {'provider': 'microsoft.foundry'}:
    raise SystemExit('Disposable provisioning requires only the microsoft.foundry provider')
projects = [s for s in services.values() if isinstance(s, dict) and s.get('host') == 'azure.ai.project'] if isinstance(services, dict) else []
if len(projects) != 1 or len(projects[0].get('deployments', [])) != 1:
    raise SystemExit('Exactly one project with one declared model deployment is required')
for service in services.values():
    if not isinstance(service, dict) or any(key in service for key in ('id', 'projectId', 'endpoint', 'projectEndpoint')):
        raise SystemExit('Existing project/endpoint bindings are forbidden')
if 'hooks' in doc or any('hooks' in s for s in services.values()):
    raise SystemExit('Lifecycle hooks are forbidden')
deployment = projects[0]['deployments'][0]
if not isinstance(deployment, dict) or not isinstance(deployment.get('name'), str) or not deployment['name']:
    raise SystemExit('Model deployment must have a name')
shutil.copytree(sample, work / 'input', ignore=shutil.ignore_patterns('.azure', '.env', '.env.*', '.git', '.venv', '__pycache__'))
PY

cd "$work"
AZURE_SUBSCRIPTION_ID="$subscription" AZURE_LOCATION="$location" \
  azd ai agent init -m "$(native_path "$work/input/azure.yaml")" --src project \
    --no-prompt --environment "$environment"
cd "$work/project"
azd env set AZURE_SUBSCRIPTION_ID "$subscription" -e "$environment"
azd env set AZURE_LOCATION "$location" -e "$environment"
azd env set AZURE_RESOURCE_GROUP "$resource_group" -e "$environment"

check_env() {
  local key=$1 expected=$2 actual
  actual=$(azd env get-value "$key" -e "$environment") || { echo "Missing azd value: $key" >&2; exit 1; }
  [ "$actual" = "$expected" ] || { echo "azd $key changed; refusing cloud operation" >&2; exit 1; }
}
check_env AZURE_ENV_NAME "$environment"
check_env AZURE_SUBSCRIPTION_ID "$subscription"
check_env AZURE_LOCATION "$location"
check_env AZURE_RESOURCE_GROUP "$resource_group"
for key in AZURE_AI_PROJECT_ID AZURE_AI_PROJECT_ENDPOINT AZURE_AIPROJECT_ENDPOINT FOUNDRY_PROJECT_ENDPOINT; do
  if azd env get-value "$key" -e "$environment" >/dev/null 2>&1; then
    echo "Init adopted an existing $key; refusing provision" >&2; exit 1
  fi
done
verify_manifest() {
MODEL_FILE="$(native_path "$work/project/azure.yaml")" INPUT_FILE="$(native_path "$work/input/azure.yaml")" "$python" - <<'PY'
import os
import yaml
doc = yaml.safe_load(open(os.environ['MODEL_FILE'], encoding='utf-8'))
source = yaml.safe_load(open(os.environ['INPUT_FILE'], encoding='utf-8'))
projects = [s for s in doc['services'].values() if s.get('host') == 'azure.ai.project']
original = [s for s in source['services'].values() if s.get('host') == 'azure.ai.project']
if doc.get('infra') != {'provider': 'microsoft.foundry'}:
    raise SystemExit('Init/provision introduced unsupported infrastructure')
if len(projects) != 1 or projects[0].get('deployments') != original[0]['deployments']:
    raise SystemExit('Init/provision removed or changed the declared model deployment')
for service in doc['services'].values():
    if any(key in service for key in ('id', 'projectId', 'endpoint', 'projectEndpoint')):
        raise SystemExit('Init/provision introduced an existing-resource binding')
PY
}
verify_manifest
[ "$(az group exists --name "$resource_group" --subscription "$subscription" -o tsv)" = false ] || {
  echo 'Resource group appeared before provision; refusing' >&2; exit 1;
}
manifest_hash=$(sha256sum "$work/project/azure.yaml")
manifest_hash=${manifest_hash%% *}
jq --arg hash "$manifest_hash" '.manifest_sha256 = $hash' "$ledger" > "$ledger.tmp"
mv "$ledger.tmp" "$ledger"
# Tag an explicitly created, previously absent group before azd starts provisioning. A failed
# provision still leaves an identifiable group that teardown can safely distinguish from a foreign one.
body=$(jq -n --arg loc "$location" --arg nonce "$nonce" \
  '{location:$loc,tags:{ciPromptOwner:$nonce}}')
az rest --method put \
  --url "https://management.azure.com/subscriptions/$subscription/resourcegroups/$resource_group?api-version=2021-04-01" \
  --headers 'If-None-Match=*' --body "$body" --output none
group=$(az group show --name "$resource_group" --subscription "$subscription" -o json)
jq -e --arg id "/subscriptions/$subscription/resourceGroups/$resource_group" --arg nonce "$nonce" \
  '(.id | ascii_downcase) == ($id | ascii_downcase) and .tags.ciPromptOwner == $nonce' <<< "$group" >/dev/null || {
    echo 'Unable to verify newly created resource group ownership' >&2; exit 1;
  }
jq '.tagged = true' "$ledger" > "$ledger.tmp"
mv "$ledger.tmp" "$ledger"
azd provision --no-prompt -e "$environment"
check_env AZURE_ENV_NAME "$environment"
check_env AZURE_SUBSCRIPTION_ID "$subscription"
check_env AZURE_RESOURCE_GROUP "$resource_group"
check_env AZURE_LOCATION "$location"
verify_manifest
post_hash=$(sha256sum "$work/project/azure.yaml")
[ "${post_hash%% *}" = "$manifest_hash" ] || { echo 'Provision changed the adopted manifest' >&2; exit 1; }
group=$(az group show --name "$resource_group" --subscription "$subscription" -o json)
jq -e --arg id "/subscriptions/$subscription/resourceGroups/$resource_group" --arg nonce "$nonce" --arg env "$environment" \
  '(.id | ascii_downcase) == ($id | ascii_downcase) and
   (.tags.ciPromptOwner == $nonce or .tags["azd-env-name"] == $env)' <<< "$group" >/dev/null || {
    echo 'Unable to verify ownership tag after provision' >&2; exit 1;
  }
project_id=$(azd env get-value AZURE_AI_PROJECT_ID -e "$environment")
endpoint=$(azd env get-value FOUNDRY_PROJECT_ENDPOINT -e "$environment" 2>/dev/null ||
  azd env get-value AZURE_AI_PROJECT_ENDPOINT -e "$environment")
[[ "${project_id,,}" =~ ^/subscriptions/${subscription,,}/resourcegroups/${resource_group,,}/providers/microsoft\.cognitiveservices/accounts/[a-z0-9][a-z0-9_-]*/projects/[a-z0-9][a-z0-9_-]*$ ]] &&
  [[ "$endpoint" == https://* ]] || { echo 'Provisioned project identity is not in the owned resource group' >&2; exit 1; }
arm_endpoint=$(az resource show --ids "$project_id" --subscription "$subscription" --query 'properties.endpoints."AI Foundry API"' -o tsv)
[ "${arm_endpoint%/}" = "${endpoint%/}" ] || { echo 'ARM project endpoint mismatch' >&2; exit 1; }
model=$(MODEL_FILE="$(native_path "$work/project/azure.yaml")" "$python" - <<'PY'
import os
import yaml
doc = yaml.safe_load(open(os.environ['MODEL_FILE'], encoding='utf-8'))
print(next(s for s in doc['services'].values() if s.get('host') == 'azure.ai.project')['deployments'][0]['name'])
PY
)
account=${project_id%/projects/*}
account=${account##*/}
az cognitiveservices account deployment show --name "$account" --resource-group "$resource_group" \
  --subscription "$subscription" --deployment-name "$model" -o json >/dev/null
jq --arg project "$project_id" --arg endpoint "$endpoint" --arg model "$model" \
  '.project_id = $project | .project_endpoint = $endpoint | .model_deployment = $model' \
  "$ledger" > "$ledger.tmp"
mv "$ledger.tmp" "$ledger"
for pair in "PROJECT_ID:$project_id" "PROJECT_ENDPOINT:$endpoint" "MODEL_DEPLOYMENT:$model"; do
  echo "##vso[task.setvariable variable=${pair%%:*}]${pair#*:}"
done
