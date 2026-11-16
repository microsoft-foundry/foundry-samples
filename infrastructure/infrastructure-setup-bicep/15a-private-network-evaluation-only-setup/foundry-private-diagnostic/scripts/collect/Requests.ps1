# Azure REST reads. Every request is checked against an allowlist (path pattern, pinned API version) and every
# response is reduced to the fields listed in references/evidence-model.md before it is kept.

$script:DiagArmHost = 'management.azure.com'
$script:DiagGraphApi = '2022-10-01'

# Field lists use '/' as separator because some ARM keys contain dots. 'x[]' maps over an array.
$script:DiagIdentity = @('identity/type', 'identity/principalId')
$script:DiagProjections = @{
    Project          = $script:DiagIdentity + @('properties/provisioningState')
    Account          = $script:DiagIdentity + @('properties/provisioningState', 'properties/publicNetworkAccess', 'properties/networkAcls/defaultAction',
        'properties/networkInjections[]/scenario', 'properties/networkInjections[]/subnetArmId', 'properties/networkInjections[]/useMicrosoftManagedNetwork',
        'properties/disableLocalAuth')
    Connection       = @('properties/category', 'properties/authType', 'properties/metadata/ResourceId')
    Deployment       = @('properties/provisioningState', 'properties/model/name', 'properties/model/format', 'properties/model/version')
    PeConnection     = @('properties/privateEndpoint/id', 'properties/privateLinkServiceConnectionState/status', 'properties/groupIds')
    Subnet           = @('properties/addressPrefix', 'properties/addressPrefixes', 'properties/delegations[]/name', 'properties/delegations[]/properties/serviceName',
        'properties/serviceAssociationLinks[]/name', 'properties/serviceAssociationLinks[]/properties/linkedResourceType', 'properties/networkSecurityGroup/id',
        'properties/routeTable/id', 'properties/natGateway/id', 'properties/privateEndpointNetworkPolicies', 'properties/defaultOutboundAccess',
        'properties/ipConfigurations[]/id')
    Vnet             = @('properties/addressSpace/addressPrefixes', 'properties/dhcpOptions/dnsServers', 'properties/subnets[]/name', 'properties/subnets[]/id')
    Peering          = @('properties/peeringState', 'properties/remoteVirtualNetwork/id', 'properties/allowForwardedTraffic', 'properties/allowGatewayTransit',
        'properties/useRemoteGateways')
    Nsg              = foreach ($set in 'securityRules', 'defaultSecurityRules') {
        "properties/$set[]/name"
        foreach ($f in 'priority', 'direction', 'access', 'protocol', 'sourceAddressPrefix', 'sourceAddressPrefixes', 'destinationAddressPrefix',
            'destinationAddressPrefixes', 'destinationPortRange', 'destinationPortRanges', 'sourceApplicationSecurityGroups', 'destinationApplicationSecurityGroups') {
            "properties/$set[]/properties/$f"
        }
    }
    RouteTable       = @('properties/disableBgpRoutePropagation', 'properties/routes[]/name', 'properties/routes[]/properties/addressPrefix',
        'properties/routes[]/properties/nextHopType', 'properties/routes[]/properties/nextHopIpAddress')
    PrivateEndpoint  = @('properties/subnet/id', 'properties/customDnsConfigs[]/fqdn', 'properties/customDnsConfigs[]/ipAddresses', 'properties/networkInterfaces[]/id') +
    @(foreach ($set in 'privateLinkServiceConnections', 'manualPrivateLinkServiceConnections') {
            "properties/$set[]/name", "properties/$set[]/properties/privateLinkServiceId", "properties/$set[]/properties/groupIds",
            "properties/$set[]/properties/privateLinkServiceConnectionState/status"
        })
    ZoneGroup        = @('properties/privateDnsZoneConfigs[]/name', 'properties/privateDnsZoneConfigs[]/properties/privateDnsZoneId',
        'properties/privateDnsZoneConfigs[]/properties/recordSets[]/recordSetName', 'properties/privateDnsZoneConfigs[]/properties/recordSets[]/fqdn',
        'properties/privateDnsZoneConfigs[]/properties/recordSets[]/ipAddresses')
    ZoneLink         = @('properties/virtualNetwork/id', 'properties/virtualNetworkLinkState', 'properties/registrationEnabled')
    ARecord          = @('properties/fqdn', 'properties/aRecords[]/ipv4Address')
    Storage          = @('properties/provisioningState', 'properties/publicNetworkAccess', 'properties/allowSharedKeyAccess', 'properties/networkAcls/defaultAction',
        'properties/networkAcls/bypass', 'properties/primaryEndpoints/blob', 'properties/primaryEndpoints/file', 'properties/primaryEndpoints/queue',
        'properties/primaryEndpoints/table')
    Component        = @('properties/provisioningState', 'properties/WorkspaceResourceId', 'properties/publicNetworkAccessForIngestion',
        'properties/publicNetworkAccessForQuery', 'properties/privateLinkScopedResources[]/ResourceId', 'properties/privateLinkScopedResources[]/ScopeId')
    Workspace        = @('properties/provisioningState', 'properties/publicNetworkAccessForIngestion', 'properties/publicNetworkAccessForQuery',
        'properties/features/enableLogAccessUsingOnlyResourcePermissions', 'properties/privateLinkScopedResources[]/resourceId',
        'properties/privateLinkScopedResources[]/scopeId')
    Ampls            = @('properties/accessModeSettings/ingestionAccessMode', 'properties/accessModeSettings/queryAccessMode', 'properties/accessModeSettings/exclusions',
        'properties/privateEndpointConnections[]/properties/privateEndpoint/id', 'properties/privateEndpointConnections[]/properties/privateLinkServiceConnectionState/status')
    ScopedResource   = @('properties/linkedResourceId', 'properties/provisioningState')
    RoleAssignment   = @('properties/principalId', 'properties/principalType', 'properties/roleDefinitionId', 'properties/scope')
    Firewall         = @('properties/provisioningState', 'properties/sku/name', 'properties/sku/tier', 'properties/firewallPolicy/id', 'properties/threatIntelMode',
        'properties/ipConfigurations[]/properties/privateIPAddress', 'properties/hubIPAddresses/privateIPAddress', 'properties/virtualHub/id',
        'properties/additionalProperties/Network.DNS.EnableProxy') +
    @(foreach ($set in 'applicationRuleCollections', 'networkRuleCollections') {
            "properties/$set[]/name", "properties/$set[]/properties/priority", "properties/$set[]/properties/action/type"
            foreach ($f in 'name', 'sourceAddresses', 'sourceIpGroups', 'targetFqdns', 'fqdnTags', 'protocols', 'destinationAddresses', 'destinationFqdns', 'destinationPorts') {
                "properties/$set[]/properties/rules[]/$f"
            }
        })
    FirewallPolicy   = @('properties/sku/tier', 'properties/basePolicy/id', 'properties/threatIntelMode', 'properties/intrusionDetection/mode',
        'properties/transportSecurity/certificateAuthority/name', 'properties/dnsSettings/enableProxy', 'properties/dnsSettings/servers')
    RuleGroup        = @('properties/priority', 'properties/ruleCollections[]/ruleCollectionType', 'properties/ruleCollections[]/name',
        'properties/ruleCollections[]/priority', 'properties/ruleCollections[]/action/type') +
    @(foreach ($f in 'ruleType', 'name', 'sourceAddresses', 'sourceIpGroups', 'targetFqdns', 'fqdnTags', 'webCategories', 'targetUrls', 'protocols', 'terminateTLS',
            'destinationAddresses', 'destinationFqdns', 'destinationPorts', 'ipProtocols') { "properties/ruleCollections[]/rules[]/$f" })
    DiagnosticSetting = @('properties/workspaceId', 'properties/storageAccountId', 'properties/eventHubName', 'properties/logs[]/category',
        'properties/logs[]/categoryGroup', 'properties/logs[]/enabled')
    VirtualHub       = @('properties/provisioningState', 'properties/azureFirewall/id', 'properties/routingState')
    HubConnection    = @('properties/remoteVirtualNetwork/id')
    RoutingIntent    = @('properties/routingPolicies[]/name', 'properties/routingPolicies[]/destinations', 'properties/routingPolicies[]/nextHop')
    Nic              = @('properties/enableIPForwarding', 'properties/networkSecurityGroup/id', 'properties/virtualMachine/id', 'properties/ipConfigurations[]/id',
        'properties/ipConfigurations[]/properties/privateIPAddress', 'properties/ipConfigurations[]/properties/subnet/id',
        'properties/ipConfigurations[]/properties/loadBalancerBackendAddressPools[]/id')
    Vm               = @('plan/publisher', 'plan/product', 'properties/storageProfile/imageReference/publisher', 'properties/storageProfile/imageReference/offer',
        'properties/storageProfile/imageReference/sku', 'properties/networkProfile/networkInterfaces[]/id')
    LoadBalancer     = @('properties/frontendIPConfigurations[]/properties/privateIPAddress', 'properties/frontendIPConfigurations[]/properties/subnet/id',
        'properties/backendAddressPools[]/id', 'properties/backendAddressPools[]/properties/backendIPConfigurations[]/id')
}

function Get-DiagArmRule {
    param([string]$Path)
    $rg = '/subscriptions/[0-9a-f-]{36}/resourceGroups/[^/]+/providers/'
    $n = "${rg}Microsoft\.Network/"
    $acct = "${rg}Microsoft\.CognitiveServices/accounts/[^/]+"
    $any = "${rg}[^/]+/[^/]+/[^/]+(?:/[^/]+/[^/]+)*"
    $fw = "${n}azureFirewalls/[^/]+"
    $rules = @(
        , @("$acct/projects/[^/]+", '2025-06-01', 'Project', $false)
        , @("$acct", '2025-06-01', 'Account', $false)
        , @("$acct/projects/[^/]+/connections", '2025-06-01', 'Connection', $true)
        , @("$acct/deployments", '2025-06-01', 'Deployment', $true)
        , @("$acct/privateEndpointConnections", '2025-06-01', 'PeConnection', $true)
        , @("${rg}Microsoft\.Storage/storageAccounts/[^/]+", '2023-05-01', 'Storage', $false)
        , @("${rg}Microsoft\.Storage/storageAccounts/[^/]+/privateEndpointConnections", '2023-05-01', 'PeConnection', $true)
        , @("${n}virtualNetworks/[^/]+", '2024-05-01', 'Vnet', $false)
        , @("${n}virtualNetworks/[^/]+/subnets/[^/]+", '2024-05-01', 'Subnet', $false)
        , @("${n}virtualNetworks/[^/]+/virtualNetworkPeerings", '2024-05-01', 'Peering', $true)
        , @("${n}networkSecurityGroups/[^/]+", '2024-05-01', 'Nsg', $false)
        , @("${n}routeTables/[^/]+", '2024-05-01', 'RouteTable', $false)
        , @("${n}privateEndpoints/[^/]+", '2024-05-01', 'PrivateEndpoint', $false)
        , @("${n}privateEndpoints/[^/]+/privateDnsZoneGroups", '2024-05-01', 'ZoneGroup', $true)
        , @("${n}privateDnsZones/[^/]+/virtualNetworkLinks", '2020-06-01', 'ZoneLink', $true)
        , @("${n}privateDnsZones/[^/]+/A", '2020-06-01', 'ARecord', $true)
        , @("${rg}Microsoft\.Insights/components/[^/]+", '2020-02-02', 'Component', $false)
        , @("${rg}Microsoft\.OperationalInsights/workspaces/[^/]+", '2023-09-01', 'Workspace', $false)
        , @("${rg}Microsoft\.Insights/privateLinkScopes/[^/]+", '2021-07-01-preview', 'Ampls', $false)
        , @("${rg}Microsoft\.Insights/privateLinkScopes/[^/]+/scopedResources", '2021-07-01-preview', 'ScopedResource', $true)
        , @("$any/providers/Microsoft\.Authorization/roleAssignments", '2022-04-01', 'RoleAssignment', $true)
        , @("$fw", '2024-05-01', 'Firewall', $false)
        , @("$fw/providers/Microsoft\.Insights/diagnosticSettings", '2021-05-01-preview', 'DiagnosticSetting', $true)
        , @("$fw/providers/Microsoft\.Insights/metrics", '2023-10-01', 'Metrics', $false)
        , @("${n}firewallPolicies/[^/]+", '2024-05-01', 'FirewallPolicy', $false)
        , @("${n}firewallPolicies/[^/]+/ruleCollectionGroups", '2024-05-01', 'RuleGroup', $true)
        , @("${n}virtualHubs/[^/]+", '2024-05-01', 'VirtualHub', $false)
        , @("${n}virtualHubs/[^/]+/hubVirtualNetworkConnections", '2024-05-01', 'HubConnection', $true)
        , @("${n}virtualHubs/[^/]+/routingIntent", '2024-05-01', 'RoutingIntent', $true)
        , @("${n}networkInterfaces/[^/]+", '2024-05-01', 'Nic', $false)
        , @("${n}loadBalancers/[^/]+", '2024-05-01', 'LoadBalancer', $false)
        , @("${rg}Microsoft\.Compute/virtualMachines/[^/]+", '2024-07-01', 'Vm', $false)
    )
    foreach ($rule in $rules) {
        if ($Path -match ('(?i)^' + $rule[0] + '$')) { return @{ ApiVersion = $rule[1]; Kind = $rule[2]; Collection = $rule[3] } }
    }
    $null
}

function Test-DiagArmPath {
    param([string]$Path)
    $Path -and $Path -match '^/subscriptions/[0-9a-fA-F-]{36}/' -and $Path -notmatch '[\\?#%\s''"]|//|(^|/)\.\.?(/|$)'
}

function Get-DiagMember {
    param($Object, [string]$Name)
    if ($Object -isnot [Collections.IDictionary]) { return $null }
    foreach ($key in $Object.Keys) { if ($key -ieq $Name) { return , $Object[$key] } }
    $null
}

# Copies one allowlisted field path from $Source into $Target, using the casing from the allowlist.
function Copy-DiagField {
    param($Source, $Target, [string[]]$Segments)
    if ($null -eq $Source -or $Source -isnot [Collections.IDictionary]) { return }
    $segment = $Segments[0]
    $isArray = $segment.EndsWith('[]')
    $name = $segment.TrimEnd('[', ']')
    $value = Get-DiagMember $Source $name
    if ($null -eq $value) { return }
    $rest = @($Segments | Select-Object -Skip 1)
    if (!$rest.Count) { $Target[$name] = $value; return }
    if ($isArray) {
        $items = @($value)
        if (!$Target.Contains($name)) { $Target[$name] = @(foreach ($i in $items) { [ordered]@{} }) }
        for ($i = 0; $i -lt $items.Count; $i++) { Copy-DiagField $items[$i] $Target[$name][$i] $rest }
        return
    }
    if (!$Target.Contains($name)) { $Target[$name] = [ordered]@{} }
    Copy-DiagField $value $Target[$name] $rest
}

function ConvertTo-DiagProjected {
    param($Item, [string]$Kind)
    $out = [ordered]@{}
    foreach ($f in 'id', 'name', 'type', 'location', 'kind') { $v = Get-DiagMember $Item $f; if ($null -ne $v) { $out[$f] = $v } }
    $sku = Get-DiagMember $Item 'sku'
    if ($sku -is [Collections.IDictionary]) { $out.sku = [ordered]@{ name = (Get-DiagMember $sku 'name'); tier = (Get-DiagMember $sku 'tier') } }
    foreach ($path in $script:DiagProjections[$Kind]) { Copy-DiagField $Item $out ($path -split '/') }
    $props = Get-DiagMember $Item 'properties'
    if (!$out.Contains('properties')) { $out.properties = [ordered]@{} }
    switch ($Kind) {
        'Account' {
            $endpoints = Get-DiagMember $props 'endpoints'
            if ($endpoints -is [Collections.IDictionary]) {
                $kept = [ordered]@{}
                foreach ($k in $endpoints.Keys) { if ("$($endpoints[$k])" -match '^https://[^/?#@]+/?$') { $kept[$k] = $endpoints[$k] } }
                $out.properties.endpoints = $kept
            }
        }
        'Connection' {
            # target is a URL or a resource ID; drop any query string (could hold a SAS).
            $target = "$(Get-DiagMember $props 'target')"
            if ($target) { $out.properties.target = ($target -split '[?#]')[0] }
            $metadata = Get-DiagMember $props 'metadata'
            $rid = Get-DiagMember $metadata 'ResourceId'
            if ($rid) { $out.properties.metadata = [ordered]@{ ResourceId = $rid } }
        }
        'RoleAssignment' {
            $condition = Get-DiagMember $props 'condition'
            $out.properties.conditionPresent = [bool]("$condition".Trim())
        }
    }
    $out
}

function ConvertTo-DiagMetrics {
    param($Body)
    $series = Get-DiagMember $Body 'value'
    $values = @(foreach ($m in @($series)) {
            $ts = Get-DiagMember $m 'timeseries'
            foreach ($t in @($ts)) { $data = Get-DiagMember $t 'data'; foreach ($d in @($data)) { $d } }
        })
    $max = @($values | ForEach-Object { Get-DiagMember $_ 'maximum' } | Where-Object { $null -ne $_ })
    $avg = @($values | ForEach-Object { Get-DiagMember $_ 'average' } | Where-Object { $null -ne $_ })
    [ordered]@{
        metric  = 'SNATPortUtilization'; timespan = 'PT24H'
        maximum = $(if ($max.Count) { [double]($max | Measure-Object -Maximum).Maximum } else { $null })
        average = $(if ($avg.Count) { [math]::Round([double]($avg | Measure-Object -Average).Average, 2) } else { $null })
    }
}

function Get-DiagErrorKind {
    param([Nullable[int]]$Status)
    switch ($Status) { 200 { $null } 401 { 'Unauthorized' } 403 { 'Forbidden' } 404 { 'NotFound' } 429 { 'Throttled' } 408 { 'Timeout' } 504 { 'Timeout' } default { 'Other' } }
}

function Invoke-DiagDefaultHttp {
    param([string]$Method, [string]$Uri, [hashtable]$Headers, [string]$Body, [int]$TimeoutSec)
    $p = @{ Method = $Method; Uri = $Uri; Headers = $Headers; TimeoutSec = $TimeoutSec; SkipHttpErrorCheck = $true; ErrorAction = 'Stop' }
    if ($Body) { $p.Body = $Body; $p.ContentType = 'application/json' }
    $r = Invoke-WebRequest @p
    $retry = $null
    if ($r.Headers -and $r.Headers['Retry-After']) { $retry = "$(@($r.Headers['Retry-After'])[0])" }
    @{ Status = [int]$r.StatusCode; Content = "$($r.Content)"; RetryAfter = $retry }
}

# Sends one HTTP request with retries on 429/503/504. Returns @{ Status; Body; ErrorKind }.
function Send-DiagHttp {
    param($Ctx, [string]$Method, [string]$Uri, [string]$Body)
    $headers = @{ Authorization = "Bearer $($Ctx.Token)"; 'x-ms-client-request-id' = [guid]::NewGuid().ToString() }
    for ($attempt = 0; ; $attempt++) {
        try { $r = & $Ctx.Http $Method $Uri $headers $Body $Ctx.RequestTimeoutSec }
        catch {
            $kind = $(if ($_.Exception -is [TimeoutException] -or $_.Exception -is [Threading.Tasks.TaskCanceledException] -or
                    $_.Exception.InnerException -is [TimeoutException]) { 'Timeout' } else { 'Network' })
            if ($attempt -lt 2) { & $Ctx.Sleep (2 * ($attempt + 1)); continue }
            return @{ Status = $null; Body = $null; ErrorKind = $kind }
        }
        if ($r.Status -in 429, 503, 504 -and $attempt -lt 3) {
            $wait = 2 * [math]::Pow(2, $attempt)
            $ra = 0; if ([int]::TryParse("$($r.RetryAfter)", [ref]$ra) -and $ra -gt 0) { $wait = [math]::Min($ra, 10) }
            & $Ctx.Sleep $wait
            continue
        }
        $parsed = $null
        if ($r.Status -eq 200) {
            try { $parsed = $r.Content | ConvertFrom-Json -AsHashtable -Depth 100 -ErrorAction Stop }
            catch { return @{ Status = $r.Status; Body = $null; ErrorKind = 'Other' } }
        }
        return @{ Status = $r.Status; Body = $parsed; ErrorKind = (Get-DiagErrorKind $r.Status) }
    }
}

function Add-DiagCollectorError {
    param($Ctx, [string]$Stage, [string]$ErrorKind, [string]$Message)
    $Ctx.Errors.Add([ordered]@{ stage = $Stage; errorKind = $ErrorKind; message = $Message })
}

function Test-DiagBudget {
    param($Ctx)
    if ($Ctx.Requests.Count -lt $Ctx.Budget) { return $true }
    if (!$Ctx.BudgetReported) {
        $Ctx.BudgetReported = $true
        Add-DiagCollectorError $Ctx 'discover' 'Budget' "Stopped reading Azure after $($Ctx.Budget) requests; some resources were not read."
    }
    $false
}

function Add-DiagRequestRecord {
    param($Ctx, [string]$Method, [string]$Api, [string]$Path, [string]$Key, [string]$ApiVersion, [string]$Query, $Status, [string]$ErrorKind, $Data)
    $record = [ordered]@{
        key = $Key; method = $Method; api = $Api; path = $Path; apiVersion = $ApiVersion; query = $(if ($Query) { $Query } else { $null })
        status = $Status; errorKind = $(if ($Status -eq 200) { $null } else { $ErrorKind })
        collectedUtc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        data = $(if ($Status -eq 200) { $Data } else { $null })
    }
    $Ctx.Requests.Add($record)
    $Ctx.Cache[$Key.ToLowerInvariant()] = $record
    $record
}

function Test-DiagNextLink {
    param([string]$Link, [string]$Path, [string]$ApiVersion)
    $u = $null
    if (![uri]::TryCreate($Link, [UriKind]::Absolute, [ref]$u) -or $u.Scheme -ne 'https' -or $u.Host -ne $script:DiagArmHost -or !$u.IsDefaultPort -or
        $u.UserInfo -or $u.Fragment -or $u.AbsolutePath.TrimEnd('/') -ine $Path) { return $false }
    foreach ($pair in $u.Query.TrimStart('?').Split('&', [StringSplitOptions]::RemoveEmptyEntries)) {
        $parts = $pair.Split('=', 2)
        $name = [uri]::UnescapeDataString($parts[0])
        $value = $(if ($parts.Count -eq 2) { [uri]::UnescapeDataString($parts[1]) } else { '' })
        if ($name -eq 'api-version' -and $value -ne $ApiVersion) { return $false }
        if ($name -eq '$filter' -and $value -ne 'atScope()') { return $false }
        if ($name -notin 'api-version', '$skiptoken', '$skipToken', 'skiptoken', '$filter') { return $false }
    }
    $true
}

# GET one allowlisted ARM path (all pages for collections). Returns the request record, or $null when the
# path isn't allowlisted or the request budget is spent.
function Invoke-DiagArm {
    param([Parameter(Mandatory)]$Ctx, [string]$Path)
    if (!(Test-DiagArmPath $Path)) { return $null }
    $Path = $Path.TrimEnd('/')
    $key = "GET $Path"
    $cached = $Ctx.Cache[$key.ToLowerInvariant()]
    if ($cached) { return $cached }
    $rule = Get-DiagArmRule $Path
    if (!$rule) { return $null }
    if (!(Test-DiagBudget $Ctx)) { return $null }

    $query = "api-version=$($rule.ApiVersion)"
    $queryText = $null
    if ($rule.Kind -eq 'RoleAssignment') { $query += '&$filter=atScope()'; $queryText = '$filter=atScope()' }
    if ($rule.Kind -eq 'Metrics') {
        $metricQuery = 'metricnames=SNATPortUtilization&timespan=PT24H&interval=PT1H&aggregation=Maximum,Average'
        $query += "&$metricQuery"; $queryText = $metricQuery
    }
    $uri = "https://$($script:DiagArmHost)$($Path)?$query"
    $items = [Collections.Generic.List[object]]::new()
    for ($page = 0; $page -lt 25; $page++) {
        $r = Send-DiagHttp $Ctx 'GET' $uri $null
        if ($r.Status -ne 200) {
            return Add-DiagRequestRecord $Ctx 'GET' 'ARM' $Path $key $rule.ApiVersion $queryText $r.Status $r.ErrorKind $null
        }
        if (!$rule.Collection) {
            $data = $(if ($rule.Kind -eq 'Metrics') { ConvertTo-DiagMetrics $r.Body } else { ConvertTo-DiagProjected $r.Body $rule.Kind })
            return Add-DiagRequestRecord $Ctx 'GET' 'ARM' $Path $key $rule.ApiVersion $queryText 200 $null $data
        }
        $pageItems = Get-DiagMember $r.Body 'value'
        foreach ($item in @($pageItems)) { if ($item) { $items.Add((ConvertTo-DiagProjected $item $rule.Kind)) } }
        $next = Get-DiagMember $r.Body 'nextLink'
        if (!$next) { break }
        if (!(Test-DiagNextLink $next $Path $rule.ApiVersion)) {
            Add-DiagCollectorError $Ctx 'discover' 'Other' "Stopped paging $(Get-ArmName $Path): unexpected next link."
            break
        }
        if ($page -eq 24) { Add-DiagCollectorError $Ctx 'discover' 'Other' "Stopped paging $(Get-ArmName $Path) after 25 pages." }
        $uri = $next
    }
    Add-DiagRequestRecord $Ctx 'GET' 'ARM' $Path $key $rule.ApiVersion $queryText 200 $null $items.ToArray()
}

# Resource Graph is the only POST. Queries come from fixed templates; inputs are validated before use.
function Get-DiagGraphQuery {
    param([ValidateSet('nextHop', 'virtualHubs')][string]$Kind, [string]$Ip)
    switch ($Kind) {
        'nextHop' {
            if ($Ip -notmatch '^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$') { throw "Invalid next-hop IP '$Ip'." }
            @"
resources
| where type in~ ('microsoft.network/azurefirewalls', 'microsoft.network/networkinterfaces', 'microsoft.network/loadbalancers')
| extend ipcs = iff(type =~ 'microsoft.network/loadbalancers', properties.frontendIPConfigurations, properties.ipConfigurations)
| extend ipcs = iff(array_length(ipcs) > 0, ipcs, dynamic([{}]))
| mv-expand ipc = ipcs
| where tostring(ipc.properties.privateIPAddress) == '$Ip' or tostring(properties.hubIPAddresses.privateIPAddress) == '$Ip'
| distinct id, type
"@
        }
        'virtualHubs' {
            @"
resources
| where type =~ 'microsoft.network/virtualhubs'
| project id, type
| take 20
"@
        }
    }
}

function Invoke-DiagResourceGraph {
    param([Parameter(Mandatory)]$Ctx, [Parameter(Mandatory)][string]$Label, [Parameter(Mandatory)][string]$Query)
    if ($Label -notmatch '^(nextHop:\d{1,3}(\.\d{1,3}){3}|virtualHubs)$') { throw "Resource Graph label '$Label' is not allowed." }
    $path = '/providers/Microsoft.ResourceGraph/resources'
    $key = "POST $path#$Label"
    $cached = $Ctx.Cache[$key.ToLowerInvariant()]
    if ($cached) { return $cached }
    if (!(Test-DiagBudget $Ctx)) { return $null }
    $body = @{ query = $Query; options = @{ resultFormat = 'objectArray'; '$top' = 50 } } | ConvertTo-Json -Compress -Depth 5
    $r = Send-DiagHttp $Ctx 'POST' "https://$($script:DiagArmHost)$($path)?api-version=$($script:DiagGraphApi)" $body
    $rows = $null
    if ($r.Status -eq 200) {
        $data = Get-DiagMember $r.Body 'data'
        $rows = @(foreach ($row in @($data)) {
                if ($row) { [ordered]@{ id = (Get-DiagMember $row 'id'); type = (Get-DiagMember $row 'type') } }
            })
    }
    Add-DiagRequestRecord $Ctx 'POST' 'ResourceGraph' "$path#$Label" $key $script:DiagGraphApi $Query $r.Status $r.ErrorKind $rows
}
