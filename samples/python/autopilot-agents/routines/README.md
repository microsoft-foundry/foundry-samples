# Routines Autopilot

Create a timer or recurring reminder from a personal Microsoft Teams message.
The model interprets the request; the application calls the Routines SDK and
reports what the service actually confirmed.

```text
send "Hello World" in 10 minutes
send "Review triage" every weekday at 9 AM America/New_York
stop routine
status
```

There is **one active routine per authenticated personal chat**. Stop it before
requesting a different one; the sample never silently replaces it. Repeating an
identical request leaves an enabled routine unchanged or re-enables it if disabled.

| Action | Message |
| --- | --- |
| Timer | `send me a message in 100 hours` |
| Calendar date | `send "Renew certificate" in 1 year America/New_York` |
| Unquoted text | `send me Take a break in 10 minutes` |
| Cron | `send "Hydrate" using cron */10 * * * * in UTC` |
| Stop | `stop routine`, `cancel my routine`, or `delete my routine` |
| Stored schedule | `status` (trimmed, case-insensitive; no model call) |

Quotes and reminder text are optional. The model copies supplied text or chooses
a short message when none was given. Delivery sends the stored text without
another model call.

Stop/cancel/delete mean **disable**, not hard deletion. A delivery already
running may finish. `status` reports the stored message and UTC timer instant
or raw cron and timezone. Recurring confirmations instead use a short
model-written description followed by the stored timezone.

Timers whose due time has passed are excluded from active status and stop
discovery, even if their stored definition is enabled. This does not prove
delivery completed. Stop before the deadline; disabling cannot recall a
delivery already in flight.

`UTC` and `Etc/UTC` use the same `UTC` name for new schedules and displayed
timezone metadata. An identical existing reminder is reused with its original
name and stored values, including older `Etc/UTC` records; no records are
rewritten. An active match takes priority; if both aliases are disabled, the
existing `UTC` record is preferred. Two active records still require resolving
the conflict. Other timezones and literal reminder text are unchanged.

Each message is a fresh request, with no pending confirmation or queued action.
Within one process, authenticated requests for the same chat wait for the prior
request's interpretation, operation and reply. Other chats remain independent;
this is not timestamp ordering or coordination across hosted replicas.
If details are missing, resend the complete request rather than just `yes`,
`tomorrow`, or `every 10 minutes`:

| Clarification needed | Complete new request |
| --- | --- |
| Exact seven-minute spacing is unsupported | `send me a message every 10 minutes` (if that alternative is wanted) |
| Today's requested lunch time has passed | `remind me to eat lunch tomorrow at 1pm` (if tomorrow is intended) |
| Stop and start requested together | Send one complete request at a time, such as `stop routine`; no next action is queued |

## Model decision to SDK call

The four strict results live beside their dispatch in [agent/app.py](agent/app.py):

| Result | Model-owned values | Application operation |
| --- | --- | --- |
| `one_shot` | Absolute aware UTC `at`, `message` | Timer trigger, guarded `create_or_update(name, body)` |
| `schedule` | Five-field `cron`, IANA `time_zone`, `message`, display-only `summary` | Schedule trigger, guarded `create_or_update(name, body)` |
| `stop` | None | Find the current chat's owned routine, then `disable(name)` |
| `else` | `answer` | Ordinary reply or clarification; no routine lookup or mutation |

The model receives the message, authenticated Activity timestamp and available
timezone. It performs duration and calendar arithmetic and returns one strict
result in `{"result": ...}`. Python does not parse the English request again,
repair the model's timing, or retry with another model.

`schedule.summary` describes the actual cron, but is used only for the reply
after SDK success and exact readback. It does not affect the stored schedule,
ownership or delivery payload. Python does not verify its meaning against cron;
use `status` to inspect the stored values.

The outbound credential and client flow is:

```python
async with DefaultAzureCredential() as credential:
    async with AIProjectClient(endpoint=project_endpoint, credential=credential) as project:
        async with project.get_openai_client(max_retries=0) as model:
            response = await model.responses.parse(...)
        await project.beta.routines.create_or_update(name, body, retry_total=0)
        await project.beta.routines.disable(name, retry_total=0)
```

The last two calls are **alternative paths**, not a sequence.
[agent/routines.py](agent/routines.py) builds the `delivery` timer or schedule
trigger and `invoke_agent_activityprotocol_api` action for the authenticated
chat. Creation, re-enable and disable require exact readback before reporting
success. Timer storage uses whole-second Unix timestamps: the application drops
subseconds before naming and creating the routine, then reports that stored instant.

`DefaultAzureCredential` supplies the outbound Foundry credential. Depending on
configuration, this may be a service principal, workload credential, managed
identity or developer credential; the source does not establish the runtime
principal. The Activity adapter's identity-proxy configuration authenticates
messages and supports channel transport. It is separate from the Foundry
credential. App/user identifiers in the action are delivery routing, not
credentials. No bearer token is manually passed or printed.

## Limits and safety

This sample uses the preview
[Routines API](https://learn.microsoft.com/python/api/azure-ai-projects/azure.ai.projects.aio.operations.routinesoperations?view=azure-python-preview).
It is not a general calendar assistant or a production scheduling service.
Verify interpretation and delivery in your intended Teams environment before
relying on it; a scheduling reply or status lookup is not delivery proof.

Only the current authenticated personal chat can create or stop a routine.
The model cannot choose credentials, tenant, sender, conversation, service URL
or resource name. Group and tagged-channel messages receive guidance without
reading or changing routines.

Native checks require an aware UTC timer, nonblank text, a named timezone and
five cron fields. Past timers are rejected, not moved forward. Valid structured
output can still contain wrong arithmetic, weekdays, text or timezone choices;
inspect the returned UTC instant or stored cron/zone.

Recurring schedules have a documented default five-minute minimum; this does
not impose a minimum lead time on one-shot timers. Cron describes clock marks,
not every elapsed interval: exact seven- or ninety-minute spacing is unsupported.
Raw `*/7 * * * *` has a shorter gap at the hour boundary. Service-side constraints
still apply, and a rejected or unconfirmed operation is never reported as success.
Suggested alternatives are optional new requests, not automatic replacements.

The `message-schedule-v2` name, ownership description, `delivery` trigger,
payload and destination must match before an existing routine is reused or
changed. Foreign, malformed or conflicting state is not overwritten. Uncertain
write outcomes, including unavailable responses, are read back by exact name.
SDK retries are disabled for create, re-enable and disable; reads keep their
default retry policy. A routine may exist or fire after an unconfirmed write;
use `status` before retrying. A model failure does not execute a stop request.

Sender, recipient and conversation display names are metadata, not identity.
Renaming or omitting these labels does not replace or rewrite a routine.
Routing identifiers, destinations and delivery values must still match.

Delivery validates the authenticated routing and
`application/vnd.microsoft.routines.messageDelivery.v1` event. Plain text is
HTML-escaped for transport, so generated text is not executable markup.
There is no sample-specific message byte cap or control-character filter;
service and client limits still apply. Verify multiline and Unicode rendering
in the intended Teams client.

Older routine formats are unsupported. Administer them with their original
version before upgrading; this sample does not migrate or clean up stored records.

## Set up the sample

Clone the public samples repository, then open this sample directory:

```powershell
git clone https://github.com/microsoft-foundry/foundry-samples.git
cd foundry-samples\samples\python\autopilot-agents\routines
```

> [!NOTE]
> Keep the sample's `scripts` and `infra` directories when copying it.
> The provisioning wrapper calls [scripts/prepare-resources.ps1](scripts/prepare-resources.ps1),
> which checks the selected subscription's tenant and requires an OpenAI model
> deployment. Other Autopilot samples use the shared provisioning helper.

### Prerequisites

Install [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
1.32.0 or later, [Azure CLI (`az`)](https://learn.microsoft.com/cli/azure/install-azure-cli)
2.80 or later, [PowerShell 7](https://learn.microsoft.com/powershell/scripting/install/installing-powershell)
or later, and Python 3.11 or later for local use. The hosted runtime is Python
3.13, deployed directly through `main.py` with Activity Protocol 2.0.0.

Install or update the Foundry agent extension:

```powershell
azd ext install azure.ai.agents
# If already installed:
azd ext upgrade azure.ai.agents
```

The extension must be 1.0.0-beta.16 or later. Cloud setup also requires an Azure
subscription, a supported hosted-agent region, model quota, and access to the
selected Foundry resources. Choose an OpenAI model deployment that supports
the Responses API and structured outputs.

Microsoft 365 and Agent 365 licensing, an AI Administrator or Global
Administrator to approve and activate the blueprint, and tenant app policies
allowing intended users to create an instance are separate requirements.
Signing in or provisioning Azure resources does not grant these permissions.
New resources, hosting, and model requests can incur charges. Review the
target subscription, resource names, permissions, and cost before proceeding.

### Select an environment

Run cloud commands from this sample directory in PowerShell 7. Authenticate
both CLIs to the intended tenant; their sign-in state is separate:

```powershell
az login --tenant <tenant-id>
azd auth login --tenant-id <tenant-id>
azd env new my-routines-autopilot
```

To select an existing environment instead:

```powershell
azd env list
azd env select <environment>
```

### Create or reuse Azure resources

```powershell
azd provision
```

The preprovision hook already supports both new and existing resources. Enter
an existing name to reuse it or a new name to create it. Selection is scoped
to the chosen subscription and parent resources, not to a built-in tenant.

| Resource | Saved name | Selection mode |
| --- | --- | --- |
| Resource group | `AZURE_RESOURCE_GROUP` | `RESOURCE_GROUP_MODE` |
| Foundry resource | `AZURE_AI_ACCOUNT_NAME` | `FOUNDRY_RESOURCE_MODE` |
| Foundry project | `AZURE_AI_PROJECT_NAME` | `FOUNDRY_PROJECT_MODE` |
| Model deployment | `AZURE_AI_MODEL_DEPLOYMENT_NAME` | `MODEL_DEPLOYMENT_MODE` |

Modes are `new` or `reuse`. An existing name is reused; a previously selected
reuse target that is missing fails rather than silently creating a replacement.
For unattended use, configure the selected environment's required names,
`AZURE_SUBSCRIPTION_ID`, `AZURE_TENANT_ID`, and, for new resources,
`AZURE_LOCATION` and `MODEL_NAME` before invoking provisioning. Missing values
that require a prompt fail in noninteractive mode.

The hook checks the subscription tenant against `AZURE_TENANT_ID`, requires a
project-capable Foundry resource, and uses an existing resource's actual region.
It preserves a reused deployment's model, version, SKU, and capacity. For a new
deployment it selects the catalog's single default OpenAI model version that
supports `GlobalStandard`, with capacity 1. Capacity 1 is not a spending cap or
a guarantee of quota, availability, or Responses API compatibility.

The hook saves the `*_EXISTS` flags consumed by `infra/main.parameters.json`;
Bicep creates only resources marked new. It does not grant RBAC, consent,
licensing, publication approval, or access to the model. Reused resources
remain shared: do not tear them down as sample cleanup.

### Deploy, publish, and create an instance

```powershell
azd deploy
azd ai agent show
```

Deployment packages the Python runtime and creates a hosted-agent version. It
does not publish a Microsoft 365 app, create a Teams instance, or schedule a
routine. The sample keeps the 0.5 CPU / 1 GiB hosted resource settings in
[azure.yaml](azure.yaml).

Review `services.routines-autopilot.activity.publish` in `azure.yaml`, including
the display name, descriptions, developer information, privacy statement,
terms, and app version. Use publication metadata appropriate to your own app.
Publication is a separate tenant action:

```powershell
azd ai agent publish
```

Have a licensed AI Administrator or Global Administrator open
[Agents in the Microsoft 365 admin center](https://admin.cloud.microsoft/?#/agents/all/requested),
review and approve the blueprint, activate the narrowest appropriate audience,
and confirm it appears in the Agent 365 registry.

In Teams, sign in with a licensed account in the same tenant. Open **Apps** >
**Agents for your team**, select the approved blueprint matching
`activity.publish.agentDisplayName`, and create an instance using the tenant's
prompts. Approval, activation, consent, and instance creation are not implied
by successful deployment or publication.

## Runtime configuration and updates

`ActivityAgentServerHost(digital_worker=True)` builds the M365 application,
adapter and blueprint identity configuration. The sample registers its Teams
and routine-delivery handlers on `host.agent_app`; the host serves
`POST /activity/messages` and `GET /readiness`, runs the web server and manages
shutdown. Hosted storage is supplied by Foundry; local runs use memory.
Requests remain stateless and routine records stay in the Routines service.

The host initializes logging and OpenTelemetry. There is no separate sample
telemetry bootstrap, middleware compatibility adapter or traceback filter.

| Setting | Meaning |
| --- | --- |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Required deployment selected during provisioning; used for four-outcome model responses. |
| `FOUNDRY_AGENT365_TRACING_ENABLED` | `"true"` enables the host's built-in Agent 365 tracing in Foundry. |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | `"false"` keeps model-content capture disabled. |

Edit the service's `env` mapping in `azure.yaml` for hosted settings.
The host uses Foundry's Application Insights configuration when available.
Telemetry resource names and instrumentation defaults now come from the SDK;
they are not an exact reproduction of the previous sample telemetry stream.
Only the unused OpenAI Agents SDK instrumentation is explicitly disabled.
Application errors log their operation, exception type and available HTTP status,
not message text, exception bodies or credentials. The application error handler
keeps a generic failure notice; HTTP delivery errors do not trigger another reply.
The native Agents SDK can record unhandled exception messages and stack traces
in telemetry before that handler runs. The content-capture setting does not
redact exceptions or provide blanket SDK-log protection. Use synthetic messages
and follow your tenant's data-handling policy.

The template's project/service/agent identifier is `routines-autopilot`, with
display name **Routines Autopilot**. These defaults are for new configurations,
not an automatic rename or migration of an existing deployment. Before applying
this template to an existing environment, explicitly map its original service
key, hosted agent name, `AZURE_AI_AGENT_NAME` output, runtime
`FOUNDRY_AGENT_NAME`, and publication identity. Agent identity participates in
routine ownership; changing it can make existing routines undiscoverable.
Keep existing identity values unless a separate migration has been reviewed.

For an intentionally selected environment, code updates use `azd deploy`.
Existing hosted sessions can remain pinned to an older version; inspect
`azd ai agent sessions list` and stop only approved stale session IDs with
`azd ai agent sessions stop <session-id> --no-prompt`. Stopping preserves logical
session state. Republish only when publication metadata or the app manifest
changes. Do not stop unrelated sessions or tear down shared environments.

## Troubleshooting and verification

| Symptom | Check |
| --- | --- |
| Provisioning cannot find a selected resource | Confirm environment, subscription, tenant, parent resource, mode, and name; do not silently substitute a new target. |
| Provisioning or model access is denied | Check existing Azure access and the selected model's compatibility/quota. This sample does not grant permissions. |
| Blueprint or instance is unavailable | Check Microsoft 365 approval, activation audience, licensing, tenant app policies, and consent separately from Azure deployment. |
| Old behavior after deployment | Verify the concrete hosted version serving the intended session; deployment alone does not update every session. |
| Clarification asks for missing details | Resend the complete request with timing and a named zone where required. |
| A different routine is already active | Send `stop routine`, confirm the actual outcome, then request the new routine. |
| Schedule rejected | Inspect the supplied UTC instant or cron/zone and service constraints. No fallback silently changes timing. |
| Outcome is uncertain | Use `status` before retrying; no second mutation was automatically submitted. |
| Acknowledged but not delivered | Compare the stored UTC target/cron/zone and actual delivery timestamp, allowing for service delay. |

Before customer use, verify model interpretation and actual timer/recurring
delivery and stop in Teams. Check the message, destination, timing, ownership
and concrete hosted version. Offline checks and status replies do not prove
end-to-end delivery or customer setup readiness.
