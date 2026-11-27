# A2A downstream session routing

## What this sample demonstrates

Can two callers reach the same downstream hosted session? This sample uses three
deterministic native A2A 1.0 agents to distinguish context IDs, tasks, hosted
sessions and user identity. It includes the source, dedicated test runners and
synthetic evidence from actual Foundry invocations.

## How it works

```text
User 1 --> A --+
              +--> C --> session-local synthetic message ledger
User 1/2 -> B -+
```

All three services run [main.py](src/agent/main.py). `REPRO_ROLE` selects A, B or
C. A/B authenticate using their own managed identities and forward the SDK's
request-scoped platform call headers. C reports:

- A2A context ID and task ID.
- Platform `FOUNDRY_AGENT_SESSION_ID` and session GUID.
- A boot UUID, which is not a substitute for a session ID.
- The first 20 hexadecimal characters of SHA-256 of the opaque platform user ID.
  This fingerprint is for comparison, not authentication.
- A sequence number and previous synthetic markers in a SQLite ledger under the
  hosted session's private home directory.

There is **no LLM, Copilot session, booking, web search or model-generated
answer**. This isolates A2A/Foundry session routing from model behavior.
User messages cannot choose an outbound URL; A/B call only `C_AGENT_ENDPOINT`.
The diagnostic ledger deliberately reveals prior synthetic markers in the same
session. Do not send secrets, real conversations or personal data.

### Three different identifiers

| Identifier | Meaning |
|---|---|
| A2A `contextId` | Opaque conversation label supplied by the client or generated when omitted |
| A2A task ID | Identifies one task; separate tasks can share a context |
| Hosted session ID | Actual platform session used for compute and session-local state |

Returning the same context ID alone is not proof of session reuse. This sample
checks the actual hosted session ID and state history too.

### Forwarding modes

The JSON *text content* sent to A/B contains a synthetic `marker` and:

| Sample-specific `mode` | What A/B send to C |
|---|---|
| `fresh` (default) | Omit downstream context ID |
| `explicit` | Set downstream context to `c_context_id` |
| `inherit` | Copy the incoming A2A context to C |

These are sample options, not standard A2A protocol fields. The actual A2A
context field is `message.context_id` in Python / `message.contextId` on the wire.

## Prerequisites

- An existing Foundry project enabled for native A2A.
- Python 3.13 for the hosted runtime; Python 3.11+ for the local source.
- Azure CLI, `azd >= 1.37.2`, and `azure.ai.agents >= 1.0.0-beta.23`.
- Permission to deploy hosted agents. An authorized owner must be able to grant
  **Foundry Agent Consumer** to A/B's managed identities at project scope.
- For the real-user test: two people independently authenticated with authorized
  Entra accounts. Do not send tokens to each other.

Follow the shared [Python startup configuration](../../../README.md#python-startup-configuration).
This diagnostic sample is CLI-only; it does not depend on Agent Inspector or a
VS Code launch configuration.

## Run and test locally

From this sample directory, restore the pinned
[requirements.txt](src/agent/requirements.txt) into an isolated environment:

```powershell
python -m venv .\src\agent\.venv
& .\src\agent\.venv\Scripts\python.exe -m pip install `
  --extra-index-url "https://pkgs.dev.azure.com/azure-sdk/public/_packaging/azure-sdk-for-python/pypi/simple/" `
  -r .\src\agent\requirements.txt

& .\src\agent\.venv\Scripts\python.exe -m unittest discover -s .\tests -v
& .\src\agent\.venv\Scripts\python.exe .\test_local.py
```

The local integration test starts and stops its three child servers on loopback
ports 18191-18193, uses temporary ledger directories, and writes
`results/local.json`. It runs 18 end-to-end calls with 29 context/history
assertions. Local C shares one process/home directory, so this run deliberately
does **not** assert platform-session separation.

The dependency fallback is intentional: the tested uv-only project was not
recognized by the remote builder, and remote restores subsequently hit TLS
errors. The committed requirements pin the complete graph from the tested local
environment. Preview agentserver packages are retrieved from the public Azure
SDK feed; index configuration is kept out of the requirements artifact.

## Deploy with Azure Developer CLI

### Initialize in an empty deployment directory

Start in this sample directory and resolve its manifest before changing folders:

```powershell
$manifest = (Resolve-Path .\azure.yaml).Path
$env:AZD_ALPHA_ENABLE_AGENTS_A2A = "true"
$env:AZURE_AI_PROJECT_ENDPOINT = "<YOUR-FOUNDRY-PROJECT-ENDPOINT>"

$deployment = Join-Path $HOME ("a2a-session-routing-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory $deployment
Set-Location $deployment

azd auth login
az login
azd ai agent init --src . -t $manifest `
  --project-id "<YOUR-EXISTING-PROJECT-ARM-ID>" `
  -e session-routing --no-prompt
azd env set AZURE_AI_PROJECT_ENDPOINT $env:AZURE_AI_PROJECT_ENDPOINT
```

Keep the deployment directory outside version control. The manifest references
an existing project and declares no new model deployment. Do not provision
unrelated infrastructure or reuse someone else's live endpoints.

Before deploying, edit the three service keys **and their `name` values** to
unique names if the defaults already exist in your project. Reusing an existing
agent name creates a new version, not a separate agent.

### Prepare a Linux dependency bundle

```powershell
.\prepare_bundle.ps1
```

The helper downloads TLS-verified Linux Python 3.13 wheels and installs them
under `src/agent/packages`. The manifest uses supported `bundled` code deployment
for all three services, avoiding remote dependency-download variability.
The wheel cache and local environments are excluded from upload. No Docker or
ACR is needed; do not import Linux `packages` directly on Windows.

### Deploy C, then A/B

Use your renamed keys below if applicable:

```powershell
azd deploy session-routing-c --no-prompt
azd ai agent show session-routing-c --output json
azd env set C_AGENT_ENDPOINT "<ACTUAL-C-agent_endpoints.a2a>"

azd deploy session-routing-a --no-prompt
azd deploy session-routing-b --no-prompt
azd ai agent show session-routing-a --output json
azd ai agent show session-routing-b --output json
```

Verify active status. An authorized owner should inspect A/B's
`instance_identity.principal_id` and grant missing runtime access:

```powershell
az role assignment create `
  --assignee-object-id "<A-OR-B-PRINCIPAL-ID>" `
  --assignee-principal-type ServicePrincipal `
  --role "Foundry Agent Consumer" `
  --scope "<YOUR-PROJECT-ARM-ID>"
```

Repeat only for the two new forwarders. Leave existing unrelated permissions
unchanged. Default Entra isolation must remain enabled on A, B and C.

## Single-user remote test

From a restored source environment:

```powershell
& .\src\agent\.venv\Scripts\python.exe .\run_experiment.py `
  --a "<ACTUAL-A-A2A-ENDPOINT>" `
  --b "<ACTUAL-B-A2A-ENDPOINT>" `
  --output .\results\same-user.json
```

The runner makes 18 parent invocations and 18 downstream calls, persisting every
receipt and failure. It checks fresh sequential/concurrent calls, explicitly
shared contexts, inherited contexts and branch-specific contexts with follow-ups.
Use one intended credential identity: the runner uses `DefaultAzureCredential`.

## Two real users, one downstream context

Each person uses their own machine or independent CLI profile and runs `az login`
with their own account. The dedicated client uses `AzureCliCredential` explicitly
so unrelated environment credentials cannot silently select another identity.
Agree on one new opaque context value, for example
`two-real-users-your-run-01`, and use it in both commands.

User 1 calls A:

```powershell
& .\src\agent\.venv\Scripts\python.exe .\run_real_user.py invoke `
  --endpoint "<ACTUAL-A-A2A-ENDPOINT>" `
  --context "two-real-users-your-run-01" `
  --marker "U1-via-A" --output .\results\u1.json
```

User 2 calls B under their own sign-in:

```powershell
& .\src\agent\.venv\Scripts\python.exe .\run_real_user.py invoke `
  --endpoint "<ACTUAL-B-A2A-ENDPOINT>" `
  --context "two-real-users-your-run-01" `
  --marker "U2-via-B" --output .\results\u2.json
```

Exchange only the synthetic receipts and compare:

```powershell
& .\src\agent\.venv\Scripts\python.exe .\run_real_user.py compare `
  .\results\u1.json .\results\u2.json
```

The comparator checks equal C contexts, different nonempty user fingerprints,
different actual C sessions, identity preservation through each parent, distinct
C tasks and absence of the other marker in session history. Repeating each
user's call with a new marker and the same context can test retention; coordinating
simultaneous calls can test concurrency. Neither extension was completed in the
recorded real-user run.

Do not use `x-ms-user-identity` or `--user-identity` here. Those test delegated
identities and require separate permission; they are not two independent sign-ins.

## Recorded results

### Same user via A and B

Run `repro-9af72d559e114a51864d528caabd0bf8` completed on November 4, 2026:
**18 invocations, 18 downstream calls, 57 passing remote assertions**.
The [historical receipts and checks](evidence/same-user.json) are included.

| Case | Observed C behavior |
|---|---|
| Omitted C context: 2 sequential + 6 concurrent calls | 8 distinct hosted sessions and contexts |
| Same explicit C context: sequential + concurrent | Same hosted session; both caller markers in its history |
| Same upstream context copied by A/B to C | A/B had separate sessions, but C reused one session |
| Different C context per branch, repeated | Separate sessions; each retained its own context history |

For the shared case, both callers had user fingerprint
`3fa479bce41fc1b2a75d` and sent:

```text
contextId: repro-9af72d559e114a51864d528caabd0bf8-shared-c
C hosted session: eeac7b653964cc989c6b26e2143e08da4dbec8a18c752e35b6225f3d28c3e95
```

The ledger advanced from sequence 1 through 4. B's sequential request saw A's
earlier marker. A different immediate caller agent was not itself a separate
session boundary in this configuration.

### Different real users via A and B

Both completed successfully using C context `two-real-users-nov9-test01`.
Only selected non-secret receipt fields are retained:
[U1](evidence/real-user-u1.json) and [U2](evidence/real-user-u2.json).
U1 was recorded directly; U2's completed response was supplied by the other tester.

| Field at C | U1 -> A -> C | U2 -> B -> C |
|---|---|---|
| UTC timestamp | 2026-11-09 16:08:50 | 2026-11-10 17:51:03 |
| User fingerprint | `3fa479bce41fc1b2a75d` | `8c98f58254de5d698ab0` |
| Context ID | `two-real-users-nov9-test01` | `two-real-users-nov9-test01` |
| Hosted session ID | `48b40392d95634cce5818562c55536b8596fd2f5f6df2d34bf73de3368c0145` | `f6a0aac7845d438e7db4ad8745900a43892360d6620c1dfb34fbb839e3ed49f` |
| Task ID | `203fe03e-2ec8-4cec-b775-7ad760cfabb4` | `1a038aa4-9078-4ae0-bfca-158514e1b296` |
| Sequence | 1 | 1 |
| Prior session/context messages | Empty | Empty |

Each parent's user fingerprint matched C's fingerprint. The equal context labels
did not merge the two users' C sessions in these observations.
Verify the saved comparison without invoking Azure:

```powershell
& .\src\agent\.venv\Scripts\python.exe .\run_real_user.py compare `
  .\evidence\real-user-u1.json .\evidence\real-user-u2.json
```

### Blocked and invalid attempts are not passes

- A synthetic delegated-user attempt using `x-ms-user-identity` returned **403**:
  "Caller is not authorized to delegate to another user." Normal access returned
  200. No delegation permissions were changed, and that attempt established no
  cross-user routing result.
- U2's first inline-JSON attempt returned HTTP 200 with JSON-RPC error **-32700**.
  Authorization/HTTP success was not a completed B -> C invocation. A corrected
  file-based request produced the completed U2 receipt above.
- Early deployment versions failed because of build/dependency download issues.
  The original cloud evidence used A version 2, B version 3 and C version 2.
  Bundled dependencies avoid the observed remote-restore issue. The portable
  manifest uses generic new names rather than embedding that deployment.

### Conclusion and limits

In the recorded configuration, **same user + same C context reused a C session**;
**different users + the same C context reached different C sessions**.
Use separate downstream context IDs for independent branches of one user's work.
Omit C's context ID for a fresh call; retain a branch's own ID for its follow-ups.

These are observations, not proof that collisions or service bugs are impossible.
The real-user requests were roughly 26 hours apart: they were **not concurrent**.
Repeat-call real-user history isolation, cross-tenant boundaries and LLM
conversation mixing have not been validated. Matching labels alone, HTTP 200
alone or a parent's `X-Agent-Session-Id` alone cannot establish C's behavior.

## Troubleshooting and cleanup

- JSON-RPC errors can arrive with HTTP 200. Require `TASK_STATE_COMPLETED` and
  a diagnostic artifact; the Python client enforces both.
- 403 during A/B -> C: inspect only the new forwarder's runtime role and confirm
  its platform call headers are forwarded.
- Different user fingerprints are a test precondition. Do not treat different
  marker strings as different authenticated users.
- `results/`, local environments, bundles and deployment state are generated
  locally. Do not replace historical evidence or commit credentials.
- Stop local helpers after tests. Delete only the three agents/sessions and
  role assignments you created when finished, using your chosen names.
  Do not run broad infrastructure deletion against a shared existing project.

### CI boundary

The shared cloud harness supports Responses and Invocations, not native A2A.
This sample has an exact-path cloud-deployment exclusion and uses its dedicated
JSON-RPC runners instead; it does not declare a misleading Responses test.
Dependency policy and unit/integration tests remain independently runnable.
