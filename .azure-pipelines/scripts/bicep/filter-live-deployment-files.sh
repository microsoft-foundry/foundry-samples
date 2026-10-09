#!/usr/bin/env bash
set -euo pipefail

if (($# != 2)); then
  printf 'Usage: %s <skiplist> <bicep-root>\n' "$0" >&2
  exit 2
fi

skiplist="$1"
bicep_root="${2%/}"

[[ -f "$skiplist" ]] || {
  printf 'Bicep live-deployment skip list not found: %s\n' "$skiplist" >&2
  exit 1
}

skipped_directories_file="$(mktemp "${TMPDIR:-/tmp}/bicep-live-skip.XXXXXX")"
trap 'rm -f "$skipped_directories_file"' EXIT
while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
  line="$(printf '%s' "$raw_line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [[ -n "$line" && "$line" != \#* ]] || continue
  [[ "$line" == "$bicep_root/"* && "$line" != */ ]] || {
    printf 'Invalid Bicep live-deployment skip-list entry: %s\n' "$line" >&2
    exit 1
  }
  [[ -d "$line" ]] || {
    printf 'Bicep live-deployment skip-list directory does not exist: %s\n' "$line" >&2
    exit 1
  }
  ! grep -Fxq "$line" "$skipped_directories_file" || {
    printf 'Duplicate Bicep live-deployment skip-list entry: %s\n' "$line" >&2
    exit 1
  }
  printf '%s\n' "$line" >>"$skipped_directories_file"
done <"$skiplist"

while IFS= read -r deployment_file || [[ -n "$deployment_file" ]]; do
  [[ -n "$deployment_file" ]] || continue
  deployment_directory="$(dirname "$deployment_file")"
  if grep -Fxq "$deployment_directory" "$skipped_directories_file"; then
    printf '##vso[task.logissue type=warning]Skipping ephemeral live deployment for %s; static Bicep compilation remains required. See %s.\n' \
      "$deployment_directory" "$skiplist" >&2
    continue
  fi
  printf '%s\n' "$deployment_file"
done
