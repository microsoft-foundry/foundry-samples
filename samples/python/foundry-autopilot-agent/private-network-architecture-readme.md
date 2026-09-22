# Private Network Architecture

This document describes the private deployment selected when
`publicNetworkAccess` is `Disabled` in `infra/main.bicep`. It covers the Azure
resources, security boundaries, routing, DNS, and application data flows.

For deployment commands, VM creation, firewall DNAT, and agent publication, see
[Private Networking Deployment Guide](./private-networking-readme.md).

## Deployment modules

`infra/main.bicep` separates the public and private account paths:

```mermaid
flowchart TD
    Main["infra/main.bicep"]
    Choice{"publicNetworkAccess"}
    Public["public-account.bicep"]
    Private["private-networking.bicep"]
    Network["network.bicep"]
    Shared["project.bicep"]
    Monitoring["monitoring.bicep"]

    Main --> Choice
    Choice -->|"Enabled"| Public
    Choice -->|"Disabled"| Private
    Private --> Network
    Public --> Shared
    Private --> Shared
    Shared --> Monitoring
```

| Module | Responsibility |
|---|---|
| `infra/main.bicep` | Parameters, public/private selection, shared module orchestration, and `azd` outputs |
| `infra/modules/public-account.bicep` | Minimal Foundry account with public network access enabled |
| `infra/modules/private-networking.bicep` | Private Foundry account configuration, subnets, NSGs, private endpoint, private DNS, and network injection |
| `infra/modules/network.bicep` | Hub and spoke VNets, Azure Firewall, firewall policy, route table, and VNet peerings |
| `infra/modules/project.bicep` | Foundry project, model deployment, ACR, RBAC, Application Insights connection, and shared resources |
| `infra/modules/monitoring.bicep` | Log Analytics workspace and Application Insights |

The Foundry account is created in either the public or private module. The
shared project module treats that account as an existing parent resource. This
keeps private network properties out of the public account definition.

## Logical topology

```mermaid
flowchart LR
    Internet((Internet))
    AzureControl["Azure control plane"]
    M365["Microsoft 365 and Teams"]
    PaaS["Azure and Microsoft endpoints"]

    subgraph Hub["Hub VNet - 10.1.0.0/16"]
        FirewallSubnet["AzureFirewallSubnet<br/>10.1.0.0/26"]
        Firewall["Azure Firewall Standard<br/>Private IP assigned dynamically"]
        FirewallPip["Standard public IP"]
        FirewallSubnet --- Firewall
        FirewallPip --- Firewall
    end

    subgraph Spoke["Foundry workload spoke - 10.0.0.0/16"]
        AgentSubnet["agent-subnet<br/>10.0.0.0/24"]
        PeSubnet["private-endpoint-subnet<br/>10.0.1.0/24"]
        VmSubnet["virtual-machine-subnet<br/>10.0.2.0/24"]
        FoundryPe["Foundry private endpoint"]
        AgentRuntime["Hosted agent network injection"]
        Vm["Optional management VM"]

        AgentSubnet --- AgentRuntime
        PeSubnet --- FoundryPe
        VmSubnet --- Vm
    end

    Foundry["Foundry account<br/>Public network access disabled"]
    RouteTable["Spoke route table<br/>0.0.0.0/0 -> Firewall"]
    PrivateDns["Private DNS zones"]

    Hub <-->|"Bidirectional VNet peering"| Spoke
    AgentSubnet --> RouteTable
    PeSubnet --> RouteTable
    VmSubnet --> RouteTable
    RouteTable --> Firewall
    Firewall --> PaaS
    Firewall --> Internet
    FirewallPip <--> Internet
    FoundryPe --> Foundry
    PrivateDns --> FoundryPe
    PrivateDns -.-> Spoke
    AzureControl --> Foundry
    M365 <--> AgentRuntime
```

## Address plan

The defaults can be changed in `infra/main.bicep`. Address spaces must not
overlap with each other or with networks that will be connected later.

| Network | Default prefix | Purpose |
|---|---:|---|
| Hub VNet | `10.1.0.0/16` | Central network services and Azure Firewall |
| `AzureFirewallSubnet` | `10.1.0.0/26` | Required dedicated subnet for Azure Firewall |
| Workload spoke VNet | `10.0.0.0/16` | Foundry hosted-agent, private endpoint, and VM subnets |
| `agent-subnet` | `10.0.0.0/24` | Foundry hosted-agent network injection |
| `private-endpoint-subnet` | `10.0.1.0/24` | Foundry account private endpoint |
| `virtual-machine-subnet` | `10.0.2.0/24` | Optional management or test VMs |

## Hub and Azure Firewall

The hub contains only `AzureFirewallSubnet` in this sample. Azure Firewall
Standard has:

- A private IP used as the `VirtualAppliance` next hop for spoke UDRs.
- A Standard static public IP for outbound SNAT and optional DNAT.
- An Azure Firewall Policy with threat intelligence in `Alert` mode.
- Forwarded-traffic support on both VNet peerings.

```mermaid
flowchart LR
    Spoke["Spoke subnets"]
    Udr["0.0.0.0/0 UDR"]
    Peering["Spoke-to-hub peering<br/>allowForwardedTraffic=true"]
    Firewall["Azure Firewall"]
    Policy["Firewall Policy"]
    PublicIp["Firewall public IP"]
    Internet((Internet))

    Spoke --> Udr --> Peering --> Firewall
    Policy --> Firewall
    Firewall --> PublicIp --> Internet
```

### Default firewall policy

| Collection | Rule | Protocol and port | Destination |
|---|---|---|---|
| `allow-required-network-traffic` | `allow-dns` | TCP/UDP 53 | Any |
| `allow-required-network-traffic` | `allow-ntp` | UDP 123 | Any |
| `allow-https-outbound` | `allow-https` | HTTPS 443 | Any FQDN |

The wildcard HTTPS rule is suitable for demonstrating centralized routing, but
it is not a least-privilege production policy. Replace it with approved FQDNs,
FQDN tags, service tags, or explicit network rules for the workload.

Azure Firewall Standard does not perform TLS inspection. It evaluates the
application rule and forwards the encrypted HTTPS session.

## Workload spoke

The spoke is peered directly with the hub. Peering is non-transitive; adding
another spoke does not automatically give that spoke connectivity to this one.
Each additional spoke requires its own hub peerings and route-table design.

### Hosted-agent subnet

`agent-subnet` is delegated to `Microsoft.App/environments` and is referenced
by the Foundry account's `networkInjections` property:

```mermaid
flowchart LR
    Account["Foundry account"]
    Injection["networkInjections<br/>scenario: agent"]
    Subnet["agent-subnet"]
    Delegation["Microsoft.App/environments delegation"]
    Nsg["Agent subnet NSG"]
    Udr["Spoke UDR"]

    Account --> Injection --> Subnet
    Delegation --> Subnet
    Nsg --> Subnet
    Subnet --> Udr
```

The agent NSG permits outbound traffic to:

- The virtual network, including private endpoints.
- Microsoft Entra ID over TCP 443.
- Azure Monitor over TCP 443.
- Azure Front Door Frontend over TCP 443.
- Microsoft Teams IPv4 ranges over TCP 443.

It then has an explicit outbound deny rule at priority `4096`. Both the NSG and
Azure Firewall policy must allow a flow.

> [!IMPORTANT]
> Foundry network injection is effectively immutable after it is set. Do not
> rename or replace `agent-subnet` for an existing account. Moving an existing
> account to another subnet can fail with
> `NetworkInjectionUpdateNotAllowed`.

### Private endpoint subnet

`private-endpoint-subnet` hosts the Foundry account private endpoint. Private
endpoint network policies are disabled as required by this configuration. The
route table is associated with the subnet, but Azure installs more-specific
`InterfaceEndpoint` routes for private endpoint addresses; those `/32` routes
take precedence over the `0.0.0.0/0` firewall route.

### VM subnet

`virtual-machine-subnet` is a non-delegated subnet for management and testing.
It has:

- A dedicated subnet NSG.
- Private endpoint network policies enabled.
- The spoke route table, forcing default egress through Azure Firewall.
- No inbound allow rules by default.

VMs should be created without direct public IPs. If RDP is required, use Azure
Bastion or an Azure Firewall DNAT rule restricted to a trusted source CIDR.

## Routing behavior

Every workload subnet is associated with the same route table:

```mermaid
flowchart TD
    Packet["Packet from spoke resource"]
    Specific{"More-specific route?"}
    Local["VNet local or private endpoint route"]
    Default["0.0.0.0/0 UDR"]
    Firewall["Next hop: Azure Firewall private IP"]
    Policy{"Firewall policy allows flow?"}
    Forward["Forward and SNAT when required"]
    Deny["Deny"]

    Packet --> Specific
    Specific -->|"Yes"| Local
    Specific -->|"No"| Default --> Firewall --> Policy
    Policy -->|"Yes"| Forward
    Policy -->|"No"| Deny
```

Azure uses longest-prefix matching. VNet-local routes and private endpoint `/32`
routes are more specific than `0.0.0.0/0`, so they do not traverse the firewall.
Internet-bound traffic follows the UDR to the firewall.

## Private endpoint and DNS

The private deployment creates and links these zones to the spoke:

- `privatelink.services.ai.azure.com`
- `privatelink.openai.azure.com`
- `privatelink.cognitiveservices.azure.com`

The private endpoint has a zone group containing all three zones.

```mermaid
sequenceDiagram
    participant Client as VM or hosted agent
    participant DNS as Azure-provided DNS
    participant Zone as Linked private DNS zone
    participant PE as Foundry private endpoint
    participant Account as Foundry account

    Client->>DNS: Resolve Foundry endpoint
    DNS->>Zone: Match privatelink zone
    Zone-->>Client: Return private endpoint IP
    Client->>PE: HTTPS 443
    PE->>Account: Private Link
    Account-->>Client: Response
```

Clients must use DNS that can resolve the linked private zones. The default
Azure-provided resolver works for resources in the linked spoke. Custom DNS
requires conditional forwarding for the Azure private DNS namespace.

## Data flows

### Control-plane provisioning

The operator runs `azd provision`. Azure Resource Manager creates the network,
Foundry, project, model, registry, RBAC, and monitoring resources.

```mermaid
sequenceDiagram
    participant Operator
    participant AZD as Azure Developer CLI
    participant ARM as Azure Resource Manager
    participant Network as Network resource provider
    participant Foundry as Cognitive Services resource provider
    participant Shared as ACR and Monitor providers

    Operator->>AZD: azd provision
    AZD->>ARM: Deploy infra/main.bicep
    ARM->>Network: Hub, spoke, firewall, UDRs, DNS, private endpoint
    ARM->>Foundry: Private account, project, model, network injection
    ARM->>Shared: ACR, Log Analytics, Application Insights, RBAC
    ARM-->>AZD: Deployment outputs
    AZD-->>Operator: Store values in azd environment
```

Azure control-plane requests are not sent through the workload firewall. They
originate from the operator and ARM deployment service.

### Hosted-agent egress

```mermaid
sequenceDiagram
    participant Agent as Hosted agent
    participant NSG as Agent subnet NSG
    participant UDR as Spoke route table
    participant FW as Azure Firewall
    participant Service as Entra, Monitor, Teams, or HTTPS endpoint

    Agent->>NSG: Outbound request
    NSG->>UDR: Allowed subnet flow
    UDR->>FW: Default route to 10.1.0.4 or assigned firewall IP
    FW->>FW: Evaluate network/application policy
    FW->>Service: Forward permitted request
    Service-->>FW: Response
    FW-->>Agent: Return through peering
```

### VM egress

```mermaid
flowchart LR
    VM["VM private IP"]
    VmNsg["VM subnet NSG"]
    Route["0.0.0.0/0 UDR"]
    Firewall["Azure Firewall"]
    Snat["Firewall public IP SNAT"]
    Destination["Internet destination"]

    VM --> VmNsg --> Route --> Firewall --> Snat --> Destination
```

The VM does not require a public IP for outbound access.

### Optional VM ingress through firewall DNAT

DNAT is an operational step because the trusted source CIDR and VM private IP
are environment-specific. It is not created by the base Bicep modules.

```mermaid
sequenceDiagram
    participant Admin as Trusted administrator
    participant PIP as Firewall public IP:3389
    participant FW as Azure Firewall DNAT
    participant NSG as VM subnet NSG
    participant VM as VM private IP:3389

    Admin->>PIP: TCP 3389
    PIP->>FW: Match trusted source CIDR
    FW->>NSG: Translate destination to VM private IP
    NSG->>VM: Allow TCP 3389 from trusted source
    VM-->>FW: Reply follows 0.0.0.0/0 UDR
    FW-->>Admin: Symmetric translated response
```

Do not attach a direct public IP to a VM that retains the forced-tunnel UDR.
Inbound traffic would arrive through the VM public IP while replies would leave
through Azure Firewall, causing asymmetric routing.

### Agent build, creation, and publication

The post-provision hook performs data-plane operations:

```mermaid
sequenceDiagram
    participant Operator as Operator on VM
    participant ACR
    participant Foundry
    participant Entra as Microsoft Entra ID
    participant M365 as Microsoft 365

    Operator->>ACR: Build and push hosted-agent image
    Operator->>Foundry: Create hosted-agent version
    Foundry->>ACR: Pull image
    Foundry-->>Operator: Agent and blueprint identities
    Operator->>Entra: Assign project-scoped Foundry User role
    Operator->>Foundry: Patch BotServiceRbac endpoint
    Operator->>Foundry: Publish Microsoft 365 digital worker
    Foundry->>M365: Submit tenant publication request
```

The Container Registry currently has public network access enabled. The Foundry
account is private, but this sample does not make ACR, Log Analytics, or
Application Insights private.

### Teams interaction

```mermaid
sequenceDiagram
    participant User as Teams user
    participant Teams as Microsoft Teams
    participant Endpoint as M365 public agent endpoint
    participant Agent as Foundry hosted agent
    participant Model as Foundry model
    participant Tools as Microsoft 365 or configured MCP tools

    User->>Teams: Send message
    Teams->>Endpoint: Deliver activity
    Endpoint->>Agent: Activity protocol 2.0.0
    Agent->>Model: Responses API request
    Agent->>Tools: Optional tool calls
    Model-->>Agent: Model response
    Tools-->>Agent: Tool results
    Agent-->>Teams: Activity response
    Teams-->>User: Display response
```

## Security boundaries and limitations

- The Foundry account has public network access disabled.
- The Foundry private endpoint is reachable from the linked spoke.
- Hosted-agent and VM default egress traverses Azure Firewall.
- NSGs and firewall policy are both enforced; allowing a flow in only one is
  insufficient.
- The VM subnet denies unsolicited inbound traffic unless an NSG rule is added.
- The default HTTPS firewall rule allows any FQDN and should be narrowed for
  production.
- ACR and monitoring endpoints are not private in this sample.
- Azure Firewall diagnostics are not currently declared by the Bicep modules.
  Configure diagnostic settings to send structured `AZFW*` logs to the sample's
  Log Analytics workspace when traffic auditing is required.
- Azure Firewall, public IP, Log Analytics ingestion, and VMs incur charges.

## Important outputs

After provisioning, `azd env get-values` includes:

| Output | Use |
|---|---|
| `VIRTUAL_NETWORK_ID` | Workload spoke resource ID |
| `HUB_VIRTUAL_NETWORK_ID` | Hub resource ID |
| `AZURE_FIREWALL_ID` | Azure Firewall resource ID |
| `AZURE_FIREWALL_PRIVATE_IP` | UDR next-hop address |
| `SPOKE_ROUTE_TABLE_ID` | Route table associated with workload subnets |
| `AGENT_SUBNET_ID` | Foundry network-injection subnet |
| `VIRTUAL_MACHINE_SUBNET_ID` | Subnet for optional VMs |
| `PRIVATE_ENDPOINT_ID` | Foundry account private endpoint |
| `AZURE_AI_PROJECT_ENDPOINT` | Foundry project data-plane endpoint |
