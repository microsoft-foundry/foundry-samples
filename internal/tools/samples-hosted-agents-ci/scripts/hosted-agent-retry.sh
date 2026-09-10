#!/usr/bin/env bash

# Shared helpers for hosted-agent quota and model-throttle retries.

hosted_agent_is_session_quota_error() {
  [ "$#" -gt 0 ] || return 1
  grep -qihE \
    'SessionQuotaExceeded|RegionalSessionQuotaExceeded|session_quota_exceeded|regional_session_quota_exceeded' \
    "$@" 2>/dev/null
}

hosted_agent_quota_retry_delay() {
  if [ -n "${HOSTED_AGENT_QUOTA_RETRY_DELAY_SECONDS:-}" ]; then
    printf '%s\n' "$HOSTED_AGENT_QUOTA_RETRY_DELAY_SECONDS"
    return
  fi

  # Jitter around one minute so blocked cells do not retry simultaneously.
  printf '%s\n' "$((50 + RANDOM % 21))"
}

hosted_agent_is_model_throttle_error() {
  [ "$#" -gt 0 ] || return 1

  # Match explicit transport/model error shapes, not assistant prose that may
  # legitimately discuss rate limiting.
  #
  # The Responses API reports deployment throttling as HTTP 200 with
  # status="failed" and code="server_error", putting the real reason only in
  # the JSON message — no 429, no rate_limit_exceeded code, no "Error calling
  # model:" prefix. Keying on the `message` field keeps assistant output (which
  # lands under output[].content[].text) from matching.
  if grep -qihE \
      "^HTTP[/0-9.]*[[:space:]]+429([[:space:]]|$)|Error calling model:.*(Error code:[[:space:]]*429|rate_limit_exceeded|TooManyRequests|Model deployment rate limit exceeded)|['\"]message['\"][[:space:]]*:[[:space:]]*['\"][^'\"]*Model deployment rate limit exceeded|['\"]code['\"][[:space:]]*:[[:space:]]*['\"](rate_limit_exceeded|TooManyRequests)['\"]|['\"]status_code['\"][[:space:]]*:[[:space:]]*429" \
      "$@" 2>/dev/null; then
    return 0
  fi

  local file
  for file in "$@"; do
    if grep -qiE 'currently experiencing high demand.*exceeds the maximum usage size allowed during peak load' "$file" 2>/dev/null && \
        grep -qiE "\"status\"[[:space:]]*:[[:space:]]*\"failed\"|['\"]error['\"][[:space:]]*:|Error calling model:" "$file" 2>/dev/null; then
      return 0
    fi
  done
  return 1
}

hosted_agent_model_retry_delay() {
  local scheduled_delay="$1"
  shift

  # Add jitter so parallel cells do not resume together. If the service gives
  # an integer Retry-After value, never retry sooner than that value.
  scheduled_delay=$((scheduled_delay + RANDOM % 31))
  local retry_after
  retry_after=$(grep -ihE '^Retry-After:[[:space:]]*[0-9]+' "$@" 2>/dev/null \
    | awk -F: '{gsub(/[^0-9]/, "", $2); print $2}' \
    | sort -nr | head -1)
  if [ -n "$retry_after" ] && [ "$retry_after" -gt "$scheduled_delay" ]; then
    scheduled_delay="$retry_after"
  fi

  printf '%s\n' "$scheduled_delay"
}
