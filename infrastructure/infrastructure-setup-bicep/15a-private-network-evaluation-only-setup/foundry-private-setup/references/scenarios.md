# Input and setup contracts

| Choice | Contract |
|---|---|
| New account/project | Both `mode: create`; exact names; explicit account publicNetworkAccess Enabled/Disabled. SystemAssigned identities. |
| Existing account/project | Both `mode: existing` with full paired ARM IDs in the configured subscription/region, AzureCloud, exactly one project, Succeeded SystemAssigned resources and stable internal IDs. No identity/CMK/backend/model migration or mixed modes. |
| RG | `create` exact name or `existing` exact name in configured subscription. Existing RG is GET/reference only. |
| Storage | New GPv2 StorageV2 with explicit publicNetworkAccess, or existing full ID with Succeeded blob endpoint. Never list keys or reset BYO policy. |
| Network | New exact private IPv4 CIDRs, distinct delegated-agent/PE subnets, or exact existing distinct subnet IDs in one same-region VNet. Agent /26 or larger, delegation Microsoft.App/environments; PE /28 or larger and not delegated. Never PUT existing subnets. |
| Monitoring none | Use `input.no-monitoring.example.json` (`applicationInsights.mode: none`). No LAW/Insights/AMPLS/monitor connection/monitor grants/monitor PE/DNS nodes. |
| Monitoring create | New Insights on new or compatible existing LAW. Preserve an existing LAW's ingestion/query policies. |
| Monitoring existing | Exact component ID; resolve its actual linked LAW, not a generated name. Preserve both policies. |
| Workload/hosts | Optional `workload`. Defaults: `intent` trace when monitoring is on, otherwise non-trace; `routeGoal` direct-private; `projectHost` requested. Trace intent requires monitoring. Hosts are visible plan nodes and run only after plan approval plus the injection acknowledgment. |

Full examples include schemaVersion 1.0, subscriptionId, location, resourceGroup,
foundryAccount, foundryProject, storageAccount, network and applicationInsights;
`workload` and `privateNetworking` are optional. No credentials, keys, SAS, tokens, connection strings or desired replacement
settings on `existing` resources. Placeholder all-zero subscription IDs must be replaced.

`input.existing.example.json` shows bounded paired retrofit with BYO dependencies.
Inspection/planning never authorizes injection. An absent agent injection may be added
only by its own exact approval plus `-AcknowledgeAccountWideImpact`; preserve public
access, identity/internal IDs, models, connection metadata, unrelated properties and
other injection scenarios. Conflicting/multiple/failed/pending/backend-configured hosts,
multiple projects and incompatible injection require investigation, not migration.

Connections are read by exact name: project `dataset-storage` and account
`monitoring`. A compatible one is reused without overwriting credentials; an
incompatible one stops the plan. To reuse a connection with a different name, set
`connectionSelection.storage` and/or `.monitoring` to its exact ID on the selected
account/project. ResourceId, endpoint, category and auth must match.

Optional `privateNetworking` in the same input file has `dnsZones`,
`privateEndpoints`, and (only with monitoring) `monitorPrivateLink`. Omitted entries
default to `mode: create`; with monitoring, the AMPLS defaults to
`ampls-<account name>`. Supply only what you bring. Keys are exact supported zone/PE
targets (see `input.existing.example.json`).
Each entry uses `mode: create`, or `mode: existing` plus exact `resourceId`.
Existing DNS optionally allows `linkVnet: true`; existing PE optionally allows
`addDnsZoneGroup: true`. These booleans describe separately reviewed additions, not
blanket approval. Existing entries default to no link/group write. Existing AMPLS
associations are inspected and reused when exact. Conflicts fail; never overwrite to
fit template defaults. A supplied zone ID must end in its selected zone name.

The guide generates the exact asset parameters, target-specific zone sets, dependency
IDs, connection reuse flags and linked-workspace references. All ten included Bicep
files are assets; the monitor-scope/workspace children are not separate infrastructure
rewrites. Existing PE zone-group additions must use the asset's selected RG/name;
different-scope/name reuse is reference-only.

## Permission contract

The operator needs existing ARM read/deployment permissions for selected scopes and
the selected resource-provider writes. Creating role assignments additionally requires
existing `Microsoft.Authorization/roleAssignments/write`, such as Role Based Access
Control Administrator or User Access Administrator at the relevant scope; Contributor
alone does not grant it. Do not elevate or add operator permissions automatically.

Project system-identity assignments proposed by the helper are exactly:

| Target | Built-in role ID |
|---|---|
| Foundry account | 53ca6127-db72-4b80-b1b0-d745d6d5456d |
| Storage blob data | ba92f5b4-2d11-453d-a403-e96b0029c9fe |
| Insights and actual linked LAW | 73c42c96-874c-492b-b04d-ab87d138a893 |

Role definition IDs are rooted in the target subscription, assignment scopes are exact,
and principal IDs come from the observed project's identity. Preview/approve each
assignment independently. Observed assignments are not a claim of effective data access.
