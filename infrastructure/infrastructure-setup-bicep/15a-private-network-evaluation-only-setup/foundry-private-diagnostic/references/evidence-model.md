# Evidence model

`evidence.json` is the only input to the checks. The collector writes it; the checks read it and nothing else.
This file defines its shape. Collectors and checks must both follow it.

## Top level

```jsonc
{
  "schema": 1,
  "tool": { "commit": "abc1234" },
  "run": { "startedUtc": "…", "durationMs": 0, "masked": false, "project": "<project id>",
           "runner": { "os": "Windows", "tokenSource": "ManagedIdentity|AzAccounts",
                       "azureVmResourceId": "<vm id>|null", "dnsServers": ["10.0.0.4"],
                       "proxy": { "system": "none|<host>", "env": ["HTTPS_PROXY"] } } },
  "discovery": { … },          // see below
  "requests": [ … ],           // every Azure read, see below
  "probes": [ … ],             // every network probe from this machine, see below
  "collectorErrors": [ { "stage": "token|discover|probe", "errorKind": "…", "message": "…" } ]
}
```

## requests[]

```jsonc
{ "key": "GET <path>", "method": "GET", "api": "ARM|ResourceGraph", "path": "<ARM path, no query>",
  "apiVersion": "…", "query": null, "status": 200, "errorKind": null, "collectedUtc": "…", "data": … }
```

- `key` is `"<METHOD> <path>"`. Paths are compared case-insensitively. Query strings are not part of the key.
- The only POST is Resource Graph: `POST /providers/Microsoft.ResourceGraph/resources#<label>`; `query` holds the text.
  Labels are `nextHop:<ip>` (who owns a next-hop address) and `virtualHubs` (which Virtual WAN hub the agent VNet connects to).
  Metrics are read with GET.
- `errorKind`: `null` (200), `NotFound` (404), `Forbidden` (403), `Unauthorized` (401), `Throttled` (429), `Timeout`, `Network`, `Other`.
- `data` for a single resource is the ARM object reduced to allowlisted fields: `{ id, name, type, location, kind, sku{name, tier}, identity, properties: {…} }`.
- `data` for a collection (path ends in a collection name) is an array of such objects (all pages merged).

### Paths the collector reads and fields checks may use

Only the fields listed here are kept. Anything else is dropped by the collector.

| Path | Fields (under `properties` unless noted) |
|---|---|
| `{project}` | `identity.type`, `identity.principalId`, `provisioningState` |
| `{account}` | `identity.*`, `provisioningState`, `publicNetworkAccess`, `networkAcls.defaultAction`, `networkInjections[]{scenario, subnetArmId, useMicrosoftManagedNetwork}`, `endpoints{}` (https URLs only), `disableLocalAuth` |
| `{project}/connections` | `name`, `category`, `target`, `authType`, `metadata.ResourceId` |
| `{account}/deployments` | `name`, `provisioningState`, `model{name, format, version}` |
| `{target}/privateEndpointConnections` | `privateEndpoint.id`, `privateLinkServiceConnectionState.status`, `groupIds` |
| `{subnet}` | `addressPrefix`, `addressPrefixes`, `delegations[]{name, properties.serviceName}`, `serviceAssociationLinks[]{properties.linkedResourceType}`, `networkSecurityGroup.id`, `routeTable.id`, `natGateway.id`, `privateEndpointNetworkPolicies`, `defaultOutboundAccess`, `ipConfigurations[].id` |
| `{vnet}` | `addressSpace.addressPrefixes`, `dhcpOptions.dnsServers`, `subnets[]{name, id}` |
| `{vnet}/virtualNetworkPeerings` | `name`, `peeringState`, `remoteVirtualNetwork.id`, `allowForwardedTraffic`, `allowGatewayTransit`, `useRemoteGateways` |
| `{nsg}` | `securityRules[]`, `defaultSecurityRules[]` with `{name, priority, direction, access, protocol, sourceAddressPrefix(es), destinationAddressPrefix(es), destinationPortRange(s), sourceApplicationSecurityGroups, destinationApplicationSecurityGroups}` |
| `{routeTable}` | `disableBgpRoutePropagation`, `routes[]{name, addressPrefix, nextHopType, nextHopIpAddress}` |
| `{privateEndpoint}` | `subnet.id`, `customDnsConfigs[]{fqdn, ipAddresses}`, `networkInterfaces[].id`, `privateLinkServiceConnections[]` and `manualPrivateLinkServiceConnections[]` `{properties.privateLinkServiceId, groupIds, privateLinkServiceConnectionState.status}` |
| `{privateEndpoint}/privateDnsZoneGroups` | `privateDnsZoneConfigs[]{name, properties.privateDnsZoneId, properties.recordSets[]{recordSetName, fqdn, ipAddresses}}` |
| `{privateDnsZone}/virtualNetworkLinks` | `virtualNetwork.id`, `virtualNetworkLinkState`, `registrationEnabled` |
| `{privateDnsZone}/A` | `name`, `fqdn`, `aRecords[]{ipv4Address}` |
| `{storage}` | `kind`, `provisioningState`, `publicNetworkAccess`, `allowSharedKeyAccess`, `networkAcls{defaultAction, bypass}`, `primaryEndpoints{blob, file, queue, table}` |
| `{appInsights}` | `provisioningState`, `WorkspaceResourceId`, `publicNetworkAccessForIngestion`, `publicNetworkAccessForQuery`, `privateLinkScopedResources[]{ResourceId, ScopeId}` |
| `{workspace}` | `provisioningState`, `publicNetworkAccessForIngestion`, `publicNetworkAccessForQuery`, `features.enableLogAccessUsingOnlyResourcePermissions`, `privateLinkScopedResources[]{resourceId, scopeId}` |
| `{ampls}` | `accessModeSettings{ingestionAccessMode, queryAccessMode, exclusions}`, `privateEndpointConnections[]{properties.privateEndpoint.id, properties.privateLinkServiceConnectionState.status}` |
| `{ampls}/scopedResources` | `linkedResourceId`, `provisioningState` |
| `{scope}/providers/Microsoft.Authorization/roleAssignments` | `principalId`, `principalType`, `roleDefinitionId`, `scope`, `conditionPresent` (read with `$filter=atScope()`) |
| `{azureFirewall}` | `provisioningState`, `sku{name, tier}`, `firewallPolicy.id`, `threatIntelMode`, `ipConfigurations[]{properties.privateIPAddress}`, `hubIPAddresses.privateIPAddress`, `virtualHub.id`, `additionalProperties{"Network.DNS.EnableProxy"}`, `applicationRuleCollections[]`, `networkRuleCollections[]` (classic rules, same rule fields as policy rules) |
| `{firewallPolicy}` | `sku.tier`, `basePolicy.id`, `threatIntelMode`, `intrusionDetection.mode`, `transportSecurity.certificateAuthority.name`, `dnsSettings{enableProxy, servers}` |
| `{firewallPolicy}/ruleCollectionGroups` | `priority`, `ruleCollections[]{ruleCollectionType, name, priority, action.type, rules[]{ruleType, name, sourceAddresses, sourceIpGroups, targetFqdns, fqdnTags, webCategories, targetUrls, protocols[]{protocolType, port}, terminateTLS, destinationAddresses, destinationFqdns, destinationPorts, ipProtocols}}` |
| `{azureFirewall}/providers/Microsoft.Insights/diagnosticSettings` | `name`, `workspaceId`, `storageAccountId`, `eventHubName`, `logs[]{category, categoryGroup, enabled}` |
| `{azureFirewall}/providers/Microsoft.Insights/metrics` | reduced by collector to `{ metric: "SNATPortUtilization", timespan: "PT24H", maximum: <number|null>, average: <number|null> }` |
| `{virtualHub}` | `provisioningState`, `azureFirewall.id`, `routingState` |
| `{virtualHub}/hubVirtualNetworkConnections` | `remoteVirtualNetwork.id` |
| `{virtualHub}/routingIntent` | `routingPolicies[]{name, destinations, nextHop}` |
| `{networkInterface}` | `enableIPForwarding`, `networkSecurityGroup.id`, `virtualMachine.id`, `ipConfigurations[]{id, properties.privateIPAddress, properties.subnet.id, properties.loadBalancerBackendAddressPools[].id}` (for an appliance NIC the collector also reads its NSG, its subnet and that subnet's NSG) |
| `{virtualMachine}` | `plan{publisher, product}`, `storageProfile.imageReference{publisher, offer, sku}`, `networkProfile.networkInterfaces[].id` |
| `{loadBalancer}` | `sku.name`, `frontendIPConfigurations[]{properties.privateIPAddress, properties.subnet.id}`, `backendAddressPools[]{id, properties.backendIPConfigurations[].id}` |

## discovery

What the collector found and decided. Checks use it to know which resources matter; resource data still comes from `requests`.

```jsonc
"discovery": {
  "project": "<project id>",
  "account": "<account id>",
  "agentSubnet": "<subnet id>|null",              // account networkInjections, scenario 'agent'
  "connections": [ { "name": "…", "category": "AzureStorageAccount|AppInsights|AzureOpenAI|AIServices|…",
                     "resource": "<target resource id>|null", "path": "Storage|MonitorQuery|Models|null" } ],
  "dependencies": [
    { "kind": "Account|Storage|AppInsights|Workspace|Ampls|Model",
      "path": "Foundry|Storage|MonitorQuery|Models",
      "resource": "<id>",
      "connection": "<connection name>|null",
      "privateEndpoints": ["<pe id>"],             // from {resource}/privateEndpointConnections (Ampls: from {ampls})
      "hosts": ["acct.services.ai.azure.com"] }    // FQDNs the agent uses for this dependency
  ],
  "paths": { "Foundry": { "used": true, "reason": "project" },
             "Storage": { "used": true, "reason": "connection <name>" },
             "MonitorQuery": { "used": true, "reason": "connection <name>" },
             "Models": { "used": false, "reason": "no model connection" } },
  "nextHops": [ { "ip": "10.0.1.4", "source": "routeTable|virtualHub",
                  "owner": "<id>|null", "ownerType": "AzureFirewall|LoadBalancer|NetworkInterface|null",
                  "request": "POST /providers/Microsoft.ResourceGraph/resources#nextHop:10.0.1.4" } ],
  "virtualHub": "<hub id>|null",                   // when the agent VNet is connected to a Virtual WAN hub
  "firewalls": ["<azureFirewall id>"],             // Azure Firewalls found in the agent egress path
  "runner": { "vm": "<id>|null", "nic": "<id>|null", "subnet": "<id>|null" },
  "evaluationCaller": "<object id>|null"           // optional: identity that starts evaluations; access.evaluationCaller runs only when set
}
```

Monitor query hosts are always `api.loganalytics.io` and `api.applicationinsights.io` (path `MonitorQuery`).

## probes[]

```jsonc
{ "host": "api.loganalytics.io", "port": 443,
  "purpose": "Foundry|Storage|MonitorQuery|Models|Comparison",
  "dns": { "resolver": "10.0.0.4|null", "cnameChain": ["…"], "answers": ["10.1.5.13"], "ms": 12, "error": null },
  "attempts": [ { "ip": "10.1.5.13",
                  "tcp":  { "ok": true, "ms": 31, "error": null },          // Timeout|Refused|Reset|Unreachable
                  "tls":  { "ok": true, "ms": 80, "issuer": "CN=…", "rootIssuer": "CN=…", "subject": "CN=…",
                            "error": null },                                  // Timeout|Untrusted|NameMismatch|Reset|Other
                  "http": { "status": 401, "firstByteMs": 120, "server": "…", "msRequestId": true,
                            "error": null },                                  // NoResponse|Reset|Other
                  "outcome": "Reachable|Stalled|Blocked|Refused|Reset|TlsFailed" } ],
  "outcome": "Reachable|Stalled|Blocked|Refused|Reset|TlsFailed|DnsFailed|Skipped",
  "budgetHit": false }
```

Outcome rules: TCP timeout → Blocked; TCP refused → Refused; reset at any stage → Reset; TLS timeout (connection accepted,
then silence during the handshake) → Stalled; other TLS failure → TlsFailed;
TLS ok but no first byte within 20 s → Stalled; any HTTP status → Reachable. Probe outcome = worst attempt
(Stalled > Blocked > Reset > Refused > TlsFailed > Reachable).
`dns.error`: `NXDOMAIN` (name doesn't exist), `Timeout`, `ServerFailure` or `Other`; `answers` is empty when it is set.
`Skipped`: the probe didn't run — `budgetHit: true` when the ~60 s probe phase ran out first, `false` when probes were
turned off for the run (then `dns` may be null and `attempts` empty).
