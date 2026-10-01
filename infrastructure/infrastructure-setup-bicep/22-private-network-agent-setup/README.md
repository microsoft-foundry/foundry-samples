---
description: Network-secured Foundry Agent Service with account network injection, project capabilitySettings, implicit capability hosts, and explicit deployment-managed or operator-managed RBAC.
page_type: sample
products:
- azure
- azure-resource-manager
urlFragment: network-secured-agent-capabilitysettings
languages:
- bicep
- json
---

# Microsoft Foundry: Network-Secured Agent Setup with Implicit Capability Hosts

**Scenario 22** uses a network-injected Foundry account and project `capabilitySettings` to select BYO Storage, Cosmos DB, and AI Search resources. The templates do not declare account or project CapabilityHost resources.

> [!IMPORTANT]
> **Implicit capability-host provisioning does not provision any RBAC.** The service does not create Azure role assignments or Cosmos DB SQL data-plane role assignments. **Bicep creates the Project managed identity's runtime grants by default**, under the deployment identity. Disabling a role module requires equivalent permissions to be explicitly managed elsewhere; there is no service-created fallback. Creating hosts, connections, or containers does not grant access to them.

> [!NOTE]
> **Network injection is the prerequisite for the implicit-host flow, not `capabilitySettings` alone.** A new account receives `properties.networkInjections` with `scenario: 'agent'`, its dedicated subnet ID, and `useMicrosoftManagedNetwork: false`. A project's `capabilitySettings` supplies the three backing-store ARM IDs. See the [account declaration](modules-network-secured/ai-account-identity.bicep#L27-L57) and [project declaration](modules-network-secured/ai-project-identity.bicep).

## Choose an entry point

| Goal | Entry point | What is written |
| --- | --- | --- |
| Create a network-secured account/project and create or reuse its supporting resources | [main.bicep](main.bicep) | New account with network injection unless an existing account is supplied; project with `capabilitySettings`; networking and enabled RBAC modules |
| Add a new project to an already network-injected account | [add-project.bicep](add-project.bicep) | New project with a timestamp-derived suffix; enabled Project managed-identity grants; no account network update |
| Update a named existing project in place | [add-existing-project.bicep](add-existing-project.bicep) | Project **PUT**, explicit connection writes, and optional RBAC modules; no account network update |

For all three paths, follow [Provisioning and runtime RBAC](#provisioning-and-runtime-rbac) before using the data plane. Role modules are **enabled by default**, but the entry points have **different RBAC switches**; do not assume the main-template flags apply to the other two.

### How this differs from Scenario 15

- Account and project hosts are implicit; there is no `createAccountCapabilityHost` parameter or explicit host module. The account must already be network injected when an existing account is reused.
- Project `capabilitySettings` contains `documentStore`, `vectorStore`, and `blobStore` resource IDs. The [main project module](modules-network-secured/ai-project-identity.bicep) and [new-project module](modules-network-secured/ai-project-identity-unique.bicep) do not declare the three backing-store connections themselves. The [existing-project module](modules-network-secured/ai-existing-project-connections.bicep) **does** declare explicit child connections in addition to its project PUT.
- Container creation and role assignment are separate responsibilities. Implicit provisioning creates the backing containers; [main](main.bicep#L237-L238) and [new-project](add-project.bicep#L24-L25) deployments default `assignContainerRoles` to `true` so **Bicep** creates the Storage/Cosmos runtime grants. The role modules do not pre-create containers.

For other deployment models, see [Scenario 15](../15-private-network-standard-agent-setup/), [Scenario 17 for user-assigned identity](../17-private-network-standard-user-assigned-identity-agent-setup/), or [Scenario 19 for tools behind a VNet](../19-private-network-agent-tools/). Scenario 22 does not configure private tool traffic for MCP, OpenAPI, Functions, or A2A.

## Deploy to Azure

[![Deploy To Azure](https://raw.githubusercontent.com/Azure/azure-quickstart-templates/master/1-CONTRIBUTION-GUIDE/images/deploytoazure.svg?sanitize=true)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fmicrosoft-foundry%2Ffoundry-samples%2Frefs%2Fheads%2Fmain%2Finfrastructure%2Finfrastructure-setup-bicep%2F22-private-network-agent-setup%2Fazuredeploy.json)

The button loads this scenario's [ARM template](azuredeploy.json) from upstream `main`. While the scenario is still in an unmerged PR, use the Bicep sources from the PR checkout instead. The button does not grant the deployer or Project identity any permissions beyond the role resources actually enabled in the template.

## Prerequisites

1. **An approved deployment identity and scope.** It needs permission to create/update the selected account, project, network, data, and optional monitoring/registry resources. Enabled Azure RBAC modules also require `Microsoft.Authorization/roleAssignments/write` at each target scope; Cosmos SQL role assignments use the Cosmos resource-provider permission. Role Based Access Administrator alone does not provide general resource-deployment access. Creating a resource group requires permission at subscription scope.
2. **Provisioning-caller access to the backing stores before the Project PUT.** See the identity and timing distinctions below. Project MI grants emitted later in the deployment do not authorize the earlier caller operation.
3. **A supported location and model/SKU/quota combination.** Check the [main location allowlist and model parameters](main.bicep). An allowed location is not a capacity reservation or proof that every model version/SKU is offered there.
4. **A dedicated agent subnet per Foundry account**, delegated exclusively to `Microsoft.App/environments`, plus a private-endpoint subnet and working private DNS. Check for address overlap with existing/peered networks and service-reserved ranges before deployment.
5. **A private-network-connected client** for data-plane checks, such as a jump host or workstation connected by VPN/ExpressRoute. Azure Bastion connects to a VM; it is not itself a data-plane client. Do not enable public access merely to bypass a private DNS/connectivity issue.
6. **Azure CLI and Bicep**, and the required registered providers: `Microsoft.CognitiveServices`, `Microsoft.Network`, `Microsoft.App`, `Microsoft.Storage`, `Microsoft.DocumentDB`, and `Microsoft.Search`. Optional resources require `Microsoft.ContainerRegistry`, `Microsoft.Insights`, and `Microsoft.OperationalInsights` as applicable.

The [preflight checks](../deployment-tools/preflight/README.md) help identify provider registration, subnet conflicts, and name reservations. They do not replace RBAC or readiness verification.

## Provisioning and runtime RBAC

### Three different identities

| Identity | Purpose | Who assigns its permissions |
| --- | --- | --- |
| **Deployment / ARM caller** | Issues Bicep deployments and Account/Project PUTs; authorizes caller-based backing-resource provisioning | An authorized administrator/platform setup, **before** the operation. None of these templates grants roles to the caller. |
| **Project system-assigned managed identity** | Authenticates the project's runtime access to BYO Storage, Cosmos DB, and Search | Enabled Bicep role modules, or an authorized operator for deferred/pre-existing grants |
| **User/application calling the Foundry data plane** | Creates/uses agents and conversations through the project endpoint | An authorized administrator assigns the appropriate Foundry data-plane role. This is separate from the Project MI's access to its backing stores. |

The account has its own managed identity, but the backing-store role modules in this scenario target `aiProject.outputs.projectPrincipalId`, **not** the account identity. Source: [main role-module calls](main.bicep), [storage role](modules-network-secured/azure-storage-account-role-assignment.bicep), [Cosmos operator role](modules-network-secured/cosmosdb-account-role-assignment.bicep), and [Search roles](modules-network-secured/ai-search-role-assignments.bicep).

### Before provisioning: authorize the ARM caller

For caller-authorized provisioning, arrange these effective permissions on the chosen stores before creating/updating the project:

- **Cosmos DB Operator** on the Cosmos DB account.
- **Storage Blob Data Contributor** on the Storage account.
- The resource-deployment and role-assignment permissions needed for the template operations at their actual scopes, including any cross-subscription resources.

An authorized administrator must create these assignments; the service does not. If the stores are also being created by the same deployment, arrange approved inherited access on a dedicated deployment scope or provision and permission the stores first and supply their existing resource IDs. Do not assume the caller gains these roles from the template's Project MI assignments.

For the main-template caller-authorized flow, `assignProjectStorageAndCosmosAccountRoles=false` defers the **Project MI's** Storage Contributor and Cosmos Operator grants. It does **not** grant the caller access and does not disable Search roles. After provisioning, grant the deferred roles to the Project identity before runtime use. The [main-template flag](main.bicep) is not available in the two add-project entry points.

### Which RBAC resources the templates create

All grants in this table target the **Project MI**. “Enabled” means **ARM deploys a role-assignment resource from Bicep**, not that the Foundry service creates an assignment.

| Grant and actual scope | Main | New additional project | Existing project | Source |
| --- | --- | --- | --- | --- |
| Storage Blob Data Contributor, Storage **account** | `assignProjectStorageAndCosmosAccountRoles` (default `true`) | Always | `assignRoles` (default `true`) | [Storage account role](modules-network-secured/azure-storage-account-role-assignment.bicep) |
| Cosmos DB Operator, Cosmos **account** | Same flag | Always | `assignRoles` | [Cosmos account role](modules-network-secured/cosmosdb-account-role-assignment.bicep) |
| Search Index Data Contributor and Search Service Contributor, Search **service** | Always | Always | `assignRoles` | [Search roles](modules-network-secured/ai-search-role-assignments.bicep) |
| Storage Blob Data Owner, Storage **account**, with the module's ABAC condition | `assignContainerRoles` (default `true`) | `assignContainerRoles` (default `true`) | `assignRoles` (default `true`) | [Main variant](modules-network-secured/blob-storage-container-role-assignments.bicep), [additional/existing-project variant](modules-network-secured/blob-storage-container-role-assignments-unique.bicep) |
| Cosmos DB Built-in Data Contributor, SQL data plane, **`enterprise_memory` database** | `assignContainerRoles` | `assignContainerRoles` | `assignRoles` | [Cosmos SQL role](modules-network-secured/cosmos-container-role-assignments.bicep) |
| AcrPull, optional ACR **registry** | `enableContainerRegistry` (default `true`) | Not declared | Not declared | [Registry role](modules-network-secured/container-registry.bicep) |

The flags are declared in [main.bicep](main.bicep), [add-project.bicep](add-project.bicep), and [add-existing-project.bicep](add-existing-project.bicep).

> [!WARNING]
> Keep `assignContainerRoles=true` for the normal main/new-project deployment. Set it to `false` only when equivalent runtime permissions already exist or an authorized external workflow explicitly supplies them before use. This opt-out does not ask the service to create assignments. Review existing role names/conditions before redeploying to avoid conflicts. **A successful Project/CapabilityHost provisioning state is not proof that runtime RBAC is complete**; verify the Bicep role deployments and allow permission propagation.

Despite their filenames and the `assignContainerRoles` flag, these modules do **not** all assign roles at individual container scope. The Storage Owner role is account-scoped; its existing ABAC expression constrains selected blob-tag/filter actions, not every action in that role. The Cosmos SQL role is database-scoped. Neither should be described as universal per-project container isolation. Review the linked modules and your access policy rather than assuming the names imply narrower permissions.

The role modules reference the project principal/internal ID, so they depend on project creation/update. There is no explicit CapabilityHost deployment resource to which they can add a `dependsOn` readiness barrier. Verify Project/host and backing-resource readiness independently; ARM file order is not execution order. Source: [project outputs](modules-network-secured/ai-project-identity.bicep) and [workspace-ID formatting](modules-network-secured/format-project-workspace-id.bicep).

### After provisioning: verify runtime access

1. Resolve the **current** Project principal ID and internal ID. A recreated project can have a new identity even when its display name is reused.
2. Inspect effective Azure RBAC for that principal on Storage and Search, and the required Cosmos account permissions. Include inherited assignments and applicable conditions in the review.
3. Inspect **Cosmos SQL data-plane role assignments separately**. Cosmos DB Operator and subscription Owner are not substitutes for Cosmos SQL data access.
4. Supply deferred/missing grants through an approved template or operator workflow, allow propagation, and verify the required database/containers and private connectivity.
5. Give the test caller the required project data-plane access (for example the built-in **Foundry User** role, ID `53ca6127-db72-4b80-b1b0-d745d6d5456d`, where appropriate). The templates here do not assign that role to the person/application running the tests.
6. Run data-plane validation from the private-connected client. Keep identity/RBAC failures separate from DNS, private-endpoint, model-deployment, and provisioning-state failures.

See the [Foundry RBAC guidance](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/rbac-azure-ai-foundry?pivots=fdp-project) and [Cosmos DB data-plane RBAC guidance](https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/security/how-to-grant-data-plane-access).

## Main-template configuration

Use [main.bicepparam](main.bicepparam) as a starting point and review [main.bicep](main.bicep) for the complete parameter definitions. The values below are **template defaults**; the sample parameter file overrides some of them.

| Parameter | Template default | Meaning / important constraint |
| --- | --- | --- |
| `location` | `eastus` | Must be in the template allowlist and support the selected services/model |
| `aiServices` | `aiservices` | Account prefix; an RG-derived suffix is appended for a new account |
| `firstProjectName` | `project` | Project prefix; the same RG-derived suffix is appended |
| `displayName` / `projectDescription` | See template | Values written to the project |
| `modelName` / `modelVersion` | `gpt-4.1` / `2025-04-14` | Validate this pair in your subscription/region |
| `modelFormat` / `modelSkuName` / `modelCapacity` | `OpenAI` / `GlobalStandard` / `30` | Model deployment settings; not the account or Search SKU |
| `skipModelDeployment` | `false` | Skips model creation for a **new** account when true; the existing-account branch creates no model regardless |
| `existingAiFoundryAccountResourceId` | Empty | Reuses an account without updating its network injection; see prerequisites below |
| `existingVnetResourceId` | Empty | Empty creates a VNet; otherwise use the supplied VNet |
| `vnetName` | Empty | **Supply a name when creating a VNet.** With an existing VNet, the name comes from its resource ID. |
| `agentSubnetName` / `peSubnetName` | `agent-subnet` / `pe-subnet` | A new account must use its own delegated agent subnet |
| `vnetAddressPrefix` | Empty | New-VNet module fallback is `192.168.0.0/16` |
| `agentSubnetPrefix` / `peSubnetPrefix` | Empty | New-VNet module derives /24 ranges at indices 0 and 1 when omitted; prefer explicit non-overlapping CIDRs |
| `reuseExistingSubnets` | `false` | Set true to reference existing subnets without updating their configuration |
| `aiSearchResourceId` | Empty | Full ARM ID of existing Search; otherwise create one |
| `azureStorageAccountResourceId` | Empty | Full ARM ID of existing Storage; otherwise create one |
| `azureCosmosDBAccountResourceId` | Empty | Full ARM ID of existing Cosmos DB; otherwise create one |
| `createDependentResourcePrivateEndpoints` | `true` | Set false only if the BYO stores already have reachable private endpoints; the Foundry endpoint is still created |
| `assignProjectStorageAndCosmosAccountRoles` | `true` | Controls only Project MI Storage Contributor and Cosmos Operator modules |
| `assignContainerRoles` | `true` | Bicep creates Storage Owner/Cosmos SQL runtime grants; opt out only for equivalent externally managed grants |
| `dnsZonesSubscriptionId` / `existingDnsZones` | Current subscription / empty map values | Controls reuse of service private DNS zones |
| `enableContainerRegistry` / `developerIpCidr` | `true` / empty | Optional Premium ACR + private endpoint + Project MI AcrPull. A supplied CIDR enables ACR public access with an allowlist. |
| `enableTracing` / `monitorLocation` | `true` / `eastus2` | Optional Log Analytics, Application Insights, and AMPLS stack |
| `existingMonitorDnsZones` | Empty map values | Reuse or create the four Azure Monitor private DNS zones |

Network defaults come from [network-agent-vnet.bicep](modules-network-secured/network-agent-vnet.bicep) and [vnet.bicep](modules-network-secured/vnet.bicep). New-account/model conditions come from [ai-account-identity.bicep](modules-network-secured/ai-account-identity.bicep).

### Reusing a VNet, backing stores, and DNS

- Supply the existing resource IDs, not account endpoints, for `existingVnetResourceId`, `aiSearchResourceId`, `azureStorageAccountResourceId`, and `azureCosmosDBAccountResourceId`.
- For preconfigured subnets, set `reuseExistingSubnets=true`; check delegation, routing, network policies, and address ranges yourself. With it false, the [existing-VNet module](modules-network-secured/existing-vnet.bicep) may create/update subnets.
- **Do not share one agent subnet between Foundry accounts.** A new account in a shared VNet still needs an unused, exclusive `Microsoft.App/environments`-delegated subnet. The private-endpoint subnet can be shared according to your network policy.
- Set `createDependentResourcePrivateEndpoints=false` only when all three supplied backing stores already have working private endpoints reachable from the selected VNet. This preserves those endpoints; it does not establish new connectivity or permissions.
- Keep cross-subscription resources in the same Entra tenant as the Project identity, and arrange deployment permissions at each target scope.
- `dnsZonesSubscriptionId` accepts a subscription GUID or full subscription ARM path. When it selects another subscription, populate the relevant existing-zone resource groups; do not assume empty entries create zones in the remote subscription. Verify VNet links/DNS forwarding, especially for centrally managed zones. See [private-endpoint-and-dns.bicep](modules-network-secured/private-endpoint-and-dns.bicep).
- The account's VNet injection is regional. Keep the account and VNet in the same region, and validate any cross-region backing-store configuration separately.

### Reusing an existing Foundry account

The [existing-account declaration](modules-network-secured/ai-account-identity.bicep#L59-L63) is reference-only. It does **not** apply `networkInjections`, create/repair the account CapabilityHost, or create a model deployment. Before choosing this path, independently verify:

- The account is already configured for the supported private agent-network flow and its Account CapabilityHost is ready.
- Its injection points to the intended exclusive agent subnet. Do not use this entry point to migrate an account onto another subnet.
- Required model deployments, private endpoints, DNS, caller permissions, and runtime grants exist or are deliberately supplied by your deployment workflow.

**There is no `createAccountCapabilityHost=true` repair switch in Scenario 22.** An account without the required network injection/host is not made ready by setting `existingAiFoundryAccountResourceId`. Use a supported separate account setup/recovery workflow or deploy a fresh account with its own subnet. The project modules use the deployment resource group, so deploy into the account's resource group/subscription rather than inferring cross-scope project support from the account reference alone.

### Search authentication and optional resources

The [new backing-resource module](modules-network-secured/standard-dependent-resources.bicep) creates Search with AAD-or-API-key authentication and disabled public network access, Storage with disabled Shared Key/public blob access, and Cosmos DB with disabled local/public access. Existing resources are referenced rather than automatically brought into policy compliance.

An existing Search service must accept Entra data-plane tokens. The [Search validation module](modules-network-secured/validate-search-aad-auth.bicep) checks this in the main BYO-Search path and existing-project path. The additional-new-project entry point does not invoke that check; validate it before deployment. Review approved changes with the Search owner rather than enabling public access to work around an authentication error.

[Optional ACR](modules-network-secured/container-registry.bicep) adds a registry endpoint and explicit AcrPull assignment. [Optional tracing](modules-network-secured/application-insights.bicep) creates an AppInsights account connection using its connection string, plus the [AMPLS private ingestion path](modules-network-secured/monitor-private-link-scope.bicep). Do not describe all optional connections as keyless or claim that these options grant the caller Foundry access.

## Deploy and verify

1. Select a new disposable deployment scope or an explicitly approved existing scope. Establish the caller permissions and networking prerequisites first.
2. Edit the parameter file and review the actual role flags for that entry point.
3. Run what-if and inspect the intended resource/role changes. What-if does not enumerate every service-side effect of implicit provisioning or prove runtime authorization.
4. Deploy once. If a PUT is accepted but provisioning is still running, observe status with GETs rather than repeatedly submitting writes.

Example for the main entry point, from this folder:

```powershell
az deployment group what-if --subscription '<subscription-id>' `
  --resource-group '<resource-group>' --template-file main.bicep `
  --parameters main.bicepparam
az deployment group create --subscription '<subscription-id>' `
  --resource-group '<resource-group>' --template-file main.bicep `
  --parameters main.bicepparam
```

### Inspect the account, project, and both host scopes

Use the **actual deployed names**, including any generated suffix. The following commands are reads; the project host collection is distinct from the account host collection:

```powershell
$Sub = '<subscription-id>'; $RG = '<account-resource-group>'
$Account = '<actual-account-name>'; $Project = '<actual-project-name>'
$AccountId = "/subscriptions/$Sub/resourceGroups/$RG/providers/Microsoft.CognitiveServices/accounts/$Account"
$A = "https://management.azure.com$AccountId"
$P = "$A/projects/$Project"
$Api = '2026-05-15-preview'; $HostApi = '2025-10-01-preview'
az rest --method get --url "${A}?api-version=$Api" `
  --query '{state:properties.provisioningState,injections:properties.networkInjections}'
az rest --method get --url "${P}?api-version=$Api" `
  --query '{state:properties.provisioningState,principalId:identity.principalId,settings:properties.capabilitySettings}'
az rest --method get --url "$A/capabilityHosts?api-version=$HostApi"
az rest --method get --url "$P/capabilityHosts?api-version=$HostApi"
```

Discover the Project host's returned name and GET that specific resource to inspect its bindings. Confirm terminal `Succeeded` state, the expected backing-store IDs, and the Account host's intended subnet. Use an API version exposing `properties.networkInjections`; an older portal/SDK projection may omit it. Host or connection existence does not establish role assignments. Complete the [runtime access checks](#after-provisioning-verify-runtime-access) before testing agents.

### Readiness checklist

- Account, Project, and expected hosts are ready; `capabilitySettings` identifies the intended three stores.
- Every new account has its own delegated subnet; private endpoints are approved; the client/runtime DNS and network path resolve/reach the correct private resources.
- Managed/explicit connections point to the intended resources; do not assume requested connection names were adopted by an implicit host.
- Provisioning caller permissions and Project MI runtime grants are both correct, including Cosmos SQL data roles and effective ABAC conditions.
- The model deployment exists and the selected SDK/API/model combination works.
- A data-plane CRUD/inference check succeeds from the private-connected client under the intended identity.

## Add a new project to the existing account

Use [add-project.bicep](add-project.bicep) with [add-project.bicepparam](add-project.bicepparam). Supply the actual existing account and store coordinates, the account's region, and the new project's display name/description. [get-existing-resources.ps1](get-existing-resources.ps1) can help discover shared resource names; verify the result rather than assuming every similarly named resource belongs to this environment.

- Deploy in the existing account's resource group/subscription. The [project module](modules-network-secured/ai-project-identity-unique.bicep) references the parent in `resourceGroup()`.
- This path does not network-inject the parent account. Verify its existing network/host readiness first.
- It uses a `deploymentTimestamp`-derived suffix. A rerun with a new timestamp can create another project; retain the timestamp for retries when you intend the same project.
- The project module sets `capabilitySettings` but does not declare backing-store connection resources. `uniqueConnectionSuffix` is currently not consumed by resource declarations and does not control service-created connection names.
- Storage Contributor, Cosmos Operator, and Search roles are unconditional **Bicep assignments** to the new Project MI. `assignContainerRoles=true` also deploys the Storage Owner/Cosmos SQL runtime grants by default. Set it to `false` only for equivalent externally managed grants. This path has no `assignProjectStorageAndCosmosAccountRoles` switch.

Preview and deploy with the same commands above, substituting the new-project entry point and parameter file. Then perform the same host, RBAC, and private data-plane checks.

## Update an existing project in place

Use [add-existing-project.bicep](add-existing-project.bicep) with [add-existing-project.bicepparam](add-existing-project.bicepparam) only after reviewing the current project and its managed/explicit connections.

> [!WARNING]
> This is a **Project PUT/upsert**, not a reference-only operation. The [existing-project module](modules-network-secured/ai-existing-project-connections.bicep) writes `location`, system-assigned identity, `displayName`, `description`, and `capabilitySettings`, then declares three AAD child connections. The template does not fetch and preserve metadata automatically. **`projectDescription` defaults to an empty string and clears an existing description if omitted.** Pass the current description explicitly when preserving it, along with the current region and display name.

The path expects an existing network-injected parent and a named Project with its intended identity. It appends no suffix, but it does not provide a read-only existence guard: do not treat a misspelled project name as a safe no-op. Deploy in the parent account's resource group/subscription.

### Preserve metadata and review connection writes

Before updating, GET the Project and record its ID, identity, `location`, display name, description, `capabilitySettings`, connections, and host bindings. In the parameter file, explicitly supply:

```bicep
param projectName = 'your-existing-project-name'
param location = 'your-project-region'
param displayName = 'your-current-display-name'
param projectDescription = 'your-current-description'
```

The `cosmosDBConnectionName`, `azureStorageConnectionName`, and `aiSearchConnectionName` overrides select the names of **explicit connection PUTs**, defaulting to `<resourceName>-<lowercase-project-name>`. They do not pass a binding-name override to an explicit host module—there is no such module. Check the returned host bindings after deployment. Service-managed connections may reject direct modification; do not overwrite them, weaken checks, or assume the connection override migrates host bindings safely. Preserve failure evidence and use a supported lifecycle if the existing managed state is incompatible.

### Existing-project role behavior

`assignRoles=true` is the default and runs **all five role modules**: Storage Contributor, Cosmos Operator, Search roles, Storage Owner, and Cosmos SQL data access. There is no separate `assignContainerRoles` switch in this entry point. These are template-created grants, not duplicates of grants the service would create.

Set `assignRoles=false` only after verifying the Project MI's required effective permissions or arranging an explicit separate grant step. It skips **all** those modules; it does not mean “keep the account grants but skip container grants.” Existing assignments created with different GUIDs/conditions can conflict with the template's deterministic names. Inspect and reconcile assignments through an authorized workflow; do not delete unrelated grants or repeatedly rerun a conflicting deployment.

Within the same entry point, fixed parameters produce deterministic names for the role resources, but that is not a blanket promise that a Project PUT, connection update, or host side effect is non-destructive. Preview, review existing state, and verify the result.

## Offline validation

[The RBAC contract tests](tests/test_role_assignments.py) compile all three entry points and sample parameter files. They verify that runtime grants are enabled by default, target the Project identity at the existing Storage account/Cosmos database scopes, retain the explicit opt-out conditions, and do not pre-create hosts or backing containers. They also check the generated portal artifacts against the Bicep sources.

Run `python tests/test_role_assignments.py` from this folder with Python and Bicep CLI installed. Set `BICEP_CLI` to the executable path if it is not on `PATH` or in the Azure CLI installation directory. These tests do not authenticate, deploy resources, grant roles, or prove live RBAC propagation/data-plane readiness.

## Module map

| Source | Responsibility |
| --- | --- |
| [ai-account-identity.bicep](modules-network-secured/ai-account-identity.bicep) | New account network injection and optional model; reference-only existing-account branch |
| [ai-project-identity.bicep](modules-network-secured/ai-project-identity.bicep) | Main Project PUT with backing-store IDs |
| [ai-project-identity-unique.bicep](modules-network-secured/ai-project-identity-unique.bicep) | Additional Project PUT; no explicit backing-store connections |
| [ai-existing-project-connections.bicep](modules-network-secured/ai-existing-project-connections.bicep) | Existing Project PUT plus explicit AAD connection writes |
| [standard-dependent-resources.bicep](modules-network-secured/standard-dependent-resources.bicep) | Create/reference BYO data resources |
| [network-agent-vnet.bicep](modules-network-secured/network-agent-vnet.bicep), [existing-vnet.bicep](modules-network-secured/existing-vnet.bicep), [vnet.bicep](modules-network-secured/vnet.bicep) | VNet/subnet creation or reuse |
| [private-endpoint-and-dns.bicep](modules-network-secured/private-endpoint-and-dns.bicep) | Service private endpoints and DNS zone groups/links |
| [validate-existing-resources.bicep](modules-network-secured/validate-existing-resources.bicep), [validate-search-aad-auth.bicep](modules-network-secured/validate-search-aad-auth.bicep) | BYO resource/DNS discovery and Search authentication checks |
| [azure-storage-account-role-assignment.bicep](modules-network-secured/azure-storage-account-role-assignment.bicep), [cosmosdb-account-role-assignment.bicep](modules-network-secured/cosmosdb-account-role-assignment.bicep), [ai-search-role-assignments.bicep](modules-network-secured/ai-search-role-assignments.bicep) | Explicit Project MI account/service grants |
| [blob-storage-container-role-assignments.bicep](modules-network-secured/blob-storage-container-role-assignments.bicep), [unique variant](modules-network-secured/blob-storage-container-role-assignments-unique.bicep), [cosmos-container-role-assignments.bicep](modules-network-secured/cosmos-container-role-assignments.bicep) | Explicit Storage account/ABAC and Cosmos SQL database grants |
| [container-registry.bicep](modules-network-secured/container-registry.bicep) | Optional ACR, endpoint/DNS, and Project MI AcrPull |
| [application-insights.bicep](modules-network-secured/application-insights.bicep), [monitor-private-link-scope.bicep](modules-network-secured/monitor-private-link-scope.bicep) | Optional tracing connection and private ingestion resources |

## Troubleshooting and cleanup

- **Provisioning authorization failure:** identify the actual ARM caller and the failed action/scope. A grant to the Project MI, or a user PIM activation, does not grant a different service principal permission.
- **Runtime 403:** check the Project MI on the backing stores, the API caller on the Foundry project, Cosmos SQL roles, role propagation, and network policy separately. Do not assume the service will repair missing RBAC.
- **Missing implicit host:** verify the parent account's network injection, exact project settings, and terminal provisioning errors. Reusing an uninjected account does not configure it.
- **`RoleAssignmentExists`:** inspect exact principal, scope, role, condition, and assignment name. The existing-project all-or-none flag can skip template grants only when required access is supplied elsewhere.
- **Private endpoint/DNS failure:** inspect approvals, VNet links/forwarders, private IP resolution, and routing from the client/runtime network. Preserve public-access restrictions.
- **Description or connection unexpectedly changed:** inspect the supplied existing-project PUT parameters. Empty description is a write, not “preserve current value.”

Delete only resources owned by your deployment after capturing diagnostics and obtaining the resource owner's approval. Project-only cleanup must not delete the shared parent Account host, stores, or subnet. For complete Account removal, follow the [documented delete/purge lifecycle](https://learn.microsoft.com/en-us/azure/ai-services/recover-purge-resources?tabs=azure-portal#purge-a-deleted-resource) and verify dependent host/network cleanup before reusing any subnet; elapsed time alone is not readiness. This template does not add role-revocation orchestration for grants on retained BYO resources—review their lifecycle separately.

[createCapHost.sh](createCapHost.sh) and [deleteCapHost.sh](deleteCapHost.sh) are **manual Account-scoped** maintenance helpers, not steps in the implicit deployment and not Project host helpers. Their route has no `/projects/...` segment. Do not use them as an automatic repair path or to recreate a second Account host. Redeploying with a nonexistent `createAccountCapabilityHost` flag cannot restore a deleted host.

## References

- [Foundry private networking](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/configure-private-link?tabs=azure-portal&pivots=fdp-project)
- [Foundry RBAC](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/rbac-azure-ai-foundry?pivots=fdp-project)
- [Azure RBAC](https://learn.microsoft.com/en-us/azure/role-based-access-control/)
- [Azure Private Link](https://learn.microsoft.com/en-us/azure/private-link/)