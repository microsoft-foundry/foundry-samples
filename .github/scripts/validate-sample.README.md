# Per-sample validation contract

`.github/scripts/validate-sample.sh` validates one sample for either build readiness
or live-service behavior. Build readiness is the default.

## CLI

```bash
# Build readiness (default)
bash .github/scripts/validate-sample.sh \
  --language python \
  --sample-dir samples/python/quickstart/responses

# Opt-in live-service validation
SKIP_PROVISION=true bash .github/scripts/validate-sample.sh \
  --mode live-service \
  --sample-dir samples/python/quickstart/responses
```

These commands invoke individual validation modes; calling `--mode live-service`
directly does not implicitly run build readiness first. The repository validation
pilot provides the end-to-end sequence: every supported sample runs build readiness,
and a sample with a `live_service_validation` declaration proceeds to live-service
validation only after readiness passes. Declaring live-service validation therefore
does not opt a sample out of build readiness.

## Build readiness

The validator supports `csharp`, `python`, `typescript`, `java`, and `go`.
Workflow callers map JavaScript samples to `typescript`.

If `sample.yaml` declares `build`, `validate`, or `test`, the validator runs
each non-empty command in that order and stops at the first failure. Declared
commands take precedence over the language default.

| Language | Default when no commands are declared |
|---|---|
| C# | Run `dotnet build --verbosity minimal` for every top-level `.csproj`; pass when none exists. |
| Python | Create and activate a temporary `.venv` in the sample directory, install `requirements.txt` when present, run `python -m py_compile` for each top-level `.py`, and remove the virtual environment on exit. |
| TypeScript / JavaScript | With `package.json`, run `npm install --no-audit --no-fund` and `npm run build --if-present`. Without it, run `node --check` for top-level `.js`; top-level `.ts` files have no default compile step. |
| Java | Run `mvn compile -q` for `pom.xml`, or a Gradle build for `build.gradle`/`build.gradle.kts`, preferring `./gradlew` before a system `gradle`; pass when neither build file exists. |
| Go | Run `go build ./...` with `go.mod`, otherwise build each top-level `.go`; pass when no top-level `.go` exists. |

Rust is not supported. The full-fleet cadence currently enables C#, Java,
Python, TypeScript, and JavaScript; Go remains available to local and
pull-request callers but is not enabled by cadence discovery.

Both modes use the same exit and verdict contract:

| Exit | Verdict | Meaning |
|---|---|---|
| `0` | `pass` | The requested check passed. In live-service mode, no declaration is also a clean no-op. |
| `1` | `fail` | The sample command/assertion failed. |
| `2` | `error` | The validator precondition or caller environment is invalid, or a live-service command explicitly reported caller/cloud infrastructure failure. |

See `CLASSIFICATION.md` for the authoritative failure-versus-error rules.

## `sample.yaml` Live-service declaration

Live-service validation is opt-in and sample-owned. A sample declares it with a top-level
`live_service_validation` mapping:

```yaml
live_service_validation:
  command: >-
    python run_sample.py --assert-response
  required_env:
    - AZURE_OPENAI_ENDPOINT
    - MODEL_DEPLOYMENT
  substitutions:
    - file: run_sample.py
      replacements:
        - placeholder: "your_project_endpoint"
          env: AZURE_AI_PROJECT_ENDPOINT
```

The contract is:

- `live_service_validation.command` is a required, non-empty shell string. The validator runs it from
  the sample directory with Bash and captures/preserves its output.
- The command owns a strict three-way result: exit `0` means pass, exit `1`
  means the sample/assertion failed, and exit `2` means a known caller/cloud
  infrastructure failure. Any other nonzero exit is conservatively classified
  as sample failure.
- The validator never infers live-service infrastructure failure from stdout/stderr text.
  A broken sample can legitimately print `503 Service Unavailable`, `Bad
  Gateway`, or similar application responses. If a command can distinguish a
  known credential, endpoint, or cloud transport failure, it must normalize
  that condition to exit `2`; ambiguous conditions must exit `1`.
- Do not expose a tool's raw exit code unless it already follows this contract.
  Common tools use `2` for sample-side conditions such as invalid arguments,
  interrupted tests, or usage errors. Wrap those commands so only a known
  caller/cloud infrastructure failure exits `2`; normalize other nonzero
  statuses to `1`.
- `live_service_validation.required_env` is optional. When present, it must be a list of valid
  environment-variable names. Every listed variable must be non-empty or the
  validator returns infrastructure error (`2`) before executing sample code.
- `live_service_validation.substitutions` is optional. Use it when source files
  intentionally contain copy/paste instructional placeholders, such as
  `"your_project_endpoint"`, but the validation caller owns the real value. Each
  substitution names a file inside the sample directory and one or more
  `placeholder` to `env` replacements. The validator requires each environment
  variable to be non-empty, replaces every exact placeholder occurrence in the
  workflow checkout before running the live-service command, and returns
  infrastructure error (`2`) if the target file is outside the sample directory,
  missing, malformed, or does not contain the placeholder. Substitutions are
  validated and applied in memory first and written only after the whole
  declaration is valid, so a rejected declaration never leaves a partially
  rewritten checkout. Target files must be regular, non-symlinked text files
  without NUL bytes. Rewriting uses Bash only, so a substitution never adds a
  toolchain requirement beyond the sample's own language.
- `SKIP_PROVISION` is a reserved caller input and must be set to exactly `true`
  or `false` whenever live-service validation is declared. The validator
  passes it through but never provisions resources itself. Current repository
  workflows use the warm project with `true`; cold provisioning and a caller
  policy for `false` are not yet delivered.
- Authentication and cloud configuration are caller-owned. The command inherits
  the caller's environment and existing CLI/OIDC login. Do not put credentials,
  secrets, resource provisioning, or production mutations in `sample.yaml`.
- If `live_service_validation` is omitted (or `sample.yaml` itself is absent),
  `--mode live-service` exits `0`
  without requiring credentials or `SKIP_PROVISION`. It emits
  `live_service_validation_declared=false`; a declared check emits
  `live_service_validation_declared=true`.
- If `$GITHUB_OUTPUT` is set, `verdict` and `live_service_validation_declared`
  are appended there.
  `--results-dir` continues to write the sample path to
  `passed.txt`, `failed.txt`, or `errored.txt`.

The validator rejects the legacy `l4` key with a migration message. It also rejects
a scalar `live_service_validation`, a missing/non-string/empty `command`, a non-list
`required_env`, invalid variable names, malformed YAML, invalid substitution
declarations, and missing declared environment inputs as infrastructure errors.

## Caller responsibilities

Local callers must install the language toolchain and Bash. Install `yq` when
the sample has `sample.yaml`; repository workflows pin `yq` 4.44.3. Callers
also own authentication, environment variables, and the decision to use a warm
or future cold environment. The validator does not log in, create cloud
resources, or infer credentials.

The pull-request workflow runs Build readiness for changed supported samples
and uses the existing warm project for its required `trusted` check. The daily
cadence discovers the full metadata-bearing inventory and publishes normalized
results as described in the
[daily validation guide](../validation-pilot.README.md).
