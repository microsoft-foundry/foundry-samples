# Hosted-agent cloud E2E test specifications

## Why this contract exists

The sample author defines the agent's intended behavior. The shared CI runner can
deploy it and collect evidence, but it should not guess what success means.

HTTP success and non-empty output can hide incomplete behavior: a pending approval,
a skipped tool, missing assistant text, or a promised file that was never created.
`test-spec.yml` prevents these false positives by declaring the owner, representative
turns, permitted approvals, and evidence that proves the sample works.

## New hosted-agent sample checklist

Every new sample under `samples/python/hosted-agents/` or
`samples/csharp/hosted-agents/` must:

1. Add an `azure.yaml` with an `azure.ai.agent` service.
2. Add `test-spec.yml` at the fixture path described below.
3. Register a responsible Microsoft alias in `sample.owner`.
   - Start with the original code author from `git log --reverse -- <sample-path>`.
   - Use the principal maintainer when the original author is no longer responsible.
   - Store the alias only, without `@microsoft.com`.
   - Do not add a new sample without an owner.
4. Declare whether the sample is supported through `azd`, `vscode`, or both.
5. Choose deterministic turns that exercise one or two defining behaviors.
6. Assert user-visible results rather than incidental implementation details.
7. If a `console_log` assertion is necessary, target a deliberate sample-owned
   event. Python agents must emit required runtime evidence through `logging`, not
   an unflushed `print()`, and contracts must not depend on mutable framework or
   dependency log wording.
8. Run both schema validation and protocol-aware planning locally.

Legacy `test-payload.txt` and generated defaults remain migration paths for existing
samples. They are not the preferred contract for new samples.

### New-sample coverage policy

Pull-request CI compares hosted-agent `azure.yaml` paths at the merge base and PR
head. Every sample root that exists only at the head must provide a valid full-path
`test-spec.yml`; schema validation and protocol-aware planning must both pass.

The initial rollout is intentionally conservative: updates to existing sample roots,
documentation-only changes, Git-detected moves or renames, deletions, and samples
excluded with `.ci-skip` do not trigger contract migration. The credential-free
workflow is a required PR check and can be run locally from the checked-out PR head with:

```bash
base=$(git merge-base origin/main HEAD)
python3 .github/scripts/check_hosted_agent_contracts.py --base "$base" --head HEAD
```

### Resolving contract policy failures

For `Missing hosted-agent behavior contract`, create the exact `Required contract`
path printed by CI, follow the [new-sample checklist](#new-hosted-agent-sample-checklist),
and run the protocol-aware validation commands from the check.

For `Invalid hosted-agent behavior contract`, fix the exact schema or planning error
shown under `Problem` and rerun those commands. The canonical contract reference is
the [complete document shape](#complete-document-shape); command usage is documented
under [local validation](#local-validation).

## Discovery and fixture identity

The fixture path is:

```text
internal/tools/samples-hosted-agents/
  <language>/                 # python | csharp
    <complete-sample-path>/   # path below samples/<language>/hosted-agents
      test-spec.yml           # preferred behavior contract
      test-payload.txt        # optional legacy payload
```

The fixture preserves the complete sample path below the language's `hosted-agents`
directory. For example:

```text
samples/python/hosted-agents/agent-framework/responses/06-files
```

maps one-to-one to:

```text
internal/tools/samples-hosted-agents/python/agent-framework/responses/06-files/
```

Both `test-spec.yml` and legacy `test-payload.txt` use this same directory identity.
Do not shorten it to the sample directory basename. Preserving the framework,
transport grouping, and other intermediate directories prevents distinct samples
with the same basename from implicitly sharing test input or a behavior contract.
CI rejects any fixture whose full path does not map back to a sample containing
`azure.yaml`.

The cloud workflow discovers all Python/C# hosted-agent `azure.yaml` files except
samples marked `.ci-skip`. A spec customizes that existing matrix participation; it
does not itself opt a sample into CI.

## Supported protocols

The runner supports `responses` and `invocations`. Other protocols require dedicated
harnesses:

- `invocations_ws` uses sample-defined, full-duplex WebSocket frames.
- `activity` requires Bot/Teams setup and sends replies asynchronously.
- A2A requires agent-card discovery and JSON-RPC/task handling.
- Voice Live uses a separate real-time audio service.

They remain unsupported until CI has transport-specific clients and evidence
collection that do not guess sample behavior.

## Local validation

Install the development requirements, then run both commands:

```bash
python3 .github/scripts/hosted_agent_test_spec.py validate \
  --spec internal/tools/samples-hosted-agents/<language>/<complete-sample-path>/test-spec.yml

python3 .github/scripts/hosted_agent_test_spec.py plan \
  --spec internal/tools/samples-hosted-agents/<language>/<complete-sample-path>/test-spec.yml \
  --protocol <responses|invocations> \
  --output /tmp/hosted-agent-test-plan.json
```

`validate` checks the YAML schema. `plan` also checks protocol-specific rules, such
as rejecting MCP approval policies for Invocations. CI runs both commands over every
spec before creating the deployment matrix.

## Complete document shape

```yaml
version: 1

sample:
  owner: sample-owner
  experiences: [azd, vscode]

tests:
  - name: unique-test-name
    when:                         # optional
      toolbox_label: code-interpreter

    turns:                        # required, non-empty
      - input: Calculate 42 multiplied by 17.

        approvals:                # optional; Responses only
          mcp:                     # exact automatic approval sequence
            - server_label: agent_framework
              name: load_skill
            - server_label: agent_framework
              name: run_skill_script

        assertions:               # optional sequence
          - source: assistant_text
            type: contains
            value: "714"

    assertions:                   # optional test-wide sequence
      - source: console_log
        type: regex
        value: '(?i)uncaught exception|traceback'
        min_matches: 0
        max_matches: 0
```

### Required fields and values

| Scope | Field | Contract |
|---|---|---|
| document | `version` | Required integer; must be `1` (Boolean `true` is not accepted). |
| document | `sample` | Required mapping; only `owner` and `experiences` are allowed. |
| document | `tests` | Required non-empty sequence. |
| sample | `owner` | Required non-empty Microsoft alias. Must start with an ASCII letter and then contain only letters, digits, `.`, `_`, or `-`; `@microsoft.com` is forbidden. |
| sample | `experiences` | Required non-empty unique sequence containing `azd`, `vscode`, or both. This is registration metadata and does not alter the cloud matrix. |
| test | `name` | Required non-empty string, unique within the file. |
| test | `when` | Optional mapping. `toolbox_label` is its only supported field. |
| test | `turns` | Required non-empty sequence. |
| test | `assertions` | Optional sequence of test-scope assertions. |
| turn | `input` | Required string, mapping, or sequence. Nested mappings require string keys and may contain strings, finite numbers, Booleans, null, mappings, and sequences. YAML-specific timestamps, sets, binary values, recursive aliases, and other non-JSON values are rejected. Numbers, Booleans, and null are not valid top-level inputs. |
| turn | `approvals` | Optional Responses-only MCP policy. |
| turn | `assertions` | Optional sequence of turn-scope assertions. |

Unknown fields and duplicate YAML keys are rejected at every scope.

## Tests, turns, and inputs

- Tests are evaluated in file order.
- Turns execute in order and use the cell-owned hosted session.
- String input is literal; no shell, environment, or template expansion occurs.
- A mapping or sequence is validated recursively and serialized as compact JSON.
- A nonmatching `when.toolbox_label` is `not_applicable`, not passed.
- Semantic assertion failures are never retried.

### Toolbox matrix query replacement

For a toolbox matrix cell with a non-empty configured query, replacement occurs only
for an applicable test that declares `when.toolbox_label`:

- all declared turns are replaced by exactly one turn;
- the replacement retains the first declared turn's assertions and approval policy;
- later turn assertions/policies are discarded;
- test-wide assertions remain;
- Responses receives the query as text;
- Invocations receives compact `{"query":"<configured query>"}` JSON.

Toolbox samples are currently recognized from a sample path containing `toolbox`.
A nonmatching conditioned test is not invoked with an unrelated matrix query.

## Assertion sources and supported checks

An assertion source selects the evidence to inspect. Sources are intentionally
named for what they contain rather than for an ambiguous HTTP or model "response."

| Source | Protocol | Scope | Evidence selected | Supported types |
|---|---|---|---|---|
| `assistant_text` | Responses only | turn | Assistant-visible `output_text`, aggregated across automatic approval steps | `contains`, `equals`, `regex` |
| `raw` | Responses, Invocations | turn | Final raw Responses JSON body, or exact captured Invocations output including sample-defined events and CLI framing | `contains`, `equals`, `regex` |
| `session_files` | Responses, Invocations | turn | Exact paths returned by listing the hosted session filesystem | `exists` |
| `console_log` | Responses, Invocations | test | Combined application console and hosted system-event logs | `contains`, `regex` |
| `trace` | Responses, Invocations | test | Session-correlated OpenTelemetry spans | `span` |

Using a source at the wrong scope, on an unsupported protocol, or with an
unsupported type is a schema/planning error.

### `assistant_text`

Use `assistant_text` for semantic assertions on Responses agents:

```yaml
- source: assistant_text
  type: contains                 # contains | equals | regex
  value: "714"
  case_sensitive: true           # optional; default true
  min_matches: 1                 # optional; default 1
  max_matches: 1                 # optional; no default maximum
```

It contains only assistant-visible `output_text`; it excludes HTTP metadata, tool
calls, approval requests, and JSON envelopes. Text from automatic approval steps is
aggregated in order. Invocations output is opaque, so `assistant_text` is rejected
for Invocations tests.

### `raw`

Use `raw` when the transport output itself matters:

```yaml
- source: raw
  type: regex                    # contains | equals | regex
  value: '"type"\\s*:\\s*"done"'
  min_matches: 1
```

For Responses, `raw` is the final unmodified Responses JSON body. For Invocations,
`raw` is the exact output captured from `azd ai agent invoke`; it can include CLI
framing and sample-defined text, JSON, or SSE events. Its shape is intentionally
protocol- and sample-dependent. The schema does not promise `done`, `full_text`, or
any other universal Invocations field.

### Common text matching rules

- `contains` requires a non-empty value and counts non-overlapping occurrences.
- `equals` is supported only for `assistant_text` and `raw`, compares the entire
  evidence string, ignores trailing CR/LF on both sides, and permits `""` to
  require empty evidence.
- `case_sensitive: false` uses Unicode case-folding for `contains`/`equals` and
  `re.IGNORECASE` for regex.
- Regex syntax is Python `re`; invalid patterns fail schema validation.
- Bounds are non-negative integers; Booleans are rejected.
- `min_matches` defaults to 1; `max_matches` has no default maximum.
- When both are present, `max_matches >= min_matches`.
- Assert absence with both bounds set to zero:

  ```yaml
  - source: console_log
    type: regex
    value: '(?i)uncaught exception|traceback'
    min_matches: 0
    max_matches: 0
  ```

JSONPath is not part of the current contract. No existing sample requires it, and
Invocations does not guarantee structured JSON output.

### `console_log`

Use `console_log` only when a deliberate application log event is the clearest
proof of the behavior. Prefer `assistant_text`, `raw`, `trace`, or `session_files`
when those sources prove the user-visible result directly.

For Python hosted agents, emit required runtime evidence with the standard
`logging` module. A long-running process may buffer ordinary stdout indefinitely,
so an unflushed `print()` is not reliable evidence. Assert sample-owned messages;
do not couple contracts to framework or dependency log text that can change on a
package update. Before adding a positive assertion, confirm the exact event appears
in deployed console evidence for every applicable deployment mode.

## Session-file existence

```yaml
- source: session_files
  type: exists
  path: /generated-travel-guides/lisbon-1-day-travel-guide.pdf
```

Session-file assertions support only positive, exact existence:

- the contract path begins with `/` and is relative to session `$HOME`;
- relative paths, `$HOME`, repeated separators, trailing `/`, and `.`/`..`
  segments are rejected;
- globs, regex paths, negative existence, match bounds, downloads, hashes, and
  content inspection are unsupported;
- the runner lists the parent directory with `azd ai agent files list` and checks
  for an exact contract-path suffix;
- failed listings, missing directories, and missing files fail the assertion.

Use this only for a prominent user-visible output. Do not assert internal note,
checkpoint, or HITL persistence merely because it lives under `$HOME`.

## Trace span assertions

```yaml
- source: trace
  type: span
  name: execute_tool             # optional exact, case-sensitive match
  attributes:                    # optional, but non-empty when present
    gen_ai.tool.name:
      regex: '(?i)code[_-]?interpreter'
    gen_ai.request.model:
      exists: true
  status: ok                     # optional: ok | error | unset
  min_matches: 1                 # optional; default 1
  max_matches: 1                 # optional
```

At least one of `name`, `attributes`, or `status` is required. Each attribute
predicate contains exactly one of:

- `exists: true|false`;
- `equals: <any YAML/JSON value>` (type-sensitive);
- `regex: <Python regex>`.

Attribute names and span names are non-empty strings. Bounds follow the common
rules. If trace evidence or Application Insights access is unavailable, the
assertion errors; it never silently passes.

## Explicit MCP approvals

Automatic approval is opt-in per Responses turn and follows an exact sequence:

```yaml
approvals:
  mcp:
    - server_label: agent_framework
      name: load_skill
    - server_label: agent_framework
      name: run_skill_script
```

The presence of `approvals.mcp` means the runner automatically approves that exact
ordered sequence. Without the block, the runner sends no approval response and
keeps `store: false`. This allows HITL tests to inspect a pending request through
`source: raw` without granting execution. Pending requests are recorded in
turn status and emit a CI warning.

Each sequence entry contains exactly one non-empty `server_label` and `name`.
Matching is exact and case-sensitive; wildcards and regexes are forbidden. Entries
may repeat when repeated execution is intentional.

For a declared sequence:

- each step expects exactly one `mcp_approval_request`;
- the request must have a unique non-empty ID and exactly match the next expected
  `(server_label, name)` pair;
- only then does the runner send an `mcp_approval_response` with `approve: true`;
- the sequence length is the continuation bound—there is no separate round limit;
- every HTTP-successful Responses body must be valid JSON with `status: completed`;
- final assistant output is accepted only after every expected step was consumed;
- missing, extra, reordered, multiple, malformed, duplicate-ID, or previously
  approved requests fail closed without a semantic retry;
- the runner never sends `approve: false`;
- approval sequences are rejected for Invocations tests.

Opted-in turns use hosted Responses `store: true` only so `previous_response_id`
can resolve. This is distinct from a sample's upstream model-client `store` option.
Requests, responses, and headers are retained by attempt and approval step.
`assistant_text` evidence aggregates assistant-visible text across responses;
`raw` evidence is the final Responses body. Turn status records approval decisions and sequence completion and summarizes the
final request attempt.

The sequence controls tool selection, order, and count—not model-generated
arguments. `server_label` is a routing label rather than a cryptographic identity.
Use automatic approval only for reviewed first-party code in a disposable hosted
session. Approval evidence can contain tool arguments and is uploaded as a CI
artifact.

## Evidence, retries, and reports

For every turn the runner retains:

- serialized input;
- HTTP status or CLI exit code;
- final request-attempt count;
- `raw` transport evidence;
- aggregated `assistant_text` evidence for Responses turns;
- initial request and Responses headers;
- approval request/response/header evidence by attempt and step;
- required session-file listings.

Test-level evidence includes combined console/system logs and required correlated
trace records. The resolved spec, execution plan, status, assertion report, and
supporting evidence are uploaded for 14 days.

Transport/readiness/session-quota/model-throttle retries remain separate from
semantic validation. Console and trace retrieval can be refreshed because those
services are eventually consistent. Monitor evidence is limited to the latest 300
lines from each console/system stream.

An applicable failed assertion, execution error, or unavailable required evidence
fails the matrix cell. Turn-status evidence is required; a missing or non-integer
`exit_code`, malformed approval status, or truncated status record is an execution
error rather than a pass. A spec whose tests all mismatch conditions reports
`not_applicable`.

## Workflow-wide gates

A spec does not bypass existing cloud E2E safeguards. A cell can fail before or
outside assertion evaluation because of:

- deployment/readiness/session failures;
- non-zero invocation exit or empty final output;
- generic response error-pattern checks;
- toolbox "tool was not called" checks;
- the special echo-agent check;
- content-safety guardrail validation;
- Voice Live smoke validation;
- temporary toolbox cleanup.

Do not design a spec that expects a generic gate to accept an intentional error
response unless the workflow is updated at the same time.

## Legacy migration behavior

Discovery order is:

1. `test-spec.yml`;
2. legacy `test-payload.txt`;
3. generated protocol default.

Legacy payloads use the same full sample-relative fixture directory as contracts.

Each non-empty legacy payload line is one ordered turn. JSON object/array lines keep
their structured Invocations meaning. Defaults are:

- Responses: three `Hello from CI` turns;
- Invocations: three `{"query":"analyze dataset"}` turns.

`test-assertions.yml` is no longer supported. Migrate payload and assertions into
one spec. Remove legacy payload support after remaining fixtures are converted.

## Current boundaries

The current contract intentionally excludes file download/content validation, MIME/size/hash checks,
external Azure-resource assertions, arbitrary scripts or custom validators,
internal note/HITL persistence assertions, model-graded checks, semantic retries,
inheritance, templates, and arbitrary code execution from the spec.
