#!/usr/bin/env bash
set -euo pipefail

readonly API_VERSION="2026-07-15-preview"
readonly MANAGEMENT_ENDPOINT="https://management.azure.com"
readonly DEFAULT_DEPLOYMENT_NAME_PREFIX="gemma-4-31b-it-a100"
readonly DEFAULT_MODEL_ID="azureml://registries/azure-huggingface/models/google--gemma-4-31b-it/versions/5"
readonly DEFAULT_DEPLOYMENT_TEMPLATE_ID="azureml://registries/azure-huggingface/deploymenttemplates/google--gemma-4-31b-it--16k-nvidia-a100/labels/latest"
readonly DEFAULT_ACCELERATOR_TYPE="A100_80GB"
readonly DEFAULT_CAPACITY="1"
readonly SKU_NAME="GlobalManagedCompute"
readonly DEFAULT_VERSION_UPGRADE_OPTION="OnceNewDefaultVersionAvailable"
readonly DEFAULT_POLL_INTERVAL_SECONDS="30"
readonly DEFAULT_LRO_TIMEOUT_SECONDS="3600"

HEADER_FILE=""
BODY_FILE=""
HTTP_STATUS=""

usage() {
  cat <<'EOF'
Manage a Microsoft Foundry managed-compute deployment through ARM REST.

Usage:
  manage-managed-compute.sh <action> [options]

Actions:
  render-create  Print the create request body without contacting Azure.
  create         PUT the deployment, poll the ARM operation, and verify it.
  show           GET one deployment.
  list           GET the account-level deployment collection.
  scale          PATCH only SKU name and capacity, then verify the deployment.
  delete         DELETE the deployment and poll until GET returns HTTP 404.

Required options for network actions (or environment variables):
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
  --poll-interval SECONDS    POLL_INTERVAL_SECONDS (default: 30)
  --timeout SECONDS          LRO_TIMEOUT_SECONDS (default: 3600)
  -h, --help                 Show this help.

Set AZURE_ACCESS_TOKEN to supply a management-plane bearer token without placing
it in command history. If it is unset, the script uses Azure CLI to acquire a
fresh token for each request. The token is never printed or written to a file.
EOF
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [[ -n "$HEADER_FILE" && -f "$HEADER_FILE" ]]; then
    rm -f -- "$HEADER_FILE"
  fi
  if [[ -n "$BODY_FILE" && -f "$BODY_FILE" ]]; then
    rm -f -- "$BODY_FILE"
  fi
}
trap cleanup EXIT

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command '$1' was not found."
}

random_suffix() {
  od -An -N3 -tx1 /dev/urandom | tr -d '[:space:]'
}

validate_positive_integer() {
  [[ "$1" =~ ^[1-9][0-9]*$ ]] || fail "$2 must be a positive integer; received '$1'."
}

validate_common_values() {
  if [[ "$ACTION" != "list" ]]; then
    [[ "$DEPLOYMENT_NAME" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]{0,56}-[a-zA-Z0-9]{6}$ ]] ||
      fail "Deployment name must end in a six-character alphanumeric suffix and be at most 64 characters."
  fi
  [[ -n "$MODEL_ID" ]] || fail "Model ID cannot be empty."
  [[ -n "$DEPLOYMENT_TEMPLATE_ID" ]] || fail "Deployment template ID cannot be empty."
  [[ -n "$ACCELERATOR_TYPE" ]] || fail "Accelerator type cannot be empty."
  validate_positive_integer "$CAPACITY" "Capacity"
  validate_positive_integer "$POLL_INTERVAL_SECONDS" "Poll interval"
  validate_positive_integer "$LRO_TIMEOUT_SECONDS" "Long-running-operation timeout"
  case "$VERSION_UPGRADE_OPTION" in
    NoAutoUpgrade | OnceCurrentVersionExpired | OnceNewDefaultVersionAvailable) ;;
    *) fail "Unsupported version upgrade option '$VERSION_UPGRADE_OPTION'." ;;
  esac
}

validate_network_inputs() {
  [[ -n "$SUBSCRIPTION_ID" ]] || fail "Set --subscription-id or AZURE_SUBSCRIPTION_ID."
  [[ "$SUBSCRIPTION_ID" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] ||
    fail "Subscription ID must be a UUID."
  [[ -n "$RESOURCE_GROUP" ]] || fail "Set --resource-group or RESOURCE_GROUP."
  [[ -n "$FOUNDRY_ACCOUNT_NAME" ]] || fail "Set --account-name or FOUNDRY_ACCOUNT_NAME."
  [[ "$FOUNDRY_ACCOUNT_NAME" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$ ]] ||
    fail "Foundry account name must be 2-64 characters and contain only letters, numbers, periods, underscores, and hyphens."
}

render_create_body() {
  # <create_request_body>
  jq -n \
    --arg sku_name "$SKU_NAME" \
    --argjson capacity "$CAPACITY" \
    --arg model "$MODEL_ID" \
    --arg deployment_template "$DEPLOYMENT_TEMPLATE_ID" \
    --arg accelerator_type "$ACCELERATOR_TYPE" \
    --arg version_upgrade_option "$VERSION_UPGRADE_OPTION" \
    '{
      sku: {
        name: $sku_name,
        capacity: $capacity
      },
      properties: {
        model: $model,
        deploymentTemplate: $deployment_template,
        acceleratorType: $accelerator_type,
        versionUpgradeOption: $version_upgrade_option
      }
    }'
  # </create_request_body>
}

render_scale_body() {
  jq -n \
    --arg sku_name "$SKU_NAME" \
    --argjson capacity "$CAPACITY" \
    '{
      sku: {
        name: $sku_name,
        capacity: $capacity
      }
    }'
}

urlencode() {
  jq -nr --arg value "$1" '$value | @uri'
}

normalize_management_url() {
  local url="$1"

  case "$url" in
    https://management.azure.com/*)
      printf '%s\n' "$url"
      ;;
    http://management.azure.com/*)
      printf 'https://%s\n' "${url#http://}"
      ;;
    *)
      fail "ARM returned an unexpected polling host; refusing to send a bearer token to '$url'."
      ;;
  esac
}

get_access_token() {
  if [[ -n "$ACCESS_TOKEN" ]]; then
    printf '%s' "$ACCESS_TOKEN"
    return
  fi

  require_command az
  az account get-access-token \
    --subscription "$SUBSCRIPTION_ID" \
    --resource "https://management.azure.com" \
    --query accessToken \
    --output tsv
}

print_response_body() {
  if [[ ! -s "$BODY_FILE" ]]; then
    return
  fi

  if jq empty "$BODY_FILE" >/dev/null 2>&1; then
    jq . "$BODY_FILE"
  else
    cat "$BODY_FILE"
    printf '\n'
  fi
}

print_arm_error() {
  local status="$1"

  if [[ -s "$BODY_FILE" ]] && jq empty "$BODY_FILE" >/dev/null 2>&1; then
    jq --arg status "$status" '{
      httpStatus: ($status | tonumber),
      error: (.error // .)
    }' "$BODY_FILE" >&2
  else
    printf 'ARM request failed with HTTP %s.\n' "$status" >&2
    if [[ -s "$BODY_FILE" ]]; then
      cat "$BODY_FILE" >&2
      printf '\n' >&2
    fi
  fi
}

response_header() {
  local header_name="$1"

  awk -v requested="$header_name" '
    {
      name = $1
      sub(/:$/, "", name)
      if (tolower(name) == tolower(requested)) {
        sub(/^[^:]*:[[:space:]]*/, "")
        sub(/\r$/, "")
        value = $0
      }
    }
    END { print value }
  ' "$HEADER_FILE"
}

arm_request() {
  local method="$1"
  local url="$2"
  local request_body="${3:-}"
  local token
  local -a curl_args

  token="$(get_access_token)"
  : >"$HEADER_FILE"
  : >"$BODY_FILE"

  # <arm_http_request>
  curl_args=(
    --silent
    --show-error
    --request "$method"
    --dump-header "$HEADER_FILE"
    --output "$BODY_FILE"
    --write-out "%{http_code}"
    --header "Accept: application/json"
    --header @-
  )
  if [[ -n "$request_body" ]]; then
    curl_args+=(
      --header "Content-Type: application/json"
      --data "$request_body"
    )
  fi

  if HTTP_STATUS="$(
    printf 'Authorization: Bearer %s\n' "$token" |
      curl "${curl_args[@]}" "$url"
  )"; then
    :
  else
    local curl_status=$?
    unset token
    print_response_body >&2
    fail "curl failed with exit code $curl_status."
  fi
  # </arm_http_request>

  unset token
  [[ "$HTTP_STATUS" =~ ^[0-9]{3}$ ]] || fail "curl returned an invalid HTTP status '$HTTP_STATUS'."
}

require_http_status() {
  local accepted
  for accepted in "$@"; do
    if [[ "$HTTP_STATUS" == "$accepted" ]]; then
      return
    fi
  done
  print_arm_error "$HTTP_STATUS"
  fail "Unexpected HTTP status $HTTP_STATUS."
}

sleep_for_retry() {
  local retry_after="$1"
  local started_at="$2"
  local elapsed=$((SECONDS - started_at))
  local remaining=$((LRO_TIMEOUT_SECONDS - elapsed))
  local delay="$POLL_INTERVAL_SECONDS"

  if [[ "$retry_after" =~ ^[0-9]+$ ]]; then
    delay="$retry_after"
  fi
  ((remaining > 0)) || fail "ARM operation exceeded the ${LRO_TIMEOUT_SECONDS}-second timeout."
  if ((delay > remaining)); then
    delay="$remaining"
  fi
  sleep "$delay"
}

poll_operation() {
  local poll_url
  poll_url="$(normalize_management_url "$1")"
  local retry_after="$2"
  local started_at=$SECONDS
  local state

  while true; do
    sleep_for_retry "$retry_after" "$started_at"
    arm_request GET "$poll_url"
    require_http_status 200 201 202 204
    retry_after="$(response_header Retry-After)"
    if [[ "$HTTP_STATUS" == "204" || ! -s "$BODY_FILE" ]]; then
      state=""
    else
      state="$(jq -r '.status // .properties.provisioningState // .properties.status // empty' "$BODY_FILE")"
    fi

    case "$state" in
      Succeeded)
        return
        ;;
      Failed | Canceled | Cancelled)
        print_arm_error "$HTTP_STATUS"
        fail "ARM long-running operation reached terminal state '$state'."
        ;;
      Accepted | Creating | Deleting | InProgress | Running | Updating | "")
        if [[ "$HTTP_STATUS" != "202" && -z "$state" ]]; then
          return
        fi
        ;;
      *)
        fail "ARM long-running operation returned unknown state '$state'."
        ;;
    esac
  done
}

poll_response_if_needed() {
  local preference="$1"
  local async_url location_url poll_url retry_after

  async_url="$(response_header Azure-AsyncOperation)"
  location_url="$(response_header Location)"
  retry_after="$(response_header Retry-After)"
  poll_url=""

  if [[ "$preference" == "location" ]]; then
    poll_url="${location_url:-$async_url}"
  else
    poll_url="${async_url:-$location_url}"
  fi

  if [[ -n "$poll_url" ]]; then
    poll_operation "$poll_url" "$retry_after"
  elif [[ "$HTTP_STATUS" == "202" ]]; then
    fail "ARM returned HTTP 202 without Azure-AsyncOperation or Location."
  fi
}

verify_deployment_file() {
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
    ' "$BODY_FILE" >/dev/null; then
    jq '{
      provisioningState: .properties.provisioningState,
      model: .properties.model,
      deploymentTemplate: .properties.deploymentTemplate,
      acceleratorType: .properties.acceleratorType,
      versionUpgradeOption: .properties.versionUpgradeOption,
      sku: .sku
    }' "$BODY_FILE" >&2
    fail "The deployment does not match the requested configuration or has not reached Succeeded."
  fi
}

deployment_immutable_snapshot() {
  jq -c '{
    model: .properties.model,
    deploymentTemplate: .properties.deploymentTemplate,
    acceleratorType: .properties.acceleratorType,
    versionUpgradeOption: .properties.versionUpgradeOption,
    computeId: .properties.computeId,
    priority: .properties.priority
  }' <<<"$1"
}

verify_scale_source() {
  local deployment_json="$1"

  if ! jq -e \
    --arg model "$MODEL_ID" \
    --arg deployment_template "$DEPLOYMENT_TEMPLATE_ID" \
    --arg accelerator "$ACCELERATOR_TYPE" \
    --arg version_upgrade_option "$VERSION_UPGRADE_OPTION" \
    --arg sku "$SKU_NAME" \
    --argjson check_model "$MODEL_ID_EXPLICIT" \
    --argjson check_template "$DEPLOYMENT_TEMPLATE_ID_EXPLICIT" \
    --argjson check_accelerator "$ACCELERATOR_TYPE_EXPLICIT" \
    --argjson check_upgrade "$VERSION_UPGRADE_OPTION_EXPLICIT" \
    '
      .properties.provisioningState == "Succeeded"
      and .sku.name == $sku
      and (($check_model == false) or .properties.model == $model)
      and (($check_template == false) or .properties.deploymentTemplate == $deployment_template)
      and (($check_accelerator == false) or .properties.acceleratorType == $accelerator)
      and (($check_upgrade == false) or .properties.versionUpgradeOption == $version_upgrade_option)
    ' >/dev/null <<<"$deployment_json"; then
    fail "The deployment isn't healthy or doesn't match the explicitly supplied scale expectations."
  fi
}

verify_scaled_deployment() {
  local deployment_json="$1"
  local immutable_snapshot="$2"

  if ! jq -e \
    --arg sku "$SKU_NAME" \
    --argjson capacity "$CAPACITY" \
    --argjson immutable "$immutable_snapshot" \
    '
      .properties.provisioningState == "Succeeded"
      and .sku.name == $sku
      and .sku.capacity == $capacity
      and {
        model: .properties.model,
        deploymentTemplate: .properties.deploymentTemplate,
        acceleratorType: .properties.acceleratorType,
        versionUpgradeOption: .properties.versionUpgradeOption,
        computeId: .properties.computeId,
        priority: .properties.priority
      } == $immutable
    ' >/dev/null <<<"$deployment_json"; then
    fail "The scaled deployment has the wrong capacity, isn't healthy, or changed an immutable field."
  fi
}

get_and_verify_deployment() {
  arm_request GET "$RESOURCE_URL"
  require_http_status 200
  verify_deployment_file
  print_response_body
}

list_deployments() {
  local next_url="$COLLECTION_URL"
  local page_values
  local all_values='[]'

  while [[ -n "$next_url" ]]; do
    arm_request GET "$(normalize_management_url "$next_url")"
    require_http_status 200
    page_values="$(jq -c '.value // []' "$BODY_FILE")"
    all_values="$(jq -cn \
      --argjson current "$all_values" \
      --argjson page "$page_values" \
      '$current + $page')"
    next_url="$(jq -r '.nextLink // empty' "$BODY_FILE")"
  done

  jq -n --argjson value "$all_values" '{value: $value}'
}

wait_until_deleted() {
  local started_at=$SECONDS
  local retry_after=""

  while true; do
    arm_request GET "$RESOURCE_URL"
    case "$HTTP_STATUS" in
      404)
        printf 'Deleted managed-compute deployment %s.\n' "$DEPLOYMENT_NAME"
        return
        ;;
      200)
        retry_after="$(response_header Retry-After)"
        sleep_for_retry "$retry_after" "$started_at"
        ;;
      *)
        print_arm_error "$HTTP_STATUS"
        fail "Unexpected HTTP status while verifying deletion: $HTTP_STATUS."
        ;;
    esac
  done
}

ACTION="${1:-}"
case "$ACTION" in
  -h | --help | help)
    usage
    exit 0
    ;;
  render-create | create | show | list | scale | delete) shift ;;
  "")
    usage >&2
    exit 1
    ;;
  *)
    usage >&2
    fail "Unknown action '$ACTION'."
    ;;
esac

MODEL_ID_EXPLICIT=false
DEPLOYMENT_TEMPLATE_ID_EXPLICIT=false
ACCELERATOR_TYPE_EXPLICIT=false
VERSION_UPGRADE_OPTION_EXPLICIT=false
[[ -n "${MODEL_ID:-}" ]] && MODEL_ID_EXPLICIT=true
[[ -n "${DEPLOYMENT_TEMPLATE_ID:-}" ]] && DEPLOYMENT_TEMPLATE_ID_EXPLICIT=true
[[ -n "${ACCELERATOR_TYPE:-}" ]] && ACCELERATOR_TYPE_EXPLICIT=true
[[ -n "${VERSION_UPGRADE_OPTION:-}" ]] && VERSION_UPGRADE_OPTION_EXPLICIT=true

SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-}"
RESOURCE_GROUP="${RESOURCE_GROUP:-}"
FOUNDRY_ACCOUNT_NAME="${FOUNDRY_ACCOUNT_NAME:-}"
DEPLOYMENT_NAME="${DEPLOYMENT_NAME:-}"
MODEL_ID="${MODEL_ID:-$DEFAULT_MODEL_ID}"
DEPLOYMENT_TEMPLATE_ID="${DEPLOYMENT_TEMPLATE_ID:-$DEFAULT_DEPLOYMENT_TEMPLATE_ID}"
ACCELERATOR_TYPE="${ACCELERATOR_TYPE:-$DEFAULT_ACCELERATOR_TYPE}"
CAPACITY="${CAPACITY:-$DEFAULT_CAPACITY}"
VERSION_UPGRADE_OPTION="${VERSION_UPGRADE_OPTION:-$DEFAULT_VERSION_UPGRADE_OPTION}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-$DEFAULT_POLL_INTERVAL_SECONDS}"
LRO_TIMEOUT_SECONDS="${LRO_TIMEOUT_SECONDS:-$DEFAULT_LRO_TIMEOUT_SECONDS}"
ACCESS_TOKEN="${AZURE_ACCESS_TOKEN:-}"

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
      MODEL_ID_EXPLICIT=true
      shift 2
      ;;
    --deployment-template)
      (($# >= 2)) || fail "Missing value for --deployment-template."
      DEPLOYMENT_TEMPLATE_ID="$2"
      DEPLOYMENT_TEMPLATE_ID_EXPLICIT=true
      shift 2
      ;;
    --accelerator-type)
      (($# >= 2)) || fail "Missing value for --accelerator-type."
      ACCELERATOR_TYPE="$2"
      ACCELERATOR_TYPE_EXPLICIT=true
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
      VERSION_UPGRADE_OPTION_EXPLICIT=true
      shift 2
      ;;
    --poll-interval)
      (($# >= 2)) || fail "Missing value for --poll-interval."
      POLL_INTERVAL_SECONDS="$2"
      shift 2
      ;;
    --timeout)
      (($# >= 2)) || fail "Missing value for --timeout."
      LRO_TIMEOUT_SECONDS="$2"
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
  if [[ "$ACTION" == "create" || "$ACTION" == "render-create" ]]; then
    DEPLOYMENT_NAME="${DEFAULT_DEPLOYMENT_NAME_PREFIX}-$(random_suffix)"
    if [[ "$ACTION" == "create" ]]; then
      printf 'Generated deployment name: %s\n' "$DEPLOYMENT_NAME" >&2
    fi
  elif [[ "$ACTION" != "list" ]]; then
    fail "Set --deployment-name or DEPLOYMENT_NAME to the suffixed name returned by create."
  fi
fi

require_command curl
require_command jq
validate_common_values

if [[ "$ACTION" == "render-create" ]]; then
  render_create_body
  exit 0
fi

validate_network_inputs
HEADER_FILE="$(mktemp "${TMPDIR:-/tmp}/managed-compute-headers.XXXXXX")"
BODY_FILE="$(mktemp "${TMPDIR:-/tmp}/managed-compute-body.XXXXXX")"

encoded_subscription_id="$(urlencode "$SUBSCRIPTION_ID")"
encoded_resource_group="$(urlencode "$RESOURCE_GROUP")"
encoded_account_name="$(urlencode "$FOUNDRY_ACCOUNT_NAME")"
encoded_deployment_name="$(urlencode "$DEPLOYMENT_NAME")"
COLLECTION_URL="${MANAGEMENT_ENDPOINT}/subscriptions/${encoded_subscription_id}/resourceGroups/${encoded_resource_group}/providers/Microsoft.CognitiveServices/accounts/${encoded_account_name}/managedComputeDeployments?api-version=${API_VERSION}"
RESOURCE_URL="${MANAGEMENT_ENDPOINT}/subscriptions/${encoded_subscription_id}/resourceGroups/${encoded_resource_group}/providers/Microsoft.CognitiveServices/accounts/${encoded_account_name}/managedComputeDeployments/${encoded_deployment_name}?api-version=${API_VERSION}"

case "$ACTION" in
  create)
    create_body="$(render_create_body)"
    arm_request PUT "$RESOURCE_URL" "$create_body"
    require_http_status 200 201 202
    poll_response_if_needed azure-async-operation
    get_and_verify_deployment
    ;;
  show)
    arm_request GET "$RESOURCE_URL"
    require_http_status 200
    print_response_body
    ;;
  list)
    list_deployments
    ;;
  scale)
    arm_request GET "$RESOURCE_URL"
    require_http_status 200
    current_deployment="$(cat "$BODY_FILE")"
    verify_scale_source "$current_deployment"
    immutable_snapshot="$(deployment_immutable_snapshot "$current_deployment")"
    scale_body="$(render_scale_body)"
    arm_request PATCH "$RESOURCE_URL" "$scale_body"
    require_http_status 200 202
    poll_response_if_needed location
    arm_request GET "$RESOURCE_URL"
    require_http_status 200
    scaled_deployment="$(cat "$BODY_FILE")"
    verify_scaled_deployment "$scaled_deployment" "$immutable_snapshot"
    jq . <<<"$scaled_deployment"
    ;;
  delete)
    arm_request DELETE "$RESOURCE_URL"
    require_http_status 200 202 204
    poll_response_if_needed location
    wait_until_deleted
    ;;
esac
