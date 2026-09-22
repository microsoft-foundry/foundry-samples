#!/usr/bin/env bash
# Prepares a job-local azure.yaml for either an external shared toolbox or
# isolated, cell-owned toolboxes. Never edits the committed sample manifest.

set -euo pipefail

usage() {
  echo "Usage: $0 <azure.yaml> <state.json> <run-id> <run-attempt> <combo-id> [shared-toolbox-endpoint] [shared-connections-json]" >&2
  exit 2
}

[ "$#" -ge 5 ] && [ "$#" -le 7 ] || usage

manifest=$1
state_file=$2
run_id=$3
run_attempt=$4
combo_id=$5
shared_endpoint=${6:-}
shared_connections=${7:-'[]'}

[ -f "$manifest" ] || { echo "Manifest not found: $manifest" >&2; exit 1; }
command -v yq >/dev/null || { echo "yq is required" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

# Explicitly selected warm-project fixtures are read-only dependencies, even
# when the cell owns its toolbox. Never infer ownership from SKIP_PROVISION or
# from connection existence alone. Callers pass [] for fresh-resource runs.
shared_connections=$(jq -ce '
  if type == "array" and all(.[]; type == "string" and test("^[A-Za-z0-9_-]+$"))
  then unique else error("Expected an array of shared connection names") end
' <<< "$shared_connections")
if [ "$shared_connections" != '[]' ]; then
  [ -z "$shared_endpoint" ] || { echo "Cannot combine shared connections with a shared toolbox override" >&2; exit 1; }
  manifest_json=$(yq -o=json '.' "$manifest")
  # Only toolbox-upstream services with unambiguous resource names qualify.
  # Refuse configuration drift instead of silently dropping a new consumer.
  if ! jq -e --argjson names "$shared_connections" '
      .services as $services |
      all($names[]; . as $name |
        $services[$name].host == "azure.ai.connection" and
        ($services[$name].name // $name) == $name and
        any($services[]; .host == "azure.ai.toolbox" and
          any(.uses[]?; . == $name) and any(.tools[]?; .connection == $name)))
    ' <<< "$manifest_json" >/dev/null; then
    echo "Shared connections must name declared toolbox-upstream connection services" >&2
    exit 1
  fi
  unsafe_reference=$(jq --argjson names "$shared_connections" '
      .services as $services |
      any($services | to_entries[] | select(.key as $key | $names | index($key) | not) | .value;
        (if .host == "azure.ai.toolbox" then del(.uses, .tools[]?.connection)
         elif .host == "azure.ai.agent" and any(.uses[]?; $services[.].host == "azure.ai.toolbox")
         then del(.uses) else . end) |
        any(.. | strings; . as $text | any($names[]; . as $name | $text | contains($name))))
    ' <<< "$manifest_json")
  if [ "$unsafe_reference" != "false" ]; then
    echo "Shared connection is referenced outside toolbox bindings; refusing to remove its declaration" >&2
    exit 1
  fi
  removed=$(jq -c 'map({key: ., value: true}) | from_entries' <<< "$shared_connections")
  REMOVED_SERVICES="$removed" yq -i '
    .services |= with_entries(select(env(REMOVED_SERVICES)[.key] != true)) |
    (.services[] | select(has("uses")) | .uses) |=
      map(select(env(REMOVED_SERVICES)[.] != true))
  ' "$manifest"
  echo "Reusing shared project connections (read-only): $(jq -r 'join(", ")' <<< "$shared_connections")"
fi

# Matrix cells use a pre-existing toolbox instead of the sample's tool surface.
# Since connections beta.7, leaving the upstream connection services declared
# makes azd deploy PUT them in every cell, even with SKIP_PROVISION=true.
# Remove only connections wired into the replaced toolboxes; independently
# declared connections remain managed. Empty state also prevents verification
# and cleanup from treating the shared toolbox as a cell-owned resource.
if [ -n "$shared_endpoint" ]; then
  if [[ ! "$shared_endpoint" =~ ^https://[^/]+/api/projects/[^/]+/toolboxes/([^/?]+)/ ]]; then
    echo "Invalid shared toolbox endpoint: $shared_endpoint" >&2
    exit 1
  fi
  shared_name=${BASH_REMATCH[1]}
  manifest_json=$(yq -o=json '.' "$manifest")
  if jq -e 'any(.services[]; .host == "azure.ai.agent" and
      (has("toolbox") or has("toolboxes") or ((.config // {}) | has("toolboxes"))))' \
      <<< "$manifest_json" >/dev/null; then
    echo "Shared toolbox override requires a runtime env consumer, not native agent toolbox bindings" >&2
    exit 1
  fi
  removed=$(jq -c '
    .services as $services |
    [.services | to_entries[] | select(.value.host == "azure.ai.toolbox")] as $toolboxes |
    ([$toolboxes[].key] +
      [$toolboxes[].value.uses[]? | select($services[.].host == "azure.ai.connection")]) |
    unique | map({key: ., value: true}) | from_entries
  ' <<< "$manifest_json")

  # Agent uses edges to the replaced toolbox's upstream connections are
  # redundant in these runtime relays. Any other surviving use (including a
  # direct credential expression in agent env) is not safe to strip. Fail closed
  # rather than silently removing a connection still needed by another consumer.
  if jq -e --argjson removed "$removed" '
      .services as $services |
      [$removed | keys[] | select($services[.].host == "azure.ai.connection") |
        ., ($services[.].name // .)] | unique as $connections |
      any($services | to_entries[] | select($removed[.key] != true) | .value;
        (if .host == "azure.ai.agent" and
            any(.uses[]?; $services[.].host == "azure.ai.toolbox")
          then del(.uses) else . end) |
        any(.. | strings; . as $text | any($connections[]; . as $name | $text | contains($name))))
    ' <<< "$manifest_json" >/dev/null; then
    echo "Cannot remove toolbox connections still referenced by a retained service" >&2
    exit 1
  fi

  REMOVED_SERVICES="$removed" SHARED_NAME="$shared_name" SHARED_ENDPOINT="$shared_endpoint" \
    yq -i '
      .services |= with_entries(select(env(REMOVED_SERVICES)[.key] != true)) |
      (.services[] | select(has("uses")) | .uses) |=
        map(select(env(REMOVED_SERVICES)[.] != true)) |
      (.services[] | select(.host == "azure.ai.agent") | .env.TOOLBOX_NAME) = strenv(SHARED_NAME) |
      (.services[] | select(.host == "azure.ai.agent") | .env.TOOLBOX_ENDPOINT) = strenv(SHARED_ENDPOINT) |
      (.services[] | select(.host == "azure.ai.agent") | select(has("environmentVariables")) |
        .environmentVariables[] | select(.name == "TOOLBOX_NAME") | .value) = strenv(SHARED_NAME) |
      (.services[] | select(.host == "azure.ai.agent") | select(has("environmentVariables")) |
        .environmentVariables[] | select(.name == "TOOLBOX_ENDPOINT") | .value) = strenv(SHARED_ENDPOINT) |
      (.services[] | select(.host == "azure.ai.agent") | select(has("config")) |
        .config | select(has("env")) | .env | select(has("TOOLBOX_NAME")) |
        .TOOLBOX_NAME) = strenv(SHARED_NAME) |
      (.services[] | select(.host == "azure.ai.agent") | select(has("config")) |
        .config | select(has("env")) | .env | select(has("TOOLBOX_ENDPOINT")) |
        .TOOLBOX_ENDPOINT) = strenv(SHARED_ENDPOINT)
    ' "$manifest"
  echo "Shared toolbox: $shared_name; removed local services: $(jq -r 'keys | join(", ")' <<< "$removed")"
fi

normalize_env_segment() {
  printf '%s' "$1" | tr '[:lower:]' '[:upper:]' | sed -E 's/[^A-Z0-9]+/_/g'
}

generate_name() {
  local original=$1 hash base max_base
  hash=$(printf '%s' "${run_id}:${run_attempt}:${combo_id}:${original}" | sha256sum | cut -c1-12)
  max_base=$((63 - 1 - ${#hash}))
  base="ci-e2e-tb-${original}"
  base=${base:0:max_base}
  base=$(printf '%s' "$base" | sed -E 's/[^A-Za-z0-9_-]+/-/g; s/[-_]+$//')
  [ -n "$base" ] || base="ci-e2e-tb"
  printf '%s-%s' "$base" "$hash"
}

if ! originals_output=$(yq -r '.services | to_entries[] | select(.value.host == "azure.ai.toolbox") | .key' "$manifest"); then
  echo "Failed to parse toolbox services from $manifest" >&2
  exit 1
fi
originals=()
if [ -n "$originals_output" ]; then
  mapfile -t originals <<< "$originals_output"
fi

state='[]'
declare -A normalized_keys=()

for original in "${originals[@]}"; do
  generated=$(generate_name "$original")
  if [[ ! "$generated" =~ ^[A-Za-z0-9_-]+$ ]] || [ "${#generated}" -gt 63 ]; then
    echo "Invalid generated toolbox name: $generated" >&2
    exit 1
  fi

  old_endpoint_key="TOOLBOX_$(normalize_env_segment "$original")_MCP_ENDPOINT"
  new_endpoint_key="TOOLBOX_$(normalize_env_segment "$generated")_MCP_ENDPOINT"
  if [ -n "${normalized_keys[$new_endpoint_key]:-}" ]; then
    echo "Generated toolbox endpoint key collision: $new_endpoint_key" >&2
    exit 1
  fi
  normalized_keys[$new_endpoint_key]=1

  # Every traversal below is guarded with `has(...)`. A bare `.a.b` or `.a[]?`
  # on the left-hand side of a yq assignment *creates* the missing nodes, so an
  # unguarded `.env.TOOLBOX_NAME?` stamps `env: {TOOLBOX_NAME: null}` onto every
  # service. azure.ai.agents >= 1.0.0-beta.7 merges the service `env:` map over
  # `environmentVariables:` (Azure/azure-dev#9149) and renders a null as "", so
  # those stubs silently blanked TOOLBOX_NAME on every deployed agent.
  #
  # TOOLBOX_NAME is rewritten in two passes: an unconditional match on the
  # pre-rename literal, and a `${TOOLBOX_NAME}` placeholder match restricted to
  # services that actually consume this toolbox (`uses:`), so multi-toolbox
  # samples cannot have their placeholder claimed by an unrelated toolbox.
  OLD_NAME="$original" NEW_NAME="$generated" PLACEHOLDER='${TOOLBOX_NAME}' \
  OLD_ENDPOINT_KEY="$old_endpoint_key" NEW_ENDPOINT_KEY="$new_endpoint_key" \
    yq -i '
      (.services[] | select(has("uses")) | .uses[] |
        select(. == strenv(OLD_NAME))) = strenv(NEW_NAME) |
      (.services[] | select(has("environmentVariables")) | .environmentVariables[] |
        select(.name == "TOOLBOX_NAME" and .value == strenv(OLD_NAME)) | .value) = strenv(NEW_NAME) |
      (.services[] | select(has("environmentVariables")) | select(has("uses")) |
        select([.uses[] | select(. == strenv(NEW_NAME))] | length > 0) |
        .environmentVariables[] |
        select(.name == "TOOLBOX_NAME" and .value == strenv(PLACEHOLDER)) | .value) = strenv(NEW_NAME) |
      (.services[] | select(has("env")) | select(.env | has("TOOLBOX_NAME")) |
        .env.TOOLBOX_NAME |
        select(. == strenv(OLD_NAME) or . == strenv(PLACEHOLDER))) = strenv(NEW_NAME) |
      (.. | select(tag == "!!str")) |=
        sub("\\$\\{" + strenv(OLD_ENDPOINT_KEY) + "\\}"; "$$" + "{" + strenv(NEW_ENDPOINT_KEY) + "}") |
      .services = (
        .services | to_entries |
        ((.[] | select(.key == strenv(OLD_NAME)) | .key) = strenv(NEW_NAME)) |
        from_entries
      )
    ' "$manifest"

  state=$(jq -c \
    --arg original "$original" \
    --arg name "$generated" \
    --arg old_endpoint_key "$old_endpoint_key" \
    --arg endpoint_key "$new_endpoint_key" \
    '. + [{original_name:$original, name:$name, old_endpoint_key:$old_endpoint_key, endpoint_key:$endpoint_key}]' \
    <<< "$state")

  echo "Toolbox isolation: $original -> $generated"
done

mkdir -p "$(dirname "$state_file")"
jq -n --argjson toolboxes "$state" --argjson sharedConnections "$shared_connections" \
  '{toolboxes:$toolboxes, sharedConnections:$sharedConnections}' > "$state_file"

# Every uses edge must still resolve to a declared service after rewriting.
# shellcheck disable=SC2016 # $services is a yq variable, not a shell variable.
dangling=$(yq -o=json '[.services as $services | .services[] | .uses[]? | select($services[.] == null)]' "$manifest")
if [ "$(jq 'length' <<< "$dangling")" -ne 0 ]; then
  echo "Dangling service references after toolbox isolation:" >&2
  jq . <<< "$dangling" >&2
  exit 1
fi

# Every generated toolbox must exist exactly once as an azure.ai.toolbox service.
while IFS= read -r generated; do
  count=$(NAME="$generated" yq '[.services | to_entries[] | select(.key == strenv(NAME) and .value.host == "azure.ai.toolbox")] | length' "$manifest")
  if [ "$count" -ne 1 ]; then
    echo "Expected one generated toolbox service named $generated, found $count" >&2
    exit 1
  fi
done < <(jq -r '.toolboxes[].name' "$state_file")

# The old endpoint variable must not survive in any scalar manifest value.
while IFS= read -r old_key; do
  old_ref="\${${old_key}}"
  if OLD_REF="$old_ref" yq -e '[.. | select(tag == "!!str") | select(contains(strenv(OLD_REF)))] | length > 0' "$manifest" >/dev/null 2>&1; then
    echo "Old toolbox endpoint placeholder still referenced after rewrite: $old_ref" >&2
    exit 1
  fi
done < <(jq -r '.toolboxes[].old_endpoint_key' "$state_file")

# Collects every declared environment value across the three shapes the agents
# extension merges at deploy time: the `environmentVariables:` list, the
# service-level `env:` map, and the deprecated `config: env:` map. Each shape is
# queried separately on purpose — yq collapses a comma union to nothing when the
# first term is empty under an `as $var` binding, which would make these checks
# silently vacuous.
env_entries() {
  {
    yq -o=json '[.services | to_entries[] as $service |
      $service.value.environmentVariables[]? |
      {"service": $service.key, "source": "environmentVariables", "key": .name, "value": .value}]' "$manifest"
    yq -o=json '[.services | to_entries[] as $service |
      $service.value.env? | select(. != null) | to_entries[] |
      {"service": $service.key, "source": "env", "key": .key, "value": .value}]' "$manifest"
    yq -o=json '[.services | to_entries[] as $service |
      $service.value.config.env? | select(. != null) | to_entries[] |
      {"service": $service.key, "source": "config.env", "key": .key, "value": .value}]' "$manifest"
  } | jq -s 'add'
}

entries=$(env_entries)

# No TOOLBOX_NAME may still point at a pre-rename toolbox name. Both rewrite
# passes are silent no-ops when they match nothing, so without this check a
# sample that changes how it declares TOOLBOX_NAME quietly deploys against a
# shared toolbox owned by another matrix cell.
stale=$(jq --slurpfile state "$state_file" '
  ($state[0].toolboxes | map(.original_name)) as $originals |
  map(select(.key == "TOOLBOX_NAME" and (.value as $v | $originals | index($v))))' <<< "$entries")
if [ "$(jq 'length' <<< "$stale")" -ne 0 ]; then
  echo "TOOLBOX_NAME still references a pre-rename toolbox after isolation:" >&2
  jq . <<< "$stale" >&2
  exit 1
fi

# A null/empty value silently becomes "" in the deployed agent, and since
# azure.ai.agents 1.0.0-beta.7 the `env:`/`config: env:` maps are merged over
# `environmentVariables:`, so a blank entry erases a correct value.
blank=$(jq 'map(select(.value == null or .value == ""))' <<< "$entries")
if [ "$(jq 'length' <<< "$blank")" -ne 0 ]; then
  echo "Blank environment values would override the deployed agent configuration:" >&2
  jq . <<< "$blank" >&2
  exit 1
fi

jq . "$state_file"
