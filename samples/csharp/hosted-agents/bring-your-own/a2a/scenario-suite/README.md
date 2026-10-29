# Twelve repeatable .NET A2A scenarios

Deploy twelve separate agents once, then rerun all their checks without editing
source or deploying again. No model deployment is required.

## What this demonstrates

| Scenario | SDK sample | Fixed agent name | Checks |
|---|---|---|---|
| 1 | 1. Getting started | `a2a-dotnet-s01-echo` | Exact message-only Echo; no Task |
| 2 | 2. Tasks and artifacts | `a2a-dotnet-s02-tasks` | Completed artifact and matching `GetTask` |
| 3 | Transport regression | `a2a-dotnet-s03-streaming` | Four paced SSE chunks, IDs, append/final flags, completion and stored artifact |
| 4 | 3. Multi-turn | `a2a-dotnet-s04-multiturn` | Exact input-required prompt; continuation; separate Task in the same context |
| 5 | 4. Long-running tasks | `a2a-dotnet-s05-longrunning` | `returnImmediately` returns unfinished; polling retrieves exact completed report |
| 6 | 5. Customize the build | `a2a-dotnet-s06-custombuild` | Injected Welcome prefix, explicit store, `AutoAppendHistory = false` |
| 7 | 6. Existing handler | `a2a-dotnet-s07-handler` | Separately constructed native handler and owned store; completed Task and retrieval |
| 8 | 7. Native hosting | `a2a-dotnet-s08-native` | Existing native `AddA2AAgent` registrations plus parameterless `AddFoundryA2A` |
| 9 | 8. Tier 1 | `a2a-dotnet-s09-tier1` | `Run` configuration callback; Configured prefix; healthy application check; 15-second shutdown setting |
| 10 | 9. Tier 2 | `a2a-dotnet-s10-tier2` | Builder composition; Composed A2A reply and independent Invocations reply |
| 11 | 10. Tier 3 | `a2a-dotnet-s11-tier3` | Raw ASP.NET host; A2A plus own `/` and readiness routes |
| 12 | 11. Persistence | `a2a-dotnet-s12-persistence` | Write in session A; retrieve and list the same Task in hosted session B |

SDK sample numbers run from 1 through 11. Scenario IDs remain fixed so existing
deployments, pinned versions, and test commands continue to address the same agents.

## How it works

All agents share one application binary, but each has a different **fixed
deployment configuration** in [azure.yaml](./azure.yaml). Requests cannot select
or switch the scenario. Hosting scenarios use their respective SDK startup APIs,
not twelve differently named copies of Echo.

[Generate-SampleCode.ps1](./scripts/Generate-SampleCode.ps1) extracts the actual
compiled handler/configuration regions from the SDK sample sources during the
build. Test framework code is not included in the deployed application. The
SDK projects are source references; there is no unpublished NuGet package
dependency.

The host verifies its registration contract at startup and emits the deliberate
`A2A_SUITE_CONFIG_VERIFIED` event. Hosted tests verify this event against the SDK
source fingerprint as well as checking protocol responses. The runner verifies
that each created session is active and bound to the exact saved agent version.

The public gateway routes declared protocols, not arbitrary application routes.
Scenario 11's own `/` route and readiness endpoint are asserted locally; cloud
checks cover its A2A endpoint and startup. Tracing exporter delivery, graceful
shutdown timing, subscription, and cancellation are not claimed by this suite.

## Prerequisites

- .NET 10 SDK and PowerShell 7 (`pwsh`).
- This sample checkout and the SDK checkout containing the eleven A2A samples
  and the transport test helper.
- Azure Developer CLI with the agents extension versions listed in
  [azure.yaml](./azure.yaml).
- An existing Foundry project with hosted agents enabled and permissions to
  deploy agents, create sessions, and access their logs.
- Existing `azd` authentication. Scripts do not sign in or change global defaults.
- For scenario 12, the hosted identity must be permitted to use Foundry state
  storage. An authorization failure fails the scenario; it never falls back to
  in-memory storage.

## Local checks

From this directory:

```powershell
.\scripts\Test-Suite.ps1 -Local -SdkRoot C:\a2a\azure-sdk-for-net
```

Run test commands from this source directory, not the external azd deployment
copy. The shared client validator is linked from the neighboring Echo sample.

Each scenario gets its own process and port (18501-18512). Processes run
sequentially and are stopped by PID after their checks. Persistence is tested by
reconstructing the local process with the same file-backed state directory.
Local persistence is not a substitute for the hosted cross-session check.

## Deploy all twelve

Choose an external deployment directory and use your existing project ARM ID:

```powershell
.\scripts\Deploy-Suite.ps1 `
    -SdkRoot C:\a2a\azure-sdk-for-net `
    -ProjectResourceId "/subscriptions/<subscription>/resourceGroups/<group>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>" `
    -DeploymentDirectory C:\a2a\deployments\a2a-suite `
    -EnvironmentName dotnet-a2a-suite-dev
```

This adopts the manifest into the external directory, publishes the source-built
application, and deploys each agent independently. It uses the existing project;
it does not provision a model or overwrite the separate Echo sample.

Successful agent versions, SDK fingerprint, and the azd environment binding are
saved to `.runs\deployment.json`. Keep this file and the deployment directory.
Later explicit deployments synchronize the suite sources into that copy and
update the pinned versions. Use `-Scenarios 12` to deliberately redeploy just one
agent; other pinned versions and their individual SDK fingerprints are preserved.
A partial deployment exits unsuccessfully and records failures and the versions
that succeeded; do not treat it as a complete suite.

## Rerun tests only

```powershell
# All twelve, using exactly the saved versions. No deployment occurs.
.\scripts\Test-Suite.ps1 -Deployments .\.runs\deployment.json

# Only selected scenarios.
.\scripts\Test-Suite.ps1 -Deployments .\.runs\deployment.json -Scenarios 3,4,12
```

Every run uses fresh session and message IDs. Scenario 12 creates two different
hosted sessions for the same agent/version and uses the same authenticated
caller. Snapshots are retained for one hour.

Sessions are deliberately **retained**, allowing later inspection. Repeated runs
consume hosted resources; delete specific sessions with `azd ai agent sessions
delete` when you no longer need them.

Each run saves:

- `summary.json`: PASS/FAIL, pinned version, session, trace ID and assertions.
- Per-scenario `wire.json`: exact requests, responses, SSE events and timing.
- Session creation responses and hosted logs, including logs on failed checks.
- Local host logs and file-backed state when running locally.

The runner collects failures across the suite and exits nonzero if any scenario
fails. It does not silently retry protocol failures or substitute another store.
No authorization headers or credentials are recorded. Trace IDs support later
correlation; their presence does not prove exported telemetry delivery.
The suite intentionally does not create synthetic model evaluation jobs.

## Troubleshooting

- **Missing snippets:** point `SdkRoot` at the SDK checkout containing the eleven
  compiled samples and transport test helper; generation fails explicitly for missing regions.
- **Storage authorization or unavailable credential:** inspect scenario 12's
  original host exception. Fix the hosted identity/storage configuration before
  rerunning; do not enable developer credentials as a production workaround.
- **SSE buffering:** four exact chunks must span at least 450 ms from the first
  artifact arrival to the last. A single buffered batch fails.
- **Shared cloud CI:** the owner contract is schema-valid, but the repository's
  shared planner currently accepts only Responses and Invocations. Native A2A
  uses this dedicated runner; it is not mislabelled as another protocol or
  bypassed through a skiplist.

For manual A2A interaction, use the public protocol endpoint and the session
header. The generic `azd ai agent invoke`/Agent Inspector path is not a replacement
for this native A2A validation.
