#!/usr/bin/env bash

set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
# shellcheck source=../scripts/hosted-agent-retry.sh
source "$repo_root/.azure-pipelines/scripts/hosted-agents/scripts/hosted-agent-retry.sh"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_quota_error() {
  hosted_agent_is_session_quota_error "$1" || fail "expected quota error in $1"
}

assert_not_quota_error() {
  if hosted_agent_is_session_quota_error "$1"; then
    fail "unexpected quota error in $1"
  fi
}

printf 'x-ms-error-code: SessionQuotaExceeded\n' > "$work/subscription-header"
printf '{"error":{"code":"session_quota_exceeded"}}\n' > "$work/subscription-body"
printf 'x-ms-error-code: RegionalSessionQuotaExceeded\n' > "$work/regional-header"
printf '{"error":{"code":"regional_session_quota_exceeded"}}\n' > "$work/regional-body"
printf 'HTTP 429\n{"error":{"code":"TooManyRequests"}}\n' > "$work/throttling"
printf 'HTTP 500\n{"error":{"code":"server_error"}}\n' > "$work/server-error"

assert_quota_error "$work/subscription-header"
assert_quota_error "$work/subscription-body"
assert_quota_error "$work/regional-header"
assert_quota_error "$work/regional-body"
assert_not_quota_error "$work/throttling"
assert_not_quota_error "$work/server-error"

assert_throttle_error() {
  hosted_agent_is_model_throttle_error "$1" || fail "expected model throttle error in $1"
}

assert_not_throttle_error() {
  if hosted_agent_is_model_throttle_error "$1"; then
    fail "unexpected model throttle error in $1"
  fi
}

# The Responses API reports deployment throttling as HTTP 200 + status "failed"
# + code "server_error", with the real reason only in the JSON message. Without
# this shape the throttle backoff never engages and the shorter generic
# transient retry gives up while the deployment is still rate limited.
printf '%s\n' '{"status":"failed","error":{"code":"server_error","message":"Model deployment rate limit exceeded. Your requests to gpt-4.1 for gpt-4.1 in northcentralus have exceeded rate limit.."}}' \
  > "$work/responses-deployment-throttle"
printf '%s\n' '{"output":[{"content":[{"text":"A model deployment rate limit exceeded error means you sent too many requests."}]}]}' \
  > "$work/assistant-prose-about-throttling"

assert_throttle_error "$work/throttling"
assert_throttle_error "$work/responses-deployment-throttle"
assert_not_throttle_error "$work/server-error"
assert_not_throttle_error "$work/assistant-prose-about-throttling"

delays=()
for _ in $(seq 1 100); do
  delay=$(hosted_agent_quota_retry_delay)
  [ "$delay" -ge 50 ] && [ "$delay" -le 70 ] || fail "jitter outside 50-70 seconds: $delay"
  delays+=("$delay")
done
[ "$(printf '%s\n' "${delays[@]}" | sort -u | wc -l)" -gt 1 ] || fail "quota delay is not jittered"

HOSTED_AGENT_QUOTA_RETRY_DELAY_SECONDS=0
[ "$(hosted_agent_quota_retry_delay)" = "0" ] || fail "delay override was not honored"

for retry_number in 1 2 3; do
  delay=$(hosted_agent_tool_retry_delay "$retry_number")
  minimum=$((10 * (1 << (retry_number - 1))))
  maximum=$((minimum + 5))
  [ "$delay" -ge "$minimum" ] && [ "$delay" -le "$maximum" ] \
    || fail "tool retry delay $delay outside $minimum-$maximum seconds"
done

tool_attempts=0
flaky_tool() {
  tool_attempts=$((tool_attempts + 1))
  [ "$tool_attempts" -ge 3 ]
}
HOSTED_AGENT_TOOL_MAX_ATTEMPTS=4
HOSTED_AGENT_TOOL_RETRY_DELAY_SECONDS=0
hosted_agent_retry_command "Test transient tool" flaky_tool >"$work/transient-tool.log" 2>&1
[ "$tool_attempts" -eq 3 ] || fail "tool retry did not stop after recovery"

failed_tool_attempts=0
failed_tool() {
  failed_tool_attempts=$((failed_tool_attempts + 1))
  return 7
}
HOSTED_AGENT_TOOL_MAX_ATTEMPTS=2
set +e
hosted_agent_retry_command "Test exhausted tool" failed_tool >"$work/exhausted-tool.log" 2>&1
failed_tool_status=$?
set -e
[ "$failed_tool_status" -eq 7 ] || fail "tool retry did not preserve the final status"
[ "$failed_tool_attempts" -eq 2 ] || fail "tool retry exceeded its attempt bound"
unset HOSTED_AGENT_TOOL_MAX_ATTEMPTS HOSTED_AGENT_TOOL_RETRY_DELAY_SECONDS

responses_helper="$repo_root/.azure-pipelines/scripts/hosted-agents/scripts/invoke_hosted_agent_responses.py"
pipeline="$repo_root/.azure-pipelines/hosted-agents-samples-ci.yml"
runner="$repo_root/.azure-pipelines/scripts/hosted-agents/run-hosted-agent.sh"

[ -f "$runner" ] || fail "hosted-agent E2E pipeline is missing: $runner"
[ "$(grep -Fc 'hosted_agent_retry_command "Download yq"' "$pipeline")" -eq 1 ] \
  || fail "discovery yq download is not retried"
[ "$(grep -Fc 'hosted_agent_retry_command "Install microsoft.foundry extension"' "$pipeline")" -eq 1 ] \
  || fail "orphan cleanup extension install is not retried"
[ "$(grep -Fc 'hosted_agent_retry_command "Download yq"' "$runner")" -eq 1 ] \
  || fail "sample yq download is not retried"
[ "$(grep -Fc 'hosted_agent_retry_command "Install microsoft.foundry extension"' "$runner")" -eq 1 ] \
  || fail "sample extension install is not retried"
grep -Fq 'CI_AGENT_SESSION_ID: ado-ci-$(Build.BuildId)-$(System.JobAttempt)-${{ shard }}-$(System.JobPositionInPhase)' "$pipeline" \
  || fail "pipeline does not define one run-specific session per cell"
response_session_uses=$((
  $(grep -Fc 'agent_session_id:$session_id' "$runner") +
  $(grep -Fc '"agent_session_id": env["CI_AGENT_SESSION_ID"]' "$responses_helper")
))
[ "$response_session_uses" -eq 4 ] \
  || fail "Responses invocation, approval continuation, and guardrails must use the cell session"
grep -Fq 'azd ai agent sessions create' "$runner" \
  || fail "pipeline does not explicitly create the cell session"
[ "$(grep -Fc -- '--session-id "$CI_AGENT_SESSION_ID"' "$runner")" -eq 6 ] \
  || fail "session create, invocation, files, traces, and both monitoring calls must use the cell session"
grep -Fq 'azd ai agent sessions delete "$CI_AGENT_SESSION_ID"' "$runner" \
  || fail "cleanup does not delete the cell session"

# Agent names must match the GitHub scheme exactly. Foundry mints one
# AgentIdentity per distinct agent name and grants it a role, and the
# subscription has a hard 5000 role-assignment cap. An ADO-specific prefix
# doubles the identity population, exhausts the cap, and then every deployed
# agent dies at startup with 403 on agents/read.
grep -Fq 'agent_name="ci-toolbox-${TOOLBOX_LABEL}-${SAMPLE_NAME}-${DEPLOY_MODE}"' "$runner" \
  || fail "toolbox agent name must reuse the shared ci-toolbox- namespace"
grep -Fq 'agent_name="ci-${SAMPLE_NAME}-${DEPLOY_MODE}"' "$runner" \
  || fail "agent name must reuse the shared ci- namespace"
grep -q 'agent_name="ado-' "$runner" \
  && fail "agent name must not use an ADO-specific prefix: it creates a parallel AgentIdentity population and exhausts the role-assignment limit"
if grep -Fq 'SID=$(grep' "$runner"; then
  fail "pipeline still scrapes session IDs from invocation output"
fi

echo "Hosted-agent session quota helper tests passed."
