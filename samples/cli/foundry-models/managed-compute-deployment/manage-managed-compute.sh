#!/usr/bin/env bash
set -euo pipefail

readonly MIN_AZURE_CLI_VERSION="2.88.0"
readonly DEFAULT_DEPLOYMENT_NAME_PREFIX="gemma-4-31b-it-a100"
readonly DEFAULT_MODEL_ID="azureml://registries/azure-huggingface/models/google--gemma-4-31b-it/versions/5"
readonly DEFAULT_DEPLOYMENT_TEMPLATE_ID="azureml://registries/azure-huggingface/deploymenttemplates/google--gemma-4-31b-it--16k-nvidia-a100/labels/latest"
readonly DEFAULT_ACCELERATOR_TYPE="A100_80GB"
readonly DEFAULT_CAPACITY="1"
readonly SKU_NAME="GlobalManagedCompute"
readonly DEFAULT_VERSION_UPGRADE_OPTION="OnceNewDefaultVersionAvailable"

usage() {
  cat <<'EOF'
Manage a Microsoft Foundry managed-compute deployment with Azure CLI.

Usage:
  manage-managed-compute.sh <action> [options]

Actions:
  create    Create the managed-compute deployment and verify it.
  show      Show one managed-compute deployment.
  list      List managed-compute deployments under the Foundry account.
  scale     Change only the deployment SKU capacity, then verify it.
  delete    Delete the managed-compute deployment.

Required options (or environment variables):
  --subscription-id ID       AZURE_SUBSCRIPTION_ID
  --resource-group NAME      RESOURCE_GROUP
  --account-name NAME        FOUNDRY_ACCOUNT_NAME

Optional values:
  --deployment-name NAME     DEPLOYMENT_NAME; create generates a suffixed name
  --model-id URI             MODEL_ID
  --deployment-template URI  DEPLOYMENT_TEMPLATE_ID
  --accelerator-type TYPE    ACCELERATOR_TYPE
  --capacity COUNT           CAPACITY
  --version-upgrade-option P VERSION_UPGRADE_OPTION
  -h, --help                 Show this help.

Authentication is caller-owned. Run `az login` before using a network action.
EOF
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command '$1' was not found."
}

random_suffix() {
  od -An -N3 -tx1 /dev/urandom | tr -d '[:space:]'
}

version_at_least() {
  local actual="$1"
  local required="$2"
  local actual_major actual_minor actual_patch
  local required_major required_minor required_patch

  IFS=. read -r actual_major actual_minor actual_patch <<<"${actual%%[^0-9.]*}"
  IFS=. read -r required_major required_minor required_patch <<<"$required"
  actual_patch="${actual_patch:-0}"
  required_patch="${required_patch:-0}"

  ((actual_major > required_major)) ||
    ((actual_major == required_major && actual_minor > required_minor)) ||
    ((actual_major == required_major && actual_minor == required_minor && actual_patch >= required_patch))
}

check_azure_cli() {
  local azure_cli_version

  require_command az
  require_command jq
  azure_cli_version="$(az version --query '"azure-cli"' --output tsv)"
  version_at_least "$azure_cli_version" "$MIN_AZURE_CLI_VERSION" ||
    fail "Azure CLI $MIN_AZURE_CLI_VERSION or later is required; found $azure_cli_version."

  if ! az cognitiveservices account managed-compute-deployment --help >/dev/null 2>&1; then
    fail "This Azure CLI build does not include the 'cognitiveservices account managed-compute-deployment' command group."
  fi
}

validate_positive_integer() {
  [[ "$1" =~ ^[1-9][0-9]*$ ]] || fail "Capacity must be a positive integer; received '$1'."
}

validate_inputs() {
  [[ -n "$SUBSCRIPTION_ID" ]] || fail "Set --subscription-id or AZURE_SUBSCRIPTION_ID."
  [[ "$SUBSCRIPTION_ID" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] ||
    fail "Subscription ID must be a UUID."
  [[ -n "$RESOURCE_GROUP" ]] || fail "Set --resource-group or RESOURCE_GROUP."
  [[ -n "$FOUNDRY_ACCOUNT_NAME" ]] || fail "Set --account-name or FOUNDRY_ACCOUNT_NAME."
  [[ "$FOUNDRY_ACCOUNT_NAME" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$ ]] ||
    fail "Foundry account name must be 2-64 characters and contain only letters, numbers, periods, underscores, and hyphens."
  if [[ "$ACTION" != "list" ]]; then
    [[ "$DEPLOYMENT_NAME" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]{0,56}-[a-zA-Z0-9]{6}$ ]] ||
      fail "Deployment name must end in a six-character alphanumeric suffix and be at most 64 characters."
  fi
  [[ -n "$MODEL_ID" ]] || fail "Model ID cannot be empty."
  [[ -n "$DEPLOYMENT_TEMPLATE_ID" ]] || fail "Deployment template ID cannot be empty."
  [[ -n "$ACCELERATOR_TYPE" ]] || fail "Accelerator type cannot be empty."
  validate_positive_integer "$CAPACITY"
  case "$VERSION_UPGRADE_OPTION" in
    NoAutoUpgrade | OnceCurrentVersionExpired | OnceNewDefaultVersionAvailable) ;;
    *) fail "Unsupported version upgrade option '$VERSION_UPGRADE_OPTION'." ;;
  esac
}

show_deployment() {
  az cognitiveservices account managed-compute-deployment show \
    --subscription "$SUBSCRIPTION_ID" \
    --resource-group "$RESOURCE_GROUP" \
    --name "$FOUNDRY_ACCOUNT_NAME" \
    --deployment-name "$DEPLOYMENT_NAME" \
    --output json
}

verify_deployment() {
  local deployment_json="$1"

  if ! jq -e \
    --arg model "$MODEL_ID" \
    --arg deployment_template "$DEPLOYMENT_TEMPLATE_ID" \
    --arg accelerator "$ACCELERATOR_TYPE" \
    --arg sku "$SKU_NAME" \
    --arg version_upgrade_option "$VERSION_UPGRADE_OPTION" \
    --argjson capacity "$CAPACITY" \
    '
      .properties.provisioningState == "Succeeded"
      and .properties.model == $model
      and .properties.deploymentTemplate == $deployment_template
      and .properties.acceleratorType == $accelerator
      and .properties.versionUpgradeOption == $version_upgrade_option
      and .sku.name == $sku
      and .sku.capacity == $capacity
    ' >/dev/null <<<"$deployment_json"; then
    jq '{
      provisioningState: .properties.provisioningState,
      model: .properties.model,
      deploymentTemplate: .properties.deploymentTemplate,
      acceleratorType: .properties.acceleratorType,
      versionUpgradeOption: .properties.versionUpgradeOption,
      sku: .sku
    }' <<<"$deployment_json" >&2
    fail "The deployment does not match the requested configuration or has not reached Succeeded."
  fi
}

ACTION="${1:-}"
case "$ACTION" in
  -h | --help | help)
    usage
    exit 0
    ;;
  create | show | list | scale | delete) shift ;;
  "")
    usage >&2
    exit 1
    ;;
  *)
    usage >&2
    fail "Unknown action '$ACTION'."
    ;;
esac

SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-}"
RESOURCE_GROUP="${RESOURCE_GROUP:-}"
FOUNDRY_ACCOUNT_NAME="${FOUNDRY_ACCOUNT_NAME:-}"
DEPLOYMENT_NAME="${DEPLOYMENT_NAME:-}"
MODEL_ID="${MODEL_ID:-$DEFAULT_MODEL_ID}"
DEPLOYMENT_TEMPLATE_ID="${DEPLOYMENT_TEMPLATE_ID:-$DEFAULT_DEPLOYMENT_TEMPLATE_ID}"
ACCELERATOR_TYPE="${ACCELERATOR_TYPE:-$DEFAULT_ACCELERATOR_TYPE}"
CAPACITY="${CAPACITY:-$DEFAULT_CAPACITY}"
VERSION_UPGRADE_OPTION="${VERSION_UPGRADE_OPTION:-$DEFAULT_VERSION_UPGRADE_OPTION}"

while (($# > 0)); do
  case "$1" in
    --subscription-id)
      (($# >= 2)) || fail "Missing value for --subscription-id."
      SUBSCRIPTION_ID="$2"
      shift 2
      ;;
    --resource-group)
      (($# >= 2)) || fail "Missing value for --resource-group."
      RESOURCE_GROUP="$2"
      shift 2
      ;;
    --account-name)
      (($# >= 2)) || fail "Missing value for --account-name."
      FOUNDRY_ACCOUNT_NAME="$2"
      shift 2
      ;;
    --deployment-name)
      (($# >= 2)) || fail "Missing value for --deployment-name."
      DEPLOYMENT_NAME="$2"
      shift 2
      ;;
    --model-id)
      (($# >= 2)) || fail "Missing value for --model-id."
      MODEL_ID="$2"
      shift 2
      ;;
    --deployment-template)
      (($# >= 2)) || fail "Missing value for --deployment-template."
      DEPLOYMENT_TEMPLATE_ID="$2"
      shift 2
      ;;
    --accelerator-type)
      (($# >= 2)) || fail "Missing value for --accelerator-type."
      ACCELERATOR_TYPE="$2"
      shift 2
      ;;
    --capacity)
      (($# >= 2)) || fail "Missing value for --capacity."
      CAPACITY="$2"
      shift 2
      ;;
    --version-upgrade-option)
      (($# >= 2)) || fail "Missing value for --version-upgrade-option."
      VERSION_UPGRADE_OPTION="$2"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *) fail "Unknown option '$1'." ;;
  esac
done

if [[ -z "$DEPLOYMENT_NAME" ]]; then
  if [[ "$ACTION" == "create" ]]; then
    DEPLOYMENT_NAME="${DEFAULT_DEPLOYMENT_NAME_PREFIX}-$(random_suffix)"
    printf 'Generated deployment name: %s\n' "$DEPLOYMENT_NAME" >&2
  elif [[ "$ACTION" != "list" ]]; then
    fail "Set --deployment-name or DEPLOYMENT_NAME to the suffixed name returned by create."
  fi
fi

validate_inputs
check_azure_cli

case "$ACTION" in
  create)
    az cognitiveservices account managed-compute-deployment create \
      --subscription "$SUBSCRIPTION_ID" \
      --resource-group "$RESOURCE_GROUP" \
      --name "$FOUNDRY_ACCOUNT_NAME" \
      --deployment-name "$DEPLOYMENT_NAME" \
      --model "$MODEL_ID" \
      --deployment-template "$DEPLOYMENT_TEMPLATE_ID" \
      --accelerator-type "$ACCELERATOR_TYPE" \
      --sku-name "$SKU_NAME" \
      --sku-capacity "$CAPACITY" \
      --version-upgrade-option "$VERSION_UPGRADE_OPTION" \
      --only-show-errors \
      --output none
    deployment_json="$(show_deployment)"
    verify_deployment "$deployment_json"
    jq . <<<"$deployment_json"
    ;;
  show)
    show_deployment
    ;;
  list)
    az cognitiveservices account managed-compute-deployment list \
      --subscription "$SUBSCRIPTION_ID" \
      --resource-group "$RESOURCE_GROUP" \
      --name "$FOUNDRY_ACCOUNT_NAME" \
      --output json
    ;;
  scale)
    az cognitiveservices account managed-compute-deployment update \
      --subscription "$SUBSCRIPTION_ID" \
      --resource-group "$RESOURCE_GROUP" \
      --name "$FOUNDRY_ACCOUNT_NAME" \
      --deployment-name "$DEPLOYMENT_NAME" \
      --sku-name "$SKU_NAME" \
      --sku-capacity "$CAPACITY" \
      --only-show-errors \
      --output none
    deployment_json="$(show_deployment)"
    verify_deployment "$deployment_json"
    jq . <<<"$deployment_json"
    ;;
  delete)
    az cognitiveservices account managed-compute-deployment delete \
      --subscription "$SUBSCRIPTION_ID" \
      --resource-group "$RESOURCE_GROUP" \
      --name "$FOUNDRY_ACCOUNT_NAME" \
      --deployment-name "$DEPLOYMENT_NAME" \
      --only-show-errors \
      --output none
    printf 'Deleted managed-compute deployment %s.\n' "$DEPLOYMENT_NAME"
    ;;
esac
