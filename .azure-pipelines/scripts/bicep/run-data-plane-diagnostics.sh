#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "usage: $0 <resource-group> <location> <deployment-file>" >&2
  exit 2
fi

resource_group="$1"
location="$2"
deployment_file="$3"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
script_path="$repo_root/.azure-pipelines/scripts/bicep/run-data-plane-diagnostics.sh"
diagnostic_sample_dir="$repo_root/samples/python/hosted-agents/bring-your-own/invocations/diagnostic-agent"
subscription_id="${AZURE_SUBSCRIPTION_ID:?AZURE_SUBSCRIPTION_ID must be set}"
build_id="${BUILD_BUILDID:-${BUILD_BUILD_ID:-local}}"
job_attempt="${SYSTEM_JOBATTEMPT:-1}"
fallback_location="${DIAGNOSTIC_FALLBACK_LOCATION:-${CI_LOCATION_FALLBACK:-}}"

log_issue() {
  local type="$1"
  local message="$2"
  echo "##vso[task.logissue type=$type]$message"
}

begin_group() {
  echo "##[group]$1"
}

end_group() {
  echo "##[endgroup]"
}

require_tool() {
  local tool="$1"
  if ! command -v "$tool" >/dev/null 2>&1; then
    log_issue error "Required tool '$tool' is not installed."
    exit 1
  fi
}

ensure_azd() {
  if ! command -v azd >/dev/null 2>&1; then
    begin_group "Install Azure Developer CLI"
    curl -fsSL https://aka.ms/install-azd.sh | bash
    export PATH="$HOME/.azd/bin:$PATH"
    end_group
  fi

  begin_group "Configure azd hosted agents extension"
  azd version
  azd ext install azure.ai.projects || azd ext upgrade azure.ai.projects || true
  azd ext install azure.ai.agents || azd ext upgrade azure.ai.agents || true

  azd config set auth.useAzCliAuth true
  azd config set defaults.subscription "$subscription_id"
  end_group
}

json_array_from_lines() {
  jq -R -s -c 'split("\n") | map(select(length > 0))'
}

discover_project() {
  local projects_json
  projects_json="$(az resource list \
    --resource-group "$resource_group" \
    --resource-type "Microsoft.CognitiveServices/accounts/projects" \
    -o json)"

  if [ "$(jq 'length' <<<"$projects_json")" -eq 0 ]; then
    echo ""
    return 0
  fi

  jq -r '.[0].id' <<<"$projects_json"
}

principal_object_id_from_token() {
  local token
  token="$(az account get-access-token --resource https://management.azure.com --query accessToken -o tsv)"
  python3 - "$token" <<'PY'
import base64
import json
import sys

token = sys.argv[1]
payload = token.split(".")[1]
payload += "=" * (-len(payload) % 4)
claims = json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")))
print(claims.get("oid") or claims.get("appid") or "")
PY
}

grant_project_access() {
  local project_id="$1"
  local principal_oid
  principal_oid="$(principal_object_id_from_token)"

  if [ -z "$principal_oid" ]; then
    log_issue warning "Could not determine Azure service connection principal object id; skipping project data-plane role assignment."
    return
  fi

  begin_group "Grant service connection project data-plane access"
  echo "Principal object id: $principal_oid"
  echo "Project scope: $project_id"

  local assigned=false
  for role in "Azure AI Developer" "Azure AI User" "Cognitive Services User"; do
    if [ -z "$(az role definition list --name "$role" --query '[0].name' -o tsv)" ]; then
      echo "Role '$role' is not available in this tenant; skipping."
      continue
    fi

    if az role assignment create \
      --assignee-object-id "$principal_oid" \
      --assignee-principal-type ServicePrincipal \
      --role "$role" \
      --scope "$project_id" \
      --only-show-errors >/dev/null; then
      echo "Assigned '$role'."
      assigned=true
    else
      echo "Role '$role' may already be assigned or is not assignable at project scope."
    fi
  done

  if [ "$assigned" = "true" ]; then
    echo "Waiting for data-plane role assignment propagation."
    sleep 30
  fi
  end_group
}

create_fallback_diagnostic_project() {
  local fallback="$1"
  local safe_location
  local account_name
  local project_name
  local template_file

  safe_location="$(printf '%s' "$fallback" | tr -cd '[:alnum:]' | cut -c1-8)"
  account_name="$(printf 'dpdiag%s%s%s' "$build_id" "$job_attempt" "$safe_location" \
    | tr '[:upper:]' '[:lower:]' \
    | tr -cd '[:alnum:]' \
    | cut -c1-45)"
  project_name="${account_name}-proj"
  template_file="$(mktemp --suffix=.bicep)"

  cat > "$template_file" <<'BICEP'
param accountName string
param projectName string
param location string

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'S0'
  }
  kind: 'AIServices'
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    disableLocalAuth: false
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  name: projectName
  parent: account
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

output projectId string = project.id
BICEP

  az deployment group create \
    --resource-group "$resource_group" \
    --name "diagnostic-fallback-$safe_location" \
    --template-file "$template_file" \
    --parameters accountName="$account_name" projectName="$project_name" location="$fallback" \
    --query properties.outputs.projectId.value -o tsv

  rm -f "$template_file"
}

host_from_url() {
  python3 - "$1" <<'PY'
import sys
from urllib.parse import urlparse

value = sys.argv[1].strip()
if not value:
    sys.exit(0)
if "://" not in value:
    value = "https://" + value
print(urlparse(value).hostname or "")
PY
}

discover_probe_hosts() {
  local account_name="$1"
  local hosts_file="$2"
  local endpoints_file

  endpoints_file="$(mktemp)"

  {
    az resource show --ids "$account_id" \
      --query "[properties.endpoint, properties.endpoints.*][]" -o tsv 2>/dev/null || true
    az resource show --ids "$project_id" \
      --query "properties.endpoints.*" -o tsv 2>/dev/null || true
  } | while IFS= read -r endpoint; do host_from_url "$endpoint"; done \
    | sed '/^$/d' | sort -u > "$endpoints_file"

  {
    if [ -s "$endpoints_file" ]; then
      cat "$endpoints_file"
    else
      printf '%s.services.ai.azure.com\n' "$account_name"
      printf '%s.cognitiveservices.azure.com\n' "$account_name"
      printf '%s.openai.azure.com\n' "$account_name"
    fi

    az storage account list --resource-group "$resource_group" \
      --query "[].primaryEndpoints.blob" -o tsv 2>/dev/null \
      | while IFS= read -r endpoint; do host_from_url "$endpoint"; done

    az cosmosdb list --resource-group "$resource_group" \
      --query "[].documentEndpoint" -o tsv 2>/dev/null \
      | while IFS= read -r endpoint; do host_from_url "$endpoint"; done

    az resource list --resource-group "$resource_group" \
      --resource-type "Microsoft.Search/searchServices" \
      --query "[].name" -o tsv 2>/dev/null \
      | while IFS= read -r name; do [ -n "$name" ] && printf '%s.search.windows.net\n' "$name"; done

    az acr list --resource-group "$resource_group" \
      --query "[].loginServer" -o tsv 2>/dev/null || true
  } | sed '/^$/d' | sort -u > "$hosts_file"

  rm -f "$endpoints_file"
}

extract_first_json_object() {
  local output_file="$1"
  local json_file="$2"
  python3 - "$output_file" "$json_file" <<'PY'
import json
import sys

text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
decoder = json.JSONDecoder()
for i, ch in enumerate(text):
    if ch != "{":
        continue
    try:
        obj, _ = decoder.raw_decode(text[i:])
    except json.JSONDecodeError:
        continue
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
    sys.exit(0)

sys.exit(1)
PY
}

validate_diagnostic_response() {
  local response_file="$1"
  python3 - "$response_file" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    doc = json.load(f)

failures: list[str] = []
non_failing_statuses = {None, "ok", "warn"}

agent_status = doc.get("status")
if agent_status == "handler_error":
    failures.append(f"handler_error: {doc.get('error', {}).get('message', '<no message>')}")
elif agent_status == "partial":
    failures.append("diagnostic agent reported a partial result")

for section_error in doc.get("section_errors") or []:
    failures.append(f"section {section_error.get('section')} failed: {section_error.get('err')}")

results = doc.get("results") or []
host_results = [result for result in results if (result.get("target") or {}).get("host")]
checks = doc.get("checks") or {}
legacy_hosts = checks.get("hosts") or []
if not host_results and not legacy_hosts:
    failures.append("diagnostic response did not include any host probes")

results_by_host: dict[str, list[dict]] = {}
for result in host_results:
    host = result["target"]["host"]
    results_by_host.setdefault(host, []).append(result)

print("Data-plane diagnostic host summary:")
for host, host_probe_results in sorted(results_by_host.items()):
    statuses = " ".join(
        f"{result.get('probe', '<unknown>')}={result.get('status', '<unknown>')}"
        for result in host_probe_results
    )
    print(f"- {host}: {statuses}")

    for result in host_probe_results:
        if result.get("status") in {"fail", "error"}:
            failures.append(
                f"{host} {result.get('probe', '<unknown>')} failed: "
                f"{result.get('summary') or result.get('findings') or result}"
            )

for public_result in (result for result in results if result.get("probe") == "egress.public"):
    if public_result.get("status") in {"fail", "error"}:
        failures.append(
            f"public probe {(public_result.get('target') or {}).get('url')} failed: "
            f"{public_result.get('summary') or public_result.get('findings') or public_result}"
        )

for host_result in legacy_hosts:
    host = host_result.get("host", "<unknown>")
    dns = host_result.get("dns") or {}
    tcp = host_result.get("tcp_443") or {}
    tls = host_result.get("tls_443") or {}
    http = host_result.get("http_get") or {}
    http_status = http.get("code") if http.get("status") == "ok" else http.get("status")
    print(f"- {host}: dns={dns.get('status')} tcp={tcp.get('status')} tls={tls.get('status')} http={http_status}")

    for layer_name, layer in (("dns", dns), ("tcp_443", tcp), ("tls_443", tls)):
        if layer.get("status") not in non_failing_statuses:
            failures.append(
                f"{host} {layer_name} failed: {layer.get('err') or layer.get('msg') or layer.get('hint') or layer}"
            )

    if http and http.get("status") not in non_failing_statuses:
        failures.append(
            f"{host} http_get failed: {http.get('err') or http.get('msg') or http.get('hint') or http}"
        )

for public_result in checks.get("public_hosts") or []:
    if public_result.get("status") not in non_failing_statuses:
        failures.append(
            f"public probe {public_result.get('url')} failed: "
            f"{public_result.get('err') or public_result.get('msg') or public_result}"
        )

summary = doc.get("summary") or {}
if summary.get("status") in {"fail", "error"} and not any(
    result.get("status") in {"fail", "error"} for result in host_results
):
    failures.append(f"diagnostic summary reported {summary.get('status')}")

if failures:
    print("Data-plane diagnostic failures:", file=sys.stderr)
    for failure in failures:
        print(f"- {failure}", file=sys.stderr)
    sys.exit(1)
PY
}

invoke_with_retries() {
  local payload_file="$1"
  local output_file="$2"
  local attempt
  local max_attempts=5
  local backoff=30
  local token
  local http_code
  local session_id

  token="$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)"

  for attempt in $(seq 1 "$max_attempts"); do
    session_id="$(python3 - <<'PY'
import uuid
print(f"ci-{uuid.uuid4().hex}")
PY
)"
    http_code="$(curl -sS -o "$output_file" -w "%{http_code}" \
      -X POST "${project_endpoint%/}/agents/$agent_name/endpoint/protocols/invocations?api-version=v1&agent_session_id=$session_id" \
      -H "Authorization: Bearer $token" \
      -H "Content-Type: application/json" \
      --max-time 180 \
      --data @"$payload_file" || true)"

    if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
      return 0
    fi

    if grep -qi "regional_session_quota_exceeded" "$output_file"; then
      return 42
    fi

    if [ "$attempt" -eq "$max_attempts" ]; then
      return 1
    fi

    if [ "$http_code" = "424" ] ||
       [ "$http_code" = "429" ] ||
       grep -qiE "Too Many Requests|status[ _]?code[: ]+429|session_not_ready|status[ _]?code[: ]+424|readiness|still being provisioned|version is still being|server_error|internal server error|connection reset|EOF|stream error.*CANCEL" "$output_file"; then
      echo "Diagnostic invoke attempt $attempt returned HTTP $http_code for session $session_id; retrying in ${backoff}s."
      sleep "$backoff"
      backoff=$((backoff * 2))
      continue
    fi

    return 1
  done
}

require_tool az
require_tool jq
require_tool python3

begin_group "Discover Foundry project and probe targets"
project_id="${DIAGNOSTIC_PROJECT_ID_OVERRIDE:-}"
if [ -z "$project_id" ]; then
  project_id="$(discover_project)"
fi
if [ -z "$project_id" ]; then
  echo "No Microsoft.CognitiveServices/accounts/projects resource was deployed in $resource_group; skipping hosted-agent data-plane diagnostics."
  end_group
  exit 0
fi

account_name="$(sed -nE 's|.*/accounts/([^/]+)/projects/.*|\1|p' <<<"$project_id")"
project_name="$(sed -nE 's|.*/projects/([^/]+)$|\1|p' <<<"$project_id")"
account_id="$(sed -nE 's|(.*?/accounts/[^/]+)/projects/.*|\1|p' <<<"$project_id")"
project_endpoint="$(az resource show --ids "$project_id" --query "properties.endpoints.\"AI Foundry API\"" -o tsv 2>/dev/null || true)"
if [ -z "$project_endpoint" ] || [ "$project_endpoint" = "null" ]; then
  project_endpoint="https://${account_name}.services.ai.azure.com/api/projects/${project_name}"
fi

echo "Deployment file: $deployment_file"
echo "Resource group:  $resource_group"
echo "Location:        $location"
echo "Account:         $account_name"
echo "Project:         $project_name"
echo "Project ID:      $project_id"
echo "Project endpoint:$project_endpoint"

public_network_access="$(az resource show --ids "$account_id" --query properties.publicNetworkAccess -o tsv 2>/dev/null || true)"
if [ "${public_network_access,,}" = "disabled" ] && [ "${DIAGNOSTIC_PRIVATE_ENDPOINT_ACCESS:-false}" != "true" ]; then
  log_issue warning "Skipping hosted-agent data-plane diagnostics because the Foundry account has publicNetworkAccess=Disabled and the Microsoft-hosted ADO runner cannot reach private endpoints. Deployment validation still covered this private sample. Set DIAGNOSTIC_PRIVATE_ENDPOINT_ACCESS=true only when the runner has private endpoint connectivity."
  end_group
  exit 0
fi

hosts_file="$(mktemp)"
if [ -n "${DIAGNOSTIC_PROBE_HOSTS:-}" ]; then
  printf '%s\n' "$DIAGNOSTIC_PROBE_HOSTS" | sed '/^$/d' | sort -u > "$hosts_file"
else
  discover_probe_hosts "$account_name" "$hosts_file"
fi
echo "Probe hosts:"
sed 's/^/  - /' "$hosts_file"
if [ ! -s "$hosts_file" ]; then
  log_issue error "No data-plane hosts were discovered for $resource_group."
  exit 1
fi
end_group

grant_project_access "$project_id"
ensure_azd

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir" "$hosts_file"' EXIT

agent_name="$(printf 'ci-diag-%s-%s-%s' "$build_id" "$job_attempt" "$account_name" \
  | tr '[:upper:]' '[:lower:]' \
  | tr -cd '[:alnum:]-' \
  | cut -c1-63 \
  | sed -e 's/^-*//' -e 's/-*$//')"
azd_env_name="$(printf 'fsci-dp-%s-%s' "$build_id" "$job_attempt" \
  | tr '[:upper:]' '[:lower:]' \
  | tr -cd '[:alnum:]-' \
  | cut -c1-32 \
  | sed -e 's/^-*//' -e 's/-*$//')"

begin_group "Scaffold diagnostic hosted agent"
cd "$work_dir"
cp -a "$diagnostic_sample_dir"/. .
service_src="src/diagnostic-agent-python-invocations"

if [ ! -f azure.yaml ] || [ ! -d "$service_src" ]; then
  log_issue error "Diagnostic hosted-agent sample is missing azure.yaml or $service_src."
  exit 1
fi

if [ ! -f "$service_src/main.py" ]; then
  log_issue error "Diagnostic hosted-agent sample is missing $service_src/main.py."
  exit 1
fi

sed -i "0,/^name: diagnostic-agent-python-invocations$/s//name: $agent_name/" azure.yaml
sed -i "s/^  diagnostic-agent-python-invocations:/  $agent_name:/" azure.yaml
sed -i "s/^    name: diagnostic-agent-python-invocations$/    name: $agent_name/" azure.yaml

azd env new "$azd_env_name" \
  --subscription "$subscription_id" \
  --location "$location" \
  --no-prompt

azd env set AZURE_SUBSCRIPTION_ID "$subscription_id"
azd env set AZURE_LOCATION "$location"
azd env set AZURE_RESOURCE_GROUP "$resource_group"
azd env set AZURE_AI_PROJECT_ID "$project_id"
azd env set AZURE_AI_PROJECT_ENDPOINT "$project_endpoint"
azd env set FOUNDRY_PROJECT_ENDPOINT "$project_endpoint"
azd env set enableHostedAgentVNext true

echo "Diagnostic agent name: $agent_name"
echo "azd environment:       $azd_env_name"
echo "Service source:        $service_src"
end_group

begin_group "Deploy diagnostic hosted agent"
SKIP_ACR_CREATION=true azd deploy --no-prompt
end_group

begin_group "Build diagnostic invocation payload"
hosts_json="$(cat "$hosts_file" | json_array_from_lines)"
payload_file="$work_dir/diagnostic-payload.json"
jq -n \
  --argjson hosts "$hosts_json" \
  '{
    hosts: $hosts,
    public_hosts: [
      "https://management.azure.com/metadata/endpoints?api-version=2022-09-01",
      "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration"
    ],
    include_env_dump: false,
    include_container_info: true,
    tcp_timeout_sec: 5,
    http_timeout_sec: 10
  }' > "$payload_file"
cat "$payload_file"
end_group

begin_group "Invoke diagnostic hosted agent"
invoke_output="$work_dir/diagnostic-invoke-output.txt"
set +e
invoke_with_retries "$payload_file" "$invoke_output"
invoke_status=$?
set -e
if [ "$invoke_status" -ne 0 ]; then
  cat "$invoke_output"
  if [ "$invoke_status" -eq 42 ] &&
     [ "${DISABLE_DIAGNOSTIC_FALLBACK:-false}" != "true" ] &&
     [ -n "$fallback_location" ] &&
     [ "$fallback_location" != "$location" ]; then
    end_group
    begin_group "Create fallback-region diagnostic project"
    echo "Hosted-agent sessions are at capacity in $location; retrying diagnostics from $fallback_location."
    if ! fallback_project_id="$(create_fallback_diagnostic_project "$fallback_location")" || [ -z "$fallback_project_id" ]; then
      log_issue error "Failed to create fallback-region diagnostic project in $fallback_location."
      exit 1
    fi
    echo "Fallback diagnostic project: $fallback_project_id"
    end_group

    DIAGNOSTIC_PROJECT_ID_OVERRIDE="$fallback_project_id" \
      DIAGNOSTIC_PROJECT_LOCATION_OVERRIDE="$fallback_location" \
      DIAGNOSTIC_PROBE_HOSTS="$(cat "$hosts_file")" \
      DISABLE_DIAGNOSTIC_FALLBACK=true \
      bash "$script_path" "$resource_group" "$fallback_location" "$deployment_file"
    exit $?
  fi
  log_issue error "Diagnostic hosted-agent invocation failed."
  exit 1
fi
cat "$invoke_output"
end_group

begin_group "Evaluate data-plane diagnostic results"
response_json="$work_dir/diagnostic-response.json"
if ! extract_first_json_object "$invoke_output" "$response_json"; then
  log_issue error "Could not extract diagnostic JSON response from hosted-agent invocation output."
  exit 1
fi
cat "$response_json" | jq .
validate_diagnostic_response "$response_json"
end_group
