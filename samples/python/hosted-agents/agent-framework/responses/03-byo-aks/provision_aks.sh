#!/usr/bin/env bash
# AKS provisioning without ACR image-admission policy.
# Step 0: verify the existing resource group.
# Step 1: AKS cluster and dedicated Kata sandbox node pool.
# Does not prepare ACR, image policy, Foundry identities, storage, delegated subnet, or role assignments.
# Does not change network security group rules.
# Prerequisites for --apply: Azure CLI and AKS provisioning rights.

set -euo pipefail

# Preserve ARM IDs when Git Bash invokes native Windows Azure CLI.
export MSYS_NO_PATHCONV=1

APPLY=false

usage() {
  cat <<'EOF'
Usage: AKS_NAME=<name> AZURE_SUBSCRIPTION_ID=<id> RESOURCE_GROUP=<name> AZURE_LOCATION=<region> KUBERNETES_VERSION=<version> bash provision_aks.sh [--apply]

Without --apply, prints the resolved plan only. With --apply, reuses the
resource group supplied by name, then provisions any missing AKS cluster and
sandbox node pool. Existing clusters/pools are not updated or fully validated.
This script does not create ACR resources, change network security group rules,
enable Azure Policy, or configure an ACR image-admission policy on the cluster.

Options:
  --resource-group <name>  Existing resource group name; overrides RESOURCE_GROUP.
  --apply                  Provision resources (Azure charges may apply).
  -h, --help               Show this help.

Environment overrides:
  AZURE_SUBSCRIPTION_ID    Required target Azure subscription ID.
  RESOURCE_GROUP           Required existing resource group name.
  AZURE_LOCATION           Required preview-supported Azure region.
  AKS_NAME                 Required target AKS cluster name.
  KUBERNETES_VERSION       Required preview-supported AKS version.
  SYSTEM_NODE_VM_SIZE      Optional explicit size; otherwise selected by region.
  SANDBOX_NODE_VM_SIZE     Optional explicit size; otherwise selected by region.
  SKU_QUERY_TIMEOUT_SECONDS    30
  SKU_QUERY_MAX_ATTEMPTS       2
  SKU_QUERY_HEARTBEAT_SECONDS  5

Azure CLI provisions AKS networking; the script does not attach a custom
subnet. This script alone does not complete Foundry BYO-AKS onboarding.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=true; shift ;;
    --resource-group)
      if [[ $# -lt 2 || -z "$2" || "$2" == --* ]]; then
        echo "--resource-group requires an Azure resource group name." >&2
        exit 2
      fi
      RESOURCE_GROUP="$2"
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-}"
if [[ -z "$SUBSCRIPTION_ID" ]]; then
  echo "Set AZURE_SUBSCRIPTION_ID to the target Azure subscription ID." >&2
  exit 2
fi
RESOURCE_GROUP="${RESOURCE_GROUP:-}"
if [[ -z "$RESOURCE_GROUP" ]]; then
  echo "Set RESOURCE_GROUP to the existing resource group name." >&2
  exit 2
fi
LOCATION="${AZURE_LOCATION:-}"
if [[ -z "$LOCATION" ]]; then
  echo "Set AZURE_LOCATION to a preview-supported Azure region." >&2
  exit 2
fi
AKS_NAME="${AKS_NAME:-}"
if [[ -z "$AKS_NAME" ]]; then
  echo "Set AKS_NAME to the target AKS cluster name." >&2
  exit 2
fi
KUBERNETES_VERSION="${KUBERNETES_VERSION:-}"
if [[ ! "$KUBERNETES_VERSION" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ ]]; then
  echo "Set KUBERNETES_VERSION to a preview-supported major.minor or major.minor.patch AKS version." >&2
  exit 2
fi
SYSTEM_NODE_VM_SIZE="${SYSTEM_NODE_VM_SIZE:-}"
SANDBOX_NODE_VM_SIZE="${SANDBOX_NODE_VM_SIZE:-}"
SKU_QUERY_TIMEOUT_SECONDS="${SKU_QUERY_TIMEOUT_SECONDS:-30}"
SKU_QUERY_MAX_ATTEMPTS="${SKU_QUERY_MAX_ATTEMPTS:-2}"
SKU_QUERY_HEARTBEAT_SECONDS="${SKU_QUERY_HEARTBEAT_SECONDS:-5}"
if [[ ! "$SKU_QUERY_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  echo "SKU_QUERY_TIMEOUT_SECONDS must be a positive integer." >&2
  exit 2
fi
if [[ ! "$SKU_QUERY_MAX_ATTEMPTS" =~ ^[1-9][0-9]*$ ]]; then
  echo "SKU_QUERY_MAX_ATTEMPTS must be a positive integer." >&2
  exit 2
fi
if [[ ! "$SKU_QUERY_HEARTBEAT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  echo "SKU_QUERY_HEARTBEAT_SECONDS must be a positive integer." >&2
  exit 2
fi
RESOURCE_GROUP_SCOPE="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}"
FOUNDRY_RESOURCE_GROUP_ID="${RESOURCE_GROUP_SCOPE}"
AKS_SCOPE="${RESOURCE_GROUP_SCOPE}/providers/Microsoft.ContainerService/managedClusters/${AKS_NAME}"
SYSTEM_NODE_VM_SIZE_DISPLAY="${SYSTEM_NODE_VM_SIZE:-auto (minimum 4 vCPU / 16 GiB)}"
SANDBOX_NODE_VM_SIZE_DISPLAY="${SANDBOX_NODE_VM_SIZE:-auto (minimum 8 vCPU / 32 GiB)}"

cat <<EOF
Mode:                    $([[ "$APPLY" == true ]] && echo apply || echo preview)
Subscription:            ${SUBSCRIPTION_ID}
Location:                ${LOCATION}
Resource group:          ${RESOURCE_GROUP}
AKS cluster:             ${AKS_NAME}
Kubernetes version:      ${KUBERNETES_VERSION}
System node VM size:     ${SYSTEM_NODE_VM_SIZE_DISPLAY}
Sandbox node VM size:    ${SANDBOX_NODE_VM_SIZE_DISPLAY}
Sandbox node pool:       sandbox (AzureLinux / KataVmIsolation)
Image admission policy:  not configured by this script

FOUNDRY_RESOURCE_GROUP_ID=${FOUNDRY_RESOURCE_GROUP_ID}
AKS_RESOURCE_ID=${AKS_SCOPE}
EOF

run() {
  printf '+ '
  printf '%q ' "$@"
  printf '\n'
  "$@"
}

query_vm_skus_with_progress() {
  local sku_url="$1"
  local query="$2"
  local temp_dir stdout_file stderr_file query_pid
  local attempt elapsed status sku_count
  local timed_out

  temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/provision-aks-skus.XXXXXX")"
  stdout_file="${temp_dir}/stdout"
  stderr_file="${temp_dir}/stderr"

  for ((attempt = 1; attempt <= SKU_QUERY_MAX_ATTEMPTS; attempt++)); do
    : >"$stdout_file"
    : >"$stderr_file"
    echo "Querying Azure Compute SKU availability (attempt ${attempt}/${SKU_QUERY_MAX_ATTEMPTS})..."

    az rest \
      --method get \
      --url "$sku_url" \
      --query "$query" \
      --output tsv \
      >"$stdout_file" \
      2>"$stderr_file" &
    query_pid=$!
    elapsed=0
    status=0
    timed_out=false

    while kill -0 "$query_pid" 2>/dev/null; do
      sleep 1
      ((elapsed += 1))
      if ((elapsed % SKU_QUERY_HEARTBEAT_SECONDS == 0)); then
        echo "Still waiting for Azure Compute API... elapsed ${elapsed}s"
      fi
      if ((elapsed >= SKU_QUERY_TIMEOUT_SECONDS)); then
        timed_out=true
        kill "$query_pid" 2>/dev/null || true
        wait "$query_pid" 2>/dev/null || true
        status=124
        echo "Azure Compute SKU query timed out after ${SKU_QUERY_TIMEOUT_SECONDS}s." >&2
        break
      fi
    done

    if [[ "$timed_out" == false ]]; then
      set +e
      wait "$query_pid"
      status=$?
      set -e
    fi

    if [[ -s "$stderr_file" ]]; then
      cat "$stderr_file" >&2
    fi
    if ((status == 0)); then
      AVAILABLE_VM_SKUS="$(<"$stdout_file")"
      sku_count="$(awk 'NF { count++ } END { print count + 0 }' "$stdout_file")"
      echo "Received ${sku_count} subscription-available VM SKUs after ${elapsed}s."
      rm -f "$stdout_file" "$stderr_file"
      rmdir "$temp_dir"
      return 0
    fi

    if ((attempt < SKU_QUERY_MAX_ATTEMPTS)); then
      echo "Retrying Azure Compute SKU query..."
    fi
  done

  rm -f "$stdout_file" "$stderr_file"
  rmdir "$temp_dir"
  echo "Failed to query Azure Compute SKU availability after ${SKU_QUERY_MAX_ATTEMPTS} attempts." >&2
  return 1
}

load_available_vm_skus() {
  local query sku_url
  query="value[?
    resourceType=='virtualMachines' &&
    length(restrictions[?type=='Location' && contains(values, '${LOCATION}')]) == \`0\`
  ].[
    name,
    capabilities[?name=='vCPUs'].value | [0],
    capabilities[?name=='MemoryGB'].value | [0],
    capabilities[?name=='PremiumIO'].value | [0],
    capabilities[?name=='AcceleratedNetworkingEnabled'].value | [0],
    capabilities[?name=='HyperVGenerations'].value | [0],
    capabilities[?name=='CpuArchitectureType'].value | [0]
  ]"
  if [[ ! "$LOCATION" =~ ^[a-z0-9]+$ ]]; then
    echo "AZURE_LOCATION must be an Azure region code containing only lowercase letters and numbers." >&2
    return 1
  fi
  # az vm list-skus applies location/size filters after downloading the global catalog.
  sku_url="https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/providers/Microsoft.Compute/skus?api-version=2021-07-01&%24filter=location%20eq%20%27${LOCATION}%27"

  echo "Searching VM SKUs available to this subscription in ${LOCATION}..."
  if ! query_vm_skus_with_progress "$sku_url" "$query"; then
    echo "Failed to list VM SKUs in ${LOCATION}." >&2
    return 1
  fi
  if [[ -z "$AVAILABLE_VM_SKUS" ]]; then
    echo "Azure returned no available VM SKUs in ${LOCATION}." >&2
    return 1
  fi
}

vm_size_is_available() {
  local requested_size="$1"
  awk -F '\t' -v requested_size="$requested_size" \
    '$1 == requested_size { found = 1; exit } END { exit !found }' \
    <<<"$AVAILABLE_VM_SKUS"
}

select_vm_size() {
  local label="$1"
  local requested_size="$2"
  local preferred_size="$3"
  local minimum_vcpus="$4"
  local minimum_memory_gb="$5"
  local selected_size

  if [[ -n "$requested_size" ]]; then
    if ! vm_size_is_available "$requested_size"; then
      echo "${label} VM size ${requested_size} is not available to this subscription in ${LOCATION}." >&2
      return 1
    fi
    printf '%s\n' "$requested_size"
    return 0
  fi

  selected_size="$(
    awk -F '\t' \
      -v preferred_size="$preferred_size" \
      -v minimum_vcpus="$minimum_vcpus" \
      -v minimum_memory_gb="$minimum_memory_gb" '
      function is_true(value) {
        return tolower(value) == "true"
      }
      {
        name = $1
        vcpus = $2 + 0
        memory_gb = $3 + 0
        premium_io = $4
        accelerated_networking = $5
        hyper_v_generations = $6
        architecture = tolower($7)

        if (name !~ /^Standard_[DE][0-9]/ ||
            name ~ /Promo/ ||
            vcpus < minimum_vcpus ||
            memory_gb < minimum_memory_gb ||
            (architecture != "" && architecture != "x64") ||
            (hyper_v_generations != "" && hyper_v_generations !~ /V2/)) {
          next
        }

        score = (vcpus - minimum_vcpus) * 10000
        score += (memory_gb - minimum_memory_gb) * 100
        score += name ~ /^Standard_E/ ? 50 : 0
        score += is_true(premium_io) ? 0 : 20
        score += is_true(accelerated_networking) ? 0 : 10

        generation_penalty = 100
        if (match(name, /_v[0-9]+$/)) {
          generation = substr(name, RSTART + 2) + 0
          generation_penalty = generation >= 5 ? generation - 5 : (5 - generation) * 10
        }
        score += generation_penalty
        if (name == preferred_size) {
          score = -1
        }

        if (!found || score < best_score || (score == best_score && name < best_name)) {
          found = 1
          best_score = score
          best_name = name
        }
      }
      END {
        if (found) {
          print best_name
        }
      }
    ' <<<"$AVAILABLE_VM_SKUS"
  )"

  if [[ -z "$selected_size" ]]; then
    echo "No suitable ${label} VM size is available in ${LOCATION}; require at least ${minimum_vcpus} vCPU and ${minimum_memory_gb} GiB." >&2
    echo "Set the corresponding *_NODE_VM_SIZE environment variable to override automatic selection." >&2
    return 1
  fi
  printf '%s\n' "$selected_size"
}

wait_for_provisioning_state() {
  local label="$1"
  shift
  local attempts=60
  local state=""

  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if ! state="$("$@")"; then
      echo "Could not query provisioning state for ${label}; retrying." >&2
      state=""
    fi
    case "$state" in
      Succeeded) return 0 ;;
      Failed|Canceled)
        echo "${label} reached terminal state ${state}." >&2
        return 1
        ;;
    esac
    echo "Waiting for ${label}: ${state:-unavailable} (${attempt}/${attempts})"
    sleep 15
  done

  echo "Timed out waiting for ${label}. Last state: ${state:-unknown}" >&2
  return 1
}

if [[ "$APPLY" != true ]]; then
  echo
  echo "Preview only. Re-run with --apply to provision the AKS cluster and sandbox pool."
  exit 0
fi

# Step 0: verify the existing resource group first.
run az group show --subscription "$SUBSCRIPTION_ID" --name "$RESOURCE_GROUP" --output none
echo "Reusing resource group: ${RESOURCE_GROUP_SCOPE}"

# Step 1: AKS and sandbox-pool provisioning.
load_available_vm_skus
SYSTEM_NODE_VM_SIZE="$(
  select_vm_size "system node pool" "$SYSTEM_NODE_VM_SIZE" "Standard_D4ds_v5" 4 16
)"
SANDBOX_NODE_VM_SIZE="$(
  select_vm_size "sandbox node pool" "$SANDBOX_NODE_VM_SIZE" "Standard_D8as_v5" 8 32
)"
echo "Selected system node VM size:  ${SYSTEM_NODE_VM_SIZE}"
echo "Selected sandbox node VM size: ${SANDBOX_NODE_VM_SIZE}"

if ! AKS_NAMES="$(az aks list --subscription "$SUBSCRIPTION_ID" -g "$RESOURCE_GROUP" --query '[].name' -o tsv)"; then
  echo "Failed to list AKS clusters. Check Azure CLI access before retrying." >&2
  exit 1
fi
AKS_NAMES="${AKS_NAMES//$'\r'/}"
if ! grep -Fxq -- "$AKS_NAME" <<<"$AKS_NAMES"; then
  run az aks create --subscription "$SUBSCRIPTION_ID" -g "$RESOURCE_GROUP" -n "$AKS_NAME" --location "$LOCATION" \
    --kubernetes-version "$KUBERNETES_VERSION" --node-vm-size "$SYSTEM_NODE_VM_SIZE" \
    --node-count 1 --network-plugin azure --network-plugin-mode overlay \
    --network-policy azure \
    --enable-managed-identity --enable-oidc-issuer --enable-workload-identity \
    --enable-aad --enable-azure-rbac \
    --no-ssh-key --output none --no-wait
fi
wait_for_provisioning_state "AKS cluster ${AKS_NAME}" \
  az aks show --subscription "$SUBSCRIPTION_ID" -g "$RESOURCE_GROUP" -n "$AKS_NAME" --query provisioningState -o tsv

if ! POOL_NAMES="$(az aks nodepool list --subscription "$SUBSCRIPTION_ID" -g "$RESOURCE_GROUP" --cluster-name "$AKS_NAME" --query '[].name' -o tsv)"; then
  echo "Failed to list AKS node pools. Check Azure CLI access before retrying." >&2
  exit 1
fi
POOL_NAMES="${POOL_NAMES//$'\r'/}"
if ! grep -Fxq -- "sandbox" <<<"$POOL_NAMES"; then
  run az aks nodepool add --subscription "$SUBSCRIPTION_ID" -g "$RESOURCE_GROUP" --cluster-name "$AKS_NAME" -n sandbox \
    --mode User --node-count 1 --node-vm-size "$SANDBOX_NODE_VM_SIZE" --os-sku AzureLinux \
    --workload-runtime KataVmIsolation \
    --labels agents.ai.azure.com/sandbox-node=true --ssh-access disabled --output none --no-wait
fi
wait_for_provisioning_state "AKS node pool sandbox" \
  az aks nodepool show --subscription "$SUBSCRIPTION_ID" -g "$RESOURCE_GROUP" --cluster-name "$AKS_NAME" -n sandbox --query provisioningState -o tsv

echo
echo "AKS provisioning complete. Cluster/pool report Succeeded."
echo "This script did not create ACR resources, change NSG rules, or configure an ACR image-admission policy."
echo "Before deploying agents, verify Ready nodes and complete the remaining Foundry BYO-AKS prerequisites."
echo "FOUNDRY_RESOURCE_GROUP_ID=${FOUNDRY_RESOURCE_GROUP_ID}"
echo "AKS_RESOURCE_ID=${AKS_SCOPE}"
