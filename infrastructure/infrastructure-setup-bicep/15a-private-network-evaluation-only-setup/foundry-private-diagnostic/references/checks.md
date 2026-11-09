# Checks

Every check returns one result per resource or path it applies to: **OK**, **Problem** (with a severity), or **Could not check** (with a gap: *Blocking* means a problem could be hiding there; *Known limit* means the diagnostic cannot see it by design).

*Where* says whether the check reads Azure configuration (**Azure**) or tests from the machine running the diagnostic (**This machine**). *Layer* is the part of the path a problem sits in.

When `runner.match` can't confirm this machine is on the agent network, every **This machine** result that isn't OK gets `offPath: true`. Those results are listed under *From this machine* in the console and `report.md`, and don't count as problems or change the exit code. Run from a VM in the agent virtual network to test the agent's own path.


## Project

| Check | What it looks at | Layer | Where |
|---|---|---|---|
| `project.publicAccess` | Account public network access | Config | Azure |
| `project.injection` | Agent network injection | Config | Azure |
| `project.resource` | Foundry account provisioning | Config | Azure |
| `project.connections` | Project connections | Config | Azure |
| `project.identity` | Project managed identity | Access | Azure |

## Subnet

| Check | What it looks at | Layer | Where |
|---|---|---|---|
| `subnet.dnsServers` | Virtual network DNS servers | Name | Azure |
| `subnet.attachments` | Other services on the agent subnet | Config | Azure |
| `subnet.resource` | Agent subnet | Config | Azure |
| `subnet.delegation` | Agent subnet delegation | Config | Azure |
| `subnet.size` | Agent subnet size | Config | Azure |

## PrivateEndpoint

| Check | What it looks at | Layer | Where |
|---|---|---|---|
| `pe.exists` | Foundry account private endpoint | Config | Azure |
| `pe.addresses` | Foundry account private endpoint addresses | Config | Azure |
| `pe.placement` | Foundry account private endpoint network | Route | Azure |
| `pe.approval` | Foundry account private endpoint approval | Config | Azure |

## Dns

| Check | What it looks at | Layer | Where |
|---|---|---|---|
| `dns.record` | DNS record for the account endpoint | Name | Azure |
| `dns.vnetLink` | Private DNS zone link for the account private DNS zone | Name | Azure |
| `dns.zoneGroup` | Foundry account private DNS zone group | Name | Azure |
| `dns.customResolver` | Custom DNS servers for private zones | Name | Azure |

## Nsg

| Check | What it looks at | Layer | Where |
|---|---|---|---|
| `nsg.agentOutbound` | Agent subnet NSG outbound rules | Nsg | Azure |
| `nsg.peInbound` | Private endpoint subnet NSG inbound rules | Nsg | Azure |
| `nsg.runner` | This machine's NSG compared with the agent subnet | Nsg | This machine |

## Egress

| Check | What it looks at | Layer | Where |
|---|---|---|---|
| `egress.peSubnetPolicy` | Private endpoint traffic routing | Route | Azure |
| `egress.vwan` | Virtual WAN hub routing | Route | Azure |
| `egress.peering` | Virtual network peerings | Route | Azure |
| `egress.natGateway` | Agent subnet outbound access | Route | Azure |
| `egress.bgp` | Routes learned over BGP | Route | Azure |
| `egress.nextHopOwner` | Next hop owner | Route | Azure |
| `egress.routeTable` | Agent subnet route table | Route | Azure |

## Firewall

| Check | What it looks at | Layer | Where |
|---|---|---|---|
| `firewall.logQuery` | Firewall log query | Firewall | Azure |
| `firewall.dnsProxy` | Firewall DNS proxy for Monitor query traffic | Firewall | Azure |
| `firewall.snat` | Firewall SNAT port use | Firewall | Azure |
| `firewall.logs` | Firewall diagnostic logs | Firewall | Azure |
| `firewall.tlsInspection` | Firewall TLS inspection for Monitor query traffic | Firewall | Azure |
| `firewall.idps` | Firewall intrusion detection for Monitor query traffic | Firewall | Azure |
| `firewall.ruleMatch` | Firewall rules for Monitor query traffic | Firewall | Azure |
| `firewall.threatIntel` | Firewall threat intelligence | Firewall | Azure |
| `firewall.state` | Azure Firewall state | Firewall | Azure |

## Nva

| Check | What it looks at | Layer | Where |
|---|---|---|---|
| `nva.ipForwarding` | Appliance IP forwarding for Monitor query traffic | Route | Azure |
| `nva.rules` | Appliance rules for Monitor query traffic | Firewall | Azure |
| `nva.nsg` | Appliance network security groups for Monitor query traffic | Nsg | Azure |
| `onprem.route` | On-premises route for Monitor query traffic | Route | Azure |
| `nva.identified` | Network virtual appliance | Route | Azure |

## Storage

| Check | What it looks at | Layer | Where |
|---|---|---|---|
| `storage.authentication` | Storage connection authentication | Access | Azure |
| `storage.privatePolicy` | Storage private access | Config | Azure |
| `storage.resource` | Storage account | Config | Azure |
| `storage.subresources` | Storage private endpoint services | Config | Azure |
| `storage.connection` | Storage connection target | Config | Azure |

## Monitoring

| Check | What it looks at | Layer | Where |
|---|---|---|---|
| `monitoring.workspace` | Log Analytics workspace | Config | Azure |
| `monitoring.amplsDnsOwner` | Azure Monitor query DNS record owner | Name | Azure |
| `monitoring.amplsMode` | Azure Monitor private link scope access mode | Config | Azure |
| `monitoring.connection` | Application Insights connection target | Config | Azure |
| `monitoring.queryAccess` | Monitor query network access | Config | Azure |
| `monitoring.component` | Application Insights component | Config | Azure |
| `monitoring.amplsPe` | Azure Monitor private endpoint and DNS zones | Name | Azure |
| `monitoring.queryPath` | Monitor query route | Config | Azure |
| `monitoring.ampls` | Azure Monitor private link scope resources | Config | Azure |

## Models

| Check | What it looks at | Layer | Where |
|---|---|---|---|
| `model.deployment` | Model deployments | Config | Azure |
| `model.target` | Model target account | Config | Azure |
| `model.connection` | Model connection | Config | Azure |
| `model.authentication` | Model connection authentication | Access | Azure |

## Access

| Check | What it looks at | Layer | Where |
|---|---|---|---|
| `access.evaluationCaller` | Evaluation caller project data role | Access | Azure |
| `access.projectAssets` | Project identity project data role | Access | Azure |
| `access.projectStorage` | Project identity storage data role | Access | Azure |
| `access.runnerReads` | Diagnostic read access | Access | Azure |
| `access.traceReader` | Project identity trace read role | Access | Azure |
| `access.modelIdentity` | Project identity model role | Access | Azure |

## Probe

| Check | What it looks at | Layer | Where |
|---|---|---|---|
| `probe.fromMicrosoft` | Responder for the account endpoint | Response | This machine |
| `probe.comparison` | Monitor query hosts compared with management.azure.com | Response | This machine |
| `probe.tlsIssuer` | TLS certificate issuer for the account endpoint | Tls | This machine |
| `probe.path` | Connection to the account endpoint | Response | This machine |
| `probe.dns` | Name resolution for the account endpoint | Name | This machine |

## Runner

| Check | What it looks at | Layer | Where |
|---|---|---|---|
| `runner.location` | Location of this machine | Config | Azure |
| `runner.proxy` | Proxy on this machine | Config | This machine |
| `runner.match` | Network match between this machine and the agent subnet | Config | Azure |
| `runner.token` | Sign-in used by this run | Config | This machine |
