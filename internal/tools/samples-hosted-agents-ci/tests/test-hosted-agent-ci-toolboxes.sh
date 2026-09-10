#!/usr/bin/env bash

set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
prepare="$repo_root/internal/tools/samples-hosted-agents-ci/scripts/prepare-hosted-agent-ci-toolboxes.sh"
cleanup="$repo_root/internal/tools/samples-hosted-agents-ci/scripts/cleanup-hosted-agent-ci-toolboxes.sh"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_eq() {
  local want=$1 got=$2 message=$3
  [ "$want" = "$got" ] || fail "$message (want=$want got=$got)"
}

command -v yq >/dev/null || fail "yq is required"
command -v jq >/dev/null || fail "jq is required"

cat > "$work/original.yaml" <<'YAML'
name: toolbox-test
services:
  ai-project:
    host: azure.ai.project
  agent-tools:
    host: azure.ai.toolbox
    uses: [ai-project]
    tools:
      - type: code_interpreter
        # This unrelated literal intentionally collides with the toolbox key;
        # only structural toolbox references should be rewritten.
        name: agent-tools
  test-agent:
    host: azure.ai.agent
    uses: [ai-project, agent-tools]
    environmentVariables:
      - name: TOOLBOX_NAME
        value: agent-tools
      - name: TOOLBOX_ENDPOINT
        value: ${TOOLBOX_AGENT_TOOLS_MCP_ENDPOINT}
YAML

cp "$work/original.yaml" "$work/a.yaml"
"$prepare" "$work/a.yaml" "$work/a-state.json" 12345 2 sample-container >/dev/null
name_a=$(jq -r '.toolboxes[0].name' "$work/a-state.json")
[[ "$name_a" == ci-e2e-tb-* ]] || fail "generated name must use the reserved prefix"
[ "${#name_a}" -le 63 ] || fail "generated name exceeds 63 characters"
[[ "$name_a" =~ ^[A-Za-z0-9_-]+$ ]] || fail "generated name contains invalid characters"
assert_eq "$name_a" "$(yq -r '.services | to_entries[] | select(.value.host == "azure.ai.toolbox") | .key' "$work/a.yaml")" "toolbox service key was not rewritten"
assert_eq "$name_a" "$(yq -r '.services.test-agent.uses[1]' "$work/a.yaml")" "uses reference was not rewritten"
assert_eq "$name_a" "$(yq -r '.services.test-agent.environmentVariables[] | select(.name == "TOOLBOX_NAME") | .value' "$work/a.yaml")" "TOOLBOX_NAME was not rewritten"
assert_eq agent-tools "$(yq -r '.services[] | select(.host == "azure.ai.toolbox") | .tools[0].name' "$work/a.yaml")" "unrelated matching scalar must not be rewritten"
expected_endpoint_key=$(jq -r '.toolboxes[0].endpoint_key' "$work/a-state.json")
assert_eq "\${$expected_endpoint_key}" "$(yq -r '.services.test-agent.environmentVariables[] | select(.name == "TOOLBOX_ENDPOINT") | .value' "$work/a.yaml")" "derived endpoint key was not rewritten"

cp "$work/original.yaml" "$work/a-repeat.yaml"
"$prepare" "$work/a-repeat.yaml" "$work/a-repeat-state.json" 12345 2 sample-container >/dev/null
assert_eq "$name_a" "$(jq -r '.toolboxes[0].name' "$work/a-repeat-state.json")" "same cell must generate a deterministic name"

cp "$work/original.yaml" "$work/b.yaml"
"$prepare" "$work/b.yaml" "$work/b-state.json" 12345 2 sample-code >/dev/null
name_b=$(jq -r '.toolboxes[0].name' "$work/b-state.json")
[ "$name_a" != "$name_b" ] || fail "different cells must generate different names"

cat > "$work/no-toolbox.yaml" <<'YAML'
name: no-toolbox
services:
  test-agent:
    host: azure.ai.agent
YAML
"$prepare" "$work/no-toolbox.yaml" "$work/empty-state.json" 12345 1 no-toolbox >/dev/null
assert_eq 0 "$(jq '.toolboxes | length' "$work/empty-state.json")" "manifest without a toolbox must produce empty state"

cat > "$work/multiple.yaml" <<'YAML'
name: multiple-toolboxes
services:
  ai-project:
    host: azure.ai.project
  first-tools:
    host: azure.ai.toolbox
    uses: [ai-project]
  second-tools:
    host: azure.ai.toolbox
    uses: [ai-project]
  test-agent:
    host: azure.ai.agent
    uses: [ai-project, first-tools, second-tools]
YAML
"$prepare" "$work/multiple.yaml" "$work/multiple-state.json" 12345 1 multiple >/dev/null
assert_eq 2 "$(jq '.toolboxes | length' "$work/multiple-state.json")" "all toolbox services must be isolated"
# shellcheck disable=SC2016 # $services is a yq variable, not a shell variable.
assert_eq 0 "$(yq '[.services as $services | .services[] | .uses[]? | select($services[.] == null)] | length' "$work/multiple.yaml")" "multiple-toolbox rewrite left a dangling use"

# Rewriting must never materialize keys a service did not declare. An
# unguarded `.env.TOOLBOX_NAME?` on the left of a yq assignment creates
# `env: {TOOLBOX_NAME: null}` on every service, and since azure.ai.agents
# 1.0.0-beta.7 the `env:` map is merged over `environmentVariables:` with a
# null rendered as "", which silently blanks TOOLBOX_NAME on deploy.
assert_eq 0 "$(yq '[.services[] | select(has("env"))] | length' "$work/a.yaml")" "rewrite must not invent an env map"
assert_eq 0 "$(yq '[.services[] | select(has("env"))] | length' "$work/multiple.yaml")" "rewrite must not invent an env map"
assert_eq 0 "$(yq '[.services.ai-project | select(has("uses") or has("environmentVariables"))] | length' "$work/a.yaml")" "rewrite must not invent empty uses/environmentVariables"

# A sample may point TOOLBOX_NAME at a ${TOOLBOX_NAME} placeholder instead of
# the literal toolbox key. Consumers of a renamed toolbox must still be pinned
# to their own cell-owned toolbox rather than relying on azd env resolution.
cat > "$work/placeholder.yaml" <<'YAML'
name: placeholder-toolbox
services:
  ai-project:
    host: azure.ai.project
  agent-tools:
    host: azure.ai.toolbox
    uses: [ai-project]
  test-agent:
    host: azure.ai.agent
    uses: [ai-project, agent-tools]
    environmentVariables:
      - name: TOOLBOX_NAME
        value: ${TOOLBOX_NAME}
YAML
"$prepare" "$work/placeholder.yaml" "$work/placeholder-state.json" 12345 1 placeholder >/dev/null
placeholder_name=$(jq -r '.toolboxes[0].name' "$work/placeholder-state.json")
assert_eq "$placeholder_name" "$(yq -r '.services.test-agent.environmentVariables[] | select(.name == "TOOLBOX_NAME") | .value' "$work/placeholder.yaml")" "placeholder TOOLBOX_NAME was not pinned to the cell toolbox"

# Samples that consume an externally provisioned toolbox declare no toolbox
# service; their placeholder must be left for the workflow to resolve.
cat > "$work/external.yaml" <<'YAML'
name: external-toolbox
services:
  ai-project:
    host: azure.ai.project
  test-agent:
    host: azure.ai.agent
    uses: [ai-project]
    environmentVariables:
      - name: TOOLBOX_NAME
        value: ${TOOLBOX_NAME}
YAML
"$prepare" "$work/external.yaml" "$work/external-state.json" 12345 1 external >/dev/null
assert_eq '${TOOLBOX_NAME}' "$(yq -r '.services.test-agent.environmentVariables[] | select(.name == "TOOLBOX_NAME") | .value' "$work/external.yaml")" "external-toolbox placeholder must be left alone"

# Each agent in a multi-toolbox manifest must resolve its own placeholder from
# its own uses edge, never another cell-mate's toolbox.
cat > "$work/per-agent.yaml" <<'YAML'
name: per-agent-toolboxes
services:
  ai-project:
    host: azure.ai.project
  first-tools:
    host: azure.ai.toolbox
    uses: [ai-project]
  second-tools:
    host: azure.ai.toolbox
    uses: [ai-project]
  first-agent:
    host: azure.ai.agent
    uses: [ai-project, first-tools]
    environmentVariables:
      - name: TOOLBOX_NAME
        value: ${TOOLBOX_NAME}
  second-agent:
    host: azure.ai.agent
    uses: [ai-project, second-tools]
    environmentVariables:
      - name: TOOLBOX_NAME
        value: second-tools
YAML
"$prepare" "$work/per-agent.yaml" "$work/per-agent-state.json" 12345 1 per-agent >/dev/null
first_name=$(jq -r '.toolboxes[] | select(.original_name == "first-tools") | .name' "$work/per-agent-state.json")
second_name=$(jq -r '.toolboxes[] | select(.original_name == "second-tools") | .name' "$work/per-agent-state.json")
assert_eq "$first_name" "$(yq -r '.services.first-agent.environmentVariables[] | select(.name == "TOOLBOX_NAME") | .value' "$work/per-agent.yaml")" "placeholder resolved to the wrong toolbox"
assert_eq "$second_name" "$(yq -r '.services.second-agent.environmentVariables[] | select(.name == "TOOLBOX_NAME") | .value' "$work/per-agent.yaml")" "literal TOOLBOX_NAME resolved to the wrong toolbox"

# The service-level `env:` map is the shape azd now prefers; a declared map must
# be rewritten in place without disturbing unrelated keys.
cat > "$work/env-map.yaml" <<'YAML'
name: env-map-toolbox
services:
  ai-project:
    host: azure.ai.project
  agent-tools:
    host: azure.ai.toolbox
    uses: [ai-project]
  test-agent:
    host: azure.ai.agent
    uses: [ai-project, agent-tools]
    env:
      TOOLBOX_NAME: agent-tools
      UNRELATED: keep-me
YAML
"$prepare" "$work/env-map.yaml" "$work/env-map-state.json" 12345 1 env-map >/dev/null
env_map_name=$(jq -r '.toolboxes[0].name' "$work/env-map-state.json")
assert_eq "$env_map_name" "$(yq -r '.services.test-agent.env.TOOLBOX_NAME' "$work/env-map.yaml")" "env map TOOLBOX_NAME was not rewritten"
assert_eq keep-me "$(yq -r '.services.test-agent.env.UNRELATED' "$work/env-map.yaml")" "unrelated env keys must be preserved"

# A blank env value silently overrides the deployed agent configuration, so the
# manifest must be rejected instead of shipped.
cat > "$work/blank-env.yaml" <<'YAML'
name: blank-env
services:
  ai-project:
    host: azure.ai.project
  agent-tools:
    host: azure.ai.toolbox
    uses: [ai-project]
  test-agent:
    host: azure.ai.agent
    uses: [ai-project, agent-tools]
    env:
      TOOLBOX_NAME:
    environmentVariables:
      - name: TOOLBOX_NAME
        value: agent-tools
YAML
set +e
"$prepare" "$work/blank-env.yaml" "$work/blank-env-state.json" 12345 1 blank-env >"$work/blank-env.log" 2>&1
blank_exit=$?
set -e
assert_eq 1 "$blank_exit" "a blank env value must fail the run"
grep -q "Blank environment values" "$work/blank-env.log" || fail "blank env failure must name the problem"

# A TOOLBOX_NAME declared in a shape the rewrite does not handle must fail loudly
# rather than deploy against the shared, pre-rename toolbox.
cat > "$work/stale-name.yaml" <<'YAML'
name: stale-name
services:
  ai-project:
    host: azure.ai.project
  agent-tools:
    host: azure.ai.toolbox
    uses: [ai-project]
  test-agent:
    host: azure.ai.agent
    uses: [ai-project, agent-tools]
    config:
      env:
        TOOLBOX_NAME: agent-tools
YAML
set +e
"$prepare" "$work/stale-name.yaml" "$work/stale-name-state.json" 12345 1 stale-name >"$work/stale-name.log" 2>&1
stale_exit=$?
set -e
assert_eq 1 "$stale_exit" "an unrewritten TOOLBOX_NAME must fail the run"
grep -q "still references a pre-rename toolbox" "$work/stale-name.log" || fail "stale TOOLBOX_NAME failure must name the problem"

# Mock the azd toolbox CRUD surface so cleanup behavior is deterministic and
# does not require Azure credentials.
mkdir -p "$work/bin" "$work/times"
cat > "$work/bin/azd" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
[ "$1" = ai ] && [ "$2" = toolbox ] || exit 2
shift 2
case "$1" in
  list)
    # A concurrent run can delete a toolbox between the janitor listing it and
    # acting on it. Drop the named toolbox from every list after the first.
    if [ -n "${MOCK_AZD_VANISH_NAME:-}" ]; then
      calls=$(cat "$MOCK_AZD_LIST_CALLS" 2>/dev/null || echo 0)
      echo $((calls + 1)) > "$MOCK_AZD_LIST_CALLS"
      if [ "$calls" -ge 1 ]; then
        jq --arg name "$MOCK_AZD_VANISH_NAME" '.toolboxes |= map(select(.name != $name))' "$MOCK_AZD_STORE"
        exit 0
      fi
    fi
    cat "$MOCK_AZD_STORE"
    ;;
  delete)
    name=$2
    if [ "$name" != "${MOCK_AZD_DELETE_NOOP_NAME:-}" ]; then
      jq --arg name "$name" '.toolboxes |= map(select(.name != $name))' "$MOCK_AZD_STORE" > "$MOCK_AZD_STORE.tmp"
      mv "$MOCK_AZD_STORE.tmp" "$MOCK_AZD_STORE"
    fi
    jq -n --arg name "$name" '{name:$name,outcome:"deleted"}'
    ;;
  versions)
    [ "$2" = list ] || exit 2
    name=$3
    created=$(cat "$MOCK_AZD_TIMES/$name" 2>/dev/null)
    field=${MOCK_AZD_CREATED_FIELD:-created_at}
    jq -n --arg name "$name" --arg field "$field" --arg created "$created" '
      {toolbox:$name,default_version:"1",versions:[{version:"1"}]} |
      .versions[0][$field] = (if ($created | test("^[0-9]+$")) then ($created | tonumber) else $created end)
    '
    ;;
  *) exit 2 ;;
esac
MOCK
chmod +x "$work/bin/azd"
export PATH="$work/bin:$PATH"
export MOCK_AZD_STORE="$work/live.json"
export MOCK_AZD_TIMES="$work/times"
export MOCK_AZD_LIST_CALLS="$work/list-calls"

jq -n --arg generated "$name_a" '{toolboxes:[{name:$generated},{name:"external-shared-toolbox"}]}' > "$MOCK_AZD_STORE"
"$cleanup" cell "$work/a-state.json" https://example.test/project "$work/cell-cleanup.json" >/dev/null
assert_eq 0 "$(jq --arg name "$name_a" '[.toolboxes[] | select(.name == $name)] | length' "$MOCK_AZD_STORE")" "cell-owned toolbox was not deleted"
assert_eq 1 "$(jq '[.toolboxes[] | select(.name == "external-shared-toolbox")] | length' "$MOCK_AZD_STORE")" "external toolbox must not be deleted"
assert_eq deleted "$(jq -r '.results[0].outcome' "$work/cell-cleanup.json")" "cleanup result must report deletion"

# Cleanup is idempotent when deploy failed before creating the toolbox.
"$cleanup" cell "$work/a-state.json" https://example.test/project "$work/cell-cleanup-again.json" >/dev/null
assert_eq not_found "$(jq -r '.results[0].outcome' "$work/cell-cleanup-again.json")" "missing toolbox must be a successful no-op"

# A delete that reports success but leaves the resource behind must fail with
# one unambiguous still_present result.
jq -n --arg generated "$name_a" '{toolboxes:[{name:$generated}]}' > "$MOCK_AZD_STORE"
export MOCK_AZD_DELETE_NOOP_NAME="$name_a"
set +e
"$cleanup" cell "$work/a-state.json" https://example.test/project "$work/cell-still-present.json" >/dev/null
cleanup_exit=$?
set -e
unset MOCK_AZD_DELETE_NOOP_NAME
assert_eq 1 "$cleanup_exit" "cleanup must fail when deletion cannot be verified"
assert_eq 1 "$(jq '.results | length' "$work/cell-still-present.json")" "cleanup result must not contain contradictory duplicates"
assert_eq still_present "$(jq -r '.results[0].outcome' "$work/cell-still-present.json")" "cleanup must report the verified final state"

now=$(date +%s)
old_name=ci-e2e-tb-old-000000000001
recent_name=ci-e2e-tb-recent-000000000002
unknown_name=ci-e2e-tb-unknown-000000000003
jq -n --arg old "$old_name" --arg recent "$recent_name" --arg unknown "$unknown_name" \
  '{toolboxes:[{name:$old},{name:$recent},{name:$unknown},{name:"external-shared-toolbox"}]}' > "$MOCK_AZD_STORE"
# Exercise epoch-milliseconds and alternate createdAt casing.
echo $(((now - 90000) * 1000)) > "$MOCK_AZD_TIMES/$old_name"
date -u -d "@$now" +%Y-%m-%dT%H:%M:%SZ > "$MOCK_AZD_TIMES/$recent_name"
echo not-a-timestamp > "$MOCK_AZD_TIMES/$unknown_name"
export MOCK_AZD_CREATED_FIELD=createdAt
"$cleanup" orphans https://example.test/project 86400 "$work/orphan-cleanup.json" >/dev/null
unset MOCK_AZD_CREATED_FIELD
assert_eq 0 "$(jq --arg name "$old_name" '[.toolboxes[] | select(.name == $name)] | length' "$MOCK_AZD_STORE")" "stale CI toolbox was not deleted"
assert_eq 1 "$(jq --arg name "$recent_name" '[.toolboxes[] | select(.name == $name)] | length' "$MOCK_AZD_STORE")" "recent CI toolbox must be retained"
assert_eq 1 "$(jq --arg name "$unknown_name" '[.toolboxes[] | select(.name == $name)] | length' "$MOCK_AZD_STORE")" "unknown-age toolbox must be retained"
assert_eq retained_unknown_age "$(jq -r --arg name "$unknown_name" '.results[] | select(.name == $name) | .outcome' "$work/orphan-cleanup.json")" "unknown timestamp must fail closed"
assert_eq 1 "$(jq '[.toolboxes[] | select(.name == "external-shared-toolbox")] | length' "$MOCK_AZD_STORE")" "orphan cleanup must not touch external toolbox"

# A toolbox deleted by a concurrent run between the janitor's list and its
# version lookup is the outcome the janitor wanted, not a failure. The same
# lookup failing while the toolbox is still live must stay fatal.
vanish_name=ci-e2e-tb-vanish-000000000004
jq -n --arg name "$vanish_name" '{toolboxes:[{name:$name}]}' > "$MOCK_AZD_STORE"
echo 0 > "$MOCK_AZD_LIST_CALLS"
export MOCK_AZD_VANISH_NAME="$vanish_name"
set +e
"$cleanup" orphans https://example.test/project 86400 "$work/orphan-vanished.json" >/dev/null
vanish_exit=$?
set -e
unset MOCK_AZD_VANISH_NAME
assert_eq 0 "$vanish_exit" "a toolbox deleted by a concurrent run must not fail the janitor"
assert_eq vanished "$(jq -r --arg name "$vanish_name" '.results[] | select(.name == $name) | .outcome' "$work/orphan-vanished.json")" "concurrent deletion must be reported as vanished"

broken_name=ci-e2e-tb-broken-000000000005
jq -n --arg name "$broken_name" '{toolboxes:[{name:$name}]}' > "$MOCK_AZD_STORE"
set +e
"$cleanup" orphans https://example.test/project 86400 "$work/orphan-broken.json" >/dev/null
broken_exit=$?
set -e
assert_eq 1 "$broken_exit" "a version lookup failing on a live toolbox must fail the janitor"
assert_eq version_list_failed "$(jq -r --arg name "$broken_name" '.results[] | select(.name == $name) | .outcome' "$work/orphan-broken.json")" "a real version-list failure must not be masked as vanished"

echo "PASS: hosted-agent CI toolbox lifecycle"
