#Requires -Version 7.2
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-Fields {
    param([System.Collections.IDictionary]$Value, [string[]]$Required, [string[]]$Optional = @())
    foreach ($key in $Required) {
        if (!$Value.Contains($key) -or $null -eq $Value[$key] -or "$($Value[$key])" -eq '') {
            throw "Missing required field: $key."
        }
    }
    foreach ($key in $Value.Keys) {
        if ($key -cnotin ($Required + $Optional)) { throw "Unexpected field: $key." }
    }
}

function Assert-Name {
    param([string]$Name, [string]$Pattern, [int]$Min, [int]$Max)
    if ($Name.Length -lt $Min -or $Name.Length -gt $Max -or $Name -cnotmatch $Pattern) {
        throw 'Resource name does not meet the selected resource naming constraints.'
    }
}

function Assert-ResourceId {
    param([string]$Id, [string]$Type)
    $segments = $Type.Split('/')
    $pattern = '^/subscriptions/([0-9a-fA-F-]{36})/resourceGroups/([a-zA-Z0-9_.()-]+)/providers/' +
        [regex]::Escape($segments[0])
    foreach ($segment in $segments[1..($segments.Count - 1)]) {
        $pattern += '/' + [regex]::Escape($segment) + '/[a-zA-Z0-9_.()-]+'
    }
    if ($Id -notmatch ($pattern + '$')) { throw "Expected a full $Type resource ID." }
    $subscription = $Id.Split('/')[2]
    if (![guid]::TryParse($subscription, [ref]([guid]::Empty))) { throw 'Invalid resource subscription ID.' }
    return $Id
}

function Get-CidrRange {
    param([string]$Cidr)
    if ($Cidr -notmatch '^(\d{1,3}(?:\.\d{1,3}){3})/(\d|[12]\d|3[0-2])$') { throw 'Expected an IPv4 CIDR.' }
    $octets = $Matches[1].Split('.')
    $prefix = [int]$Matches[2]
    [long]$address = 0
    foreach ($octet in $octets) {
        if ([int]$octet -gt 255 -or "$([int]$octet)" -cne $octet) { throw 'Invalid IPv4 octet.' }
        $address = $address * 256 + [int]$octet
    }
    [long]$size = [long][math]::Pow(2, 32 - $prefix)
    if ($address % $size -ne 0) { throw 'CIDR must use a network address.' }
    return @{ Start = $address; End = $address + $size - 1; Prefix = $prefix }
}

function Assert-Access {
    param($Value)
    if ($Value -cnotin @('Enabled', 'Disabled')) { throw 'Public access must be explicitly Enabled or Disabled.' }
}

function Assert-PrivateCidr {
    param($Range)
    $private = @((Get-CidrRange '10.0.0.0/8'), (Get-CidrRange '172.16.0.0/12'), (Get-CidrRange '192.168.0.0/16'))
    if (!@($private | Where-Object { $Range.Start -ge $_.Start -and $Range.End -le $_.End }).Count) {
        throw 'Foundry subnets must use RFC 1918 private IPv4 space.'
    }
}

function Assert-OwnedResource {
    param($Value, [string]$Type, [string]$NamePattern, [int]$Min = 1, [int]$Max = 63)
    if ($Value.mode -ceq 'existing') {
        Assert-Fields $Value @('mode', 'resourceId')
        $null = Assert-ResourceId $Value.resourceId $Type
    } elseif ($Value.mode -ceq 'create') {
        Assert-Fields $Value @('mode', 'name', 'publicNetworkAccess')
        Assert-Name $Value.name $NamePattern $Min $Max
        Assert-Access $Value.publicNetworkAccess
    } else { throw 'Unsupported resource ownership mode.' }
}

function Split-SetupInput($Raw) {
    if ($Raw -isnot [Collections.IDictionary]) { throw 'Setup input must be a JSON object.' }
    $config = Copy-Data $Raw
    $networking = if ($config.Contains('privateNetworking')) { $config.privateNetworking } else { @{} }
    $null = $config.Remove('privateNetworking')
    if ($networking -isnot [Collections.IDictionary]) { throw 'privateNetworking must be an object.' }
    if (!$config.Contains('workload')) { $config.workload = @{} }
    if ($config.workload -isnot [Collections.IDictionary]) { throw 'workload must be an object.' }
    $monitoring = $config.Contains('applicationInsights') -and $config.applicationInsights -is [Collections.IDictionary] -and
        $config.applicationInsights['mode'] -cne 'none'
    $defaults = @{ intent = $(if ($monitoring) { 'trace' } else { 'non-trace' }); routeGoal = 'direct-private'; projectHost = 'requested' }
    foreach ($key in $defaults.Keys) { if (!$config.workload.Contains($key)) { $config.workload[$key] = $defaults[$key] } }
    @{ config = $config; networking = $networking }
}
function Read-SetupConfig {
    param([string]$Path)
    $raw = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -AsHashtable
    Assert-SetupConfig (Split-SetupInput $raw).config
}
function Assert-SetupConfig($config) {
    Assert-Fields $config @('schemaVersion', 'subscriptionId', 'location', 'resourceGroup',
        'foundryAccount', 'foundryProject', 'storageAccount', 'network', 'applicationInsights','workload') @('connectionSelection')
    Assert-Fields $config.workload @('intent','routeGoal','projectHost')
    if ($config.workload.intent -cnotin @('non-trace','trace') -or
        $config.workload.routeGoal -cnotin @('configuration-only','direct-private') -or
        $config.workload.projectHost -cnotin @('requested','not-requested')) { throw 'Explicit supported workload/route/host choices are required.' }
    if ($config.workload.intent -eq 'trace' -and $config.applicationInsights.mode -eq 'none') { throw 'Trace intent requires monitoring.' }
    if ($config.schemaVersion -cne '1.0') { throw 'Unsupported schemaVersion.' }
    if (![guid]::TryParse($config.subscriptionId, [ref]([guid]::Empty))) { throw 'Invalid subscriptionId.' }
    Assert-Name $config.location '^[a-z][a-z0-9]+$' 2 40
    Assert-Fields $config.resourceGroup @('mode', 'name')
    if ($config.resourceGroup.mode -cnotin @('create', 'existing')) { throw 'Unsupported resource-group mode.' }
    Assert-Name $config.resourceGroup.name '^[a-zA-Z0-9_().-]+(?<!\.)$' 1 90
    Assert-OwnedResource $config.foundryAccount 'Microsoft.CognitiveServices/accounts' '^[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]$' 2 64
    if ($config.foundryProject.mode -cne $config.foundryAccount.mode) { throw 'Mixed existing/create Foundry modes are unsupported.' }
    if ($config.foundryProject.mode -ceq 'create') {
        Assert-Fields $config.foundryProject @('mode', 'name')
        Assert-Name $config.foundryProject.name '^[a-zA-Z0-9][a-zA-Z0-9_-]*[a-zA-Z0-9]$' 2 64
        if ($config.Contains('connectionSelection')) { throw 'Explicit connection selection is for existing Foundry only.' }
    } else {
        Assert-Fields $config.foundryProject @('mode','resourceId')
        $null = Assert-ResourceId $config.foundryProject.resourceId 'Microsoft.CognitiveServices/accounts/projects'
        if (($config.foundryProject.resourceId -replace '/projects/[^/]+$', '') -ine $config.foundryAccount.resourceId) {
            throw 'Existing project must belong to the exact selected account.'
        }
        if ($config.foundryAccount.resourceId.Split('/')[2] -ine $config.subscriptionId) {
            throw 'Existing account/project must use the configured subscription.'
        }
        if ($config.Contains('connectionSelection')) {
            Assert-Fields $config.connectionSelection @() @('storage','monitoring')
            foreach ($selected in $config.connectionSelection.Values) {
                if ($selected -match '/projects/') { $null = Assert-ResourceId $selected 'Microsoft.CognitiveServices/accounts/projects/connections' }
                else { $null = Assert-ResourceId $selected 'Microsoft.CognitiveServices/accounts/connections' }
                $parent = $selected -replace '/connections/[^/]+$', ''
                if ($parent -ine $config.foundryAccount.resourceId -and $parent -ine $config.foundryProject.resourceId) {
                    throw 'Connection selection must belong to the selected account/project.'
                }
            }
            if ($config.applicationInsights.mode -eq 'none' -and $config.connectionSelection.Contains('monitoring')) {
                throw 'Monitoring-none conflicts with an explicit monitoring connection.'
            }
        }
    }
    Assert-OwnedResource $config.storageAccount 'Microsoft.Storage/storageAccounts' '^[a-z0-9]+$' 3 24
    $network = $config.network
    if ($network.mode -ceq 'existing') {
        Assert-Fields $network @('mode', 'agentSubnetResourceId', 'privateEndpointSubnetResourceId')
        foreach ($key in @('agentSubnetResourceId', 'privateEndpointSubnetResourceId')) {
            $null = Assert-ResourceId $network[$key] 'Microsoft.Network/virtualNetworks/subnets'
        }
        if ($network.agentSubnetResourceId -ieq $network.privateEndpointSubnetResourceId -or
            ($network.agentSubnetResourceId -replace '/subnets/[^/]+$', '') -ine
            ($network.privateEndpointSubnetResourceId -replace '/subnets/[^/]+$', '')) {
            throw 'Agent and PE subnets must be distinct subnets in the same VNet.'
        }
    } elseif ($network.mode -ceq 'create') {
        Assert-Fields $network @('mode', 'vnetName', 'addressPrefix', 'agentSubnetName', 'agentSubnetPrefix',
            'privateEndpointSubnetName', 'privateEndpointSubnetPrefix')
        foreach ($key in @('vnetName', 'agentSubnetName', 'privateEndpointSubnetName')) {
            Assert-Name $network[$key] '^[a-zA-Z0-9][a-zA-Z0-9_.-]*[a-zA-Z0-9_]$' 2 64
        }
        if ($network.agentSubnetName -ieq $network.privateEndpointSubnetName) { throw 'Subnet names must differ.' }
        $vnet = Get-CidrRange $network.addressPrefix
        $agent = Get-CidrRange $network.agentSubnetPrefix
        $pe = Get-CidrRange $network.privateEndpointSubnetPrefix
        Assert-PrivateCidr $vnet
        foreach ($subnet in @($agent, $pe)) {
            if ($subnet.Start -lt $vnet.Start -or $subnet.End -gt $vnet.End) { throw 'Subnet lies outside the VNet.' }
        }
        if ($agent.Prefix -gt 26 -or $pe.Prefix -gt 28) { throw 'Agent subnet must be /26 or larger; PE subnet /28 or larger.' }
        if ($agent.Start -le $pe.End -and $pe.Start -le $agent.End) { throw 'Subnet CIDRs overlap.' }
    } else { throw 'Unsupported network mode.' }
    $insights = $config.applicationInsights
    switch -CaseSensitive ($insights.mode) {
        'none' { Assert-Fields $insights @('mode') }
        'existing' {
            Assert-Fields $insights @('mode', 'resourceId')
            $null = Assert-ResourceId $insights.resourceId 'Microsoft.Insights/components'
        }
        'create' {
            Assert-Fields $insights @('mode', 'name', 'logAnalyticsWorkspace',
                'publicNetworkAccessForIngestion', 'publicNetworkAccessForQuery')
            Assert-Name $insights.name '^[a-zA-Z0-9][a-zA-Z0-9_.()-]*[a-zA-Z0-9)]$' 2 255
            Assert-Access $insights.publicNetworkAccessForIngestion
            Assert-Access $insights.publicNetworkAccessForQuery
            $workspace = $insights.logAnalyticsWorkspace
            if ($workspace.mode -ceq 'create') {
                Assert-Fields $workspace @('mode', 'name')
                Assert-Name $workspace.name '^[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]$' 4 63
            } elseif ($workspace.mode -ceq 'existing') {
                Assert-Fields $workspace @('mode', 'resourceId')
                $null = Assert-ResourceId $workspace.resourceId 'Microsoft.OperationalInsights/workspaces'
            } else { throw 'Unsupported workspace mode.' }
        }
        default { throw 'Explicit Application Insights none/create/existing mode is required.' }
    }
    return $config
}

function ConvertTo-Canonical {
    param($Value)
    if ($Value -is [System.Collections.IDictionary]) {
        $sorted = [ordered]@{}
        foreach ($key in ($Value.Keys | Sort-Object -CaseSensitive)) { $sorted[$key] = ConvertTo-Canonical $Value[$key] }
        return $sorted
    }
    if ($Value -is [array]) { return ,@($Value | ForEach-Object { ConvertTo-Canonical $_ }) }
    return $Value
}

function Get-Digest {
    param($Value)
    $json = ConvertTo-Json -InputObject (ConvertTo-Canonical $Value) -Depth 100 -Compress
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($json))).ToLowerInvariant()
}

function Get-SetupIds {
    param($Config)
    $rg = "/subscriptions/$($Config.subscriptionId)/resourceGroups/$($Config.resourceGroup.name)"
    $account = if ($Config.foundryAccount.mode -eq 'existing') { $Config.foundryAccount.resourceId }
        else { "$rg/providers/Microsoft.CognitiveServices/accounts/$($Config.foundryAccount.name)" }
    $project = if ($Config.foundryProject.mode -eq 'existing') { $Config.foundryProject.resourceId }
        else { "$account/projects/$($Config.foundryProject.name)" }
    $storage = if ($Config.storageAccount.mode -eq 'existing') { $Config.storageAccount.resourceId }
        else { "$rg/providers/Microsoft.Storage/storageAccounts/$($Config.storageAccount.name)" }
    $agent = if ($Config.network.mode -eq 'existing') { $Config.network.agentSubnetResourceId }
        else { "$rg/providers/Microsoft.Network/virtualNetworks/$($Config.network.vnetName)/subnets/$($Config.network.agentSubnetName)" }
    $pe = if ($Config.network.mode -eq 'existing') { $Config.network.privateEndpointSubnetResourceId }
        else { "$rg/providers/Microsoft.Network/virtualNetworks/$($Config.network.vnetName)/subnets/$($Config.network.privateEndpointSubnetName)" }
    $insights = switch ($Config.applicationInsights.mode) {
        'create' { "$rg/providers/Microsoft.Insights/components/$($Config.applicationInsights.name)" }
        'existing' { $Config.applicationInsights.resourceId }
        default { '' }
    }
    return @{ ResourceGroup = $rg; Account = $account; Project = $project
        Storage = $storage; AgentSubnet = $agent; PeSubnet = $pe; Vnet = ($agent -replace '/subnets/[^/]+$', '')
        Insights = $insights }
}
