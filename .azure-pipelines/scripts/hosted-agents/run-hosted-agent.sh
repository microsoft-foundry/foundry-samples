#!/usr/bin/env bash

# ADO owns phase conditions, authentication and final job status. Each old
# operation runs in its own shell: exit, traps, cwd and shell options must
# not leak into the next operation. PHASE_* inputs are mapped only to the
# operation that originally received them, especially credentials.
# FD 3 carries shell source without consuming the commands' standard input.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <action>" >&2
  exit 2
fi

case "$1" in
  hydrate)
    echo "##[section]Hydrate combo record"
    bash /dev/fd/3 3<<'STEP_HYDRATE_COMBO_RECORD'
set -euo pipefail
entries="$PIPELINE_WORKSPACE/HostedAgentSamplesMatrix/entries.json"
record="$(jq -c --arg id "$COMBO_ID" 'map(select(.comboId == $id)) | .[0] // empty' "$entries")"
if [ -z "$record" ]; then
  echo "##vso[task.logissue type=error]No discovery record for combo $COMBO_ID"
  exit 1
fi
jq . <<< "$record"

emit() {
  # Values are single-line by construction (paths, names, labels,
  # URLs, a short query). setvariable is line-oriented, so guard.
  local name="$1" value="$2"
  case "$value" in
    *$'\n'*)
      echo "##vso[task.logissue type=error]$name contains a newline; refusing to set"
      exit 1
      ;;
  esac
  echo "##vso[task.setvariable variable=$name]$value"
}

emit SAMPLE_ID        "$(jq -r '.sampleId' <<< "$record")"
emit SAMPLE_PATH      "$(jq -r '.samplePath' <<< "$record")"
emit SAMPLE_NAME      "$(jq -r '.sampleName' <<< "$record")"
emit SAMPLE_LANGUAGE  "$(jq -r '.sampleLanguage' <<< "$record")"
emit PROTOCOL         "$(jq -r '.protocol' <<< "$record")"
emit PROTOCOL_VERSION "$(jq -r '.protocolVersion' <<< "$record")"
emit IS_TOOLBOX       "$(jq -r '.isToolbox' <<< "$record")"
emit TOOLBOX_LABEL    "$(jq -r '.toolboxLabel' <<< "$record")"
emit TOOLBOX_URL      "$(jq -r '.toolboxUrl' <<< "$record")"
emit TOOLBOX_QUERY    "$(jq -r '.toolboxQuery' <<< "$record")"
emit USE_WESTUS2      "$(jq -r '.useWestus2' <<< "$record")"
emit VOICE_LIVE       "$(jq -r '.voiceLive' <<< "$record")"
emit DEPLOY_MODE      "$(jq -r '.deployMode' <<< "$record")"
emit SAMPLE_RUNTIME   "$(jq -r '.runtime' <<< "$record")"
emit ENTRY_POINT      "$(jq -r '.entryPoint' <<< "$record")"
emit DEP_RESOLUTION   "$(jq -r '.depResolution' <<< "$record")"

# Code-deploy arm skips ACR provisioning (no image to push).
if [ "$(jq -r '.deployMode' <<< "$record")" = "code" ]; then
  emit skipAcrCreation "true"
else
  emit skipAcrCreation "false"
fi
STEP_HYDRATE_COMBO_RECORD
    ;;
  prepare)
    echo "##[section]Install azd, Foundry extension and yq"
    bash /dev/fd/3 3<<'STEP_INSTALL_AZD_FOUNDRY_EXTENSION_AND_YQ'
set -euo pipefail
curl -fsSL https://aka.ms/install-azd.sh | bash
azd version

# Install the latest unified Foundry CLI extension. The verify
# step below fails fast if the installed build doesn't expose the
# --deploy-mode/--runtime/--entry-point flags the code arm needs.
# The unified azure.yaml declares `requiredVersions.extensions:
# microsoft.foundry`, matching the sample READMEs.
azd ext install microsoft.foundry

# azd authenticates through the az CLI session that AzureCLI@2
# establishes for each task. This config write needs no auth.
azd config set auth.useAzCliAuth true

sudo curl -fsSL -o /usr/local/bin/yq \
  https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64
sudo chmod +x /usr/local/bin/yq
yq --version

python3 -m pip install --disable-pip-version-check --quiet "PyYAML==6.0.2"
STEP_INSTALL_AZD_FOUNDRY_EXTENSION_AND_YQ
    echo "##[section]Validate required variables"
    AZURE_SERVICE_CONNECTION="$PHASE_AZURE_SERVICE_CONNECTION" \
    AZURE_SUBSCRIPTION_ID="$PHASE_AZURE_SUBSCRIPTION_ID" \
    AZURE_AI_PROJECT_ID="$PHASE_AZURE_AI_PROJECT_ID" \
    AZURE_AI_PROJECT_ENDPOINT="$PHASE_AZURE_AI_PROJECT_ENDPOINT" \
      bash /dev/fd/3 3<<'STEP_VALIDATE_REQUIRED_VARIABLES'
set -euo pipefail
# An unset ADO variable macro-expands to the literal '$(NAME)'.
is_missing() { [ -z "${1:-}" ] || [[ "$1" == \$\(*\) ]]; }
missing=()
for var in AZURE_SERVICE_CONNECTION AZURE_SUBSCRIPTION_ID AZURE_AI_PROJECT_ID AZURE_AI_PROJECT_ENDPOINT; do
  eval "val=\${$var:-}"
  is_missing "$val" && missing+=("$var")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "##vso[task.logissue type=error]Missing required pipeline variables: ${missing[*]}"
  echo "Configure these in the samples-hosted-agents-ci variable group."
  exit 1
fi
echo "Required pipeline variables are present."
STEP_VALIDATE_REQUIRED_VARIABLES
    echo "##[section]Validate sample structure"
    bash /dev/fd/3 3<<'STEP_VALIDATE_SAMPLE_STRUCTURE'
set -euo pipefail
sample_dir="$SAMPLE_PATH"
errors=()
if [ ! -f "$sample_dir/azure.yaml" ]; then
  errors+=("missing azure.yaml")
else
  proj=$(yq '(.services[] | select(.host == "azure.ai.agent") | .project) // ""' "$sample_dir/azure.yaml")
  if [ -z "$proj" ]; then
    errors+=("azure.yaml has no 'project: src/<agent>' entry")
  elif [ ! -d "$sample_dir/$proj" ]; then
    errors+=("missing source directory '$proj'")
  fi
fi
if [ ${#errors[@]} -gt 0 ]; then
  for err in "${errors[@]}"; do
    echo "##vso[task.logissue type=error]$sample_dir: $err"
  done
  exit 1
fi
echo "PASS $sample_dir has azure.yaml with a matching src/<agent> directory"
STEP_VALIDATE_SAMPLE_STRUCTURE
    echo "##[section]Compute environment and agent names"
    BUILD_ID="$PHASE_BUILD_ID" COMBO_ID="$PHASE_COMBO_ID" bash /dev/fd/3 3<<'STEP_COMPUTE_ENVIRONMENT_AND_AGENT_NAMES'
set -euo pipefail
truncate_name() { echo "${1:0:63}" | sed 's/[-_.]*$//'; }

azd_env_name="ado-ci-e2e-${BUILD_ID}-${COMBO_ID}"
azd_env_name=$(truncate_name "$azd_env_name")
echo "##vso[task.setvariable variable=AZD_ENV_NAME]$azd_env_name"
echo "AZD_ENV_NAME: $azd_env_name (${#azd_env_name} chars)"

# Agent names deliberately match the GitHub workflow's scheme
# (no ADO-specific prefix). Foundry mints one AgentIdentity per
# distinct agent name and assigns it a Foundry User role, and the
# subscription has a hard 5000 role-assignment cap. A separate
# ADO namespace would double the identity population and exhaust
# that cap, after which Foundry silently fails to grant the role
# and every deployed agent dies at startup with 403 on
# agents/read. Stable, shared names mean identities are reused.
# Concurrent runs are safe because the invoke step pins the exact
# agent version this cell deployed.
if [ "$IS_TOOLBOX" = "true" ]; then
  agent_name="ci-toolbox-${TOOLBOX_LABEL}-${SAMPLE_NAME}-${DEPLOY_MODE}"
else
  agent_name="ci-${SAMPLE_NAME}-${DEPLOY_MODE}"
fi
# Keep agent names stable but unique. Some samples share the same
# manifest name, so append a stable hash of comboId and preserve
# that suffix when enforcing the 63-character limit.
agent_hash=$(printf '%s' "$COMBO_ID" | sha256sum | cut -c1-8)
agent_prefix_max=$((63 - ${#agent_hash} - 1))
agent_prefix=$(printf '%s' "$agent_name" | cut -c1-"$agent_prefix_max" | sed 's/[-_.]*$//')
agent_name="${agent_prefix}-${agent_hash}"
echo "##vso[task.setvariable variable=FOUNDRY_AGENT_NAME]$agent_name"
echo "FOUNDRY_AGENT_NAME: $agent_name (${#agent_name} chars)"
STEP_COMPUTE_ENVIRONMENT_AND_AGENT_NAMES
    echo "##[section]Verify azd ext supports --deploy-mode"
    bash /dev/fd/3 3<<'STEP_VERIFY_AZD_EXT_SUPPORTS_DEPLOY_MODE'
set -euo pipefail

echo "##[group]Installed azd toolchain"
# Diagnostic only; must not create a new gate.
set +e
echo "azd path: $(command -v azd)"
sha256sum "$(command -v azd)"
azd version
azd ext list
azd ext show microsoft.foundry
azd ext show azure.ai.agents
azd ext show azure.ai.toolboxes
for extension_id in azure.ai.agents azure.ai.toolboxes; do
  extension_dir="$HOME/.azd/extensions/$extension_id"
  if [ -d "$extension_dir" ]; then
    echo "Installed files for $extension_id:"
    find "$extension_dir" -maxdepth 1 -type f -printf '  %f (%s bytes)\n' | sort
    find "$extension_dir" -maxdepth 1 -type f -perm /111 -exec sha256sum {} +
  else
    echo "##vso[task.logissue type=warning]Expected extension directory is missing: $extension_dir"
  fi
done
set -e
echo "##[endgroup]"

PREFLIGHT_DIR=$(mktemp -d "/tmp/azd-preflight-XXXXXX")
trap 'rm -rf "$PREFLIGHT_DIR"' EXIT

# A debug invocation is evidence only: it is bounded, never
# replaces the first result, and cannot turn a failed preflight
# into a pass.
debug_failed_preflight() {
  local label="$1"
  shift
  local executable="$1"
  shift
  local debug_output debug_status
  debug_output=$(mktemp "$PREFLIGHT_DIR/debug-XXXXXX.log")

  echo "##[group]Secondary debug invocation: $label"
  printf 'Command: AZD_EXT_DEBUG=true timeout 30s %q --debug' "$executable"
  printf ' %q' "$@"
  printf '\n'
  set +e
  AZD_EXT_DEBUG=true timeout 30s "$executable" --debug "$@" >"$debug_output" 2>&1
  debug_status=$?
  set -e
  echo "Exit code: $debug_status"
  echo "--- combined stdout/stderr ---"
  cat "$debug_output"
  echo "--- end combined stdout/stderr ---"
  echo "##[endgroup]"
}

# Capture each command outside command substitution so `set -e`
# cannot discard its output before the failure is diagnosed.
run_preflight() {
  local label="$1"
  local output_file="$2"
  shift 2
  local started_at finished_at status
  started_at=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)

  echo "##[group]Preflight: $label"
  printf 'Command:'
  printf ' %q' "$@"
  printf '\nStarted: %s\n' "$started_at"

  set +e
  "$@" >"$output_file" 2>&1
  status=$?
  set -e

  finished_at=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)
  echo "Finished: $finished_at"
  echo "Exit code: $status"
  echo "Captured bytes: $(wc -c < "$output_file")"
  if [ "$status" -ne 0 ]; then
    echo "--- combined stdout/stderr ---"
    cat "$output_file"
    echo "--- end combined stdout/stderr ---"
  fi
  echo "##[endgroup]"

  if [ "$status" -ne 0 ]; then
    echo "##vso[task.logissue type=error]$label failed with exit code $status"
    debug_failed_preflight "$label" "$@"
    exit "$status"
  fi
}

agent_help="$PREFLIGHT_DIR/agent-init-help.log"
run_preflight "azd ai agent init --help" "$agent_help" azd ai agent init --help
for flag in -- "--deploy-mode" "--runtime" "--entry-point"; do
  if ! grep -q -- "$flag" "$agent_help"; then
    echo "##vso[task.logissue type=error]azd ai agent init does not expose '$flag' — extension is too old"
    echo "--- combined stdout/stderr ---"
    cat "$agent_help"
    echo "--- end combined stdout/stderr ---"
    exit 1
  fi
done
echo "PASS azd ai agent init exposes --deploy-mode / --runtime / --entry-point"

toolbox_delete_help="$PREFLIGHT_DIR/toolbox-delete-help.log"
run_preflight "azd ai toolbox delete --help" "$toolbox_delete_help" azd ai toolbox delete --help
for flag in "--project-endpoint" "--force"; do
  if ! grep -q -- "$flag" "$toolbox_delete_help"; then
    echo "##vso[task.logissue type=error]azd ai toolbox delete does not expose '$flag' — extension is too old"
    echo "--- combined stdout/stderr ---"
    cat "$toolbox_delete_help"
    echo "--- end combined stdout/stderr ---"
    exit 1
  fi
done

run_preflight "azd ai toolbox list --help" \
  "$PREFLIGHT_DIR/toolbox-list-help.log" azd ai toolbox list --help
run_preflight "azd ai toolbox versions list --help" \
  "$PREFLIGHT_DIR/toolbox-versions-list-help.log" azd ai toolbox versions list --help
echo "PASS azd ai toolbox supports list/version verification and project-scoped cleanup"
STEP_VERIFY_AZD_EXT_SUPPORTS_DEPLOY_MODE
    ;;
  scaffold)
    echo "##[section]Verify Azure auth"
    AZURE_SUBSCRIPTION_ID="$PHASE_AZURE_SUBSCRIPTION_ID" bash /dev/fd/3 3<<'STEP_VERIFY_AZURE_AUTH'
set -euo pipefail
azd config set defaults.subscription "$AZURE_SUBSCRIPTION_ID"
echo "Subscription ID: $AZURE_SUBSCRIPTION_ID"
echo "--- az account show ---"
az account show --query "{subscriptionId:id, tenantId:tenantId, state:state}" -o table
echo "--- ARM test: list locations ---"
az rest --method GET \
  --url "https://management.azure.com/subscriptions/$AZURE_SUBSCRIPTION_ID/locations?api-version=2022-01-01" \
  --query "value[0].name" -o tsv
STEP_VERIFY_AZURE_AUTH
    echo "##[section]Scaffold agent project"
    REPO_ROOT="$PHASE_REPO_ROOT" BUILD_ID="$PHASE_BUILD_ID" \
    JOB_ATTEMPT="$PHASE_JOB_ATTEMPT" COMBO_ID="$PHASE_COMBO_ID" \
    AZURE_AI_PROJECT_ID="$PHASE_AZURE_AI_PROJECT_ID" \
    TOOLBOX_PROJECT_ID="$PHASE_TOOLBOX_PROJECT_ID" \
    TOOLBOX_PROJECT_ID_WESTUS2="$PHASE_TOOLBOX_PROJECT_ID_WESTUS2" \
    GH_PAT="$PHASE_GH_PAT" github_pat="$PHASE_github_pat" \
    PLAYWRIGHT_SERVICE_ACCESS_TOKEN="$PHASE_PLAYWRIGHT_SERVICE_ACCESS_TOKEN" \
    RAI_POLICY_ID="$PHASE_RAI_POLICY_ID" SKIP_ACR_CREATION="$PHASE_SKIP_ACR_CREATION" \
      timeout --kill-after=30s 5m bash /dev/fd/3 3<<'STEP_SCAFFOLD_AGENT_PROJECT'
set -euo pipefail
AGENT_NAME="$FOUNDRY_AGENT_NAME"

mkdir -p "$WORK_DIR" && cd "$WORK_DIR"
# Toolbox samples target a dedicated Foundry project
# (TOOLBOX_PROJECT_ID). Samples flagged useWestus2 deploy to the
# westus2 project where the MCP tool-name namespace fix is live.
if [ "$USE_WESTUS2" = "true" ]; then
  PROJECT_ID="$TOOLBOX_PROJECT_ID_WESTUS2"; project_id_var="TOOLBOX_PROJECT_ID_WESTUS2"
elif [ "$IS_TOOLBOX" = "true" ]; then
  PROJECT_ID="$TOOLBOX_PROJECT_ID"; project_id_var="TOOLBOX_PROJECT_ID"
else
  PROJECT_ID="$AZURE_AI_PROJECT_ID"; project_id_var="AZURE_AI_PROJECT_ID"
fi
# An unset ADO variable macro-expands to the literal '$(NAME)',
# which azd would otherwise accept as a project id and fail on
# much later with an unrelated-looking error.
if [ -z "$PROJECT_ID" ] || [[ "$PROJECT_ID" == \$\(*\) ]]; then
  echo "##vso[task.logissue type=error]$project_id_var is not set, so $SAMPLE_PATH has no Foundry project to deploy into."
  echo "Add $project_id_var to the 'samples-hosted-agents-ci' variable group."
  exit 1
fi
# Force a fresh agent definition hash on every CI attempt by
# rewriting the agent's description to a unique CI string. This
# prevents Foundry from short-circuiting to a cached version on
# job re-runs (where the build id stays the same but the job
# attempt increments) and provides an audit trail — every
# deployed agent self-identifies its CI provenance in the
# Foundry portal.
# NOTE: The description lives on the azure.ai.agent service
# inside azure.yaml. We target the service whose `host:` is
# azure.ai.agent and set (or insert) its `description:`
# specifically — other services (e.g. azure.ai.toolbox) may
# carry their own `description:`.
MANIFEST_SRC="$REPO_ROOT/$SAMPLE_PATH/azure.yaml"
CI_DESC="CI build $BUILD_ID attempt $JOB_ATTEMPT $COMBO_ID ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
if [ "$(yq '[.services[] | select(.host == "azure.ai.agent")] | length' "$MANIFEST_SRC")" = "0" ]; then
  echo "No azure.ai.agent service found; leaving azure.yaml unchanged."
else
  CI_DESC="$CI_DESC" yq -i '(.services[] | select(.host == "azure.ai.agent") | .description) = strenv(CI_DESC)' "$MANIFEST_SRC"
  echo "Set agent description -> $CI_DESC"
fi
# Inject the real RAI policy ARM ID into azure.yaml before init.
# Targets only the agent service's rai_policy entry that still
# carries a documented placeholder, so it is a no-op for every
# sample that lacks it. Two placeholder forms are recognized:
# the canonical ARM-ID placeholder (content-safety sample) and
# the ${RAI_POLICY_ID} azd variable used by layered samples
# whose egress policy is normally provisioned by a Bicep layer —
# since CI runs with SKIP_PROVISION, that layer output never
# materializes. Fails fast if a placeholder is present but
# RAI_POLICY_ID is unset/invalid.
RAI_PLACEHOLDER="/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<account>/raiPolicies/<policy-name>"
RAI_PLACEHOLDER_VAR='${RAI_POLICY_ID}'
if [ "$(RAI_PLACEHOLDER="$RAI_PLACEHOLDER" RAI_PLACEHOLDER_VAR="$RAI_PLACEHOLDER_VAR" yq '[.services[] | select(.host == "azure.ai.agent") | .policies[]? | select(.type == "rai_policy") | select(.raiPolicyName == strenv(RAI_PLACEHOLDER) or .raiPolicyName == strenv(RAI_PLACEHOLDER_VAR))] | length' "$MANIFEST_SRC")" = "0" ]; then
  echo "No RAI policy placeholder in azure.yaml; skipping policy injection."
else
  RAI_POLICY_ID="${RAI_POLICY_ID:-}"
  if [ -z "$RAI_POLICY_ID" ] || [[ "$RAI_POLICY_ID" == \$\(*\) ]]; then
    echo "##vso[task.logissue type=error]azure.yaml has an RAI policy placeholder but AZURE_AI_RAI_POLICY_ID is not set."
    exit 1
  fi
  if ! printf '%s' "$RAI_POLICY_ID" | grep -qiE '^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.CognitiveServices/accounts/[^/]+/raiPolicies/[^/]+$'; then
    echo "##vso[task.logissue type=error]AZURE_AI_RAI_POLICY_ID must be the full ARM ID of a Microsoft.CognitiveServices raiPolicies resource."
    exit 1
  fi
  RAI_POLICY_ID="$RAI_POLICY_ID" yq -i '(.services[] | select(.host == "azure.ai.agent") | .policies[]? | select(.type == "rai_policy") | .raiPolicyName) = strenv(RAI_POLICY_ID)' "$MANIFEST_SRC"
  echo "Injected RAI policy into azure.yaml (policy: ${RAI_POLICY_ID##*/})."
fi
# Validate the Browser Automation secret is present when the
# sample templates it into a connection credential (no-prompt
# init requires every secret placeholder to be resolvable).
if grep -q 'PLAYWRIGHT_SERVICE_ACCESS_TOKEN' "$MANIFEST_SRC"; then
  if [ -z "${PLAYWRIGHT_SERVICE_ACCESS_TOKEN:-}" ] || [[ "$PLAYWRIGHT_SERVICE_ACCESS_TOKEN" == \$\(*\) ]]; then
    echo "##vso[task.logissue type=error]Missing Browser Automation secret for no-prompt init: PLAYWRIGHT_SERVICE_ACCESS_TOKEN"
    exit 1
  fi
fi
# Build the `azd ai agent init` command in a single array so we
# can echo the exact invocation before running it.
AZD_ARGS=(
  ai agent init
  -m "$REPO_ROOT/$SAMPLE_PATH/azure.yaml"
  --project-id "$PROJECT_ID"
  --no-prompt
  --environment "$AZD_ENV_NAME"
)
if [ "$DEPLOY_MODE" = "code" ]; then
  AZD_ARGS+=(
    --deploy-mode code
    --runtime "$SAMPLE_RUNTIME"
    --entry-point "$ENTRY_POINT"
    --dep-resolution "$DEP_RESOLUTION"
  )
else
  AZD_ARGS+=(
    --deploy-mode container
  )
fi
# Pretty-print the resolved command so reviewers can copy/paste
# it locally to reproduce.
echo "── Resolved azd command ───────────────────────────────"
printf '  azd'
for a in "${AZD_ARGS[@]}"; do
  case "$a" in *[[:space:]]*) printf " \\\\\n    %q" "$a" ;; *) printf " \\\\\n    %s" "$a" ;; esac
done
printf '\n──────────────────────────────────────────────────────\n'
echo "deployMode     = $DEPLOY_MODE"
echo "runtime        = $SAMPLE_RUNTIME"
echo "entryPoint     = $ENTRY_POINT"
echo "depResolution  = $DEP_RESOLUTION"
echo "language       = $SAMPLE_LANGUAGE"
echo
( set -x; azd "${AZD_ARGS[@]}" )

if [ ! -f azure.yaml ] && [ -f "$SAMPLE_NAME/azure.yaml" ]; then
  shopt -s dotglob nullglob
  mv "$SAMPLE_NAME"/* .
  shopt -u dotglob nullglob
  rmdir "$SAMPLE_NAME"
fi
[ -f azure.yaml ] || { echo "##vso[task.logissue type=error]azd ai agent init did not create azure.yaml"; exit 1; }

# `azd ai agent init` adopts azure.yaml as the project manifest
# and scaffolds the agent source under src/<agent>/. Some flows
# only scaffold the manifest; when the scaffolded service
# directory has no source files, copy them from the sample's
# src/<agent>/ directory in the repo.
SERVICE_SRC="src/$SAMPLE_NAME"
if [ ! -d "$SERVICE_SRC" ] && [ -d "$SAMPLE_NAME" ]; then
  SERVICE_SRC="$SAMPLE_NAME"
fi
SAMPLE_SRC="$REPO_ROOT/$SAMPLE_PATH/src/$SAMPLE_NAME"
if [ ! -d "$SAMPLE_SRC" ]; then
  # Fall back to the sample root for any sample not yet migrated.
  SAMPLE_SRC="$REPO_ROOT/$SAMPLE_PATH"
fi
if [ ! -f "$SERVICE_SRC/main.py" ] && [ ! -f "$SERVICE_SRC/Program.cs" ]; then
  echo "Scaffolded service has no source — copying from sample directory: $SAMPLE_SRC"
  mkdir -p "$SERVICE_SRC"
  cp -a "$SAMPLE_SRC"/. "$SERVICE_SRC/"
  # Remove non-source files that shouldn't be in the build context
  rm -f "$SERVICE_SRC/azure.yaml" "$SERVICE_SRC/.env" \
        "$SERVICE_SRC/.env.example" "$SERVICE_SRC/README.md" \
        "$SERVICE_SRC/.foundry-agent-build.log" \
        "$SERVICE_SRC/test-payload.txt" "$SERVICE_SRC/test-payload.json"
else
  echo "Scaffolded service already has source — skipping source copy"
fi
echo "Contents of $SERVICE_SRC:" && ls -la "$SERVICE_SRC"

# Rename the agent so each matrix job deploys to a UNIQUE
# Foundry agent. Without this, the bare sample name is used and:
#   - container + code arms of the same sample collide on one
#     agent (each arm pushes a version; "latest" flips by
#     publish order, so the invoke routes to the wrong code)
#   - parallel toolbox matrix jobs all collapse onto one agent
# The azure.ai.agents postdeploy handler reads
# AGENT_<service-key>_VERSION and then fetches the agent version
# using that same key as the agent name, so the service key and
# the agent `name:` must both become AGENT_NAME or it 404s.
if [ -f azure.yaml ]; then
  # Also flip any azd-scaffolded `remoteBuild: true` to false.
  # ACR Tasks remote build frequently fails to expose
  # rawtext.log in time for azd's log streamer, then azd falls
  # back to a local publish path without a local package
  # artifact. CI agents have Docker, so build/push locally.
  AGENT_NAME="$AGENT_NAME" yq -i '
    .name = strenv(AGENT_NAME) |
    (.services[] | select(.host == "azure.ai.agent") | .name) = strenv(AGENT_NAME) |
    (.. | select(has("remoteBuild")) | .remoteBuild) = false |
    .services = (.services | to_entries | map(select(.value.host == "azure.ai.agent").key = strenv(AGENT_NAME)) | from_entries)
  ' azure.yaml
  if [ "$(AGENT_NAME="$AGENT_NAME" yq '.services | has(strenv(AGENT_NAME))' azure.yaml)" != "true" ]; then
    echo "##vso[task.logissue type=error]Failed to update azure.yaml agent service key to $AGENT_NAME"
    exit 1
  fi
  echo "Renamed agent → $AGENT_NAME"
  AGENT_NAME="$AGENT_NAME" yq '{"name": .name, "agentServiceKey": (.services | to_entries | map(select(.value.host == "azure.ai.agent")) | .[0].key), "agentName": (.services[] | select(.host == "azure.ai.agent") | .name)}' azure.yaml

  # Shared-toolbox cells drop the unused sample toolbox and upstream
  # connections before provision/verification/deploy, avoiding repeated
  # ARM writes to shared connections. Other cells isolate their owned
  # toolboxes. Only this temporary azure.yaml is rewritten.
  "$REPO_ROOT/.azure-pipelines/scripts/hosted-agents/scripts/prepare-hosted-agent-ci-toolboxes.sh" \
    azure.yaml \
    "$CI_TOOLBOX_STATE_FILE" \
    "$BUILD_ID" \
    "$JOB_ATTEMPT" \
    "$COMBO_ID" \
    "${TOOLBOX_URL:-}"
fi
# Fail fast if the RAI policy placeholder survived into
# azure.yaml (e.g. azd dropped the policies block at init).
if [ -f azure.yaml ] && grep -Fq "raiPolicies/<policy-name>" azure.yaml; then
  echo "##vso[task.logissue type=error]RAI policy placeholder survived into azure.yaml — policy injection/propagation failed."
  exit 1
fi
# Some templates scaffold the azd project in ./<agent-name>/.
# Normalize to the working directory so all subsequent azd
# commands resolve azure.yaml correctly.
if [ ! -f azure.yaml ] && [ -f "$SAMPLE_NAME/azure.yaml" ]; then
  echo "Flattening nested azd project directory: $SAMPLE_NAME"
  shopt -s dotglob nullglob
  mv "$SAMPLE_NAME"/* .
  rmdir "$SAMPLE_NAME"
fi
STEP_SCAFFOLD_AGENT_PROJECT
    echo "##[section]Configure azd environment"
    GH_PAT="$PHASE_GH_PAT" bash /dev/fd/3 3<<'STEP_CONFIGURE_AZD_ENVIRONMENT'
set -euo pipefail
cd "$WORK_DIR"

azd env set AZURE_SUBSCRIPTION_ID "$AZURE_SUBSCRIPTION_ID"
azd env set AZURE_LOCATION "$AZURE_LOCATION"
azd env set enableHostedAgentVNext true

# Strip BOM/CR and trim leading/trailing whitespace. Uses sed
# (not xargs) so values containing quotes/apostrophes are
# preserved verbatim — xargs treats quotes specially and aborts
# with "unmatched single quote" on values like "don't".
sanitize() { printf '%s' "$1" | sed -e 's/^\xEF\xBB\xBF//' -e 's/\r//g' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'; }

# An unset ADO variable macro-expands to the literal '$(NAME)'.
unset_macro() { [[ "${1:-}" == \$\(*\) ]]; }
optional() { if unset_macro "${1:-}"; then printf ''; else printf '%s' "${1:-}"; fi; }

# ponytail: GitHub Actions could dump every repo variable via
# toJson(vars); Azure Pipelines has no equivalent, so the
# passthrough is a prefix allow-list over the task environment
# (variable-group values land there). Add a prefix here if a new
# variable falls outside the set.
PASSTHROUGH_PREFIXES="AZURE_ FOUNDRY_ TOOLBOX_ MODEL_ OPENAI_ BING_ SEARCH_ STORAGE_ SERVICEBUS_ CONTENT_SAFETY_ PLAYWRIGHT_ SKIP_ CLOUD_E2E_"
# Injected by the agent / az CLI, not configuration, plus the
# names already set above. AZURE_DEV_COLLECT_TELEMETRY is azd's
# own opt-out knob, read from the process environment — it does
# not belong in the azd environment file.
PASSTHROUGH_DENY=" AZURE_HTTP_USER_AGENT AZURE_CONFIG_DIR AZURE_EXTENSION_DIR AZURE_CORE_COLLECT_TELEMETRY AZURE_CORE_ONLY_SHOW_ERRORS AZURE_DEV_COLLECT_TELEMETRY AZURE_SERVICE_CONNECTION AZD_ENV_NAME AZURE_SUBSCRIPTION_ID AZURE_LOCATION "

echo "Passing through pipeline variables to azd:"
while IFS= read -r -d '' kv; do
  key="${kv%%=*}"
  value="${kv#*=}"
  [ -z "$value" ] && continue
  unset_macro "$value" && continue
  case "$PASSTHROUGH_DENY" in *" $key "*) continue ;; esac
  matched=false
  for prefix in $PASSTHROUGH_PREFIXES; do
    case "$key" in "$prefix"*) matched=true; break ;; esac
  done
  [ "$matched" = "true" ] || continue
  azd env set "$key" "$(sanitize "$value")"
  echo "  • $key"
done < <(env -0)

# Mirror AZURE_OPENAI_DEPLOYMENT → AZURE_AI_MODEL_DEPLOYMENT_NAME
# with a gpt-4o default. Runs after the loop so the default
# applies when AZURE_OPENAI_DEPLOYMENT is unset/empty.
OPENAI_EP="$(optional "${AZURE_OPENAI_ENDPOINT:-}")"
OPENAI_DEP="$(optional "${AZURE_OPENAI_DEPLOYMENT:-}")"
if [ -n "$OPENAI_EP" ]; then
  azd env set AZURE_OPENAI_DEPLOYMENT "$(sanitize "${OPENAI_DEP:-gpt-4o}")"
  # Samples read AZURE_AI_MODEL_DEPLOYMENT_NAME (Foundry
  # AIProjectClient) — mirror AZURE_OPENAI_DEPLOYMENT.
  azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "$(sanitize "${OPENAI_DEP:-gpt-4o}")"
  echo "Azure OpenAI env vars set"
else
  echo "##vso[task.logissue type=warning]AZURE_OPENAI_ENDPOINT not configured - LLM samples will fail"
fi

# The GitHub Copilot SDK sample requires a fine-grained PAT.
azd env set GITHUB_TOKEN "$(optional "${GH_PAT:-}")"

# Secret manifest parameters must be available at init time and
# in the azd environment.
PLAYWRIGHT_TOKEN="$(optional "${PLAYWRIGHT_SERVICE_ACCESS_TOKEN:-}")"
[ -n "$PLAYWRIGHT_TOKEN" ] && azd env set PLAYWRIGHT_SERVICE_ACCESS_TOKEN "$PLAYWRIGHT_TOKEN"

# For toolbox-consuming samples, derive TOOLBOX_NAME from the
# per-cell toolbox URL so the agent-framework server-side
# resolution (`client.get_toolbox(TOOLBOX_NAME)`) picks the same
# toolbox the matrix cell is targeting. Falls back to the global
# TOOLBOX_NAME variable for non-toolbox samples.
if [ -n "$TOOLBOX_URL" ]; then
  DERIVED_TOOLBOX_NAME="$(echo "$TOOLBOX_URL" | sed -n 's@.*/toolboxes/\([^/]*\)/.*@\1@p')"
  azd env set TOOLBOX_NAME "${DERIVED_TOOLBOX_NAME:-$(optional "${TOOLBOX_NAME:-}")}"
elif [ -f "$CI_TOOLBOX_STATE_FILE" ] && [ "$(jq '.toolboxes | length' "$CI_TOOLBOX_STATE_FILE")" -gt 0 ]; then
  # Non-cartesian samples such as responses/06-files consume the
  # toolbox declared in their own manifest. Point TOOLBOX_NAME at
  # the cell-owned name generated during scaffold.
  azd env set TOOLBOX_NAME "$(jq -r '.toolboxes[0].name' "$CI_TOOLBOX_STATE_FILE")"
else
  azd env set TOOLBOX_NAME "$(optional "${TOOLBOX_NAME:-}")"
fi

# ── Per-cell toolbox project overrides ────────────────
# The auto-loop above set every matching variable. For toolbox
# cells we re-point project + ACR + model at the dedicated
# TOOLBOX_PROJECT_*. useWestus2 routes to the westus2 fallback
# (kept as a hatch in case the ncus path regresses).
#
# NOTE: a westus2 cell deploys into a different subscription, so
# enabling that hatch also requires a service connection scoped
# to TOOLBOX_SUBSCRIPTION_ID_WESTUS2 on the deploy tasks.
if [ "$USE_WESTUS2" = "true" ]; then
  azd env set AZURE_SUBSCRIPTION_ID "$(sanitize "$(optional "${TOOLBOX_SUBSCRIPTION_ID_WESTUS2:-}")")"
  azd env set AZURE_LOCATION "westus2"
  azd env set AZURE_RESOURCE_GROUP "$(sanitize "$(optional "${TOOLBOX_RESOURCE_GROUP_WESTUS2:-${TOOLBOX_RESOURCE_GROUP:-${AZURE_RESOURCE_GROUP:-}}}")")"
  azd env set AZURE_AI_ACCOUNT_NAME "$(sanitize "$(optional "${TOOLBOX_AI_ACCOUNT_NAME_WESTUS2:-${TOOLBOX_AI_ACCOUNT_NAME:-${AZURE_AI_ACCOUNT_NAME:-}}}")")"
  azd env set AZURE_AI_PROJECT_NAME "$(sanitize "$(optional "${TOOLBOX_AI_PROJECT_NAME_WESTUS2:-${TOOLBOX_AI_PROJECT_NAME:-${AZURE_AI_PROJECT_NAME:-}}}")")"
  azd env set AZURE_AI_PROJECT_ENDPOINT "$(sanitize "$(optional "${TOOLBOX_PROJECT_ENDPOINT_WESTUS2:-}")")"
  azd env set AZURE_AI_PROJECT_ID "$(sanitize "$(optional "${TOOLBOX_PROJECT_ID_WESTUS2:-}")")"
  azd env set FOUNDRY_PROJECT_ENDPOINT "$(sanitize "$(optional "${TOOLBOX_PROJECT_ENDPOINT_WESTUS2:-}")")"
  azd env set AZURE_CONTAINER_REGISTRY_ENDPOINT "$(sanitize "$(optional "${TOOLBOX_CONTAINER_REGISTRY_ENDPOINT_WESTUS2:-${AZURE_CONTAINER_REGISTRY_ENDPOINT:-}}")")"
  azd env set TOOLBOX_ENDPOINT "$(sanitize "$TOOLBOX_URL")"
  MODEL_NAME="$(sanitize "$(optional "${TOOLBOX_MODEL_DEPLOYMENT_NAME:-}")")"
  azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "$MODEL_NAME"
  azd env set MODEL_DEPLOYMENT_NAME "$MODEL_NAME"
elif [ "$IS_TOOLBOX" = "true" ]; then
  azd env set AZURE_RESOURCE_GROUP "$(sanitize "$(optional "${TOOLBOX_RESOURCE_GROUP:-${AZURE_RESOURCE_GROUP:-}}")")"
  azd env set AZURE_AI_ACCOUNT_NAME "$(sanitize "$(optional "${TOOLBOX_AI_ACCOUNT_NAME:-${AZURE_AI_ACCOUNT_NAME:-}}")")"
  azd env set AZURE_AI_PROJECT_NAME "$(sanitize "$(optional "${TOOLBOX_AI_PROJECT_NAME:-${AZURE_AI_PROJECT_NAME:-}}")")"
  azd env set AZURE_AI_PROJECT_ENDPOINT "$(sanitize "$(optional "${TOOLBOX_PROJECT_ENDPOINT:-}")")"
  azd env set AZURE_AI_PROJECT_ID "$(sanitize "$(optional "${TOOLBOX_PROJECT_ID:-}")")"
  azd env set FOUNDRY_PROJECT_ENDPOINT "$(sanitize "$(optional "${TOOLBOX_PROJECT_ENDPOINT:-}")")"
  azd env set TOOLBOX_ENDPOINT "$(sanitize "$TOOLBOX_URL")"
  MODEL_NAME="$(sanitize "$(optional "${TOOLBOX_MODEL_DEPLOYMENT_NAME:-}")")"
  azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "$MODEL_NAME"
  azd env set MODEL_DEPLOYMENT_NAME "$MODEL_NAME"
fi

echo "══════════════════════════════════════════"
echo "  Cloud E2E Configuration"
echo "══════════════════════════════════════════"
echo "  SKIP_PROVISION:  $(optional "${SKIP_PROVISION:-}")"
echo "  AZURE_LOCATION:  $AZURE_LOCATION"
echo "  AZD_ENV_NAME:    $AZD_ENV_NAME"
echo "  Resource Group:  $(optional "${AZURE_RESOURCE_GROUP:-}")"
echo "  AI Account:      $(optional "${AZURE_AI_ACCOUNT_NAME:-}")"
echo "  AI Project:      $(optional "${AZURE_AI_PROJECT_NAME:-}")"
echo "  Project ID:      $(optional "${AZURE_AI_PROJECT_ID:-}")"
echo "  Project Endpoint:$(optional "${AZURE_AI_PROJECT_ENDPOINT:-}")"
echo "  ACR Endpoint:    $(optional "${AZURE_CONTAINER_REGISTRY_ENDPOINT:-}")"
echo "  OpenAI Endpoint: ${OPENAI_EP:-<not set>}"
echo "  OpenAI Deploy:   ${OPENAI_DEP:-gpt-4o (default)}"
echo "══════════════════════════════════════════"

echo ""
echo "=== Configured Azure variable names (values omitted) ==="
azd env get-values | cut -d= -f1 | grep -E "^(AZURE_OPENAI|AZURE_AI_PROJECT)" || echo "(no matching vars)"
STEP_CONFIGURE_AZD_ENVIRONMENT
    ;;
  provision)
    echo "##[section]Provision Azure resources"
    bash /dev/fd/3 3<<'STEP_PROVISION_AZURE_RESOURCES'
set -euo pipefail
cd "$WORK_DIR"
azd provision --no-prompt
STEP_PROVISION_AZURE_RESOURCES
    ;;
  prepare-deploy)
    echo "##[section]Verify Foundry project connections"
    bash /dev/fd/3 3<<'STEP_VERIFY_FOUNDRY_PROJECT_CONNECTIONS'
set -euo pipefail
cd "$WORK_DIR"

mapfile -t required_connections < <(
  yq -r '
    .services
    | to_entries[]
    | select(.value.host == "azure.ai.connection")
    | .key
  ' azure.yaml
)
if [ ${#required_connections[@]} -eq 0 ]; then
  echo "No azure.ai.connection services declared; skipping connection verification."
  exit 0
fi

endpoint="$(azd env get-value AZURE_AI_PROJECT_ENDPOINT)"
if [ -z "$endpoint" ]; then
  echo "##vso[task.logissue type=error]AZURE_AI_PROJECT_ENDPOINT is not set in the active azd environment"
  exit 1
fi

connections_json="$(azd ai connection list \
  --project-endpoint "$endpoint" \
  --output json \
  --no-prompt)"
echo "Connections in the selected Foundry project:"
jq -r '.[].name' <<< "$connections_json"

missing=()
for name in "${required_connections[@]}"; do
  if ! jq -e --arg name "$name" 'any(.[]; .name == $name)' \
      <<< "$connections_json" >/dev/null; then
    missing+=("$name")
  fi
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "##vso[task.logissue type=error]Missing Foundry project connections at $endpoint: ${missing[*]}"
  exit 1
fi

connection_names=$(IFS=,; echo "${required_connections[*]}")
azd env set AZURE_AI_PROJECT_CONNECTION_NAMES "$connection_names"
azd env set AZURE_AI_PROJECT_CONNECTIONS_PROJECT_ENDPOINT "$endpoint"
echo "Verified Foundry project connections: $connection_names"
STEP_VERIFY_FOUNDRY_PROJECT_CONNECTIONS
    if [ "$IS_TOOLBOX" = "true" ]; then
    echo "##[section]Override toolbox env in azure.yaml"
    bash /dev/fd/3 3<<'STEP_OVERRIDE_TOOLBOX_ENV_IN_AZURE_YAML'
set -euo pipefail
cd "$WORK_DIR"
AZURE_YAML="azure.yaml"
if [ ! -f "$AZURE_YAML" ]; then
  echo "##vso[task.logissue type=warning]$AZURE_YAML not found, skipping toolbox env override"
  exit 0
fi
unset_macro() { [[ "${1:-}" == \$\(*\) ]]; }
optional() { if unset_macro "${1:-}"; then printf ''; else printf '%s' "${1:-}"; fi; }

REPL_TOOLBOX_ENDPOINT="$TOOLBOX_URL"
REPL_MODEL_DEPLOYMENT_NAME="$(optional "${TOOLBOX_MODEL_DEPLOYMENT_NAME:-}")"
REPL_AZURE_AI_MODEL_DEPLOYMENT_NAME="$REPL_MODEL_DEPLOYMENT_NAME"
if [ "$USE_WESTUS2" = "true" ]; then
  REPL_AZURE_AI_PROJECT_ENDPOINT="$(optional "${TOOLBOX_PROJECT_ENDPOINT_WESTUS2:-}")"
else
  REPL_AZURE_AI_PROJECT_ENDPOINT="$(optional "${TOOLBOX_PROJECT_ENDPOINT:-}")"
fi

# Derive TOOLBOX_NAME from the matrix toolbox URL slug
# (e.g. .../toolboxes/file-search/mcp?... -> "file-search") so a
# server-side `client.get_toolbox(name)` resolves the per-cell one.
DERIVED_TOOLBOX_NAME=""
if [ -n "$REPL_TOOLBOX_ENDPOINT" ]; then
  DERIVED_TOOLBOX_NAME=$(printf '%s' "$REPL_TOOLBOX_ENDPOINT" | sed -n 's@.*/toolboxes/\([^/]*\)/.*@\1@p')
  [ -n "$DERIVED_TOOLBOX_NAME" ] && echo "Derived TOOLBOX_NAME from URL: $DERIVED_TOOLBOX_NAME"
fi
# Build the override map (skip empty values) and apply each to the
# azure.ai.agent service's `env:` map with yq, which parses the
# YAML structurally and preserves comments. FOUNDRY_*/AGENT_* are
# reserved by the platform and injected at runtime, so none of
# these keys use those prefixes.
if [ "$(yq '[.services[] | select(.host == "azure.ai.agent")] | length' "$AZURE_YAML")" = "0" ]; then
  echo "##vso[task.logissue type=warning]No azure.ai.agent service found; skipping env override."
else
  set_agent_env() {
    local key="$1" val="$2"
    [ -z "$val" ] && return 0
    key="$key" val="$val" yq -i \
      '(.services[] | select(.host == "azure.ai.agent") | .env[strenv(key)]) = strenv(val)' \
      "$AZURE_YAML"
    echo "  $key=$val"
  }
  echo "Applied toolbox env overrides:"
  set_agent_env TOOLBOX_ENDPOINT "$REPL_TOOLBOX_ENDPOINT"
  set_agent_env MODEL_DEPLOYMENT_NAME "$REPL_MODEL_DEPLOYMENT_NAME"
  set_agent_env AZURE_AI_MODEL_DEPLOYMENT_NAME "$REPL_AZURE_AI_MODEL_DEPLOYMENT_NAME"
  set_agent_env AZURE_AI_PROJECT_ENDPOINT "$REPL_AZURE_AI_PROJECT_ENDPOINT"
  set_agent_env TOOLBOX_NAME "$DERIVED_TOOLBOX_NAME"
fi
# Fail if any unresolved connection-credential mustache
# placeholder ({{...}}) survived init.
if grep -qE '\{\{[^}]+\}\}' "$AZURE_YAML"; then
  echo "##vso[task.logissue type=error]azure.yaml still contains unresolved {{...}} placeholders after init"
  exit 1
fi
STEP_OVERRIDE_TOOLBOX_ENV_IN_AZURE_YAML
    fi
    echo "##[section]Pre-pull Docker base images"
    bash /dev/fd/3 3<<'STEP_PRE_PULL_DOCKER_BASE_IMAGES'
set -euo pipefail
cd "$WORK_DIR"
base_images=$(find src -name Dockerfile \
  -exec awk '/^FROM mcr\.microsoft\.com\// { print $2 }' {} + \
  | sort -u)

if [ -z "$base_images" ]; then
  echo "No MCR base images found to pre-pull"
  exit 0
fi

while IFS= read -r image; do
  [ -z "$image" ] && continue
  echo "Pre-pulling $image"
  for attempt in 1 2 3; do
    if docker pull "$image"; then
      break
    fi
    if [ "$attempt" -eq 3 ]; then
      echo "##vso[task.logissue type=error]Failed to pre-pull $image after 3 attempts"
      exit 1
    fi
    sleep_seconds=$((attempt * 20))
    echo "##vso[task.logissue type=warning]docker pull failed for $image (attempt $attempt/3); retrying in ${sleep_seconds}s"
    sleep "$sleep_seconds"
  done
done <<< "$base_images"
STEP_PRE_PULL_DOCKER_BASE_IMAGES
    ;;
  deploy)
    echo "##[section]Deploy agent"
    bash /dev/fd/3 3<<'STEP_DEPLOY_AGENT'
set -uo pipefail
cd "$WORK_DIR"
echo "Deploying azure.yaml from $(pwd) (credential-bearing manifest omitted)"
# NOTE: use PIPESTATUS[0] to capture azd exit code, not tee's.
#
# Retry on transient container-publish failures. Known flaky
# patterns in the Foundry hosted-agent package service:
#   1) "failed retrieving package result details" — rpc Unknown
#      from the package service when ACR task logs aren't yet
#      readable.
#   2) ACR Tasks log blob "BlobNotFound" on the rawtext.log poll.
#   3) "toomanyrequests" — ACR per-identity rate limit (HTTP 429)
#      when many container matrix jobs push concurrently under
#      the shared CI service principal. Back off past the 60s
#      rolling window with jitter so retries don't re-collide.
# All are timing races; a retry with backoff clears them.
attempt=0
max_attempts=3
while : ; do
  attempt=$((attempt+1))
  echo "─── Deploy attempt $attempt/$max_attempts ───"
  azd deploy --no-prompt 2>&1 | tee /tmp/azd-deploy.log
  azd_exit=${PIPESTATUS[0]}
  if [ $azd_exit -eq 0 ]; then
    echo "Deploy succeeded"
    break
  fi
  transient=false
  if grep -qE "failed retrieving package result details|BlobNotFound|container publish failed: rpc error" /tmp/azd-deploy.log; then
    transient=true
  fi
  # Foundry intermittently returns 401 PermissionDenied when
  # resolving a project connection, for a principal that
  # demonstrably has access. Evidence: the identical request,
  # same service principal and same ai.azure.com audience,
  # returned 200 in two probe runs and 401 in a third — 12/12
  # success within a run, all-or-nothing between runs. RBAC,
  # group and app-permission parity with the working GitHub
  # principal was confirmed via Authorization/checkAccess, and
  # `azd ai connection list` succeeded in a job where the raw
  # HTTP call was denied. Both conditions are required so a
  # genuine permission failure is not retried into silence.
  if grep -q "resolve_project_connection" /tmp/azd-deploy.log &&
     grep -q "PermissionDenied" /tmp/azd-deploy.log; then
    transient=true
    echo "##vso[task.logissue type=warning]Intermittent connection-resolution 401 from Foundry (attempt $attempt) — retrying"
  fi
  throttled=false
  if grep -qiE "toomanyrequests|exceeded the per-identity rate limit" /tmp/azd-deploy.log; then
    transient=true
    throttled=true
  fi
  if [ "$transient" = "true" ] && [ $attempt -lt $max_attempts ]; then
    if [ "$throttled" = "true" ]; then
      backoff=$((60 + RANDOM % 60))
      echo "##vso[task.logissue type=warning]ACR per-identity rate limit hit (attempt $attempt) — backing off ${backoff}s"
    else
      backoff=$((attempt * 30))
      echo "##vso[task.logissue type=warning]Transient publish failure (attempt $attempt) — retrying in ${backoff}s"
    fi
    sleep $backoff
    continue
  fi
  echo "Deploy failed"
  exit 1
done
STEP_DEPLOY_AGENT
    ;;
  verify-deploy)
    echo "##[section]Verify temporary toolbox deployment"
    timeout --kill-after=30s 3m bash /dev/fd/3 3<<'STEP_VERIFY_TEMPORARY_TOOLBOX_DEPLOYMENT'
set -euo pipefail
cd "$WORK_DIR"
if [ ! -f "$CI_TOOLBOX_STATE_FILE" ] || [ "$(jq '.toolboxes | length' "$CI_TOOLBOX_STATE_FILE")" -eq 0 ]; then
  echo "No azure.ai.toolbox services declared; skipping toolbox verification."
  jq -n '{toolboxes:[]}' > "$CI_TOOLBOX_DEPLOY_RESULT"
  exit 0
fi

ENDPOINT="$(azd env get-value AZURE_AI_PROJECT_ENDPOINT)"
results='[]'
while IFS= read -r name; do
  versions=$(azd ai toolbox versions list "$name" \
    --project-endpoint "$ENDPOINT" --output json --no-prompt)
  count=$(jq '.versions | length' <<< "$versions")
  if [ "$count" -lt 1 ]; then
    echo "##vso[task.logissue type=error]Temporary toolbox $name has no published version"
    exit 1
  fi
  # A transient azd deploy retry can legitimately publish more
  # than one version to this cell-owned resource. Isolation and
  # teardown, not an exact count, are the lifecycle invariants.
  version=$(jq -r '.versions[0].version' <<< "$versions")
  results=$(jq -c --arg name "$name" --arg version "$version" --argjson count "$count" \
    '. + [{name:$name,version:$version,versions_count:$count}]' <<< "$results")
  echo "PASS Temporary toolbox $name exists with $count version(s)"
done < <(jq -r '.toolboxes[].name' "$CI_TOOLBOX_STATE_FILE")
jq -n --arg project_endpoint "$ENDPOINT" --argjson toolboxes "$results" \
  '{project_endpoint:$project_endpoint,toolboxes:$toolboxes}' > "$CI_TOOLBOX_DEPLOY_RESULT"
STEP_VERIFY_TEMPORARY_TOOLBOX_DEPLOYMENT
    echo "##[section]Verify deployed agent environment"
    timeout --kill-after=30s 3m bash /dev/fd/3 3<<'STEP_VERIFY_DEPLOYED_AGENT_ENVIRONMENT'
set -euo pipefail
cd "$WORK_DIR"
AGENT_JSON=$(azd ai agent show --no-prompt --output json 2>/dev/null || true)
DEPLOYED_ENV=$(jq -c '.definition.environment_variables // {}' <<< "$AGENT_JSON" 2>/dev/null || echo '{}')
if [ -z "$DEPLOYED_ENV" ] || [ "$DEPLOYED_ENV" = "{}" ] || [ "$DEPLOYED_ENV" = "null" ]; then
  echo "##vso[task.logissue type=warning]Could not read deployed environment variables from 'azd ai agent show'; skipping check"
  exit 0
fi
echo "Deployed environment variable names (values omitted):"
jq 'keys' <<< "$DEPLOYED_ENV"

# An empty deployed value means something upstream (azd env
# resolution, an env-shape precedence change, a rewrite that
# silently matched nothing) dropped it. TOOLBOX_NAME is fatal at
# container startup, so fail on it; report the rest so they are
# visible without turning an unset optional secret into a red job.
blank=$(jq -r 'to_entries | map(select(.value == "")) | map(.key) | join(", ")' <<< "$DEPLOYED_ENV")
if [ -n "$blank" ]; then
  echo "##vso[task.logissue type=warning]Deployed agent has empty environment variable(s): $blank"
fi
if jq -e 'has("TOOLBOX_NAME") and .TOOLBOX_NAME == ""' <<< "$DEPLOYED_ENV" >/dev/null; then
  echo "##vso[task.logissue type=error]Deployed agent has an empty TOOLBOX_NAME; the agent cannot resolve its toolbox"
  exit 1
fi

# When the sample owns a cell-scoped toolbox, the deployed
# TOOLBOX_NAME must be that toolbox — not a shared one from the
# committed manifest.
if [ -f "$CI_TOOLBOX_STATE_FILE" ] && [ "$(jq '.toolboxes | length' "$CI_TOOLBOX_STATE_FILE")" -gt 0 ]; then
  # Mirror azd's precedence: the `env:` map overrides
  # `environmentVariables:` (Azure/azure-dev#9149), which is how
  # the per-cell toolbox override takes effect.
  EXPECTED_TOOLBOX=$(yq -r '[.services[] | select(.host == "azure.ai.agent") | select(has("env")) | .env.TOOLBOX_NAME] | .[0] // ""' azure.yaml)
  if [ -z "$EXPECTED_TOOLBOX" ]; then
    EXPECTED_TOOLBOX=$(yq -r '[.services[] | select(.host == "azure.ai.agent") | .environmentVariables[]? | select(.name == "TOOLBOX_NAME") | .value] | .[0] // ""' azure.yaml)
  fi
  DEPLOYED_TOOLBOX=$(jq -r '.TOOLBOX_NAME // ""' <<< "$DEPLOYED_ENV")
  if [ -n "$EXPECTED_TOOLBOX" ] && [ "$EXPECTED_TOOLBOX" != "$DEPLOYED_TOOLBOX" ]; then
    echo "##vso[task.logissue type=error]Deployed TOOLBOX_NAME does not match azure.yaml (expected '$EXPECTED_TOOLBOX', deployed '$DEPLOYED_TOOLBOX')"
    exit 1
  fi
  # Cartesian toolbox cells deliberately point at a shared,
  # externally provisioned toolbox, so ownership only applies to
  # samples that declare their own toolbox service.
  if [ -n "$DEPLOYED_TOOLBOX" ] && [ -z "${TOOLBOX_URL:-}" ] && \
     [ "$(jq -r --arg name "$DEPLOYED_TOOLBOX" '[.toolboxes[] | select(.name == $name)] | length' "$CI_TOOLBOX_STATE_FILE")" -eq 0 ]; then
    echo "##vso[task.logissue type=error]Deployed TOOLBOX_NAME '$DEPLOYED_TOOLBOX' is not a cell-owned toolbox for this job"
    jq '.toolboxes' "$CI_TOOLBOX_STATE_FILE"
    exit 1
  fi
  echo "PASS Deployed TOOLBOX_NAME: ${DEPLOYED_TOOLBOX:-(not declared)}"
fi
STEP_VERIFY_DEPLOYED_AGENT_ENVIRONMENT
    ;;
  diagnose-deploy)
    echo "##[section]Surface Foundry deploy error"
    bash /dev/fd/3 3<<'STEP_SURFACE_FOUNDRY_DEPLOY_ERROR'
set +e
AGENT_NAME="$FOUNDRY_AGENT_NAME"
cd "$WORK_DIR" 2>/dev/null || exit 0
ENDPOINT="$(azd env get-value AZURE_AI_PROJECT_ENDPOINT 2>/dev/null)"
if [ -z "$ENDPOINT" ]; then
  echo "##vso[task.logissue type=warning]AZURE_AI_PROJECT_ENDPOINT not set in azd env — skipping diagnostic"
  exit 0
fi
ENDPOINT="${ENDPOINT%/}"
TOKEN="$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv 2>/dev/null)"
if [ -z "$TOKEN" ]; then
  echo "##vso[task.logissue type=warning]Could not acquire ai.azure.com token — skipping diagnostic"
  exit 0
fi
API_VER="2025-11-15-preview"
FEATURES="CodeAgents=V1Preview,HostedAgents=V1Preview"

echo "##[group]Foundry agent state for $AGENT_NAME"
AGENT_URL="$ENDPOINT/agents/$AGENT_NAME?api-version=$API_VER"
echo "GET $AGENT_URL"
curl -sS -H "Authorization: Bearer $TOKEN" \
     -H "Foundry-Features: $FEATURES" \
     -H "Accept: application/json" \
     "$AGENT_URL" | tee /tmp/agent.json \
     | jq '{id, name, status, error, latest_version: .versions.latest.version}' \
     || echo "Could not parse agent diagnostic response (raw body omitted)"
echo "##[endgroup]"

VERSION=$(jq -r '.versions.latest.version // empty' /tmp/agent.json 2>/dev/null)
if [ -z "$VERSION" ]; then
  echo "##vso[task.logissue type=warning]Could not read latest version from agent GET — skipping version-level diagnostic"
  exit 0
fi

echo "##[group]Foundry agent-version $VERSION (status and error payload)"
VER_URL="$ENDPOINT/agents/$AGENT_NAME/versions/$VERSION?api-version=$API_VER"
echo "GET $VER_URL"
curl -sS -H "Authorization: Bearer $TOKEN" \
     -H "Foundry-Features: $FEATURES" \
     -H "Accept: application/json" \
     "$VER_URL" | tee /tmp/agent-version.json \
     | jq '{id, name, version, status, status_details, error}' \
     || echo "Could not parse agent-version diagnostic response (raw body omitted)"
echo "##[endgroup]"

# Try several common error-location shapes; emit whichever has content.
ERR=$(jq -r '
  .status_details.error.message //
  .status_details.message //
  .error.message //
  .properties.error.message //
  empty' /tmp/agent-version.json 2>/dev/null)
STATUS=$(jq -r '.status // empty' /tmp/agent-version.json 2>/dev/null)
if [ -n "$ERR" ]; then
  echo "##vso[task.logissue type=error]Foundry deploy error (status=$STATUS): $ERR"
else
  echo "##vso[task.logissue type=warning]No error message field found in agent-version response (status=$STATUS) — see status fields above"
fi
STEP_SURFACE_FOUNDRY_DEPLOY_ERROR
    ;;
  session)
    echo "##[section]Wait for agent to be active"
    timeout --kill-after=30s 3m bash /dev/fd/3 3<<'STEP_WAIT_FOR_AGENT_TO_BE_ACTIVE'
set -uo pipefail
cd "$WORK_DIR"
echo "Waiting for agent to reach active state..."
for i in $(seq 1 18); do
  STATUS=$(azd ai agent show --no-prompt 2>&1 | grep -i "status" | head -1 || true)
  echo "  Poll $i/18: $STATUS"
  if echo "$STATUS" | grep -qi "active"; then
    echo "PASS Agent is active"
    exit 0
  fi
  sleep 5
done
echo "##vso[task.logissue type=warning]Agent may not be active yet — proceeding with invoke anyway"
STEP_WAIT_FOR_AGENT_TO_BE_ACTIVE
    echo "##[section]Create agent session"
    REPO_ROOT="$PHASE_REPO_ROOT" timeout --kill-after=30s 15m bash /dev/fd/3 3<<'STEP_CREATE_AGENT_SESSION'
set -euo pipefail
cd "$WORK_DIR"
source "$REPO_ROOT/.azure-pipelines/scripts/hosted-agents/scripts/hosted-agent-retry.sh"
AGENT_JSON=$(azd ai agent show --no-prompt --output json 2>/dev/null || true)
DEPLOYED_AGENT_VERSION=$(jq -r '.version // empty' <<< "$AGENT_JSON" 2>/dev/null || true)
if [ -z "$DEPLOYED_AGENT_VERSION" ]; then
  echo "##vso[task.logissue type=error]Could not resolve the deployed agent version from 'azd ai agent show'"
  exit 1
fi

quota_retries=0
transient_attempt=1
max_transient_attempts=4
backoff=15
session_create_may_have_succeeded=false
while :; do
  set +e
  azd ai agent sessions create \
    --session-id "$CI_AGENT_SESSION_ID" \
    --version "$DEPLOYED_AGENT_VERSION" \
    --no-prompt --output json \
    > /tmp/session-create.txt 2>&1
  create_exit=$?
  set -e
  cat /tmp/session-create.txt
  if [ $create_exit -eq 0 ]; then
    break
  fi
  if [ "$session_create_may_have_succeeded" = "true" ] && \
      grep -qiE "session_already_exists|A session with this ID already exists" /tmp/session-create.txt; then
    echo "##vso[task.logissue type=warning]The earlier create request created the session; continuing with the existing session"
    break
  fi
  if hosted_agent_is_session_quota_error /tmp/session-create.txt; then
    if [ $quota_retries -ge "$HOSTED_AGENT_QUOTA_MAX_RETRIES" ]; then
      echo "##vso[task.logissue type=error]Exhausted $HOSTED_AGENT_QUOTA_MAX_RETRIES session quota retries"
      exit "$create_exit"
    fi
    quota_retries=$((quota_retries + 1))
    quota_delay=$(hosted_agent_quota_retry_delay)
    echo "##vso[task.logissue type=warning]Session quota exceeded; retry $quota_retries/$HOSTED_AGENT_QUOTA_MAX_RETRIES in ${quota_delay}s"
    sleep "$quota_delay"
    continue
  fi
  if [ $transient_attempt -lt $max_transient_attempts ] && \
      grep -qiE "session_not_ready|status[ _]?code[: ]+424|HTTP 424|readiness|still being provisioned|version is still being|server_error|internal server error|received from peer|connection reset by peer|EOF while reading response" /tmp/session-create.txt; then
    if grep -qiE "session_not_ready|status[ _]?code[: ]+424|HTTP 424" /tmp/session-create.txt; then
      session_create_may_have_succeeded=true
    fi
    echo "##vso[task.logissue type=warning]Session create transient attempt $transient_attempt failed; retrying in ${backoff}s"
    sleep "$backoff"
    backoff=$((backoff * 2))
    transient_attempt=$((transient_attempt + 1))
    continue
  fi
  exit "$create_exit"
done
STEP_CREATE_AGENT_SESSION
    ;;
  invoke)
    echo "##[section]Invoke agent"
    bash /dev/fd/3 3<<'STEP_INVOKE_AGENT'
set +e  # Capture errors manually so we can log all turns first
cd "$WORK_DIR" || exit 1
source "$REPO_ROOT/.azure-pipelines/scripts/hosted-agents/scripts/hosted-agent-retry.sh"
if ! FIXTURE_RELATIVE=$(python3 "$REPO_ROOT/.github/scripts/hosted_agent_fixture.py" \
    fixture-dir --sample-dir "$SAMPLE_PATH"); then
  echo "##vso[task.logissue type=error]Could not resolve the hosted-agent test fixture path"
  exit 1
fi
FIXTURE_DIR="$REPO_ROOT/$FIXTURE_RELATIVE"
SPEC_FILE="$FIXTURE_DIR/test-spec.yml"
PAYLOAD_FILE="$FIXTURE_DIR/test-payload.txt"
PLAN_FILE="/tmp/agent-test-plan-${COMBO_ID}.json"
TURN_PLAN="/tmp/agent-turn-plan-${COMBO_ID}.jsonl"
EVIDENCE_DIR="/tmp/agent-test-evidence-${COMBO_ID}"
mkdir -p "$EVIDENCE_DIR"
: > "$TURN_PLAN"

if [ -f "$SPEC_FILE" ]; then
  echo "Using hosted-agent test spec: $SPEC_FILE"
  if ! python3 "$REPO_ROOT/.github/scripts/hosted_agent_test_spec.py" plan \
      --spec "$SPEC_FILE" \
      --toolbox-label "$TOOLBOX_LABEL" \
      --toolbox-query "$TOOLBOX_QUERY" \
      --protocol "$PROTOCOL" \
      --output "$PLAN_FILE"; then
    echo "##vso[task.logissue type=error]Could not build the hosted-agent test execution plan"
    exit 1
  fi
  if ! jq -c '.tests[].turns[]' "$PLAN_FILE" > "$TURN_PLAN"; then
    echo "##vso[task.logissue type=error]Could not resolve turns from $PLAN_FILE"
    exit 1
  fi
  # A nonmatching condition is not_applicable. Do not silently
  # apply a matrix toolbox query to some other declared test.
else
  # Legacy migration path: a toolbox matrix query replaces the
  # line-oriented payload; otherwise use test-payload.txt or
  # defaults.
  if [ -n "$TOOLBOX_QUERY" ] && [ "$IS_TOOLBOX" = "true" ]; then
    echo "Using legacy toolbox-specific query: $TOOLBOX_QUERY"
    PAYLOAD_FILE="/tmp/toolbox-query-${COMBO_ID}.txt"
    if [ "$PROTOCOL" = "invocations" ]; then
      jq -nc --arg q "$TOOLBOX_QUERY" '{query:$q}' > "$PAYLOAD_FILE"
    else
      printf '%s\n' "$TOOLBOX_QUERY" > "$PAYLOAD_FILE"
    fi
  elif [ ! -f "$PAYLOAD_FILE" ]; then
    echo "No test spec or legacy payload found — generating default 3-turn payload"
    PAYLOAD_FILE="/tmp/default-payload-${COMBO_ID}.txt"
    if [ "$PROTOCOL" = "invocations" ]; then
      for i in 1 2 3; do echo '{"query":"analyze dataset"}' >> "$PAYLOAD_FILE"; done
    else
      for i in 1 2 3; do echo "Hello from CI" >> "$PAYLOAD_FILE"; done
    fi
  fi
  legacy_turn=0
  while IFS= read -r legacy_line || [ -n "$legacy_line" ]; do
    [ -z "$legacy_line" ] && continue
    legacy_turn=$((legacy_turn + 1))
    jq -nc --argjson turn "$legacy_turn" --arg input "$legacy_line" \
      '{turn:$turn,global_turn:$turn,serialized_input:$input,assertions:[]}' \
      >> "$TURN_PLAN"
  done < "$PAYLOAD_FILE"
fi

echo "Resolved turn plan:"
jq . "$TURN_PLAN"
echo ""

# For the responses protocol we POST directly to the agent's
# OpenAI-compatible /responses endpoint and extract the
# assistant text from the JSON response. `azd ai agent invoke`
# prints only header/footer metadata and never includes the
# actual response body, so it cannot validate the model's reply.
# For invocations we still use `azd ai agent invoke` (the
# payload shape is opaque and validated by exit code only).
AGENT_JSON=$(azd ai agent show --no-prompt --output json 2>/dev/null)
DEPLOYED_AGENT_VERSION=$(jq -r '.version // empty' <<< "$AGENT_JSON")
if [ -z "$DEPLOYED_AGENT_VERSION" ]; then
  echo "##vso[task.logissue type=error]Could not resolve the deployed agent version from 'azd ai agent show'"
  exit 1
fi
echo "Invoking deployed agent version: $DEPLOYED_AGENT_VERSION"

AGENT_RESPONSES_URL=""
AAD_TOKEN=""
if [ "$PROTOCOL" = "responses" ]; then
  AGENT_RESPONSES_URL=$(jq -r '.agent_endpoints.responses // empty' <<< "$AGENT_JSON")
  if [ -z "$AGENT_RESPONSES_URL" ]; then
    echo "##vso[task.logissue type=error]Could not resolve agent responses endpoint from 'azd ai agent show'"
    exit 1
  fi
  AAD_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
  echo "Agent responses endpoint: $AGENT_RESPONSES_URL"
fi

# Invoke each resolved turn in order. The final retry attempt is
# copied into a stable evidence directory for semantic
# evaluation and upload.
turn=0
overall_exit=0
quota_retries=0
while IFS= read -r turn_record || [ -n "$turn_record" ]; do
  [ -z "$turn_record" ] && continue
  turn=$(jq -r '.global_turn' <<< "$turn_record")
  line=$(jq -r '.serialized_input' <<< "$turn_record")
  echo "─── Turn $turn ───"
  echo "Prompt: $line"
  printf '%s\n' "$line" > "$EVIDENCE_DIR/turn-$turn-input.txt"

  TURN_FILE="/tmp/turn-${COMBO_ID}-${turn}"
  TURN_RECORD_FILE="/tmp/turn-record-${COMBO_ID}-${turn}.json"
  printf '%s\n' "$line" > "$TURN_FILE"
  printf '%s\n' "$turn_record" > "$TURN_RECORD_FILE"

  request_attempt=0
  transient_attempt=1
  max_transient_attempts=4
  backoff=15
  model_throttle_retries=0
  max_model_throttle_retries=3
  model_throttle_backoff=60
  model_throttle_exhausted=false
  turn_exit=1
  while : ; do
    request_attempt=$((request_attempt + 1))
    approval_terminal_error=false
    approval_error=""
    approval_events='[]'
    approval_pending_count=0
    approval_auto=false
    if [ "$PROTOCOL" = "responses" ]; then
      result_file="/tmp/invoke-result-${turn}.json"
      rm -f "$result_file"
      AGENT_RESPONSES_URL="$AGENT_RESPONSES_URL" \
      AAD_TOKEN="$AAD_TOKEN" \
      DEPLOYED_AGENT_VERSION="$DEPLOYED_AGENT_VERSION" \
      CI_AGENT_SESSION_ID="$CI_AGENT_SESSION_ID" \
        python3 "$REPO_ROOT/.azure-pipelines/scripts/hosted-agents/scripts/invoke_hosted_agent_responses.py" \
          "$turn" "$TURN_FILE" "$TURN_RECORD_FILE" "$EVIDENCE_DIR" "$request_attempt"
      if [ ! -s "$result_file" ] || ! jq -e 'type == "object"' "$result_file" >/dev/null; then
        approval_terminal_error=true
        approval_error="Responses helper did not produce a valid result"
        turn_exit=1
        http_code=""
        echo "##vso[task.logissue type=error]$approval_error"
        printf '%s\n' "$approval_error" > "/tmp/invoke-out-${turn}.txt"
      else
        turn_exit=$(jq -r '.turn_exit' "$result_file")
        http_code=$(jq -r '.http_code' "$result_file")
        approval_terminal_error=$(jq -r '.approval_terminal_error' "$result_file")
        approval_error=$(jq -r '.approval_error' "$result_file")
        approval_events=$(jq -c '.approval_events' "$result_file")
        approval_pending_count=$(jq -r '.approval_pending_count' "$result_file")
        approval_auto=$(jq -r '.approval_auto' "$result_file")
      fi
    else
      # The explicit create step already bound this session to
      # the deployed version; azd rejects --version with
      # --session-id.
      azd ai agent invoke -p "$PROTOCOL" -f "$TURN_FILE" \
        --session-id "$CI_AGENT_SESSION_ID" --no-prompt \
        > /tmp/invoke-out-${turn}.txt 2>&1
      turn_exit=$?
    fi
    if [ "$approval_terminal_error" = "true" ]; then
      # Policy and protocol errors are deterministic and must
      # never enter quota, throttle, readiness, or semantic
      # retry paths.
      break
    fi
    quota_error_files=(/tmp/invoke-out-${turn}.txt)
    if [ "$PROTOCOL" = "responses" ]; then
      quota_error_files+=(/tmp/invoke-headers-${turn}.txt /tmp/invoke-raw-${turn}.json)
    fi
    if [ $turn_exit -ne 0 ] && hosted_agent_is_session_quota_error "${quota_error_files[@]}"; then
      if [ $quota_retries -ge "$HOSTED_AGENT_QUOTA_MAX_RETRIES" ]; then
        echo "##vso[task.logissue type=warning]Turn $turn exhausted $HOSTED_AGENT_QUOTA_MAX_RETRIES session quota retries"
        turn_exit=1
        break
      fi
      quota_retries=$((quota_retries + 1))
      quota_delay=$(hosted_agent_quota_retry_delay)
      echo "##vso[task.logissue type=warning]Turn $turn request $request_attempt hit session quota; retry $quota_retries/$HOSTED_AGENT_QUOTA_MAX_RETRIES in ${quota_delay}s"
      sleep "$quota_delay"
      continue
    fi
    # Model throttling can surface either as an HTTP 429 or
    # inside a successful transport response, so inspect all
    # captured output.
    if hosted_agent_is_model_throttle_error "${quota_error_files[@]}"; then
      if [ $model_throttle_retries -ge $max_model_throttle_retries ]; then
        echo "##vso[task.logissue type=warning]Turn $turn exhausted $max_model_throttle_retries model-throttle retries"
        model_throttle_exhausted=true
        turn_exit=1
        break
      fi
      model_throttle_retries=$((model_throttle_retries + 1))
      model_throttle_delay=$(hosted_agent_model_retry_delay "$model_throttle_backoff" "${quota_error_files[@]}")
      echo "##vso[task.logissue type=warning]Turn $turn request $request_attempt hit model throttling; retry $model_throttle_retries/$max_model_throttle_retries in ${model_throttle_delay}s"
      sleep "$model_throttle_delay"
      model_throttle_backoff=$((model_throttle_backoff * 2))
      continue
    fi
    if [ $turn_exit -eq 0 ]; then
      # Even on HTTP 200, the response may contain a transient
      # platform error (status:failed + error.code:server_error)
      # or a model hallucination (the toolbox tool was not
      # actually called). Both are worth one more invoke attempt
      # before giving up — the model is non-deterministic and
      # the platform sometimes returns a single-shot 500. We
      # re-use the SAME hallucination pattern as the post-loop
      # validator so the per-turn retry decision matches it.
      _retry_reason=""
      if grep -qiE '"status"[[:space:]]*:[[:space:]]*"failed"|"code"[[:space:]]*:[[:space:]]*"server_error"|invalid_payload|internal server error occurred' /tmp/invoke-out-${turn}.txt; then
        _retry_reason="HTTP 200 body carries a platform error"
      elif [ "$IS_TOOLBOX" = "true" ] && grep -qiE "(I don.t have access to real|I cannot access|I don.t have real-time|unable to retrieve|couldn.t retrieve|I do not have access to real|wasn.t able to retrieve|was not able to retrieve|temporary issue accessing|appears there was a temporary issue|please upload|if you have a document or file|fictional (company|organization)|is not a real (company|organization)|likely because the repository is private|don.t have permission to view)" /tmp/invoke-out-${turn}.txt; then
        _retry_reason="model hallucinated instead of calling the toolbox tool"
      fi
      if [ -z "$_retry_reason" ]; then
        break
      fi
      if [ $transient_attempt -ge $max_transient_attempts ]; then
        echo "##vso[task.logissue type=warning]Turn $turn transient attempt $transient_attempt: $_retry_reason; out of retries"
        break
      fi
      echo "##vso[task.logissue type=warning]Turn $turn transient attempt $transient_attempt: $_retry_reason; retrying in ${backoff}s"
      sleep "$backoff"
      backoff=$((backoff * 2))
      transient_attempt=$((transient_attempt + 1))
      continue
    fi
    if [ $transient_attempt -ge $max_transient_attempts ]; then
      break
    fi
    # Retry transient readiness (424) and AAD role-propagation
    # races (500 + PermissionDenied on storage/history) that can
    # occur right after a fresh role grant on the agent identity.
    # Also retry generic platform 500s and toolbox-MCP 401s — the
    # latter can occur while a freshly-granted Foundry User role
    # propagates to the MCP gateway's auth cache. The HTTP/2
    # "stream ... CANCEL" signal is a transient server-side
    # stream reset and is also retried.
    if grep -qiE "session_not_ready|status[ _]?code[: ]+424|HTTP 424|readiness|PermissionDenied|Principal does not have access|still being provisioned|version is still being|\"status\"[[:space:]]*:[[:space:]]*\"failed\"|\"code\"[[:space:]]*:[[:space:]]*\"server_error\"|invalid_payload|internal server error occurred|401 Unauthorized|stream error.*CANCEL|received from peer|connection reset by peer|EOF while reading response" /tmp/invoke-out-${turn}.txt; then
      echo "##vso[task.logissue type=warning]Turn $turn transient attempt $transient_attempt hit transient error; retrying in ${backoff}s"
      sleep "$backoff"
      backoff=$((backoff * 2))
      transient_attempt=$((transient_attempt + 1))
      continue
    fi
    break
  done

  # Persist only the final retry attempt as assertion evidence.
  cp "/tmp/invoke-out-${turn}.txt" "$EVIDENCE_DIR/turn-$turn-invoke.txt"
  if [ "$PROTOCOL" = "responses" ]; then
    cp "$EVIDENCE_DIR/turn-$turn-attempt-$request_attempt-approval-step-0-request.json" \
      "$EVIDENCE_DIR/turn-$turn-request.json"
    cp "/tmp/invoke-headers-${turn}.txt" "$EVIDENCE_DIR/turn-$turn-headers.txt"
    cp "/tmp/invoke-raw-${turn}.json" "$EVIDENCE_DIR/turn-$turn-raw.txt"
    cp "/tmp/invoke-response-${turn}.txt" "$EVIDENCE_DIR/turn-$turn-assistant-text.txt"
  else
    cp "/tmp/invoke-out-${turn}.txt" "$EVIDENCE_DIR/turn-$turn-raw.txt"
  fi
  jq -n --argjson turn "$turn" --argjson exit_code "$turn_exit" \
    --argjson attempts "$request_attempt" --arg protocol "$PROTOCOL" \
    --arg http_status "${http_code:-}" \
    --argjson approval_auto "$approval_auto" \
    --argjson pending_approvals "$approval_pending_count" \
    --argjson approval_events "$approval_events" \
    --arg approval_error "$approval_error" \
    '{turn:$turn,exit_code:$exit_code,http_status:(if $http_status == "" then null else ($http_status | tonumber) end),final_attempt:$attempts,protocol:$protocol,mcp_approvals:{automatic:$approval_auto,pending:$pending_approvals,error:(if $approval_error == "" then null else $approval_error end),steps:$approval_events}}' \
    > "$EVIDENCE_DIR/turn-$turn-status.json"

  # Collect only listings required by this turn's file contracts.
  while IFS=$'\t' read -r assertion_index contract_path; do
    [ -z "$contract_path" ] && continue
    parent_path=$(dirname "$contract_path")
    listing="$EVIDENCE_DIR/turn-$turn-session-files-$assertion_index.json"
    if ! azd ai agent files list "$parent_path" \
        --session-id "$CI_AGENT_SESSION_ID" --output json --no-prompt > "$listing"; then
      echo "{}" > "$listing"
      echo "##vso[task.logissue type=warning]Could not list session directory $parent_path"
    fi
  done < <(jq -r '
    .assertions | to_entries[] |
    select(.value.source == "session_files") |
    [(.key + 1), .value.path] | @tsv
  ' <<< "$turn_record")

  cat "/tmp/invoke-out-${turn}.txt"
  [ $turn_exit -ne 0 ] && overall_exit=$turn_exit
  [ "$model_throttle_exhausted" = "true" ] && break
done < "$TURN_PLAN"

if [ "$turn" -eq 0 ]; then
  echo "No tests apply to this matrix cell; semantic result is not_applicable."
  mkdir -p /tmp/agent-response
  echo "not_applicable" > /tmp/agent-response/response.txt
  exit 0
fi

echo ""
echo "┌──────────────────────────────────────────┐"
echo "│ Turns: $turn  |  Overall exit: $overall_exit"
echo "└──────────────────────────────────────────┘"

# Validate using the last turn's output as the representative response.
response=$(cat /tmp/invoke-out-${turn}.txt 2>/dev/null)

if [ $overall_exit -ne 0 ]; then
  echo "##vso[task.logissue type=error]Agent invocation failed (exit: $overall_exit)"
  exit 1
fi

if [ -z "$response" ]; then
  echo "##vso[task.logissue type=error]Empty response from agent"
  exit 1
fi

# Narrow error pattern — avoids false positives on normal prose.
#   "error": / "errors": → JSON error payloads, but ONLY when the
#                          value is a string or object —
#                          "error": null is success, not failure.
#   Traceback            → Python stack traces
#   ^ERROR:              → CLI-style error prefixes
#   plus natural-language failure phrases.
# Skipped for the github-copilot sample — its non-deterministic
# output may legitimately match these.
if [[ "$SAMPLE_PATH" != *"github-copilot"* ]]; then
  if echo "$response" | grep -qiE '("error"[[:space:]]*:[[:space:]]*("|\{)|"errors"[[:space:]]*:[[:space:]]*\[|'\''error'\''[[:space:]]*:[[:space:]]*["{\[]|\bTraceback\b|^ERROR:|^\#\#\[error\]|Error calling model:|invalid_request_error|I encountered an error|request was cancelled|unhandled errors|Please retry|Failed to process request)'; then
    echo "##vso[task.logissue type=error]Agent returned an error response"
    echo "--- response ---"; echo "$response"; echo "--- end response ---"
    exit 1
  fi
else
  echo "Skipping error-pattern check for github-copilot sample (non-deterministic output)"
fi

# Toolbox samples: detect tool-call hallucination. When the model
# answers from training data without invoking the toolbox we get
# phrases like "I don't have access to real-time". These mean the
# toolbox tool was not actually called and the job should fail.
if [ "$IS_TOOLBOX" = "true" ]; then
  if echo "$response" | grep -qiE "(I don.t have access to real|I cannot access|I don.t have real-time|unable to retrieve|couldn.t retrieve|I do not have access to real|wasn.t able to retrieve|was not able to retrieve|temporary issue accessing|appears there was a temporary issue|please upload|if you have a document or file|fictional (company|organization)|is not a real (company|organization)|likely because the repository is private|don.t have permission to view)"; then
    echo "##vso[task.logissue type=error]Agent did not call the toolbox tool (hallucinated answer from training data)"
    echo "--- response ---"; echo "$response"; echo "--- end response ---"
    exit 1
  fi
fi

# Save raw response into artifact for inspection.
mkdir -p /tmp/agent-response
echo "$response" > /tmp/agent-response/response.txt

# Echo-agent: verify the message was echoed back.
if [ "$SAMPLE_NAME" = "echo-agent" ]; then
  if echo "$response" | grep -qi "hello"; then
    echo "PASS Echo agent responded correctly"
  else
    echo "##vso[task.logissue type=error]Echo agent did not echo back the message"
    exit 1
  fi
fi

echo "PASS Agent responded successfully ($turn turn(s), protocol: $PROTOCOL)"
STEP_INVOKE_AGENT
    ;;
  guardrail)
    echo "##[section]Guardrail block test"
    bash /dev/fd/3 3<<'STEP_GUARDRAIL_BLOCK_TEST'
set -uo pipefail
cd "$WORK_DIR"
source "$REPO_ROOT/.azure-pipelines/scripts/hosted-agents/scripts/hosted-agent-retry.sh"
if [ -z "${GUARDRAIL_TRIGGER:-}" ] || [[ "$GUARDRAIL_TRIGGER" == \$\(*\) ]]; then
  echo "CONTENT_SAFETY_TEST_PROMPT is not set — skipping the guardrail block"
  echo "test. Set it to a policy-violating prompt to enable an end-to-end"
  echo "block assertion for this sample."
  exit 0
fi
AGENT_RESPONSES_URL=$(azd ai agent show --no-prompt --output json 2>/dev/null \
  | jq -r '.agent_endpoints.responses // empty')
if [ -z "$AGENT_RESPONSES_URL" ]; then
  echo "##vso[task.logissue type=error]Could not resolve agent responses endpoint from 'azd ai agent show'"
  exit 1
fi
AAD_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

# 1) Benign prompt must be allowed through (proves the agent
#    works with a policy attached and does not over-block).
jq -n --arg session_id "$CI_AGENT_SESSION_ID" \
  '{input:"Write a short friendly hello message.", stream:false, store:false, agent_session_id:$session_id}' \
  > /tmp/gr-benign.json
quota_retries=0
while :; do
  benign_code=$(curl -sS -D /tmp/gr-benign-headers.txt \
    -o /tmp/gr-benign-out.json -w '%{http_code}' \
    -X POST "$AGENT_RESPONSES_URL" \
    -H "Authorization: Bearer $AAD_TOKEN" -H 'Content-Type: application/json' \
    --max-time 300 --data @/tmp/gr-benign.json)
  echo "Benign prompt → HTTP $benign_code"
  if [ "$benign_code" = "200" ] || [ "$benign_code" = "201" ]; then
    break
  fi
  if ! hosted_agent_is_session_quota_error /tmp/gr-benign-headers.txt /tmp/gr-benign-out.json \
      || [ $quota_retries -ge "$HOSTED_AGENT_QUOTA_MAX_RETRIES" ]; then
    break
  fi
  quota_retries=$((quota_retries + 1))
  quota_delay=$(hosted_agent_quota_retry_delay)
  echo "##vso[task.logissue type=warning]Benign prompt hit session quota; retry $quota_retries/$HOSTED_AGENT_QUOTA_MAX_RETRIES in ${quota_delay}s"
  sleep "$quota_delay"
done
if [ "$benign_code" != "200" ] && [ "$benign_code" != "201" ]; then
  echo "##vso[task.logissue type=error]Benign prompt was not allowed (HTTP $benign_code) — guardrail over-blocking?"
  cat /tmp/gr-benign-out.json
  exit 1
fi

# 2) Violating prompt must be blocked at the input stage. The
#    agents runtime returns HTTP 400 with
#    {"error":{"code":"content_filter",...}}. Retry to absorb
#    transient fail-open behavior (AACS unavailable).
jq -n --arg p "$GUARDRAIL_TRIGGER" --arg session_id "$CI_AGENT_SESSION_ID" \
  '{input:$p, stream:false, store:false, agent_session_id:$session_id}' > /tmp/gr-block.json
attempt=0; max_attempts=3; backoff=15; blocked=0; quota_retries=0
while [ $attempt -lt $max_attempts ]; do
  block_code=$(curl -sS -D /tmp/gr-block-headers.txt \
    -o /tmp/gr-block-out.json -w '%{http_code}' \
    -X POST "$AGENT_RESPONSES_URL" \
    -H "Authorization: Bearer $AAD_TOKEN" -H 'Content-Type: application/json' \
    --max-time 300 --data @/tmp/gr-block.json)
  if hosted_agent_is_session_quota_error /tmp/gr-block-headers.txt /tmp/gr-block-out.json; then
    if [ $quota_retries -ge "$HOSTED_AGENT_QUOTA_MAX_RETRIES" ]; then
      echo "##vso[task.logissue type=warning]Violating prompt exhausted $HOSTED_AGENT_QUOTA_MAX_RETRIES session quota retries"
      break
    fi
    quota_retries=$((quota_retries + 1))
    quota_delay=$(hosted_agent_quota_retry_delay)
    echo "##vso[task.logissue type=warning]Violating prompt hit session quota; retry $quota_retries/$HOSTED_AGENT_QUOTA_MAX_RETRIES in ${quota_delay}s"
    sleep "$quota_delay"
    continue
  fi
  attempt=$((attempt + 1))
  echo "Violating prompt attempt $attempt → HTTP $block_code"
  if [ "$block_code" = "400" ] && grep -q '"code"[[:space:]]*:[[:space:]]*"content_filter"' /tmp/gr-block-out.json; then
    blocked=1; break
  fi
  if [ $attempt -lt $max_attempts ]; then
    echo "##vso[task.logissue type=warning]attempt $attempt did not block (HTTP $block_code) — possible fail-open; retrying in ${backoff}s"
    sleep "$backoff"; backoff=$((backoff * 2))
  fi
done
if [ "$blocked" != "1" ]; then
  echo "##vso[task.logissue type=error]Guardrail did NOT block the violating prompt (last HTTP $block_code)."
  echo "--- response ---"; cat /tmp/gr-block-out.json; echo; echo "--- end response ---"
  echo "Confirm the policy referenced by rai_policy_name blocks the configured"
  echo "category/severity, and that CONTENT_SAFETY_TEST_PROMPT actually violates it."
  exit 1
fi
echo "PASS Guardrail blocked the violating prompt at input stage (HTTP 400 content_filter)"
STEP_GUARDRAIL_BLOCK_TEST
    ;;
  voicelive)
    echo "##[section]Voice Live smoke test"
    bash /dev/fd/3 3<<'STEP_VOICE_LIVE_SMOKE_TEST'
set -uo pipefail
cd "$WORK_DIR"
echo "══════════════════════════════════════════"
echo "  Voice Live E2E: $SAMPLE_NAME"
echo "══════════════════════════════════════════"
# Wait for the agent to be fully ready before running the smoke
# test — observed transient failures when the test hits the
# agent too quickly after deploy.
echo "Waiting 5s for agent to be fully ready..."
sleep 5
# Derive the Voice Live endpoint from AZURE_AI_PROJECT_ENDPOINT
# (scheme + host).
VOICE_LIVE_ENDPOINT=$(echo "$AZURE_AI_PROJECT_ENDPOINT" | sed 's|^\(https\?://[^/]*\).*|\1|')
echo "Voice Live endpoint: $VOICE_LIVE_ENDPOINT"
pip install -q "azure-ai-voicelive[aiohttp]==1.3.0b1" azure-identity
set +e
python "$REPO_ROOT/.azure-pipelines/scripts/hosted-agents/voicelive/voicelive_audio_smoke_test.py" \
  --endpoint "$VOICE_LIVE_ENDPOINT" \
  --agent-name "$FOUNDRY_AGENT_NAME" \
  --project-name "$AZURE_AI_PROJECT_NAME" \
  2>&1 | tee /tmp/voicelive-smoke-test.log
test_exit=${PIPESTATUS[0]}
echo ""
if [ $test_exit -eq 0 ]; then
  echo "PASS Voice Live smoke test"
else
  echo "##vso[task.logissue type=error]Voice Live smoke test FAILED (exit: $test_exit)"
  exit $test_exit
fi
STEP_VOICE_LIVE_SMOKE_TEST
    ;;
  status)
    echo "##[section]Check agent status"
    bash /dev/fd/3 3<<'STEP_CHECK_AGENT_STATUS'
set -uo pipefail
cd "$WORK_DIR" 2>/dev/null || { echo "No azd working directory; skipping."; exit 0; }
azd ai agent show --no-prompt -o json \
  | jq '{id, name, version, status, agent_endpoints}' | tee /tmp/agent-status.txt
echo "Agent status retrieved"
STEP_CHECK_AGENT_STATUS
    ;;
  evidence)
    echo "##[section]Check agent logs and feature assertions"
    bash /dev/fd/3 3<<'STEP_CHECK_AGENT_LOGS_AND_FEATURE_ASSERTIONS'
set -o pipefail
AGENT_NAME="$FOUNDRY_AGENT_NAME"
cd "$WORK_DIR" 2>/dev/null || { echo "No azd working directory; skipping."; exit 0; }
fixture_relative=$(python3 "$REPO_ROOT/.github/scripts/hosted_agent_fixture.py" \
  fixture-dir --sample-dir "$SAMPLE_PATH")
fixture_dir="$REPO_ROOT/$fixture_relative"
spec_file="$fixture_dir/test-spec.yml"
plan_file="/tmp/agent-test-plan-${COMBO_ID}.json"
report_file="/tmp/agent-test-report-${COMBO_ID}.json"
resolved_file="/tmp/resolved-test-spec-${COMBO_ID}.json"
evidence_dir="/tmp/agent-test-evidence-${COMBO_ID}"
console_log="/tmp/agent-console-${COMBO_ID}.txt"
system_log="/tmp/agent-system-${COMBO_ID}.txt"
evidence_log="/tmp/agent-log-evidence-${COMBO_ID}.txt"
trace_file="/tmp/agent-traces-${COMBO_ID}.json"

has_spec=false
needs_trace=false
if [ -f "$spec_file" ] && [ -f "$plan_file" ]; then
  if ! python3 "$REPO_ROOT/.github/scripts/hosted_agent_test_spec.py" validate \
      --spec "$spec_file" --output "$resolved_file"; then
    echo "##vso[task.logissue type=error]Hosted-agent test spec became invalid after invocation planning"
    exit 1
  fi
  has_spec=true
  needs_trace=$(jq -r '[.tests[] | select(.status == "applicable") | .assertions[]? | select(.source == "trace")] | length > 0' "$plan_file")
else
  echo "No applicable test-spec.yml execution plan; legacy smoke validation applies."
fi

# Application stderr can surface through either monitor stream.
# Logs and traces are eventually consistent, so only those
# evidence sources receive bounded retrieval retries.
collect_delayed_evidence() {
  local attempt="$1"
  echo "Using session: $CI_AGENT_SESSION_ID"
  echo "=== Console Logs (attempt $attempt) ==="
  if ! azd ai agent monitor --type console --session-id "$CI_AGENT_SESSION_ID" --tail 300 --no-prompt 2>&1 \
      | tee "$console_log"; then
    echo "(no console logs available)"
  fi
  echo "=== System Event Logs (attempt $attempt) ==="
  if ! azd ai agent monitor --type system --session-id "$CI_AGENT_SESSION_ID" --tail 300 --no-prompt 2>&1 \
      | tee "$system_log"; then
    echo "(no system logs available)"
  fi
  : > "$evidence_log"
  for log_file in "$console_log" "$system_log"; do
    [ -f "$log_file" ] && cat "$log_file" >> "$evidence_log"
  done

  if [ "$needs_trace" = "true" ]; then
    resource_group=$(azd env get-value AZURE_RESOURCE_GROUP 2>/dev/null || true)
    python3 "$REPO_ROOT/.azure-pipelines/scripts/hosted-agents/scripts/collect-hosted-agent-traces.py" \
      --resource-group "$resource_group" \
      --agent-name "$AGENT_NAME" \
      --session-id "$CI_AGENT_SESSION_ID" \
      --output "$trace_file" || true
  fi
}

max_evidence_attempts=4
backoff=30
attempt=1
while [ "$attempt" -le "$max_evidence_attempts" ]; do
  collect_delayed_evidence "$attempt"

  if [ "$has_spec" != "true" ]; then
    echo "Agent monitoring check completed"
    exit 0
  fi

  set +e
  python3 "$REPO_ROOT/.github/scripts/hosted_agent_test_spec.py" evaluate \
    --plan "$plan_file" \
    --evidence-dir "$evidence_dir" \
    --console-log "$evidence_log" \
    --trace-file "$trace_file" \
    --report "$report_file"
  validation_exit=$?
  set -e
  [ "$validation_exit" -eq 0 ] && exit 0

  retryable=$(jq -r '
    [.tests[].assertions[]? | select(.status == "failed" or .status == "error")] as $failures |
    ($failures | length > 0) and
    ($failures | all(.source == "console_log" or .source == "trace"))
  ' "$report_file")
  if [ "$retryable" != "true" ] || [ "$attempt" -eq "$max_evidence_attempts" ]; then
    echo "##vso[task.logissue type=error]Hosted-agent feature assertions failed; see $report_file"
    exit "$validation_exit"
  fi

  echo "Delayed assertion evidence is unavailable (attempt $attempt/$max_evidence_attempts)."
  echo "Waiting ${backoff}s before refreshing logs and traces."
  sleep "$backoff"
  backoff=$((backoff * 2))
  attempt=$((attempt + 1))
done
STEP_CHECK_AGENT_LOGS_AND_FEATURE_ASSERTIONS
    ;;
  delete-session)
    echo "##[section]Delete agent session"
    bash /dev/fd/3 3<<'STEP_DELETE_AGENT_SESSION'
set -uo pipefail
cd "$WORK_DIR" 2>/dev/null || exit 0
echo "Deleting session: $CI_AGENT_SESSION_ID"
azd ai agent sessions delete "$CI_AGENT_SESSION_ID" --no-prompt 2>&1 \
  || echo "(session was not created or could not be deleted; continuing)"
STEP_DELETE_AGENT_SESSION
    ;;
  delete-toolboxes)
    echo "##[section]Delete temporary toolboxes"
    bash /dev/fd/3 3<<'STEP_DELETE_TEMPORARY_TOOLBOXES'
set -euo pipefail
if [ ! -f "$CI_TOOLBOX_STATE_FILE" ] || [ "$(jq '.toolboxes | length' "$CI_TOOLBOX_STATE_FILE")" -eq 0 ]; then
  echo "No cell-owned toolboxes to delete."
  jq -n '{operation:"cell",results:[]}' > "$CI_TOOLBOX_CLEANUP_RESULT"
  exit 0
fi
if [ ! -d "$WORK_DIR" ]; then
  echo "##vso[task.logissue type=error]Toolbox state exists but azd working directory is missing: $WORK_DIR"
  exit 1
fi
cd "$WORK_DIR"
ENDPOINT="$(azd env get-value AZURE_AI_PROJECT_ENDPOINT)"
"$REPO_ROOT/.azure-pipelines/scripts/hosted-agents/scripts/cleanup-hosted-agent-ci-toolboxes.sh" \
  cell "$CI_TOOLBOX_STATE_FILE" "$ENDPOINT" "$CI_TOOLBOX_CLEANUP_RESULT"
STEP_DELETE_TEMPORARY_TOOLBOXES
    ;;
  results)
    echo "##[section]Write status file and stage artifacts"
    bash /dev/fd/3 3<<'STEP_WRITE_STATUS_FILE_AND_STAGE_ARTIFACTS'
set -uo pipefail
# SucceededWithIssues means the job only logged warnings, which
# the GitHub job status reported as success.
case "$JOB_STATUS" in
  Succeeded|SucceededWithIssues) echo "success" > /tmp/result.txt ;;
  *) echo "failure" > /tmp/result.txt ;;
esac
echo "Sample: $SAMPLE_NAME" >> /tmp/result.txt
echo "Toolbox: $TOOLBOX_LABEL" >> /tmp/result.txt
echo "ID: $COMBO_ID" >> /tmp/result.txt
echo "Path: $SAMPLE_PATH" >> /tmp/result.txt
cat /tmp/result.txt

staging="$ARTIFACT_STAGING/cloud-e2e-results-$COMBO_ID"
mkdir -p "$staging"
for item in \
  /tmp/agent-status.txt \
  "/tmp/agent-console-${COMBO_ID}.txt" \
  "/tmp/agent-system-${COMBO_ID}.txt" \
  "/tmp/agent-log-evidence-${COMBO_ID}.txt" \
  "/tmp/agent-test-plan-${COMBO_ID}.json" \
  "/tmp/resolved-test-spec-${COMBO_ID}.json" \
  "/tmp/agent-test-report-${COMBO_ID}.json" \
  "/tmp/agent-traces-${COMBO_ID}.json" \
  "/tmp/agent-test-evidence-${COMBO_ID}" \
  /tmp/result.txt \
  /tmp/agent-response/response.txt \
  /tmp/voicelive-smoke-test.log \
  "$CI_TOOLBOX_STATE_FILE" \
  "$CI_TOOLBOX_DEPLOY_RESULT" \
  "$CI_TOOLBOX_CLEANUP_RESULT" ; do
  [ -e "$item" ] && cp -a "$item" "$staging/"
done
ls -la "$staging"
STEP_WRITE_STATUS_FILE_AND_STAGE_ARTIFACTS
    ;;
  teardown)
    echo "##[section]Teardown Azure resources"
    bash /dev/fd/3 3<<'STEP_TEARDOWN_AZURE_RESOURCES'
set -uo pipefail
cd "$WORK_DIR" 2>/dev/null || exit 0
echo "Tearing down azd environment: $AZD_ENV_NAME"
if ! azd down --force --purge --no-prompt 2>&1; then
  echo "##vso[task.logissue type=warning]azd down failed — resources may need manual cleanup"
  echo "##vso[task.logissue type=warning]Environment: $AZD_ENV_NAME"
fi
STEP_TEARDOWN_AZURE_RESOURCES
    ;;
  *)
    echo "Unknown hosted-agent action: $1" >&2
    exit 2
    ;;
esac
