#!/usr/bin/env bash
# Recovery for a separately authenticated always() task; never initialize a project.
set +x
set -euo pipefail
umask 077

script_dir=$(dirname "$(realpath "${BASH_SOURCE[0]}")")
python=${PYTHON:-python3}
artifacts= project_id= project_endpoint= model=
usage() {
  echo "Usage: $0 --artifacts DIR --project-id ID --project-endpoint URL --model-deployment NAME"
}
while [ "$#" -gt 0 ]; do
  if [ "$1" = --help ]; then usage; exit 0; fi
  [ "$#" -ge 2 ] || { usage >&2; exit 2; }
  case "$1" in
    --artifacts) artifacts=$2 ;;
    --project-id) project_id=$2 ;;
    --project-endpoint) project_endpoint=${2%/} ;;
    --model-deployment) model=$2 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift 2
done
[ -n "$artifacts" ] && [ -n "$project_id" ] && [ -n "$project_endpoint" ] &&
  [ -n "$model" ] || { usage >&2; exit 2; }

case "${OSTYPE:-}" in
  msys*|cygwin*) export MSYS_NO_PATHCONV=1; jq() { command jq --binary "$@"; } ;;
esac
native_path() {
  case "${OSTYPE:-}" in msys*|cygwin*) cygpath -m "$1" ;; *) printf '%s\n' "$1" ;; esac
}
artifacts=$(realpath -m "$artifacts")
ownership=$(native_path "$artifacts/ownership.json")
if [ ! -e "$artifacts/ownership.json" ] && [ ! -L "$artifacts/ownership.json" ]; then
  echo "No ownership ledger; no recovery resources to attempt."
  exit 0
fi
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }
mkdir -p "$artifacts/recovery"
recovery=$(mktemp -d "$artifacts/recovery/attempt-XXXXXX")
context=$(native_path "$artifacts/context.json")
helper=$(native_path "$script_dir/prompt_agent_helpers.py")
validated=false
cleanup_failed=false
command_index=0
last_code=0
last_stdout= last_stderr=

finish() {
  local code=$? cleanup=null
  trap - EXIT INT TERM
  set +e
  if [ "$cleanup_failed" = true ]; then code=1; fi
  if [ "$validated" = true ]; then
    cleanup=$(jq -c .cleanup "$ownership") || code=1
    if [ -e "$artifacts/result.json" ]; then
      # Recovery can update cleanup evidence, but can never upgrade an E2E result.
      if jq -s --argjson cleanup "$cleanup" --argjson code "$code" '
        if length != 1 or (.[0] | type) != "object" then error("invalid result") else
          .[0] | .cleanup = $cleanup | if $code != 0 then .status = "failed" else . end
        end
      ' "$(native_path "$artifacts/result.json")" > "$recovery/result.tmp" 2>> "$recovery/validation-stderr.txt"; then
        mv "$recovery/result.tmp" "$artifacts/result.json" || code=1
      else
        code=1
      fi
    fi
  fi
  if jq -n --argjson code "$code" --argjson validated "$validated" --argjson cleanup "$cleanup" '
    {status:"cleanup-only", exit_code:$code, ownership_validated:$validated,
     cleanup_status:(if $code == 0 then "complete" else "failed" end), cleanup:$cleanup}
  ' > "$recovery/recovery-result.json"; then
    cp "$recovery/recovery-result.json" "$artifacts/recovery-result.json" || code=1
  else
    code=1
  fi
  if [ "$code" -eq 0 ]; then
    echo "Prompt-agent recovery complete (cleanup only, not an E2E pass)."
  else
    echo "Prompt-agent recovery failed; inspect recovery diagnostics and retain pending resources for orphan cleanup." >&2
  fi
  # The disposable pipeline agent owns scratch disposal. Never publish its .azure/auth files.
  exit "$code"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

fail() { echo "$1" >&2; exit 1; }
for tool in "$python" timeout; do
  command -v "$tool" >/dev/null || fail "$tool is required"
done

# Validate the complete ledger/context before using any artifact-supplied identity.
if ! jq -e -s --arg id "$project_id" --arg endpoint "$project_endpoint" --slurpfile contexts "$context" '
  length == 1 and ($contexts | length) == 1 and
  (.[0] as $o | $contexts[0] as $c |
    ($o | type) == "object" and ($c | type) == "object" and
    $o.project_id == $id and ($o.project_endpoint | rtrimstr("/")) == $endpoint and
    ($c.project_endpoint | rtrimstr("/")) == $endpoint and
    ($o.deployment_attempted | type) == "boolean" and
    ($o.toolbox_deployment_attempted | type) == "boolean" and
    ($o.working_directory | type) == "string" and
    ($o.working_directory | test("^(?:/[^/]|[A-Za-z]:[/\\\\])")) and
    ($o.working_directory | test("[\\x00-\\x1f\\x7f]") | not) and
    ($c.agent_name | type) == "string" and ($c.agent_name | test("^ci-prompt-[0-9a-f]{32}$")) and
    $o.agent_name == $c.agent_name and $o.agent_service == $c.agent_service and
    ($c.agent_service | type) == "string" and ($c.agent_service | test("^[A-Za-z0-9][A-Za-z0-9_ -]*$")) and
    $c.service_env_key == ($c.agent_service | gsub("[- ]"; "_") | ascii_upcase) and
    ($c.service_env_key | test("^[A-Z0-9_]+$")) and
    $o.toolbox_name == $c.toolbox_name and
    (if $c.execution_profile == "managed" then
       $c.toolbox_name == ("ci-e2e-tb-" + ($c.agent_name | ltrimstr("ci-prompt-")))
     else $c.execution_profile == "prompt" and $c.toolbox_name == "" and
       $o.toolbox_deployment_attempted == false end) and
    ($o.cleanup | type) == "object" and
    ($o.cleanup | to_entries | all(
      ((.key == $o.agent_name and $o.deployment_attempted) or
       (.key == $o.toolbox_name and $o.toolbox_deployment_attempted)) and
      (.value | type) == "string" and (.value | length) > 0)))
' "$ownership" > "$recovery/validation-stdout.txt" 2> "$recovery/validation-stderr.txt"; then
  fail "Invalid ownership/context or trusted project mismatch; refusing recovery commands."
fi
validated=true
name=$(jq -r .agent_name "$context")
service=$(jq -r .agent_service "$context")
env_key=$(jq -r .service_env_key "$context")
toolbox=$(jq -r .toolbox_name "$context")
agent_pending=$(jq -r '.deployment_attempted and .cleanup[.agent_name] != "absent"' "$ownership")
toolbox_pending=$(jq -r '.toolbox_deployment_attempted and .cleanup[.toolbox_name] != "absent"' "$ownership")
if [ "$agent_pending" = false ] && [ "$toolbox_pending" = false ]; then exit 0; fi

work=$(jq -r .working_directory "$ownership")
case "${OSTYPE:-}" in msys*|cygwin*) work=$(cygpath -u "$work") ;; esac
project="$work/project"
[ -d "$project" ] || fail "Owned working directory/project is missing while cleanup is pending; refusing to initialize it."
for manifest in "$artifacts/azure.yaml" "$project/azure.yaml"; do
  if ! timeout --kill-after=10s 60s "$python" "$helper" verify-adopted \
    --manifest "$(native_path "$manifest")" --context "$context" --model-deployment "$model" \
    >> "$recovery/validation-stdout.txt" 2>> "$recovery/validation-stderr.txt"; then
    fail "Saved adopted manifest verification failed; refusing recovery commands."
  fi
done
cmp -s "$artifacts/azure.yaml" "$project/azure.yaml" || fail "Working project differs from the saved adopted manifest."
command -v azd >/dev/null || fail "azd is required"

run_command() {
  local code
  command_index=$((command_index + 1))
  last_stdout="$recovery/command-$command_index-stdout.txt"
  last_stderr="$recovery/command-$command_index-stderr.txt"
  last_code=125
  if ! { : > "$last_stdout" && : > "$last_stderr"; }; then cleanup_failed=true; return 1; fi
  if timeout --kill-after=10s 60s "$@" > "$last_stdout" 2> "$last_stderr"; then code=0; else code=$?; fi
  last_code=$code
  if ! jq -n --argjson code "$code" --args '
    {command:$ARGS.positional, exit_code:$code, timed_out:($code == 124 or $code == 137)}
  ' -- "$@" > "$recovery/command-$command_index.json"; then cleanup_failed=true; fi
  return "$code"
}
save_status() {
  jq --arg name "$1" --arg status "$2" '.cleanup[$name] = $status' "$ownership" \
    > "$recovery/ownership.tmp" && mv "$recovery/ownership.tmp" "$artifacts/ownership.json"
}
agent_absent() {
  # A timeout is not absence, even if a partial stream happens to contain a 404.
  [ "$last_code" -ne 0 ] && [ "$last_code" -ne 124 ] && [ "$last_code" -ne 137 ] || return 1
  timeout --kill-after=10s 60s "$python" "$helper" absent \
    --stderr "$(native_path "$last_stderr")" --stdout "$(native_path "$last_stdout")" \
    --exit-code "$last_code" --context "$context" --project-endpoint "$project_endpoint" \
    >> "$recovery/validation-stdout.txt" 2>> "$recovery/validation-stderr.txt"
}
toolbox_absent() {
  timeout --kill-after=10s 60s "$python" "$helper" toolbox-absent \
    --metadata "$(native_path "$last_stdout")" --context "$context" \
    >> "$recovery/validation-stdout.txt" 2>> "$recovery/validation-stderr.txt"
}

# Pin both process variables and the retained azd environment; do not trust defaults.
export FOUNDRY_PROJECT_ENDPOINT="$project_endpoint" AZURE_AI_PROJECT_ENDPOINT="$project_endpoint"
export AZURE_AI_PROJECT_ID="$project_id" AZURE_ENV_NAME="$name" "AGENT_${env_key}_NAME=$name"
azd_project=(azd -C "$(native_path "$project")")
for key in FOUNDRY_PROJECT_ENDPOINT AZURE_AI_PROJECT_ENDPOINT AZURE_AI_PROJECT_ID "AGENT_${env_key}_NAME"; do
  run_command "${azd_project[@]}" env set "$key" "${!key}" --environment "$name" --no-prompt ||
    fail "Cannot pin the owned azd environment; refusing recovery commands."
done

cleanup_agent() {
  local attempt
  save_status "$name" unverified || return 1
  run_command "${azd_project[@]}" ai agent show "$service" --output json --no-prompt || :
  if agent_absent; then save_status "$name" absent; return $?; fi
  [ "$last_code" -eq 0 ] || return 1
  # Cleanup needs the exact identity, not a healthy/fully deployed definition.
  jq -e -s --arg name "$name" 'length == 1 and (.[0] | type) == "object" and .[0].name == $name' \
    "$(native_path "$last_stdout")" >> "$recovery/validation-stdout.txt" 2>> "$recovery/validation-stderr.txt" || return 1
  run_command "${azd_project[@]}" ai agent delete "$service" --force --no-prompt --output json || cleanup_failed=true
  for attempt in 1 2 3; do
    run_command "${azd_project[@]}" ai agent show "$service" --output json --no-prompt || :
    if agent_absent; then save_status "$name" absent; return $?; fi
    [ "$last_code" -eq 0 ] || return 1
    [ "$attempt" -eq 3 ] || sleep 5
  done
  return 1
}
cleanup_toolbox() {
  local attempt
  save_status "$toolbox" unverified || return 1
  run_command "${azd_project[@]}" ai toolbox list --project-endpoint "$project_endpoint" --output json --no-prompt || return 1
  if toolbox_absent; then save_status "$toolbox" absent; return $?; fi
  # The helper returns 1 for both presence and malformed data. Only valid presence permits deletion.
  jq -e -s --arg name "$toolbox" '
    length == 1 and (.[0] | type) == "object" and (.[0].toolboxes | type) == "array" and
    (.[0].toolboxes | all(type == "object" and (.name | type) == "string" and (.name | test("\\S")))) and
    (.[0].toolboxes | any((.name | ascii_downcase) == $name))
  ' "$(native_path "$last_stdout")" >> "$recovery/validation-stdout.txt" 2>> "$recovery/validation-stderr.txt" || return 1
  run_command "${azd_project[@]}" ai toolbox delete "$toolbox" --project-endpoint "$project_endpoint" \
    --force --no-prompt --output json || cleanup_failed=true
  for attempt in 1 2 3; do
    run_command "${azd_project[@]}" ai toolbox list --project-endpoint "$project_endpoint" --output json --no-prompt || return 1
    if toolbox_absent; then save_status "$toolbox" absent; return $?; fi
    [ "$attempt" -eq 3 ] || sleep 5
  done
  return 1
}
if [ "$agent_pending" = true ]; then cleanup_agent || cleanup_failed=true; fi
# Agent errors must not strand an independently owned toolbox.
if [ "$toolbox_pending" = true ]; then cleanup_toolbox || cleanup_failed=true; fi
if [ "$cleanup_failed" = true ]; then exit 1; fi
