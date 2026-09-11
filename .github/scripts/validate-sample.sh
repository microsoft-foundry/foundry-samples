#!/usr/bin/env bash
# validate-sample.sh — reusable single-sample build-readiness or live-service validator.
#
# Ported from .azure-pipelines/validation.yml Stage 2, which duplicated the same
# per-sample body across five per-language jobs (C#, Python, TypeScript, Java, Go).
# That duplication is collapsed here into ONE function set: the sample.yaml command
# runner lives once, and only the genuinely per-language default differs.
#
# Single responsibility: validate ONE sample directory. The caller owns the
# `while read dir` loop (per-sample granularity for validation/<pipeline>/<sample-path>
# statuses) and the toolchain SETUP (setup-dotnet / setup-python / ... actions).
# This script assumes the required toolchain is already on PATH and reports ERROR if not.
#
# Usage:
#   validate-sample.sh [--mode build-readiness] --language <csharp|python|typescript|java|go> \
#                      --sample-dir <path> [--results-dir <dir>]
#   validate-sample.sh --mode live-service --sample-dir <path> [--results-dir <dir>]
#
# Verdict / exit codes — the classifier. This split is load-bearing: downstream lanes
# and the sync gate trust it, and ERROR must NEVER be treated as a sample failure
# (that is what protects good samples from being quarantined when our infra breaks).
#
#   0  PASS   the requested level passed
#             (build-readiness commands/default pass; or live-service command passes/none is declared)
#   1  FAIL   the SAMPLE is broken
#             (a build-readiness/live-service sample command exits non-zero; or the language default's
#              compile/build/py_compile exits non-zero, without positive infra evidence)
#   2  ERROR  OUR INFRA is sick — page us, do not quarantine
#             PRECONDITION errors (bad/missing args, unknown language, missing sample dir,
#             unreadable or malformed sample.yaml, a required toolchain binary missing from
#             PATH, yq unavailable when a sample.yaml must be read), OR a dedicated `pip install` /
#             `npm install` failure with positive transport evidence, OR a live-service command that
#             explicitly reports caller/cloud infrastructure failure with exit 2.
#
# failure-vs-error at runtime (honest v1): the two DEDICATED install steps (`pip install`,
# `npm install`) are inspected for positive transport evidence. Arbitrary live-service output is NEVER
# inferred: its command owns normalization to 0=PASS, 1=FAIL, or 2=ERROR; every other nonzero
# remains FAIL (bias ambiguous->fail, never fail-open). The merged resolve+compile tools
# (dotnet build, mvn compile, gradle build, go build, npm run build) are NOT inspected in v1.
# Documented limit in CLASSIFICATION.md.
#
# Outputs:
#   - prints `verdict=pass|fail|error` on stdout (also appended to $GITHUB_OUTPUT if set)
#   - in live-service mode, also prints/appends `live_service_validation_declared=true|false`
#   - if --results-dir is given, appends the sample path to
#     passed.txt | failed.txt | errored.txt in that directory.
#
# NOTE: `set -e` is intentionally NOT used. The classifier owns every exit code, so a
# failing external command must be caught (`if ! cmd`) and routed to fail()/error(),
# never allowed to abort the script with its own status.
set -uo pipefail

LANGUAGE=""
SAMPLE_DIR=""
RESULTS_DIR=""
MODE="build-readiness"
LIVE_SERVICE_VALIDATION_DECLARED=""
SAMPLE_YAML_FAIL_STEP=""
PYTHON_VENV_DIR=""

usage() {
    cat <<'EOF'
Usage:
  validate-sample.sh [--mode build-readiness] --language <lang> --sample-dir <path> [--results-dir <dir>]
  validate-sample.sh --mode live-service --sample-dir <path> [--results-dir <dir>]

  --mode         Validation mode: build-readiness (default) or live-service.
  --language     One of: csharp | python | typescript | java | go (frozen set).
                 Required for build readiness; optional for live-service validation.
  --sample-dir   Path to the single sample directory to validate.
  --results-dir  Optional. Directory to append passed.txt/failed.txt/errored.txt.

Exit codes: 0 = pass, 1 = fail (sample broken), 2 = error (infra broken).
EOF
}

# --- Classifier emit helpers -------------------------------------------------
# Each terminates the process with the verdict's exit code so no path can fall
# through without emitting exactly one verdict.

emit_verdict() {
    # $1 = pass|fail|error, $2 = exit code
    local verdict="$1" code="$2"
    if [ "$MODE" = "live-service" ] && [ -n "$LIVE_SERVICE_VALIDATION_DECLARED" ]; then
        echo "live_service_validation_declared=${LIVE_SERVICE_VALIDATION_DECLARED}"
    fi
    echo "verdict=${verdict}"
    if [ -n "${GITHUB_OUTPUT:-}" ]; then
        if [ "$MODE" = "live-service" ] && [ -n "$LIVE_SERVICE_VALIDATION_DECLARED" ]; then
            echo "live_service_validation_declared=${LIVE_SERVICE_VALIDATION_DECLARED}" >> "$GITHUB_OUTPUT"
        fi
        echo "verdict=${verdict}" >> "$GITHUB_OUTPUT"
    fi
    if [ -n "$RESULTS_DIR" ]; then
        mkdir -p "$RESULTS_DIR"
        case "$verdict" in
            pass)  echo "$SAMPLE_DIR" >> "$RESULTS_DIR/passed.txt" ;;
            fail)  echo "$SAMPLE_DIR" >> "$RESULTS_DIR/failed.txt" ;;
            error) echo "$SAMPLE_DIR" >> "$RESULTS_DIR/errored.txt" ;;
        esac
    fi
    exit "$code"
}

pass() {
    echo "PASS: ${SAMPLE_DIR:-<no-dir>}"
    emit_verdict pass 0
}

fail() {
    # $1 = reason (optional)
    echo "FAIL: ${SAMPLE_DIR:-<no-dir>}${1:+ — $1}"
    emit_verdict fail 1
}

error() {
    # $1 = reason (optional). ERROR is infra-sick: page us, never quarantine.
    echo "ERROR: ${1:-infra failure} (sample=${SAMPLE_DIR:-<no-dir>})" >&2
    emit_verdict error 2
}

# require_tool <bin>: a required toolchain binary must be on PATH, else ERROR.
require_tool() {
    command -v "$1" >/dev/null 2>&1 || error "required toolchain binary not found on PATH: $1"
}

# ensure_yq: lazy precondition — only needed to read a sample.yaml. yq setup itself
# belongs to the caller/workflow; the script only asserts its presence.
ensure_yq() {
    command -v yq >/dev/null 2>&1 || error "yq not available on PATH (required to read sample.yaml)"
}

# dep_infra_signature <logfile>: return 0 IFF a captured dedicated dependency-install log shows
# HIGH-CONFIDENCE transport/registry evidence (DNS / connection refused-reset / connect-read
# timeout / registry 5xx). This is a deliberately NARROW pip/npm heuristic:
#   - it matches only tool-specific transport strings, never generic words like "timeout";
#   - a positive match wins even when pip later prints a generic "No matching distribution"
#     line (pip emits that AFTER exhausting retries against an unreachable index);
#   - it is scoped to direct `pip install` and `npm install` logs only;
#   - arbitrary sample/live-service output MUST NOT be passed here;
#   - anything unmatched stays FAIL (bias ambiguous->fail, never fail-open to pass);
#   - EXPECT maintenance as runner pip/npm versions drift their error strings.
# The full captured log is printed by the caller before classifying, so diagnosis is preserved.
dep_infra_signature() {
    local log="${1:-}"
    [ -n "$log" ] && [ -f "$log" ] || return 1
    grep -Eiq \
        -e 'temporary failure in name resolution' \
        -e 'could not resolve host' \
        -e 'name or service not known' \
        -e 'getaddrinfo' \
        -e 'eai_again' \
        -e 'enotfound' \
        -e 'econnrefused' \
        -e 'connection refused' \
        -e 'econnreset' \
        -e 'connection reset' \
        -e 'etimedout' \
        -e 'connection timed out' \
        -e 'read timed out' \
        -e 'readtimeouterror' \
        -e 'connecttimeouterror' \
        -e 'network timeout' \
        -e 'newconnectionerror' \
        -e 'max retries exceeded' \
        -e 'failed to establish a new connection' \
        -e 'proxyerror' \
        -e 'network is unreachable' \
        -e '50[0234] server error' \
        -e 'service unavailable' \
        -e 'bad gateway' \
        -e 'gateway time-?out' \
        -e 'internal server error' \
        "$log"
}

# --- Part 1: the once-only shared sample.yaml runner -------------------------
# Byte-identical across all five ADO jobs today. Reads build -> validate -> test
# and runs them in order; the first non-zero command is a sample FAIL.
#
# Returns: 0 = ran >=1 command and all passed (caller should PASS)
#          1 = a command exited non-zero    (caller should FAIL)
#          3 = no sample.yaml, or it declared no commands (caller runs the default)
# Unreadable/malformed YAML calls error() directly (ERROR 2).
#
# For Python the per-sample venv is already activated in the parent shell before this
# runs, so the `( cd ... && eval )` subshell inherits it — keeping this function
# identical for all five languages (mirrors ADO, which sourced the venv per command).
run_sample_yaml() {
    local yaml="$SAMPLE_DIR/sample.yaml"
    [ -f "$yaml" ] || return 3

    ensure_yq

    if ! yq eval '.' "$yaml" >/dev/null 2>&1; then
        error "sample.yaml is unreadable or malformed: $yaml"
    fi
    if [ "$(yq eval 'has("l4")' "$yaml" 2>/dev/null)" = "true" ]; then
        error "legacy sample.yaml key 'l4' is unsupported; rename it to 'live_service_validation'"
    fi

    local had_cmd=false cmd cmd_type
    for cmd_type in build validate test; do
        cmd="$(yq eval ".${cmd_type} // \"\"" "$yaml" 2>/dev/null)"
        if [ -n "$cmd" ] && [ "$cmd" != "null" ]; then
            had_cmd=true
            echo "Running $cmd_type: $cmd"
            if ! ( cd "$SAMPLE_DIR" && eval "$cmd" ); then
                SAMPLE_YAML_FAIL_STEP="$cmd_type"
                return 1
            fi
        fi
    done

    [ "$had_cmd" = true ] && return 0
    return 3
}

# --- Part 2: per-language defaults (grounded in validation.yml Stage 2) -------
# Each ends by calling pass() or fail(). require_tool guards are placed only where
# the tool is actually invoked, preserving ADO's "no build file present => PASS" edges.

# ADO validation.yml L285-298
default_validate_csharp() {
    if ls "$SAMPLE_DIR"/*.csproj 1>/dev/null 2>&1; then
        require_tool dotnet
        local proj
        for proj in "$SAMPLE_DIR"/*.csproj; do
            echo "Building: $proj"
            if ! dotnet build "$proj" --verbosity minimal; then
                fail "dotnet build failed: $proj"
            fi
        done
        pass
    else
        echo "No .csproj found in $SAMPLE_DIR"
        pass
    fi
}

# ADO validation.yml L368-439. Venv is created + activated by python_setup_venv
# (called before the sample.yaml/default branch, mirroring ADO's up-front venv).
default_validate_python() {
    if [ -f "$SAMPLE_DIR/requirements.txt" ]; then
        echo "Installing requirements..."
        local piplog; piplog="$(mktemp)"
        if ! pip install -r "$SAMPLE_DIR/requirements.txt" -q >"$piplog" 2>&1; then
            cat "$piplog"
            if dep_infra_signature "$piplog"; then
                rm -f "$piplog"
                error "pip install: registry/network unreachable (transport evidence in log)"
            fi
            rm -f "$piplog"
            echo "[classify:fail] pip install dependency-resolution failure (no transport evidence)"
            fail "pip install failed"
        fi
        rm -f "$piplog"
    fi
    local pyfile
    for pyfile in "$SAMPLE_DIR"/*.py; do
        [ -f "$pyfile" ] || continue
        echo "Checking: $pyfile"
        if ! python -m py_compile "$pyfile"; then
            fail "py_compile failed: $pyfile"
        fi
    done
    pass
}

# ADO validation.yml L528-569
default_validate_typescript() {
    if [ -f "$SAMPLE_DIR/package.json" ]; then
        require_tool npm
        echo "Installing dependencies..."
        local npmlog; npmlog="$(mktemp)"
        # NOT --silent: that suppresses error output too, which would blind
        # dep_infra_signature to transport errors. --loglevel=error keeps success
        # quiet while still emitting the network/registry failure text we classify on.
        if ! ( cd "$SAMPLE_DIR" && npm install --no-audit --no-fund --loglevel=error ) >"$npmlog" 2>&1; then
            cat "$npmlog"
            if dep_infra_signature "$npmlog"; then
                rm -f "$npmlog"
                error "npm install: registry/network unreachable (transport evidence in log)"
            fi
            rm -f "$npmlog"
            echo "[classify:fail] npm install dependency-resolution failure (no transport evidence)"
            fail "npm install failed"
        fi
        rm -f "$npmlog"
        if ( cd "$SAMPLE_DIR" && npm run build --if-present ); then
            pass
        else
            fail "npm run build failed"
        fi
    else
        require_tool node
        local jsfile tsfile
        for jsfile in "$SAMPLE_DIR"/*.js; do
            [ -f "$jsfile" ] || continue
            echo "Checking: $jsfile"
            if ! node --check "$jsfile"; then
                fail "node --check failed: $jsfile"
            fi
        done
        for tsfile in "$SAMPLE_DIR"/*.ts; do
            [ -f "$tsfile" ] || continue
            echo "TypeScript file without package.json, skipping: $tsfile"
        done
        pass
    fi
}

# ADO validation.yml L669-694
default_validate_java() {
    if [ -f "$SAMPLE_DIR/pom.xml" ]; then
        require_tool mvn
        echo "Building with Maven..."
        if ( cd "$SAMPLE_DIR" && mvn compile -q ); then
            pass
        else
            fail "mvn compile failed"
        fi
    elif [ -f "$SAMPLE_DIR/build.gradle" ] || [ -f "$SAMPLE_DIR/build.gradle.kts" ]; then
        echo "Building with Gradle..."
        # Prefer the sample-provided wrapper; only require a system gradle when there is none.
        if [ ! -f "$SAMPLE_DIR/gradlew" ]; then
            require_tool gradle
        fi
        if ( cd "$SAMPLE_DIR" && { ./gradlew build -q 2>/dev/null || gradle build -q; } ); then
            pass
        else
            fail "gradle build failed"
        fi
    else
        echo "No pom.xml or build.gradle found in $SAMPLE_DIR"
        pass
    fi
}

# ADO validation.yml L787-811
default_validate_go() {
    require_tool go
    if [ -f "$SAMPLE_DIR/go.mod" ]; then
        echo "Building Go module..."
        if ( cd "$SAMPLE_DIR" && go build ./... ); then
            pass
        else
            fail "go build ./... failed"
        fi
    else
        local gofile
        for gofile in "$SAMPLE_DIR"/*.go; do
            [ -f "$gofile" ] || continue
            echo "Checking: $gofile"
            if ! ( cd "$SAMPLE_DIR" && go build "$(basename "$gofile")" ); then
                fail "go build failed: $gofile"
            fi
        done
        pass
    fi
}

# Python isolation pre-step (mirrors ADO: venv created up front, torn down on exit).
cleanup_python_venv() {
    [ -n "$PYTHON_VENV_DIR" ] || return 0
    command -v deactivate >/dev/null 2>&1 && deactivate || true
    rm -rf "$PYTHON_VENV_DIR"
}

# --- Part 3: opt-in live-service validation ---------------------------------
# Contract:
#   live_service_validation:
#     command: "<credentialed runtime assertion>"
#     required_env: [OPTIONAL_ENV_NAME, ...]  # optional
#     substitutions:                         # optional
#       - file: "relative/sample-file.py"
#         replacements:
#           - placeholder: "your_project_endpoint"
#             env: AZURE_AI_PROJECT_ENDPOINT
#
# The caller owns authentication and configuration. This script never provisions, logs in,
# or invents defaults: it inherits the caller environment and requires the caller to set
# SKIP_PROVISION to exactly true or false. A missing declaration is a successful no-op.
escape_bash_pattern_literal() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\*/\\*}"
    value="${value//\?/\\?}"
    value="${value//\[/\\[}"
    value="${value//\]/\\]}"
    value="${value//\(/\\(}"
    value="${value//\)/\\)}"
    value="${value//@/\\@}"
    value="${value//\!/\\!}"
    value="${value//+/\\+}"
    value="${value//|/\\|}"
    printf '%s' "$value"
}

apply_live_service_substitutions() {
    local yaml="$SAMPLE_DIR/sample.yaml"
    if [ "$(yq eval '.live_service_validation | has("substitutions")' "$yaml" 2>/dev/null)" != "true" ]; then
        return 0
    fi

    local substitutions_kind substitutions_count i substitution_kind file_tag file replacement_count replacements_kind
    local resolved_sample_root resolved_dir target_file
    substitutions_kind="$(yq eval '.live_service_validation.substitutions | kind' "$yaml" 2>/dev/null)" ||
        error "failed to read sample.yaml live_service_validation.substitutions: $yaml"
    [ "$substitutions_kind" = "seq" ] ||
        error "sample.yaml live_service_validation.substitutions must be a list"
    substitutions_count="$(yq eval '.live_service_validation.substitutions | length' "$yaml" 2>/dev/null)" ||
        error "failed to read sample.yaml live_service_validation.substitutions: $yaml"

    resolved_sample_root="$(cd "$SAMPLE_DIR" 2>/dev/null && pwd -P)" ||
        error "failed to resolve sample directory: $SAMPLE_DIR"

    # Preflight: every replacement is validated and applied in memory first, so a
    # later invalid replacement can never leave the checkout partially rewritten.
    # Parallel indexed arrays (not an associative array) keep this loop working on
    # Bash 3.2, which is still the default shell on macOS.
    local -a pending_paths=()
    local -a pending_contents=()
    local slot pending_index pending_count=0

    i=0
    while [ "$i" -lt "$substitutions_count" ]; do
        substitution_kind="$(yq eval ".live_service_validation.substitutions[$i] | kind" "$yaml" 2>/dev/null)" ||
            error "failed to read sample.yaml live_service_validation.substitutions[$i]: $yaml"
        [ "$substitution_kind" = "map" ] ||
            error "sample.yaml live_service_validation.substitutions[$i] must be a mapping"

        file_tag="$(yq eval ".live_service_validation.substitutions[$i].file | tag" "$yaml" 2>/dev/null)" ||
            error "failed to read sample.yaml live_service_validation.substitutions[$i].file: $yaml"
        [ "$file_tag" = "!!str" ] ||
            error "sample.yaml live_service_validation.substitutions[$i].file must be a non-empty string"
        file="$(yq eval ".live_service_validation.substitutions[$i].file" "$yaml" 2>/dev/null)" ||
            error "failed to read sample.yaml live_service_validation.substitutions[$i].file: $yaml"
        printf '%s' "$file" | grep -q '[^[:space:]]' ||
            error "sample.yaml live_service_validation.substitutions[$i].file must be a non-empty string"
        case "$file" in
            /*|*../*|../*|*/..|..|".") error "sample.yaml live_service_validation.substitutions[$i].file must stay inside the sample directory: $file" ;;
        esac
        [ -f "$SAMPLE_DIR/$file" ] ||
            error "sample.yaml live_service_validation.substitutions[$i].file does not exist or is not a regular file: $file"
        [ ! -L "$SAMPLE_DIR/$file" ] ||
            error "sample.yaml live_service_validation.substitutions[$i].file must not be a symlink: $file"
        resolved_dir="$(cd "$(dirname "$SAMPLE_DIR/$file")" 2>/dev/null && pwd -P)" ||
            error "sample.yaml live_service_validation.substitutions[$i].file resolves outside the sample directory: $file"
        case "$resolved_dir" in
            "$resolved_sample_root"|"$resolved_sample_root"/*) ;;
            *) error "sample.yaml live_service_validation.substitutions[$i].file resolves outside the sample directory: $file" ;;
        esac
        target_file="$resolved_dir/$(basename "$file")"
        [ -r "$target_file" ] ||
            error "sample.yaml live_service_validation.substitutions[$i].file is not readable: $file"

        replacements_kind="$(yq eval ".live_service_validation.substitutions[$i].replacements | kind" "$yaml" 2>/dev/null)" ||
            error "failed to read sample.yaml live_service_validation.substitutions[$i].replacements: $yaml"
        [ "$replacements_kind" = "seq" ] ||
            error "sample.yaml live_service_validation.substitutions[$i].replacements must be a list"
        replacement_count="$(yq eval ".live_service_validation.substitutions[$i].replacements | length" "$yaml" 2>/dev/null)" ||
            error "failed to read sample.yaml live_service_validation.substitutions[$i].replacements: $yaml"
        [ "$replacement_count" -gt 0 ] ||
            error "sample.yaml live_service_validation.substitutions[$i].replacements must not be empty"

        slot=""
        pending_index=0
        while [ "$pending_index" -lt "$pending_count" ]; do
            if [ "${pending_paths[$pending_index]}" = "$target_file" ]; then
                slot="$pending_index"
                break
            fi
            pending_index=$((pending_index + 1))
        done
        if [ -z "$slot" ]; then
            local content=""
            # Shell strings cannot carry NUL bytes, so a binary file is rejected rather
            # than silently truncated at its first NUL when the rewrite is written back.
            tr -d '\000' <"$target_file" | cmp -s - "$target_file" ||
                error "sample.yaml live_service_validation.substitutions[$i].file is not a NUL-free text file: $file"
            # read exits non-zero at EOF without a NUL delimiter, which is the normal
            # case for a text file; the whole file is still captured in "$content".
            IFS= read -r -d '' content <"$target_file" || true
            slot="$pending_count"
            pending_paths+=("$target_file")
            pending_contents+=("$content")
            pending_count=$((pending_count + 1))
        fi

        local j replacement_kind placeholder_tag placeholder placeholder_pattern env_tag env_name env_value
        j=0
        while [ "$j" -lt "$replacement_count" ]; do
            replacement_kind="$(yq eval ".live_service_validation.substitutions[$i].replacements[$j] | kind" "$yaml" 2>/dev/null)" ||
                error "failed to read sample.yaml live_service_validation.substitutions[$i].replacements[$j]: $yaml"
            [ "$replacement_kind" = "map" ] ||
                error "sample.yaml live_service_validation.substitutions[$i].replacements[$j] must be a mapping"
            placeholder_tag="$(yq eval ".live_service_validation.substitutions[$i].replacements[$j].placeholder | tag" "$yaml" 2>/dev/null)" ||
                error "failed to read sample.yaml live_service_validation.substitutions[$i].replacements[$j].placeholder: $yaml"
            [ "$placeholder_tag" = "!!str" ] ||
                error "sample.yaml live_service_validation.substitutions[$i].replacements[$j].placeholder must be a non-empty string"
            placeholder="$(yq eval ".live_service_validation.substitutions[$i].replacements[$j].placeholder" "$yaml" 2>/dev/null)" ||
                error "failed to read sample.yaml live_service_validation.substitutions[$i].replacements[$j].placeholder: $yaml"
            printf '%s' "$placeholder" | grep -q '[^[:space:]]' ||
                error "sample.yaml live_service_validation.substitutions[$i].replacements[$j].placeholder must be a non-empty string"
            placeholder_pattern="$(escape_bash_pattern_literal "$placeholder")"

            env_tag="$(yq eval ".live_service_validation.substitutions[$i].replacements[$j].env | tag" "$yaml" 2>/dev/null)" ||
                error "failed to read sample.yaml live_service_validation.substitutions[$i].replacements[$j].env: $yaml"
            [ "$env_tag" = "!!str" ] ||
                error "sample.yaml live_service_validation.substitutions[$i].replacements[$j].env must be a string"
            env_name="$(yq eval ".live_service_validation.substitutions[$i].replacements[$j].env" "$yaml" 2>/dev/null)" ||
                error "failed to read sample.yaml live_service_validation.substitutions[$i].replacements[$j].env: $yaml"
            [[ "$env_name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] ||
                error "sample.yaml live_service_validation.substitutions[$i].replacements[$j].env is not a valid environment-variable name: $env_name"
            [ -n "${!env_name:-}" ] ||
                error "required live-service substitution environment variable is missing or empty: $env_name"
            env_value="${!env_name}"

            case "${pending_contents[$slot]}" in
                *$placeholder_pattern*) ;;
                *) error "live-service substitution placeholder not found in $file: $placeholder" ;;
            esac
            local updated_content="" remaining_content="${pending_contents[$slot]}" prefix
            while case "$remaining_content" in *$placeholder_pattern*) true ;; *) false ;; esac; do
                prefix="${remaining_content%%$placeholder_pattern*}"
                updated_content+="$prefix$env_value"
                remaining_content="${remaining_content#"$prefix"}"
                remaining_content="${remaining_content#"$placeholder"}"
            done
            pending_contents[$slot]="$updated_content$remaining_content"
            j=$((j + 1))
        done
        i=$((i + 1))
    done

    # Commit: the whole declaration validated, so every rewrite can now be written.
    pending_index=0
    while [ "$pending_index" -lt "$pending_count" ]; do
        printf '%s' "${pending_contents[$pending_index]}" >"${pending_paths[$pending_index]}" ||
            error "live-service substitution failed to write file: ${pending_paths[$pending_index]}"
        pending_index=$((pending_index + 1))
    done
}

run_live_service_validation() {
    local yaml="$SAMPLE_DIR/sample.yaml"
    if [ ! -f "$yaml" ]; then
        LIVE_SERVICE_VALIDATION_DECLARED=false
        echo "No sample.yaml live-service declaration; nothing owes live-service validation."
        pass
    fi

    ensure_yq
    if ! yq eval '.' "$yaml" >/dev/null 2>&1; then
        error "sample.yaml is unreadable or malformed: $yaml"
    fi

    if [ "$(yq eval 'has("l4")' "$yaml" 2>/dev/null)" = "true" ]; then
        error "legacy sample.yaml key 'l4' is unsupported; rename it to 'live_service_validation'"
    fi
    if [ "$(yq eval 'has("live_service_validation")' "$yaml" 2>/dev/null)" != "true" ]; then
        LIVE_SERVICE_VALIDATION_DECLARED=false
        echo "No sample.yaml live-service declaration; nothing owes live-service validation."
        pass
    fi
    LIVE_SERVICE_VALIDATION_DECLARED=true

    local declaration_kind command_tag cmd
    declaration_kind="$(yq eval '.live_service_validation | kind' "$yaml" 2>/dev/null)" ||
        error "failed to read sample.yaml live_service_validation declaration: $yaml"
    [ "$declaration_kind" = "map" ] ||
        error "sample.yaml live_service_validation must be a mapping with a string command"

    command_tag="$(yq eval '.live_service_validation.command | tag' "$yaml" 2>/dev/null)" ||
        error "failed to read sample.yaml live_service_validation.command: $yaml"
    [ "$command_tag" = "!!str" ] ||
        error "sample.yaml live_service_validation.command must be a non-empty string"
    cmd="$(yq eval '.live_service_validation.command' "$yaml" 2>/dev/null)" ||
        error "failed to read sample.yaml live_service_validation.command: $yaml"
    printf '%s' "$cmd" | grep -q '[^[:space:]]' ||
        error "sample.yaml live_service_validation.command must be a non-empty string"

    if [ "$(yq eval '.live_service_validation | has("required_env")' "$yaml" 2>/dev/null)" = "true" ]; then
        local required_env_kind env_count i env_name env_tag
        required_env_kind="$(yq eval '.live_service_validation.required_env | kind' "$yaml" 2>/dev/null)" ||
            error "failed to read sample.yaml live_service_validation.required_env: $yaml"
        [ "$required_env_kind" = "seq" ] ||
            error "sample.yaml live_service_validation.required_env must be a list of environment-variable names"
        env_count="$(yq eval '.live_service_validation.required_env | length' "$yaml" 2>/dev/null)" ||
            error "failed to read sample.yaml live_service_validation.required_env: $yaml"
        i=0
        while [ "$i" -lt "$env_count" ]; do
            env_tag="$(yq eval ".live_service_validation.required_env[$i] | tag" "$yaml" 2>/dev/null)" ||
                error "failed to read sample.yaml live_service_validation.required_env[$i]: $yaml"
            [ "$env_tag" = "!!str" ] ||
                error "sample.yaml live_service_validation.required_env[$i] must be a string"
            env_name="$(yq eval ".live_service_validation.required_env[$i]" "$yaml" 2>/dev/null)" ||
                error "failed to read sample.yaml live_service_validation.required_env[$i]: $yaml"
            [[ "$env_name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] ||
                error "sample.yaml live_service_validation.required_env[$i] is not a valid environment-variable name: $env_name"
            [ -n "${!env_name:-}" ] ||
                error "required live-service environment variable is missing or empty: $env_name"
            i=$((i + 1))
        done
    fi

    case "${SKIP_PROVISION:-}" in
        true|false) ;;
        "") error "SKIP_PROVISION must be set by the live-service caller to true or false" ;;
        *) error "SKIP_PROVISION must be exactly true or false (got: $SKIP_PROVISION)" ;;
    esac

    apply_live_service_substitutions

    echo "Running live-service command (SKIP_PROVISION=$SKIP_PROVISION): $cmd"
    local live_service_log
    live_service_log="$(mktemp)" || error "failed to create temporary live-service command log"
    local live_service_rc
    ( cd "$SAMPLE_DIR" && eval "$cmd" ) >"$live_service_log" 2>&1
    live_service_rc=$?
    cat "$live_service_log"
    rm -f "$live_service_log"
    case "$live_service_rc" in
        0) pass ;;
        1) fail "sample.yaml live_service_validation.command reported sample failure (exit 1)" ;;
        2) error "sample.yaml live_service_validation.command reported caller/cloud infrastructure error (exit 2)" ;;
        *) fail "sample.yaml live_service_validation.command exited with unexpected status $live_service_rc (classified fail)" ;;
    esac
}

python_setup_venv() {
    require_tool python
    PYTHON_VENV_DIR="$SAMPLE_DIR/.venv"
    echo "Creating virtual environment..."
    if ! python -m venv "$PYTHON_VENV_DIR"; then
        error "failed to create Python venv (toolchain/infra failure): $PYTHON_VENV_DIR"
    fi
    # shellcheck disable=SC1091
    source "$PYTHON_VENV_DIR/bin/activate" || error "failed to activate Python venv: $PYTHON_VENV_DIR"
}

# --- Argument parsing --------------------------------------------------------
while [ $# -gt 0 ]; do
    case "$1" in
        --mode)        MODE="${2:-}";        shift $(( $# > 1 ? 2 : 1 )) ;;
        --language)    LANGUAGE="${2:-}";    shift $(( $# > 1 ? 2 : 1 )) ;;
        --sample-dir)  SAMPLE_DIR="${2:-}";  shift $(( $# > 1 ? 2 : 1 )) ;;
        --results-dir) RESULTS_DIR="${2:-}"; shift $(( $# > 1 ? 2 : 1 )) ;;
        -h|--help)     usage; exit 0 ;;
        *)             usage >&2; error "unknown argument: $1" ;;
    esac
done

# --- Guards (ordered so the ERROR tier is provable without any toolchain) -----
case "$MODE" in
    build-readiness|live-service) ;;
    "") error "missing value for --mode (expected build-readiness or live-service)" ;;
    *)  error "unsupported validation mode '$MODE' (expected build-readiness or live-service)" ;;
esac

[ -n "$SAMPLE_DIR" ] || error "missing required --sample-dir"
[ -d "$SAMPLE_DIR" ] || error "sample directory not found: $SAMPLE_DIR"
SAMPLE_DIR="${SAMPLE_DIR%/}"

if [ "$MODE" = "build-readiness" ] || [ -n "$LANGUAGE" ]; then
    case "$LANGUAGE" in
        csharp|python|typescript|java|go) ;;
        "") error "missing required --language for build readiness" ;;
        *)  error "unsupported language '$LANGUAGE' (frozen set: csharp|python|typescript|java|go)" ;;
    esac
fi

echo "=== validate-sample: mode=$MODE language=${LANGUAGE:-n/a} dir=$SAMPLE_DIR ==="

if [ "$MODE" = "live-service" ]; then
    run_live_service_validation
    error "internal: no live-service verdict emitted"
fi

# Python creates its isolated venv before the sample.yaml/default branch (ADO parity),
# so sample.yaml commands also run inside the venv.
if [ "$LANGUAGE" = python ]; then
    trap cleanup_python_venv EXIT
    python_setup_venv
fi

# Part 1: sample.yaml commands take precedence over language defaults.
run_sample_yaml
rc=$?
case "$rc" in
    0) pass ;;
    1) fail "sample.yaml '${SAMPLE_YAML_FAIL_STEP:-?}' command exited non-zero" ;;
    3) : ;;  # no commands declared — fall through to the language default
esac

# Part 2: language default.
case "$LANGUAGE" in
    csharp)     default_validate_csharp ;;
    python)     default_validate_python ;;
    typescript) default_validate_typescript ;;
    java)       default_validate_java ;;
    go)         default_validate_go ;;
esac

# Unreachable: every default_validate_* ends in pass()/fail().
error "internal: no verdict emitted for language=$LANGUAGE"
