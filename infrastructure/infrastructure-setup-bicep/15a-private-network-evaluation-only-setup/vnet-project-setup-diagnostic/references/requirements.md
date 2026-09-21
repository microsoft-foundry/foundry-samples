# Requirement catalog and certainty boundaries

Contents: [Check families](#requirement-catalog-and-certainty-boundaries) |
[Authentication and transport](#authentication-and-transport) |
[Public references and assessment rules](#public-references-and-assessment-rules) |
[Evidence rules](#evidence-rules).

This document describes this tool's checks, not a complete specification of
Foundry service internals. Paths refer only to files in this diagnostic bundle.
API versions are explicit in `scripts\ArmReader.ps1`; unsupported versions are
Unknown, not a reason to use another identity or a mutating API.

## Authentication and transport

Both providers use the same ARM allowlist, paging guards, checks, and report
objects. `AzureCli` retains existing invocation behavior; `AzurePowerShell` requires
installed Az.Accounts 5.3.3+ and a pre-authenticated AzureCloud context for the
selected subscription. The 5.3.3 command/type surface is locally inspected and is
the enforced prerequisite, not a verified earliest compatible release; older
versions are not qualified. [Get-AzAccessToken](https://learn.microsoft.com/en-us/powershell/module/az.accounts/get-azaccesstoken)
documents `ResourceUrl`, `TenantId`, `DefaultProfile`, and SecureString token output.
The captured in-memory context container is passed explicitly; the diagnostic never
signs in, changes subscription/identity or invokes a fallback provider.

The AzurePowerShell HTTP handler disables redirects/cookies/default credentials,
uses the fixed public ARM token audience, bounds token acquisition and GET time,
and discards non-200 bodies. 401/403 remain distinct from 404; only 429/503/504 are
retried, at most three attempts. Tokens stay in memory, not arguments, environment
variables, files or output. A token-acquisition timeout does not launch repeated
auth attempts or use a late result.

`scripts\MetadataProjection.ps1` applies an allowlisted projection before either
provider response enters the shared cache. It preserves permission blocks and safe
identity/network/monitoring fields while excluding secret-bearing fields. Native
projection is compared offline with CLI JMESPath plus the same final metadata
boundary. Fixtures use neither provider. No live authentication, customer evaluation
or effective authorization is exercised by the offline tests.

| Check family | Selected by / principal | Metadata and interpretation |
| --- | --- | --- |
| `resource.*`, `identity.*` | Core / account and project separately | Cognitive Services account/project GET, 2025-06-01. Provisioning failure is distinct from transient state. Project does not need its own network injection. |
| `network.injection`, `network.subnet`, `network.delegation` | Core / account-owned agent subnet | Network GET, 2024-05-01. `Microsoft.App/environments` delegation; legitimate SAL is an observation, not a conflict. |
| `caphost.*` | Core / account and project separately | Child list, 2025-04-01-preview. ARM visibility/state only; empty lists remain Unknown for topology compatibility. A Succeeded resource does not certify service execution or network reachability. |
| `storage.*`, `connection.*` | Core / project MI | Project and shared account connection metadata, target ResourceId, storage GET 2023-05-01. No name invention, keys, SAS, blob operations, or mandatory Data Owner role. |
| `rbac.assets.*` | Core / project MI and explicitly supplied evaluation caller | Compare visible grants with the catalog's asset read/write **dataActions**, separately from Blob access. Omitted optional caller is NotAssessed coverage; explicitly selected unreadable grants stay required Unknown. This tool selects the project MI for Scheduled/Continuous profiles, not the operator. |
| `rbac.blob.*` | Core / project MI | Actual storage scope, read/write Blob dataActions. Role names/IDs are hints; evaluate every live permission block and subtract exclusions within each block. |
| `model.*` | Models/Graders / connection-selected authentication | Deployment list and model metadata. API-key path checks disableLocalAuth but never tests keys. Entra path uses supplied caller or scheduled/continuous project MI. Ambiguous deployment selection is Unknown. |
| `monitoring.*`, `rbac.trace.*` | Traces / project MI selected by this tool | Resolve the Insights component and backing workspace. Assess resource-context and workspace-permission alternatives under the workspace access-control mode, not mandatory grants at both scopes. No query is executed. Optional on Core; privileged permission and private query-path coverage remain separate. |
| `agent.*` | Agent / discovered references | Search/Cosmos metadata only if discovered; unimplemented authorization/topology is NotAssessed coverage, not a health finding. Actual required dependency-read gaps stay Unknown. Not mandatory for Core/template15a. |
| `pe.*`, `dns.*`, `network.attachments` | Core + selected dependencies | Resource PECs, PE subresources, NIC IPs, zone groups, A records, links. DNS 2020-06-01; NSG/UDR/custom DNS observations are not full NVA simulation. |
| `endpoint.*` | ConfigurationAndNetwork / diagnostic host | Discovered HTTPS endpoint FQDNs only, DNS/CNAME, expected IPs, TCP443, TLS hostname/certificate validation, target-only hosts overrides. Shared regional endpoints do not prove private-path health. |

## Public references and assessment rules

- [Template 15a: evaluation-only setup with network isolation](https://github.com/microsoft-foundry/foundry-samples/tree/1dea30fe7da7aeace17a4dd35c6f2499f6cf423c/infrastructure/infrastructure-setup-bicep/15a-private-network-evaluation-only-setup)
  documents the sample's account, project, storage, private networking, monitoring,
  and optional capability-host resources. It does not require Cosmos DB or
  Azure AI Search for its evaluation-only setup. Template revisions and parameter
  choices differ; inspect deployed metadata instead of assuming all components
  are present. This tool never deploys or modifies the template.
- [Azure role definitions](https://learn.microsoft.com/en-us/azure/role-based-access-control/role-definitions)
  describes Actions, DataActions, exclusions, and role scopes. Inspect complete
  live definitions and assignments rather than requiring a particular role name.
  A sample's role choices do not make every listed role a universal prerequisite.
- [Private endpoint DNS configuration](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns)
  describes private DNS zones, endpoint NIC information, and name resolution.
  The tool compares discovered endpoint, NIC, zone, record, and VNet-link metadata;
  it does not infer effective routing from resource existence.
- [Azure Monitor access control](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/manage-access)
  describes resource-context and workspace-context access. The tool uses this
  model to assess configured grants for the project MI discovered in ARM. This is
  the tool's selected assessment principal, not proof of which identity every
  service operation uses.
- [Application Insights telemetry data model](https://learn.microsoft.com/en-us/azure/azure-monitor/app/data-model-complete)
  describes the telemetry tables used by the trace permission checks. The tool
  inspects configuration only; it does not read those tables.

Connection discovery accepts the supported category and target metadata shapes,
including `AppInsights` and `ApplicationInsights`. A connection alias, AppId,
component resource ID, and workspace resource ID are different identifiers.
Connection strings and secret values are excluded from collected metadata.

The role action strings in `requirements.json` are **assessment targets**, never
operations the transport may execute. Definitions are read live; neither Azure AI
Developer nor any other friendly name can alone pass a check. Matching the
catalog does not certify every dataset, grader, or service API permission.

For trace grants, the tool considers resource-context access to the component,
not just the location of the backing workspace. Azure Monitor access control
documents resource-scope `Microsoft.Insights/logs/<table>/read` management actions
and workspace-scope `Microsoft.OperationalInsights/workspaces/query/read` plus
table reads. Read `features.enableLogAccessUsingOnlyResourcePermissions` from the
existing workspace GET: true permits component-scoped resource-context grants;
false requires workspace permissions. Missing policy is not silently assumed true.
A sufficient workspace-permission alternative can also satisfy the configured
grant check, but cannot override a relevant/unknown deny at the queried component.
Individual candidates are optional; the required summary identifies the query
resource, policy, selected grant scope and principal. It does not require both grants.
When resource permissions are explicitly enabled and the component grant passes
without deny uncertainty, skip workspace RBAC reads entirely. Record the unused
alternative as Inventory/NotApplicable/Info, not Passed or incomplete coverage.
If that path is insufficient or access policy is false/unknown, assess the workspace
alternative normally and retain relevant read errors and deny uncertainty.

The catalog includes `AppRequests`, `AppDependencies`, and `AppTraces` from the
Application Insights data model. It evaluates concrete management actions so
exclusions are not lost behind a wildcard assessment target. Report fields such
as `queryApi` and `queryResourceId` describe the assessed access model; they do
not indicate that a query was executed. Table existence, protected-table policies, and
resource-ID data attribution remain untested; candidate gaps are Unknown rather
than a reason to demand broad workspace grants. Privileged content remains a
separate, explicitly incomplete configuration assessment.

For Models/Graders, a selected connection lacking ResourceId can associate with
exactly one already-read Cognitive Services account when its canonical target
hostname equals that account's endpoint metadata. Report the association source
and preserve the selected connection's authentication. Do not synthesize ARM IDs,
use private-link aliases for this association, fetch unrelated accounts, substitute
an AAD connection for an API-key connection, or default foreign/ambiguous targets
to the project's parent account. Explicit IDs remain authoritative.

## Evidence rules

Schema 2 separates `Finding`, `Inventory`, and `Coverage`. Exit aggregation uses
required implemented findings only; actual access-denied, timeout, missing required
metadata or unresolved path evidence stays Unknown/Failed as appropriate. Inventory
success is `Observed`, not a health probe, and repeated inventory observations are
deduplicated by check ID/resource/principal. Unimplemented/unselected coverage is
`NotAssessed`/Info and appears prominently in a separate summary, never Passed.
Default Core does not require the optional evaluation caller. Basic network mode
retains DNS/mapping/TCP/TLS; DNS-only and route details require AdvancedNetworkDetails.
Unsupported optional commands and unavailable host-context collection are
informational coverage, not warnings about the project. Supported optional probes
which fail remain explicit Unknown evidence.

403, unsupported API, timeout, missing permission, malformed paging, and omitted
fields are Unknown. A 404 on a validated explicit dependency ID is a missing
resource; a 404 on an optional collection may indicate unsupported topology.
Visible unconditional direct/inherited grants can pass a **configured grant**
check, not effective access. Missing grants stay Unknown when group/PIM/management
group inheritance could supply them. Conditional/unreadable allow assignments
prevent certainty only when unconditional coverage is insufficient; an extra
conditional allow cannot revoke an unconditional grant. Denies are filtered by
scope inheritance, child-scope applicability, explicit principal inclusion/
exclusion, and the selected actions versus dataActions channel (including all
permission blocks and exclusions). Subscription list results can include unrelated
descendant scopes. Reports include ignored deny IDs/scopes/reasons and safe relevant
deny metadata. Unreadable scopes, ambiguous group membership/inheritance, or a
potentially matching deny remain Unknown; the deny-condition engine is not emulated.
Assignment timestamps are recorded; no fixed propagation interval is promised.

Custom/central DNS without a zone group is Unknown, not absent DNS. Readable
missing/null/empty VNet DNS-server collections mean Azure-provided DNS, not custom
DNS; unreadable metadata is never assumed to be Azure DNS. Missing/null/empty
record IP arrays use exact PE FQDN-to-NIC evidence, or the sole address of a
single-address PE; multi-host NIC addresses are never indiscriminately copied.
Insufficient mapping is Unknown. Additional addresses can belong to another
approved PE and remain Unknown without complete mapping evidence, not Failed.
A linked zone missing a demonstrably expected PE address is a mismatch;
missing link alone can be legitimate centralized DNS. Disabled public access is
normal. Local TCP/TLS failures are Unknown required host evidence, not proven
Azure defects. Backend execution, service-managed resources, and effective
service-side network paths are outside this assessment.

Monitoring GET 2020-02-02 exposes `properties.PrivateLinkScopedResources` with
`ResourceId`/`ScopeId` on Application Insights; normalize those fields and the
lowercase form to safe metadata only. Missing associations produce empty arrays,
not `[null]`. `monitoring.component` and `.workspace` are discovery checks only.
`monitoring.queryPathCoverage` is NotAssessed coverage for the unimplemented path,
not a required health Unknown. Unavailable actual query-policy evidence produces
the separate required `monitoring.queryPolicy` Unknown. AMPLS/DCE/DCR traversal
and private monitoring DNS/reachability are outside this version. Public-enabled
metadata does not certify runtime reachability either. Ingestion policy is recorded
but ingestion authorization is not part of this trace-read assessment.

Private-link aliases are DNS evidence, not separate TLS endpoints. The supported
zone mappings correspond to the public private-endpoint DNS guidance:
`privatelink.services.ai.azure.com` -> `services.ai.azure.com`,
`privatelink.openai.azure.com` -> `openai.azure.com`,
`privatelink.cognitiveservices.azure.com` -> `cognitiveservices.azure.com`, and
`privatelink.blob.core.windows.net` -> `blob.core.windows.net`.
Bind a single-label alias and its verified PE NIC IPs only to an independently
discovered canonical service host of the same ARM resource and matching PE
subresource. Preserve alias/source metadata separately. Use the canonical hostname
for TCP/TLS/SNI; never strip arbitrary `privatelink` labels from custom hosts.

Offline fixtures describe evaluation topologies with monitoring, with private
monitoring, and with custom DNS but no monitoring. They use synthetic resource
identifiers and deliberately are not inventories of deployed environments.
