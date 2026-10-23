#!/usr/bin/env bash
# Exercise azd itself. Python handles structured contracts, not Azure operations.
set -euo pipefail

script_dir=$(dirname "$(realpath "${BASH_SOURCE[0]}")")
repo=$(realpath "$script_dir/../../..")
python=${PYTHON:-python3}
sample= project_id= project_endpoint= model= artifacts= spec=
command_timeout=1200
turn_timeout=600
usage() {
  echo "Usage: $0 --sample PATH --project-id ID --project-endpoint URL --model-deployment NAME --artifacts NEWPATH [--repo PATH] [--spec PATH] [--command-timeout SECONDS] [--turn-timeout SECONDS]"
}
while [ "$#" -gt 0 ]; do
  if [ "$1" = --help ]; then usage; exit 0; fi
  [ "$#" -ge 2 ] || { usage >&2; exit 2; }
  case "$1" in
    --repo) repo=$2 ;;
    --sample) sample=$2 ;;
    --project-id) project_id=$2 ;;
    --project-endpoint) project_endpoint=${2%/} ;;
    --model-deployment) model=$2 ;;
    --artifacts) artifacts=$2 ;;
    --spec) spec=$2 ;;
    --command-timeout) command_timeout=$2 ;;
    --turn-timeout) turn_timeout=$2 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift 2
done
[ -n "$sample" ] && [ -n "$project_id" ] && [ -n "$project_endpoint" ] &&
  [ -n "$model" ] && [ -n "$artifacts" ] || { usage >&2; exit 2; }
for seconds in "$command_timeout" "$turn_timeout"; do
  [[ "$seconds" =~ ^[1-9][0-9]*$ ]] || { echo "timeouts must be positive integer seconds" >&2; exit 2; }
done
for tool in "$python" jq az azd timeout; do
  command -v "$tool" >/dev/null || { echo "$tool is required" >&2; exit 1; }
done
# Preserve ARM IDs under Git Bash and avoid native jq CRLF in shell variables.
case "${OSTYPE:-}" in
  msys*|cygwin*) export MSYS_NO_PATHCONV=1; jq() { command jq --binary "$@"; } ;;
esac
# Native Windows Python/azd need Windows paths; Linux uses the original paths.
native_path() {
  case "${OSTYPE:-}" in msys*|cygwin*) cygpath -m "$1" ;; *) printf '%s\n' "$1" ;; esac
}
repo=$(realpath "$repo")
artifacts=$(realpath -m "$artifacts")
[ -z "$spec" ] || spec=$(realpath "$spec")
helper=$(native_path "$script_dir/prompt_agent_helpers.py")
evaluator=$(native_path "$repo/.github/scripts/hosted_agent_test_spec.py")
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
prepare=(prepare --repo "$(native_path "$repo")" --sample "$sample" --project-id "$project_id"
  --project-endpoint "$project_endpoint" --model-deployment "$model"
  --artifacts "$(native_path "$artifacts")" --work "$(native_path "$work")")
[ -z "$spec" ] || prepare+=(--spec "$(native_path "$spec")")
"$python" "$helper" "${prepare[@]}"
context=$(native_path "$artifacts/context.json")
name=$(jq -r .agent_name "$context")
service=$(jq -r .agent_service "$context")
env_key=$(jq -r .service_env_key "$context")
account=$(jq -r .account_name "$context")
toolbox=$(jq -r .toolbox_name "$context")
deployed=false
toolbox_deployed=false
cleanup_status=not_needed
toolbox_cleanup_status=not_needed
cleanup_failed=false
command_index=0
last_code=0
last_stdout= last_stderr=

save_ownership() {
  jq --argjson attempted "$deployed" --arg status "$cleanup_status" --arg name "$name" \
    --argjson toolbox_attempted "$toolbox_deployed" --arg toolbox "$toolbox" --arg toolbox_status "$toolbox_cleanup_status" '
    .deployment_attempted = $attempted |
    .toolbox_deployment_attempted = $toolbox_attempted |
    .cleanup = ((if $attempted then {($name): $status} else {} end) +
      (if $toolbox_attempted then {($toolbox): $toolbox_status} else {} end))
  ' "$(native_path "$artifacts/ownership.json")" > "$work/ownership.json" &&
    cp "$work/ownership.json" "$artifacts/ownership.json"
}

# Logs live in scratch first: unavailable artifacts must not suppress cleanup.
run_command() {
  local seconds=$1 mode=$2 code=0 logging_failed=false
  shift 2
  command_index=$((command_index + 1))
  last_stdout="$work/command-$command_index-stdout.txt"
  last_stderr="$work/command-$command_index-stderr.txt"
  if ! jq -n --args '$ARGS.positional' -- "$@" > "$work/command-$command_index.json"; then
    if [ "$mode" != cleanup ]; then return 1; fi
    cleanup_failed=true
  fi
  if ! { : > "$last_stdout" && : > "$last_stderr"; }; then
    if [ "$mode" != cleanup ]; then return 1; fi
    cleanup_failed=true
    # Still attempt identity pinning/deletion when even scratch capture is unavailable.
    if timeout --kill-after=10s "${seconds}s" "$@" >&2; then last_code=0; else last_code=$?; fi
    return 0
  fi
  if timeout --kill-after=10s "${seconds}s" "$@" > "$last_stdout" 2> "$last_stderr"; then
    code=0
  else
    code=$?
  fi
  last_code=$code
  if ! jq -n --argjson code "$code" --slurpfile argv "$(native_path "$work/command-$command_index.json")" \
    '{command:$argv[0], exit_code:$code, timed_out:($code == 124 or $code == 137)}' \
    > "$artifacts/command-$command_index.json"; then logging_failed=true; fi
  cp "$last_stdout" "$artifacts/command-$command_index-stdout.txt" || logging_failed=true
  cp "$last_stderr" "$artifacts/command-$command_index-stderr.txt" || logging_failed=true
  if [ "$logging_failed" = true ]; then
    if [ "$mode" = cleanup ]; then cleanup_failed=true; else return 1; fi
  fi
  # Probe callers examine the captured exit code; normal commands fail immediately.
  if [ "$mode" = checked ] && [ "$code" -ne 0 ]; then
    echo "Command failed ($code): $*" >&2
    return "$code"
  fi
}

absent() {
  "$python" "$helper" absent --stderr "$(native_path "$last_stderr")" --stdout "$(native_path "$last_stdout")" \
    --exit-code "$last_code" --context "$context" --project-endpoint "$project_endpoint"
}

finish() {
  local code=$? evaluation=1 final=1 attempt
  trap - EXIT INT TERM
  set +e
  # Leave time for the separately authenticated recovery and infra teardown tasks.
  local cleanup_timeout=10
  if [ "$deployed" = true ]; then
    cleanup_status=unverified
    if run_command "$cleanup_timeout" cleanup azd env set "AGENT_${env_key}_NAME" "$name" && [ "$last_code" -eq 0 ]; then
      run_command "$cleanup_timeout" cleanup azd ai agent delete "$service" --force --no-prompt --output json
      [ "$last_code" -eq 0 ] || cleanup_failed=true
      for attempt in 1 2 3; do
        if ! run_command "$cleanup_timeout" cleanup azd ai agent show "$service" --output json --no-prompt; then
          cleanup_failed=true; break
        fi
        if absent; then cleanup_status=absent; break; fi
        [ "$last_code" -eq 0 ] || break
        [ "$attempt" -eq 3 ] || sleep 5
      done
    else
      cleanup_failed=true
    fi
    [ "$cleanup_status" = absent ] || cleanup_failed=true
  fi
  if [ "$toolbox_deployed" = true ]; then
    toolbox_cleanup_status=unverified
    run_command "$cleanup_timeout" cleanup azd ai toolbox delete "$toolbox" \
      --project-endpoint "$project_endpoint" --force --no-prompt --output json
    [ "$last_code" -eq 0 ] || cleanup_failed=true
    for attempt in 1 2 3; do
      if ! run_command "$cleanup_timeout" cleanup azd ai toolbox list \
        --project-endpoint "$project_endpoint" --output json --no-prompt; then break; fi
      [ "$last_code" -eq 0 ] || break
      if "$python" "$helper" toolbox-absent --metadata "$(native_path "$last_stdout")" --context "$context"; then
        toolbox_cleanup_status=absent; break
      fi
      [ "$attempt" -eq 3 ] || sleep 5
    done
    [ "$toolbox_cleanup_status" = absent ] || cleanup_failed=true
  fi
  save_ownership || cleanup_failed=true
  "$python" "$evaluator" evaluate --plan "$(native_path "$artifacts/plan.json")" \
    --evidence-dir "$(native_path "$artifacts/evidence")" \
    --console-log "$(native_path "$artifacts/unused-console.log")" \
    --trace-file "$(native_path "$artifacts/unused-traces.json")" \
    --report "$(native_path "$artifacts/report.json")" >&2
  evaluation=$?
  if [ "$code" -eq 0 ] && [ "$evaluation" -eq 0 ] && [ "$cleanup_failed" = false ]; then final=0; fi
  if ! jq -n --argjson code "$code" --argjson evaluation "$evaluation" --argjson final "$final" \
    --slurpfile ownership "$(native_path "$artifacts/ownership.json")" '
    {status:(if $final == 0 then "passed" else "failed" end), exit_code:$code,
     evaluation_exit_code:$evaluation, cleanup:$ownership[0].cleanup,
     response_retention:$ownership[0].response_retention}
  ' > "$artifacts/result.json"; then final=1; fi
  cat "$artifacts/result.json"
  if [ "${PROMPT_AGENT_KEEP_WORKSPACE:-false}" != true ]; then rm -rf "$work"; fi
  exit "$final"
}

# Project-scoped azd and the EXIT cleanup run in the disposable workspace.
mkdir "$work/project"
cd "$work/project"
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
run_command 60 checked az resource show --ids "$project_id" --query 'properties.endpoints."AI Foundry API"' -o tsv
resolved=$(tr -d '\r\n' < "$last_stdout")
[ "${resolved%/}" = "$project_endpoint" ] || { echo "project endpoint does not match ARM project" >&2; exit 1; }
run_command "$command_timeout" checked azd version
run_command "$command_timeout" checked azd extension list --installed --output json
run_command "$command_timeout" checked azd ai agent init -m "$(native_path "$work/input/azure.yaml")" \
  --project-id "$project_id" --model-deployment "$model" --agent-name "$name" \
  --src . --no-prompt --environment "$name"
"$python" "$helper" verify-adopted --manifest "$(native_path "$work/project/azure.yaml")" --context "$context" --model-deployment "$model"
run_command "$command_timeout" checked azd env set AZURE_AI_PROJECT_ID "$project_id"
run_command "$command_timeout" checked azd env set AZURE_AI_PROJECT_ENDPOINT "$project_endpoint"
run_command "$command_timeout" checked azd env set FOUNDRY_PROJECT_ENDPOINT "$project_endpoint"
run_command "$command_timeout" checked azd env set AZURE_AI_ACCOUNT_NAME "$account"
run_command "$command_timeout" checked azd env set "AGENT_${env_key}_NAME" "$name"
cp "$work/project/azure.yaml" "$artifacts/azure.yaml"
run_command "$command_timeout" probe azd ai agent show "$service" --output json --no-prompt
absent || { echo "cannot confirm generated name is unused; refusing deployment" >&2; exit 1; }
verify_options=()
if [ -n "$toolbox" ]; then
  run_command "$command_timeout" checked azd ai toolbox list --project-endpoint "$project_endpoint" --output json --no-prompt
  "$python" "$helper" toolbox-absent --metadata "$(native_path "$last_stdout")" --context "$context" || {
    echo "cannot confirm generated toolbox name is unused; refusing deployment" >&2; exit 1;
  }
  toolbox_deployed=true
  save_ownership
  run_command "$command_timeout" checked azd deploy "$toolbox" --no-prompt --timeout "$command_timeout"
  toolbox_env_key=${toolbox//-/_}
  toolbox_env_key=${toolbox_env_key^^}
  run_command "$command_timeout" checked azd env get-value "TOOLBOX_${toolbox_env_key}_MCP_ENDPOINT"
  toolbox_endpoint=$(tr -d '\r\n' < "$last_stdout")
  run_command "$command_timeout" checked azd ai toolbox show "$toolbox" --project-endpoint "$project_endpoint" --output json --no-prompt
  cp "$last_stdout" "$artifacts/toolbox.json"
  "$python" "$helper" verify-toolbox --metadata "$(native_path "$artifacts/toolbox.json")" --context "$context" --endpoint "$toolbox_endpoint"
  verify_options=(--toolbox-metadata "$(native_path "$artifacts/toolbox.json")")
fi
deployed=true
save_ownership
run_command "$command_timeout" checked azd deploy "$service" --no-prompt --timeout "$command_timeout"
run_command "$command_timeout" checked azd ai agent show "$service" --output json --no-prompt
cp "$last_stdout" "$artifacts/agent.json"
"$python" "$helper" verify-deployed --metadata "$(native_path "$artifacts/agent.json")" --context "$context" --model-deployment "$model" "${verify_options[@]}"
jq -c '.[]' "$(native_path "$artifacts/turns.json")" > "$work/turns.jsonl"
while IFS= read -r turn; do
  number=$(jq -r .global_turn <<< "$turn")
  prefix="$artifacts/evidence/turn-$number"
  invoke=(ai agent invoke "$service" --input-file "$(native_path "$prefix-input.txt")" --protocol responses --no-prompt)
  if [ "$(jq -r .new_conversation <<< "$turn")" = true ]; then invoke+=(--new-conversation); fi
  run_command "$turn_timeout" probe azd "${invoke[@]}"
  cp "$last_stdout" "$prefix-stdout.txt"
  cp "$last_stderr" "$prefix-stderr.txt"
  "$python" "$helper" record-turn --prefix "$(native_path "$prefix")" --exit-code "$last_code"
  [ "$last_code" -eq 0 ] || { echo "azd invoke failed for turn $number ($last_code)" >&2; exit 1; }
done < "$work/turns.jsonl"
