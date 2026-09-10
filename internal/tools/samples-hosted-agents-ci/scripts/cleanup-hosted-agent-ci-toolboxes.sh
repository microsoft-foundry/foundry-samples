#!/usr/bin/env bash
# Deletes cell-owned E2E toolboxes and reclaims stale toolboxes left by
# cancelled jobs. Only the reserved ci-e2e-tb- namespace is eligible.

set -uo pipefail

usage() {
  cat >&2 <<EOF
Usage:
  $0 cell <state.json> <project-endpoint> <result.json>
  $0 orphans <project-endpoint> <ttl-seconds> <result.json>
EOF
  exit 2
}

[ "$#" -ge 1 ] || usage
mode=$1
command -v azd >/dev/null || { echo "azd is required" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

list_toolboxes() {
  local endpoint=$1 out err status
  # The caller captures stdout, so on failure azd's message would be swallowed
  # and only recorded as {"outcome":"list_failed"}. Keep stdout clean for the
  # JSON payload, capture stderr separately, and echo both when the call fails
  # so the actual reason (auth, RBAC, endpoint) reaches the log.
  err=$(mktemp)
  out=$(azd ai toolbox list \
    --project-endpoint "$endpoint" \
    --output json \
    --no-prompt 2>"$err")
  status=$?
  if [ "$status" -ne 0 ]; then
    {
      printf 'azd ai toolbox list failed (exit %s) for %s\n' "$status" "$endpoint"
      printf -- '--- stdout ---\n%s\n' "$out"
      printf -- '--- stderr ---\n%s\n' "$(cat "$err")"
    } >&2
  fi
  rm -f "$err"
  [ "$status" -eq 0 ] || return "$status"
  printf '%s\n' "$out"
}

delete_toolbox() {
  local endpoint=$1 name=$2
  azd ai toolbox delete "$name" \
    --project-endpoint "$endpoint" \
    --force \
    --output json \
    --no-prompt
}

# True when the toolbox is no longer present. A concurrent run can delete a
# toolbox between this janitor listing it and acting on it; that is the outcome
# the janitor wanted, so it must be told apart from a real failure. Returns
# non-zero if the check itself could not be made, so an unknown state is never
# mistaken for a benign disappearance.
toolbox_absent() {
  local endpoint=$1 name=$2 current
  current=$(list_toolboxes "$endpoint") || return 1
  ! jq -e --arg name "$name" '.toolboxes[]? | select(.name == $name)' <<< "$current" >/dev/null
}

write_result() {
  local output=$1 operation=$2 endpoint=$3 results=$4
  mkdir -p "$(dirname "$output")"
  jq -n \
    --arg operation "$operation" \
    --arg project_endpoint "$endpoint" \
    --argjson results "$results" \
    '{operation:$operation, project_endpoint:$project_endpoint, results:$results}' \
    > "$output"
  jq . "$output"
}

cleanup_cell() {
  [ "$#" -eq 3 ] || usage
  local state_file=$1 endpoint=$2 output=$3
  [ -f "$state_file" ] || {
    echo "No toolbox state file; nothing to clean up."
    write_result "$output" cell "$endpoint" '[]'
    return 0
  }

  local live results='[]' failed=0
  if ! live=$(list_toolboxes "$endpoint"); then
    results=$(jq -c '. + [{outcome:"list_failed"}]' <<< "$results")
    write_result "$output" cell "$endpoint" "$results"
    return 1
  fi

  while IFS= read -r name; do
    if [[ "$name" != ci-e2e-tb-* ]]; then
      echo "Refusing to delete toolbox outside the CI namespace: $name" >&2
      results=$(jq -c --arg name "$name" '. + [{name:$name,outcome:"refused"}]' <<< "$results")
      failed=1
      continue
    fi

    if ! jq -e --arg name "$name" '.toolboxes[]? | select(.name == $name)' <<< "$live" >/dev/null; then
      echo "Toolbox $name was not created; cleanup is a no-op."
      results=$(jq -c --arg name "$name" '. + [{name:$name,outcome:"not_found"}]' <<< "$results")
      continue
    fi

    echo "Deleting cell-owned toolbox: $name"
    if ! delete_toolbox "$endpoint" "$name" >/dev/null; then
      results=$(jq -c --arg name "$name" '. + [{name:$name,outcome:"delete_failed"}]' <<< "$results")
      failed=1
      continue
    fi

    if ! live_after=$(list_toolboxes "$endpoint"); then
      results=$(jq -c --arg name "$name" '. + [{name:$name,outcome:"verify_list_failed"}]' <<< "$results")
      failed=1
      continue
    fi
    if jq -e --arg name "$name" '.toolboxes[]? | select(.name == $name)' <<< "$live_after" >/dev/null; then
      results=$(jq -c --arg name "$name" '. + [{name:$name,outcome:"still_present"}]' <<< "$results")
      failed=1
    else
      results=$(jq -c --arg name "$name" '. + [{name:$name,outcome:"deleted"}]' <<< "$results")
    fi
  done < <(jq -r '.toolboxes[].name' "$state_file")

  write_result "$output" cell "$endpoint" "$results"
  return "$failed"
}

cleanup_orphans() {
  [ "$#" -eq 3 ] || usage
  local endpoint=$1 ttl_seconds=$2 output=$3
  [[ "$ttl_seconds" =~ ^[0-9]+$ ]] || { echo "TTL must be an integer number of seconds" >&2; return 2; }

  local live results='[]' failed=0 now
  now=$(date +%s)
  if ! live=$(list_toolboxes "$endpoint"); then
    results=$(jq -c '. + [{outcome:"list_failed"}]' <<< "$results")
    write_result "$output" orphans "$endpoint" "$results"
    return 1
  fi

  while IFS= read -r name; do
    echo "Inspecting possible orphan: $name"
    if ! versions=$(azd ai toolbox versions list "$name" \
      --project-endpoint "$endpoint" --output json --no-prompt); then
      if toolbox_absent "$endpoint" "$name"; then
        echo "Toolbox $name disappeared while being inspected; another run deleted it."
        results=$(jq -c --arg name "$name" '. + [{name:$name,outcome:"vanished"}]' <<< "$results")
        continue
      fi
      results=$(jq -c --arg name "$name" '. + [{name:$name,outcome:"version_list_failed"}]' <<< "$results")
      failed=1
      continue
    fi

    # Current azd emits created_at as epoch seconds. Accept common casing and
    # timestamp variants as well so a CLI schema evolution cannot silently
    # disable orphan reclamation.
    newest=$(jq -r '[.versions[] | (.created_at // .createdAt // .created // .createdDateTime // empty)] | max // empty' <<< "$versions")
    created_epoch=""
    if [[ "$newest" =~ ^[0-9]+$ ]]; then
      created_epoch=$newest
      # Be tolerant if a future API emits epoch milliseconds instead of the
      # current epoch-seconds contract.
      if [ "$created_epoch" -gt $((now * 100)) ]; then
        created_epoch=$((created_epoch / 1000))
      fi
    elif [ -n "$newest" ]; then
      created_epoch=$(date -d "$newest" +%s 2>/dev/null || true)
    fi
    if [[ ! "$created_epoch" =~ ^[0-9]+$ ]] || [ "$created_epoch" -le 0 ] || [ "$created_epoch" -gt "$now" ]; then
      # Fail closed: an unknown or future timestamp must never make a
      # concurrent run's live toolbox eligible for deletion.
      echo "Cannot safely establish age for $name; retaining it."
      results=$(jq -c --arg name "$name" '. + [{name:$name,outcome:"retained_unknown_age"}]' <<< "$results")
      continue
    fi
    age=$((now - created_epoch))
    if [ "$age" -lt "$ttl_seconds" ]; then
      results=$(jq -c --arg name "$name" --argjson age "$age" '. + [{name:$name,outcome:"retained_recent",age_seconds:$age}]' <<< "$results")
      continue
    fi

    echo "Deleting orphaned toolbox $name (${age}s old)"
    if delete_toolbox "$endpoint" "$name" >/dev/null; then
      results=$(jq -c --arg name "$name" --argjson age "$age" '. + [{name:$name,outcome:"deleted",age_seconds:$age}]' <<< "$results")
    elif toolbox_absent "$endpoint" "$name"; then
      echo "Toolbox $name was already gone; another run deleted it."
      results=$(jq -c --arg name "$name" --argjson age "$age" '. + [{name:$name,outcome:"vanished",age_seconds:$age}]' <<< "$results")
    else
      results=$(jq -c --arg name "$name" --argjson age "$age" '. + [{name:$name,outcome:"delete_failed",age_seconds:$age}]' <<< "$results")
      failed=1
    fi
  done < <(jq -r '.toolboxes[]?.name | select(startswith("ci-e2e-tb-"))' <<< "$live")

  if ! final=$(list_toolboxes "$endpoint"); then
    results=$(jq -c '. + [{outcome:"verify_list_failed"}]' <<< "$results")
    failed=1
  else
    # Every toolbox reported as deleted must be absent from the final list.
    mapfile -t deleted_names < <(jq -r '.[] | select(.outcome == "deleted") | .name' <<< "$results")
    for name in "${deleted_names[@]}"; do
      if jq -e --arg name "$name" '.toolboxes[]? | select(.name == $name)' <<< "$final" >/dev/null; then
        results=$(jq -c --arg name "$name" '
          map(if .name == $name and .outcome == "deleted" then .outcome = "still_present" else . end)
        ' <<< "$results")
        failed=1
      fi
    done
  fi

  write_result "$output" orphans "$endpoint" "$results"
  return "$failed"
}

case "$mode" in
  cell)
    shift
    cleanup_cell "$@"
    ;;
  orphans)
    shift
    cleanup_orphans "$@"
    ;;
  *) usage ;;
esac
