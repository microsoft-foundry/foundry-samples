# Activity sample tests

Run from the repository root:

```powershell
dotnet test .\samples\csharp\hosted-agents\bring-your-own\activity\tests\ActivitySamples.Tests.csproj
```

[offline.runsettings](offline.runsettings) excludes the `Live` category by
default. Offline tests reference the actual sample projects, not copied handlers.
They cover native TestAdapter replies, welcome/card actions, non-streaming
fallback, user-facing errors, persistence/isolation, file URL/path/size checks,
mocked download/consent upload, and readiness/202/session headers.
Card validation tests verify that empty or missing titles return an actionable
BadRequest without changing tasks or triggering the generic error reply.
Streaming tests verify that only root-agent text deltas are forwarded; subagent
and empty deltas do not suppress the final-response fallback.
The Echo HTTP round-trip test starts real Kestrel hosts for the agent and a
local connector, posts multiple messages to `/activity/messages`, and asserts
the outbound replies received by the connector.
The model is replaced only in the offline Copilot handler tests.

## Opt-in live model test

Sign in with `az login` and use an existing Foundry project/model:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT = "https://<account>.services.ai.azure.com/api/projects/<project>"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME = "gpt-5-mini"
dotnet test .\samples\csharp\hosted-agents\bring-your-own\activity\tests\ActivitySamples.Tests.csproj --settings .\samples\csharp\hosted-agents\bring-your-own\activity\tests\live.runsettings
```

These tests start the bundled Copilot runtime and use Azure credentials to
invoke the model. They check add/list/complete tools, conversation resume,
shared-text-file reading, and generation of a downloadable text file.
The live HTTP test additionally sends Activity messages through Kestrel and
the M365 adapter, and verifies actual outbound connector replies and task state
across turns. Use the live settings file: `--filter` alone is combined with
the default offline exclusion and does not execute live tests.
It incurs model inference charges. Configuration is required; the test fails
explicitly rather than silently skipping when it is missing.

## What these tests do not prove

Neither TestAdapter nor a live model call proves deployed Bot authentication,
actual Teams streaming/card rendering, or File Consent round trips. Validate
those with the deployed agent in Teams.

The shared repository cloud runner currently supports Responses/Invocations,
not Activity's asynchronous channel delivery. Both samples have behavior
contracts in `.azure-pipelines/hosted-agent-tests/csharp/bring-your-own/activity/`
but are explicitly excluded from that runner, just like their Python counterparts.
Schema validation is supported; an Activity execution plan is not. Do not pass
`--protocol responses` to make an Activity plan appear valid.

Validate the contracts from the repository root:

```powershell
python .\.github\scripts\hosted_agent_test_spec.py validate --spec .\.azure-pipelines\hosted-agent-tests\csharp\bring-your-own\activity\echo\test-spec.yml
python .\.github\scripts\hosted_agent_test_spec.py validate --spec .\.azure-pipelines\hosted-agent-tests\csharp\bring-your-own\activity\github-copilot\test-spec.yml
```

## Linux publish

```powershell
dotnet publish .\samples\csharp\hosted-agents\bring-your-own\activity\echo\src\echo-dotnet-activity\echo.csproj -c Release -r linux-x64 --self-contained false -p:PublishReadyToRun=true
dotnet publish .\samples\csharp\hosted-agents\bring-your-own\activity\github-copilot\src\github-copilot-dotnet-activity\github-copilot.csproj -c Release -r linux-x64 --self-contained false -p:PublishReadyToRun=true
```

On Windows, use a short checkout or add `--artifacts-path C:\build\activity`
if the Copilot CLI archive extraction exceeds Windows path limits.
