#!/usr/bin/env bash
# Discover hosted-agent cloud-E2E combos and emit Azure Pipelines matrices.
#
# Ported from the `find-samples` step of the retired GitHub Actions workflow
# .github/workflows/hosted-agents-cloud-e2e.yml so the ADO pipeline selects
# exactly the same combos (sample x toolbox x deploy-mode).
#
# Env inputs:
#   DISCOVERY_MODE          all | changed
#   BASE_REF                git ref to diff against when DISCOVERY_MODE=changed
#   SAMPLE_FILTER           optional comma-separated substring filter (OR-matched)
#   TOOLBOX_ENDPOINT_LIST   TOOLBOX_ENDPOINT_NCUS value, one entry per line
#   CODE_DEPLOY_ENABLED     'false' disables the code-deploy arm globally
#
# Emits one JSON document on stdout:
#   {count, count_python, count_csharp, matrix_all, matrix_python, matrix_csharp, entries}
#
# matrix_* use the Azure Pipelines shape {"<leg>": {"comboId": "..."}}. Only
# comboId travels in the matrix: a full 300-combo matrix would be ~200 KB and a
# single ADO variable cannot reliably carry that. Each matrix job hydrates the
# rest of its record from `entries` (published as the HostedAgentSamplesMatrix
# artifact).
#
# The per-language key names are `<kind>_<language>` so the pipeline's
# `${{ each shard in parameters.shards }}` loop can compose them directly.
#
# Diagnostics go to stderr; stdout is the JSON document.
set -euo pipefail

DISCOVERY_MODE="${DISCOVERY_MODE:-all}"
BASE_REF="${BASE_REF:-origin/main}"
SAMPLE_FILTER="${SAMPLE_FILTER:-}"
TOOLBOX_ENDPOINT_LIST="${TOOLBOX_ENDPOINT_LIST:-}"
CODE_DEPLOY_ENABLED="${CODE_DEPLOY_ENABLED:-}"

HOSTED_ROOTS=(samples/python/hosted-agents samples/csharp/hosted-agents)

for tool in jq yq git python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "$tool is required." >&2; exit 1; }
done

# ── Parse TOOLBOX_ENDPOINT_NCUS into a list ────────────────────────────
# Format: one entry per line, "label=https://...|optional query text"
# Used to expand toolbox samples into a cartesian product.
toolboxes=()
tb_index=0
while IFS= read -r raw || [ -n "$raw" ]; do
  line=$(echo "$raw" | sed 's/^\xEF\xBB\xBF//' | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  [ -z "$line" ] && continue
  if echo "$line" | grep -q '|'; then
    urlpart=$(echo "$line" | sed 's/|.*//' | sed 's/[[:space:]]*$//')
    query=$(echo "$line" | sed 's/^[^|]*|//' | sed 's/^[[:space:]]*//')
  else
    urlpart="$line"
    query=""
  fi
  if echo "$urlpart" | grep -q '='; then
    label=$(echo "$urlpart" | cut -d= -f1 | sed 's/[[:space:]]*$//')
    url=$(echo "$urlpart" | cut -d= -f2- | sed 's/^[[:space:]]*//')
  else
    tb_index=$((tb_index + 1))
    if [ $tb_index -eq 1 ] && [ ${#toolboxes[@]} -eq 0 ]; then label="default"; else label="tb$tb_index"; fi
    url="$urlpart"
  fi
  [ -z "$url" ] && continue
  toolboxes+=("$(jq -n --arg l "$label" --arg u "$url" --arg q "$query" '{label:$l, url:$u, query:$q}')")
  echo "Toolbox: $label -> $url${query:+  (query: \"$query\")}" >&2
done <<< "$TOOLBOX_ENDPOINT_LIST"

if [ ${#toolboxes[@]} -eq 0 ]; then
  toolboxes_json='[]'
else
  toolboxes_json=$(printf '%s\n' "${toolboxes[@]}" | jq -s -c '.')
fi

# ── Matrix leg name ────────────────────────────────────────────────────
# ADO only allows [A-Za-z0-9_] in a matrix key. Convert separators to
# underscores (rather than deleting them), drop the constant hosted-agents-
# segment so the sample path stays legible, and suffix a hash of the FULL
# combo id so two long combos cannot collide after truncation.
matrix_key() {
  local combo_id="$1" key hash
  hash="$(printf '%s' "$combo_id" | sha256sum | cut -c1-7)"
  key="$(printf '%s' "$combo_id" \
    | sed 's/hosted-agents-//' \
    | tr -c '[:alnum:]' '_' | tr -s '_' | sed 's/^_//; s/_$//' \
    | cut -c1-72)"
  printf '%s_%s' "$key" "$hash"
}

# ── Emit one or many matrix entries for a given sample ─────────────────
# - hosted-agents samples: one entry per deploy mode (combo_id = id-mode).
# - toolbox samples: cartesian product over $toolboxes (combo_id = id-label-mode).
#
# ── deploy-mode axis ──
# Every sample is emitted twice — once with deployMode='container' (today's
# path) and once with deployMode='code' (azd direct code-deploy via
# `--deploy-mode code`). To disable the code arm (e.g. azd extension outage),
# set CLOUD_E2E_CODE_DEPLOY_ENABLED=false. comboId is suffixed with the mode so
# artifact / env names stay unique.
emit_entries() {
  local sample_dir="$1" agent_name="$2" sample_id="$3" protocol="$4"
  local is_toolbox="false"
  # Voice Live compatibility (from azure.yaml metadata or path) — consumed
  # downstream by the Voice Live smoke-test step. The flag may live at the top
  # level or on the azure.ai.agent service.
  local voice_live="false"
  local yaml_file="$sample_dir/azure.yaml"
  if { [ -f "$yaml_file" ] && [ "$(yq '((.voiceLiveCompatible // false) == true) or ((.services[] | select(.host == "azure.ai.agent") | .voiceLiveCompatible) == true)' "$yaml_file")" = "true" ]; } || echo "$sample_dir" | grep -q '/voicelive/'; then
    voice_live="true"
  fi
  # Toolbox samples live exclusively under hosted-agents — match any
  # hosted-agents sample whose directory name contains "toolbox".
  case "$sample_dir" in
    samples/python/hosted-agents/*toolbox*|samples/csharp/hosted-agents/*toolbox*) is_toolbox="true" ;;
  esac
  # Toolbox samples use the default ncus project, so the matrix is expanded
  # from the TOOLBOX_ENDPOINT_NCUS variable.
  local use_westus2="false"

  # ─── language / runtime / deploy-mode axes ───────────────────────────
  # sampleLanguage / runtime / entryPoint are only meaningful for the code arm
  # but we emit them on every row so the record schema is uniform.
  # runtime and entryPoint prefer each sample's codeConfiguration; legacy
  # manifests without those fields fall back to the language defaults.
  #
  # Per-language classification (explicit allow-list — fails loudly if a new
  # language gets a hosted-agents/ subdir without us noticing).
  local language runtime entry_point deploy_modes
  case "$sample_dir" in
    samples/python/hosted-agents/*)
      language="python"
      # Resolved with yq, the same way the csharp arm below reads its entry
      # point, so this pipeline shares no scripts with the GitHub workflow.
      # A manifest-defined module/argument entry point must stay a single
      # matrix value so azd can build the complete launch command.
      runtime=$(yq -r '.services[] | select(.host == "azure.ai.agent") | .codeConfiguration.runtime // ""' "$yaml_file" | head -1)
      [ -n "$runtime" ] || runtime="python_3_13"
      entry_point=$(yq -r '.services[] | select(.host == "azure.ai.agent") | .codeConfiguration.entryPoint // ""' "$yaml_file" | head -1)
      [ -n "$entry_point" ] || entry_point="main.py"
      deploy_modes='["container","code"]'
      ;;
    samples/csharp/hosted-agents/*)
      language="csharp"
      runtime="dotnet_10"
      # Prefer the manifest's authoritative code entry point. Fall back to the
      # project assembly only for older manifests.
      entry_point=$(yq -r '.services[] | select(.host == "azure.ai.agent") | .codeConfiguration.entryPoint // ""' "$yaml_file" | head -1)
      if [ -z "$entry_point" ]; then
        local csproj asm
        csproj=$(find "$sample_dir" -name "*.csproj" | head -1)
        if [ -n "$csproj" ]; then
          asm=$(grep -oE '<AssemblyName>[^<]+</AssemblyName>' "$csproj" | head -1 | sed -E 's|</?AssemblyName>||g')
          [ -z "$asm" ] && asm=$(basename "$csproj" .csproj)
        else
          asm=$(basename "$sample_dir")
        fi
        entry_point="${asm}.dll"
      fi
      # All hosted-agents csharp samples target net10.0 and ship a Dockerfile
      # based on mcr.microsoft.com/dotnet/{sdk,aspnet}:10.0, which the Foundry
      # container deploy path supports.
      deploy_modes='["container","code"]'
      ;;
    *)
      echo "##vso[task.logissue type=error]emit_entries: unsupported language path '$sample_dir' — only samples/python/hosted-agents/* and samples/csharp/hosted-agents/* are wired into the code-deploy matrix." >&2
      return 1
      ;;
  esac

  # Per-sample code-deploy opt-out: drop a `.code-ci-skip` file in the sample
  # directory to skip just the code deploy arm while keeping the container arm
  # (cf. `.ci-skip`, which excludes the sample entirely).
  local code_compatible="true"
  if [ -f "$sample_dir/.code-ci-skip" ]; then
    echo "  - $sample_dir (code deploy skipped via .code-ci-skip — container-only)" >&2
    code_compatible="false"
  fi

  # Opt-out kill-switch: set CLOUD_E2E_CODE_DEPLOY_ENABLED=false to skip the
  # code arm globally (e.g. during an azd extension outage).
  if [ "$CODE_DEPLOY_ENABLED" = "false" ] || [ "$code_compatible" != "true" ]; then
    deploy_modes='["container"]'
  fi

  # Dependency resolution mode for the code arm. Only meaningful when
  # deployMode='code'; empty for the container arm.
  local dep_resolution="remote_build"

  # Extract protocol version from azure.yaml (defaults to 1.0.0).
  local protocol_version
  protocol_version=$(protocol="$protocol" yq '[.services[] | select(.host == "azure.ai.agent") | .protocols[] | select(.protocol == strenv(protocol)) | .version] | .[0] // "1.0.0"' "$yaml_file")
  [ -z "$protocol_version" ] && protocol_version="1.0.0"

  if [ "$is_toolbox" = "true" ]; then
    if [ "$toolboxes_json" = "[]" ]; then
      echo "##vso[task.logissue type=warning]Skipping toolbox sample $sample_dir — TOOLBOX_ENDPOINT_NCUS is empty" >&2
      return 0
    fi
    # Per-sample toolbox exclusions for known-broken combos.
    local filtered_toolboxes_json="$toolboxes_json"
    case "$sample_dir" in
      samples/csharp/hosted-agents/agent-framework/foundry-toolbox-server-side|samples/csharp/hosted-agents/agent-framework/toolbox-auth-paths)
        # The csharp foundry-toolbox-server-side and toolbox-auth-paths samples
        # trigger an 'invalid_payload' on /tools/0/container when they hand a
        # code_interpreter tool to the Responses API — a serialization bug in
        # the .NET Agent Framework SDK (Microsoft.Agents.AI.Foundry.Hosting)
        # that cannot be fixed from this repo.
        # TODO(hosted-agents): drop this exclusion once the SDK fix ships.
        echo "##vso[task.logissue type=warning]Excluding csharp $sample_dir x code-interpreter combo: known .NET Agent Framework SDK bug serializes tools[].container as null where the Responses API requires a string." >&2
        filtered_toolboxes_json=$(echo "$toolboxes_json" | jq -c 'map(select(.label != "code-interpreter" and .label != "foundry-iq-kb"))')
        ;;
      samples/python/hosted-agents/agent-framework/responses/17-foundry-iq-toolbox)
        # Unlike the generic toolbox relays, this sample is grounded on a
        # specific Foundry IQ knowledge base: main.py instructs the agent to
        # answer only from the knowledge base and otherwise say it doesn't
        # know. Fanning it across the generic shared toolboxes makes it
        # correctly answer "I don't know". Pin it to the dedicated
        # knowledge-base toolbox whose paired query matches the KB content.
        echo "##vso[task.logissue type=warning]Pinning $sample_dir to the foundry-iq-kb knowledge toolbox only (skipping generic toolbox combos)." >&2
        filtered_toolboxes_json=$(echo "$toolboxes_json" | jq -c 'map(select(.label == "foundry-iq-kb"))')
        if [ "$filtered_toolboxes_json" = "[]" ]; then
          echo "##vso[task.logissue type=warning]Skipping $sample_dir — no 'foundry-iq-kb' entry found in TOOLBOX_ENDPOINT_NCUS. Add 'foundry-iq-kb=<kb-mcp-endpoint>|<query>' to enable this sample's cloud e2e." >&2
          return 0
        fi
        ;;
      *)
        # The `foundry-iq-kb` toolbox is dedicated to 17-foundry-iq-toolbox
        # above (its paired query only matches that knowledge base's content).
        filtered_toolboxes_json=$(echo "$toolboxes_json" | jq -c 'map(select(.label != "foundry-iq-kb"))')
        ;;
    esac
    echo "$filtered_toolboxes_json" | jq -c \
      --arg id "$sample_id" --arg path "$sample_dir" --arg name "$agent_name" \
      --arg protocol "$protocol" --arg protocol_version "$protocol_version" \
      --arg use_westus2 "$use_westus2" \
      --arg language "$language" --arg runtime "$runtime" --arg entry_point "$entry_point" \
      --arg dep_resolution "$dep_resolution" \
      --arg voiceLive "$voice_live" \
      --argjson deploy_modes "$deploy_modes" '
      .[] as $tb | $deploy_modes[] as $mode | {
        sampleId: $id, samplePath: $path, sampleName: $name, protocol: $protocol,
        protocolVersion: $protocol_version,
        isToolbox: "true",
        toolboxLabel: $tb.label, toolboxUrl: $tb.url, toolboxQuery: $tb.query,
        useWestus2: $use_westus2,
        voiceLive: $voiceLive,
        deployMode: $mode,
        sampleLanguage: $language, runtime: $runtime, entryPoint: $entry_point,
        depResolution: (if $mode == "code" then $dep_resolution else "" end),
        comboId: (
          $id + "-" + $tb.label + "-" +
          (if $mode == "code" then "code-" + $dep_resolution else "container" end)
        )
      }'
  else
    echo "$deploy_modes" | jq -c \
      --arg id "$sample_id" --arg path "$sample_dir" --arg name "$agent_name" \
      --arg protocol "$protocol" --arg protocol_version "$protocol_version" \
      --arg use_westus2 "$use_westus2" \
      --arg language "$language" --arg runtime "$runtime" --arg entry_point "$entry_point" \
      --arg dep_resolution "$dep_resolution" \
      --arg voiceLive "$voice_live" '
      .[] | {
        sampleId: $id, samplePath: $path, sampleName: $name, protocol: $protocol,
        protocolVersion: $protocol_version,
        isToolbox: "false",
        toolboxLabel: "", toolboxUrl: "", toolboxQuery: "",
        useWestus2: $use_westus2,
        voiceLive: $voiceLive,
        deployMode: .,
        sampleLanguage: $language, runtime: $runtime, entryPoint: $entry_point,
        depResolution: (if . == "code" then $dep_resolution else "" end),
        comboId: ($id + "-" + (if . == "code" then "code-" + $dep_resolution else "container" end))
      }'
  fi
}

# ── Find candidate samples ─────────────────────────────────────────────
entries=()

if [ "$DISCOVERY_MODE" = "changed" ]; then
  echo "Changed-sample discovery against $BASE_REF" >&2
  changed_files=$(git diff --name-only "$BASE_REF...HEAD")
  echo "Changed files:" >&2
  echo "$changed_files" >&2

  # Pipeline and lifecycle-helper changes must exercise the real matrix.
  # Without this, a runner change triggers the pipeline but the changed-sample
  # filter emits an empty matrix, so the change is never validated before merge.
  test_all="false"
  if echo "$changed_files" | grep -qE '^(\.azure-pipelines/hosted-agents-samples-ci\.yml|internal/tools/samples-hosted-agents-ci/(discover-samples\.sh|scripts/((prepare|cleanup)-hosted-agent-ci-toolboxes|hosted-agent-retry)\.sh|scripts/(hosted_agent_fixture|hosted_agent_test_spec|invoke_hosted_agent_responses|collect-hosted-agent-traces)\.py|tests/test-hosted-agent-(ci-toolboxes|session-quota)\.sh|tests/test_hosted_agent_(fixture|test_spec)\.py))$'; then
    test_all="true"
    echo "Hosted-agent E2E infrastructure changed — testing the full matrix" >&2
  fi

  while IFS= read -r yaml_file; do
    sample_dir=$(dirname "$yaml_file")
    if [ -f "$sample_dir/.ci-skip" ]; then
      echo "  - $sample_dir (skipped - requires external credentials)" >&2
      continue
    fi
    if [ "$(yq '[.services[] | select(.host == "azure.ai.agent") | .protocols[]?.protocol] | any_c(. == "invocations")' "$yaml_file")" = "true" ]; then
      protocol="invocations"
    else
      protocol="responses"
    fi
    fixture_dir=$(python3 internal/tools/samples-hosted-agents-ci/scripts/hosted_agent_fixture.py fixture-dir --sample-dir "$sample_dir")
    if [ "$test_all" = "true" ] || echo "$changed_files" | grep -qE "^(${sample_dir}|${fixture_dir})/"; then
      agent_name=$(yq '.name // ""' "$yaml_file")
      sample_id=$(echo "$sample_dir" | sed 's|samples/||' | tr '/' '-')
      while IFS= read -r entry; do
        [ -n "$entry" ] && entries+=("$entry")
      done < <(emit_entries "$sample_dir" "$agent_name" "$sample_id" "$protocol")
      echo "  - $sample_dir (changed, protocol=$protocol)" >&2
    fi
  done < <(find "${HOSTED_ROOTS[@]}" -name "azure.yaml" -type f 2>/dev/null | sort)
else
  echo "Full discovery - testing all samples" >&2
  while IFS= read -r yaml_file; do
    sample_dir=$(dirname "$yaml_file")
    if [ -f "$sample_dir/.ci-skip" ]; then
      echo "  - $sample_dir (skipped - requires external credentials)" >&2
      continue
    fi
    agent_name=$(yq '.name // ""' "$yaml_file")
    sample_id=$(echo "$sample_dir" | sed 's|samples/||' | tr '/' '-')
    if [ "$(yq '[.services[] | select(.host == "azure.ai.agent") | .protocols[]?.protocol] | any_c(. == "invocations")' "$yaml_file")" = "true" ]; then
      protocol="invocations"
    else
      protocol="responses"
    fi
    while IFS= read -r entry; do
      [ -n "$entry" ] && entries+=("$entry")
    done < <(emit_entries "$sample_dir" "$agent_name" "$sample_id" "$protocol")
  done < <(find "${HOSTED_ROOTS[@]}" -name "azure.yaml" -type f 2>/dev/null | sort)
fi

# ── Optional single-case filter (manual runs) ──────────────────────────
# When SAMPLE_FILTER is set, keep only entries whose comboId, samplePath, or
# sampleName contains any of the comma-separated tokens (case-insensitive,
# OR-matched). A filter with no comma is a single token.
if [ -n "$SAMPLE_FILTER" ] && [ ${#entries[@]} -gt 0 ]; then
  echo "Applying sampleFilter: '$SAMPLE_FILTER'" >&2
  filtered=()
  while IFS= read -r entry; do
    [ -n "$entry" ] && filtered+=("$entry")
  done < <(printf '%s\n' "${entries[@]}" | jq -c --arg f "$SAMPLE_FILTER" '
    ($f | ascii_downcase | split(",")
       | map(gsub("^\\s+|\\s+$"; "")) | map(select(length > 0))) as $tokens
    | ((.comboId + " " + .samplePath + " " + .sampleName) | ascii_downcase) as $hay
    | select(any($tokens[]; . as $t | $hay | contains($t)))')
  entries=("${filtered[@]}")
  if [ ${#entries[@]} -eq 0 ]; then
    echo "##vso[task.logissue type=warning]sampleFilter '$SAMPLE_FILTER' matched no samples — emitting empty matrix" >&2
  else
    echo "sampleFilter matched ${#entries[@]} matrix entr(y/ies)" >&2
  fi
fi

if [ ${#entries[@]} -eq 0 ]; then
  jq -n '{count:0, count_python:0, count_csharp:0, matrix_all:{}, matrix_python:{}, matrix_csharp:{}, entries:[]}'
  exit 0
fi

# Attach the ADO matrix leg name to every entry.
keyed=()
while IFS= read -r entry; do
  [ -n "$entry" ] || continue
  combo_id=$(jq -r '.comboId' <<< "$entry")
  keyed+=("$(jq -c --arg key "$(matrix_key "$combo_id")" '. + {matrixKey:$key}' <<< "$entry")")
done < <(printf '%s\n' "${entries[@]}")

printf '%s\n' "${keyed[@]}" | jq -s '
  def matrix: map({(.matrixKey): {comboId: .comboId}}) | add // {};
  . as $all
  | ($all | map(select(.sampleLanguage == "python"))) as $py
  | ($all | map(select(.sampleLanguage == "csharp"))) as $cs
  | {
      count: ($all | length),
      count_python: ($py | length),
      count_csharp: ($cs | length),
      matrix_all: ($all | matrix),
      matrix_python: ($py | matrix),
      matrix_csharp: ($cs | matrix),
      entries: $all
    }'
