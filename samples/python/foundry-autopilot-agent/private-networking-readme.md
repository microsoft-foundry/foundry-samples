# Private Networking Deployment Guide

This guide deploys the sample in four stages:

1. Provision control-plane resources without running data-plane hooks.
2. Create a VM in the firewall-routed VM subnet and optionally configure
   restricted RDP through Azure Firewall DNAT.
3. Run the `postprovision` hook from the VM to build, create, and publish the
   agent through the Foundry private endpoint.
4. Approve and use the agent in Microsoft Teams.

For resource-level design and data-flow diagrams, see
[Private Network Architecture](./private-network-architecture-readme.md).

> [!CAUTION]
> This deployment creates Azure Firewall Standard and other billable resources.
> Review current Azure pricing and remove resources when they are no longer
> needed.

## Prerequisites

- An Azure subscription.
- Owner, or equivalent permissions to deploy resources and create role
  assignments.
- Azure CLI.
- Azure Developer CLI (`azd`).
- Git.
- A region that supports the model and Foundry hosted agents used by the
  sample.
- Enrollment in the
  [Frontier preview program](https://adoption.microsoft.com/en-us/copilot/frontier-program/)
  for Autopilot publication.
- A Microsoft 365 administrator who can approve the published blueprint.
- A non-overlapping hub and spoke address plan.

The default private address plan is:

| Resource | Prefix |
|---|---:|
| Hub VNet | `10.1.0.0/16` |
| Azure Firewall subnet | `10.1.0.0/26` |
| Workload spoke | `10.0.0.0/16` |
| Hosted-agent subnet | `10.0.0.0/24` |
| Private endpoint subnet | `10.0.1.0/24` |
| VM subnet | `10.0.2.0/24` |

Change the defaults in `infra/main.bicep` before the first deployment if they
overlap with an existing or connected network.

## Phase 1: Provision control-plane resources

### 1. Authenticate

```powershell
$tenantId = "<tenant-id>"
$subscriptionId = "<subscription-id>"
$location = "<supported-azure-region>"
$environmentName = "<unique-azd-environment-name>"

az login --tenant $tenantId
az account set --subscription $subscriptionId
azd auth login --tenant-id $tenantId
```

### 2. Create the `azd` environment

Run these commands from this sample directory:

```powershell
azd env new $environmentName `
  --subscription $subscriptionId `
  --location $location

azd env select $environmentName
```

If the agent should use the Azure DevOps remote MCP server, set the organization
name before provisioning:

```powershell
azd env set AZURE_DEVOPS_ORGANIZATION "<organization-name>"
```

Do not include the `https://dev.azure.com/` prefix.

### 3. Select private networking

`publicNetworkAccess` defaults to `Enabled` in `infra/main.bicep`. Set the
corresponding `azd` environment value to `Disabled` before the first
provisioning operation:

```powershell
azd env set PUBLIC_NETWORK_ACCESS Disabled
```

Confirm the setting:

```powershell
azd env get-value PUBLIC_NETWORK_ACCESS
```

The command must return `Disabled`. This selects
`infra/modules/private-networking.bicep`; leaving the value unset selects the
public account deployment instead.

> [!IMPORTANT]
> Set this value before creating the Foundry account. Azure does not support
> moving an existing Foundry network injection to a different subnet.

### 4. Defer data-plane operations

`azd provision` normally runs the `postprovision` hook automatically. Set this
guard so the first pass creates only ARM-managed resources:

```powershell
azd env set SKIP_POSTPROVISION true
```

The hook remains registered in `azure.yaml`, but
`scripts/post-provision.ps1` exits before building or publishing the agent.

### 5. Provision Azure resources

```powershell
azd provision
```

This runs the `preprovision` provider-registration hook and deploys:

- Hub and spoke VNets and peerings.
- Azure Firewall, policy, and public IP.
- Spoke route table and subnet UDR associations.
- Hosted-agent, private endpoint, and VM subnets.
- Foundry account with public access disabled and hosted-agent network
  injection.
- Foundry private endpoint and private DNS zones.
- Foundry project and model deployment.
- Azure Container Registry.
- Log Analytics and Application Insights.
- Required role assignments and the Application Insights project connection.

Inspect the resulting values:

```powershell
azd env get-values
```

Confirm that private networking was selected:

```powershell
azd env get-value PUBLIC_NETWORK_ACCESS
azd env get-value VIRTUAL_MACHINE_SUBNET_ID
azd env get-value AZURE_FIREWALL_ID
```

The first command must return `Disabled`; the other two must return resource
IDs.

> [!IMPORTANT]
> Do not reuse an existing Foundry account that was injected into another
> subnet. Azure does not allow the original network injection to be removed or
> replaced.

## Phase 2: Create a VM in the VM subnet

The VM provides a private execution environment for Foundry data-plane
operations. Create it without a direct public IP.

### 1. Load environment values

```powershell
$subscriptionId = azd env get-value SUBSCRIPTION_ID
$resourceGroup = azd env get-value RESOURCE_GROUP
$location = azd env get-value LOCATION
$vmSubnetId = azd env get-value VIRTUAL_MACHINE_SUBNET_ID
$firewallId = azd env get-value AZURE_FIREWALL_ID

$vmName = "$environmentName-vm"
$nicName = "$vmName-nic"
```

If this is a new PowerShell session, set `$environmentName` again or replace it
with the selected `azd` environment name.

### 2. Create a private NIC

```powershell
az network nic create `
  --subscription $subscriptionId `
  --resource-group $resourceGroup `
  --location $location `
  --name $nicName `
  --subnet $vmSubnetId `
  --accelerated-networking true

$nicId = az network nic show `
  --subscription $subscriptionId `
  --resource-group $resourceGroup `
  --name $nicName `
  --query id `
  --output tsv
```

Because an existing NIC is supplied to `az vm create`, Azure CLI does not
create a VM public IP.

### 3. Create the Windows VM

Choose a strong password when prompted. Input is masked and the password is not
placed directly in shell history.

```powershell
$adminUsername = "azureuser"
$securePassword = Read-Host "Enter the VM administrator password" -AsSecureString
$adminPassword = [System.Net.NetworkCredential]::new("", $securePassword).Password

az vm create `
  --subscription $subscriptionId `
  --resource-group $resourceGroup `
  --location $location `
  --name $vmName `
  --nics $nicId `
  --image "MicrosoftWindowsServer:WindowsServer:2022-datacenter-azure-edition:latest" `
  --size "Standard_D4ads_v6" `
  --admin-username $adminUsername `
  --admin-password $adminPassword `
  --security-type TrustedLaunch `
  --enable-secure-boot true `
  --enable-vtpm true

Remove-Variable adminPassword
Remove-Variable securePassword
```

Confirm that the VM has a private address and no public address:

```powershell
az vm show `
  --subscription $subscriptionId `
  --resource-group $resourceGroup `
  --name $vmName `
  --show-details `
  --query "{state:powerState,privateIp:privateIps,publicIp:publicIps}" `
  --output table
```

### 4. Verify the forced route

```powershell
az network nic show-effective-route-table `
  --subscription $subscriptionId `
  --resource-group $resourceGroup `
  --name $nicName `
  --output table
```

The active `0.0.0.0/0` route must have:

- Source: `User`
- Next hop type: `VirtualAppliance`
- Next hop IP: the value of `AZURE_FIREWALL_PRIVATE_IP`

## Optional: Configure RDP through Azure Firewall DNAT

Skip this section when the VM will use Azure Bastion or no interactive inbound
access is required.

DNAT must be restricted to a trusted public source CIDR. Use `/32` for one
administrator address. Do not use `*`, `Internet`, or `0.0.0.0/0`.

```powershell
$trustedSourceCidr = "<your-public-ip>/32"
```

### 1. Resolve firewall and VM addresses

```powershell
$firewall = az network firewall show `
  --ids $firewallId `
  --output json | ConvertFrom-Json

$firewallPolicyId = $firewall.firewallPolicy.id
$firewallPolicyName = Split-Path $firewallPolicyId -Leaf
$firewallPublicIpId = $firewall.ipConfigurations[0].publicIPAddress.id

$firewallPublicIp = az network public-ip show `
  --ids $firewallPublicIpId `
  --query ipAddress `
  --output tsv

$vmPrivateIp = az network nic show `
  --subscription $subscriptionId `
  --resource-group $resourceGroup `
  --name $nicName `
  --query "ipConfigurations[0].privateIPAddress" `
  --output tsv
```

### 2. Create a DNAT collection

```powershell
$ruleCollectionGroup = "vm-ingress-dnat"
$natCollection = "rdp-dnat"
$natRule = "allow-rdp-$vmName"

az network firewall policy rule-collection-group create `
  --subscription $subscriptionId `
  --resource-group $resourceGroup `
  --policy-name $firewallPolicyName `
  --name $ruleCollectionGroup `
  --priority 200

az network firewall policy rule-collection-group collection add-nat-collection `
  --subscription $subscriptionId `
  --resource-group $resourceGroup `
  --policy-name $firewallPolicyName `
  --rule-collection-group-name $ruleCollectionGroup `
  --name $natCollection `
  --collection-priority 100 `
  --action DNAT `
  --rule-name $natRule `
  --source-addresses $trustedSourceCidr `
  --destination-addresses $firewallPublicIp `
  --destination-ports 3389 `
  --ip-protocols TCP `
  --translated-address $vmPrivateIp `
  --translated-port 3389
```

Firewall policy updates can take several minutes. Wait for the rule collection
group's provisioning state to become `Succeeded` before testing.

### 3. Permit the same source in the subnet NSG

```powershell
$vmNsgId = az network vnet subnet show `
  --ids $vmSubnetId `
  --query networkSecurityGroup.id `
  --output tsv

$vmNsgName = Split-Path $vmNsgId -Leaf

az network nsg rule create `
  --subscription $subscriptionId `
  --resource-group $resourceGroup `
  --nsg-name $vmNsgName `
  --name "Allow-RDP-From-Trusted-Source" `
  --priority 100 `
  --direction Inbound `
  --access Allow `
  --protocol Tcp `
  --source-address-prefixes $trustedSourceCidr `
  --source-port-ranges "*" `
  --destination-address-prefixes "*" `
  --destination-port-ranges 3389
```

The DNAT rule and NSG rule must use compatible source ranges. The firewall rule
translates the destination; the NSG independently decides whether the packet
may enter the VM subnet.

### 4. Connect

From a computer whose public IP is in `$trustedSourceCidr`:

```powershell
Test-NetConnection $firewallPublicIp -Port 3389
mstsc /v:$firewallPublicIp
```

Use the VM credentials created earlier. Connect to the firewall public IP, not
the VM private IP. The Azure portal's VM Connect blade may continue to show a
private-IP line-of-sight warning because the VM intentionally has no direct
public IP; that warning does not understand the custom firewall DNAT path.

## Phase 3: Run private data-plane operations

The Foundry account rejects public data-plane access. Run the post-provision
hook from the VM, which can resolve and reach the Foundry private endpoint.

### 1. Prepare the VM

Connect through Bastion or the DNAT path. Install:

- Git
- Azure CLI
- Azure Developer CLI

Place an authorized copy of this repository on the VM and open PowerShell in
the sample directory.

### 2. Authenticate on the VM

```powershell
$tenantId = "<tenant-id>"
$subscriptionId = "<subscription-id>"
$environmentName = "<existing-azd-environment-name>"

az login --tenant $tenantId
az account set --subscription $subscriptionId
azd auth login --tenant-id $tenantId
```

Use an identity with permission to run ACR builds, create Foundry agent
versions, assign the required role, and publish the Microsoft 365 agent.

### 3. Restore the `azd` environment

```powershell
azd env refresh $environmentName
azd env select $environmentName
azd env get-values
```

`azd env refresh` obtains values from the previous infrastructure provision.
Confirm at least these values are populated:

```powershell
azd env get-value AZURE_AI_PROJECT_ENDPOINT
azd env get-value AZURE_CONTAINER_REGISTRY_ENDPOINT
azd env get-value ACCOUNT_NAME
azd env get-value PROJECT_NAME
azd env get-value TENANT_ID
```

If Azure DevOps MCP integration is required, ensure
`AZURE_DEVOPS_ORGANIZATION` is also present.

### 4. Confirm private DNS and HTTPS

```powershell
$accountName = azd env get-value ACCOUNT_NAME
Resolve-DnsName "$accountName.services.ai.azure.com"
Test-NetConnection "$accountName.services.ai.azure.com" -Port 443
```

DNS should resolve through the linked private DNS zone to an address in
`private-endpoint-subnet`, not to a public service address.

### 5. Run the post-provision hook

Clear the staging guard and run the registered hook:

```powershell
azd env set SKIP_POSTPROVISION false
azd hooks run postprovision
```

The hook runs these operations in order:

1. Stops active sessions for the existing agent, when present.
2. Runs an ACR cloud build and pushes
   `hello-world-a365-agent:latest`.
3. Creates a new hosted-agent version with Activity Protocol v1 and the
   Microsoft 365 public endpoint enabled.
4. Waits for the agent version to become active.
5. Grants the agent instance identity the Foundry User role on the project.
6. Configures `BotServiceRbac` authorization.
7. Publishes the digital worker to the Microsoft 365 tenant.

The source for this sequence is `scripts/post-provision.ps1`.

## Phase 4: Approve and use the agent in Teams

### 1. Approve the blueprint

1. Open the
   [Microsoft 365 admin center](https://admin.cloud.microsoft/?#/agents/all/requested).
2. Open **Agents** and locate the request whose display name matches
   `AGENT_NAME`.
3. Select **Approve request and activate**.
4. Review and consent to the requested Microsoft 365 and optional MCP
   permissions according to your tenant policy.

Publication submits the request; it does not bypass tenant administrator
approval.

### 2. Create an agent instance

1. Open Microsoft Teams.
2. Go to **Apps** and then **Agents for your team**.
3. Find the approved agent.
4. Create an instance for the intended team or scope.
5. Open the agent and send a test message.

Teams communicates with the Microsoft 365 public endpoint configured on the
hosted agent. The management VM does not need to remain running for users to
interact with the published agent.

## Operational checks

### Confirm the VM has no direct public IP

```powershell
az vm show `
  --subscription $subscriptionId `
  --resource-group $resourceGroup `
  --name $vmName `
  --show-details `
  --query publicIps `
  --output tsv
```

The result should be empty.

### Confirm RDP DNAT

```powershell
az network firewall policy rule-collection-group show `
  --subscription $subscriptionId `
  --resource-group $resourceGroup `
  --policy-name $firewallPolicyName `
  --name $ruleCollectionGroup `
  --output table
```

### Query firewall logs

Enable resource-specific firewall logs in the environment's Log Analytics
workspace:

```powershell
$workspaceId = az monitor log-analytics workspace show `
  --subscription $subscriptionId `
  --resource-group $resourceGroup `
  --workspace-name "$environmentName-logs" `
  --query id `
  --output tsv

az monitor diagnostic-settings create `
  --subscription $subscriptionId `
  --name "firewall-traffic-logs" `
  --resource $firewallId `
  --workspace $workspaceId `
  --export-to-resource-specific true `
  --logs '[
    {"category":"AZFWNetworkRule","enabled":true},
    {"category":"AZFWApplicationRule","enabled":true},
    {"category":"AZFWNatRule","enabled":true},
    {"category":"AZFWThreatIntel","enabled":true},
    {"category":"AZFWDnsQuery","enabled":true},
    {"category":"AZFWFqdnResolveFailure","enabled":true}
  ]' `
  --metrics '[{"category":"AllMetrics","enabled":true}]'
```

Then query the workspace:

```kusto
union isfuzzy=true
    AZFWNetworkRule,
    AZFWApplicationRule,
    AZFWNatRule,
    AZFWDnsQuery
| where TimeGenerated > ago(1h)
| order by TimeGenerated desc
```

RDP-specific query:

```kusto
AZFWNatRule
| where TimeGenerated > ago(1h)
| where DestinationPort == 3389
| order by TimeGenerated desc
```

Initial table creation and log ingestion can take several minutes.

## Troubleshooting

| Symptom | Check |
|---|---|
| `NetworkInjectionUpdateNotAllowed` | The account was previously injected into another subnet. Use a new account/environment or retain the original injected subnet. |
| Portal says the VM has no line of sight | Expected with firewall DNAT. Use the firewall public IP in the RDP client. |
| RDP times out | Confirm the trusted source CIDR, DNAT destination, VM private IP, NSG rule, VM power state, and Windows RDP listener. |
| RDP works with a direct VM IP but not forced routing | Remove the direct VM public IP and use firewall DNAT to preserve symmetric routing. |
| Foundry data-plane call returns a network error | Run it from the spoke VM and verify private DNS resolution and TCP 443. |
| ACR build fails | Verify Azure CLI authentication, ACR permissions, firewall HTTPS access, and registry public access. |
| No firewall logs | Confirm diagnostic settings, generate traffic, and allow time for first-time Log Analytics table creation. |
| Agent publication is pending | A Microsoft 365 administrator must approve and activate the blueprint. |
