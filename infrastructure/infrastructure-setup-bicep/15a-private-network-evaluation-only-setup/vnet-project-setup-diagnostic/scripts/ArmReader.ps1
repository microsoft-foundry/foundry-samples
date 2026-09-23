# All outbound ARM operations pass through this allowlist, including fixture reads.
. (Join-Path $PSScriptRoot 'MetadataProjection.ps1')
. (Join-Path $PSScriptRoot 'AzurePowerShellReader.ps1')

function Get-ArmRule {
    param([string]$Path)
    $root = '/subscriptions/[0-9a-f-]{36}/resourceGroups/[^/]+/providers/'
    $account = "${root}Microsoft.CognitiveServices/accounts/[^/]+"
    $scope = '/subscriptions/[0-9a-f-]{36}(?:/resourceGroups/[^/]+(?:/providers/[^/]+/[^/]+/[^/]+(?:/[^/]+/[^/]+)*)?)?'
    $rules = @(
        @("$account(?:/projects/[^/]+)?$", '2025-06-01', 'Resource'),
        @("$account(?:/projects/[^/]+)?/connections(?:/[^/]+)?$", '2025-06-01', 'Connection'),
        @("$account(?:/projects/[^/]+)?/capabilityHosts(?:/[^/]+)?$", '2025-04-01-preview', 'Capability'),
        @("$account/deployments(?:/[^/]+)?$", '2025-06-01', 'Deployment'),
        @("$account/privateEndpointConnections(?:/[^/]+)?$", '2025-06-01', 'PrivateConnection'),
        @("${root}Microsoft.Storage/storageAccounts/[^/]+$", '2023-05-01', 'Storage'),
        @("${root}Microsoft.Storage/storageAccounts/[^/]+/privateEndpointConnections(?:/[^/]+)?$", '2023-05-01', 'PrivateConnection'),
        @("${root}Microsoft.Network/virtualNetworks/[^/]+(?:/subnets/[^/]+)?$", '2024-05-01', 'Network'),
        @("${root}Microsoft.Network/(?:privateEndpoints|networkInterfaces|networkSecurityGroups|routeTables)/[^/]+$", '2024-05-01', 'Network'),
        @("${root}Microsoft.Network/privateEndpoints/[^/]+/privateDnsZoneGroups(?:/[^/]+)?$", '2024-05-01', 'Network'),
        @("${root}Microsoft.Network/privateDnsZones/[^/]+(?:/(?:A|virtualNetworkLinks)(?:/[^/]+)?)?$", '2020-06-01', 'Network'),
        @("${root}Microsoft.Insights/components/[^/]+$", '2020-02-02', 'Monitoring'),
        @("${root}Microsoft.OperationalInsights/workspaces/[^/]+$", '2023-09-01', 'Monitoring'),
        @("${root}Microsoft.Search/searchServices/[^/]+$", '2023-11-01', 'Dependency'),
        @("${root}Microsoft.DocumentDB/databaseAccounts/[^/]+$", '2024-05-15', 'Dependency'),
        @("$scope/providers/Microsoft.Authorization/(?:roleAssignments|denyAssignments)$", '2022-04-01', 'Authorization'),
        @("(?:$scope)?/providers/Microsoft.Authorization/roleDefinitions/[0-9a-f-]{36}$", '2022-04-01', 'Role')
    )
    foreach ($rule in $rules) {
        if ($Path -match ('(?i)^' + $rule[0])) {
            return @{ Version = $rule[1]; Kind = $rule[2] }
        }
    }
    throw 'ARM operation is not in the read-only metadata allowlist.'
}

function Assert-ArmId {
    param([string]$Id, [switch]$Project)
    if (!$Id -or $Id -match '[\\?#%\s]' -or $Id -match '(^|/)\.\.?(/|$)' -or
        $Id -notmatch '^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[a-zA-Z0-9_.()-]+/providers/[a-zA-Z0-9.]+(?:/[a-zA-Z0-9_.@()-]+)+$') {
        throw 'Invalid ARM resource ID.'
    }
    if ($Project -and $Id -notmatch '(?i)/providers/Microsoft.CognitiveServices/accounts/[^/]+/projects/[^/]+$') {
        throw 'Expected a Foundry account/project ARM ID.'
    }
    if (![guid]::TryParse(($Id -split '/')[2], [ref]([guid]::Empty))) { throw 'Invalid subscription ID.' }
    $null = Get-ArmRule $Id
    return $Id
}

function Assert-ArmRequest {
    param([string]$Uri, [string]$Method = 'GET', [string]$InitialPath)
    if ($Method -cne 'GET') { throw 'Only GET is permitted.' }
    $u = $null
    if (![uri]::TryCreate($Uri, [UriKind]::Absolute, [ref]$u) -or
        $u.Scheme -ne 'https' -or $u.Host -ne 'management.azure.com' -or
        !$u.IsDefaultPort -or $u.UserInfo -or $u.Fragment -or $Uri -match '[\\\r\n]|/\.\.?(/|[?])' -or
        $u.AbsolutePath -match '%|//|(^|/)\.\.?(/|$)') { throw 'Invalid ARM URL.' }
    $rule = Get-ArmRule $u.AbsolutePath
    if ($u.AbsolutePath -match '^/subscriptions/([^/]+)' -and
        ![guid]::TryParse($Matches[1], [ref]([guid]::Empty))) { throw 'Invalid subscription ID in ARM request.' }
    if ($InitialPath -and $u.AbsolutePath -cne $InitialPath) { throw 'Paging escaped its original collection scope.' }
    $keys = @{}
    foreach ($pair in $u.Query.TrimStart('?').Split('&')) {
        $parts = $pair.Split('=', 2)
        $key = [uri]::UnescapeDataString($parts[0])
        if ($parts.Count -ne 2 -or $keys.ContainsKey($key) -or $key -notin @('api-version', '$skiptoken', '$skipToken', '$filter')) {
            throw 'Unapproved ARM query parameter.'
        }
        $keys[$key] = [uri]::UnescapeDataString($parts[1])
    }
    if ($keys['api-version'] -ne $rule.Version) { throw 'Unapproved ARM API version.' }
    if ($keys.ContainsKey('$filter') -and $keys['$filter'] -ne 'atScope()') { throw 'Unapproved ARM filter.' }
    return $rule
}

function Get-MetadataProjection {
    param([string]$Kind, [bool]$Collection)
    $base = 'id:id,name:name,type:type,location:location'
    $identity = 'identity:{type:identity.type,principalId:identity.principalId,tenantId:identity.tenantId,userAssignedIdentities:identity.userAssignedIdentities}'
    $properties = switch ($Kind) {
        'Connection' { 'category:category,authType:authType,target:target,isSharedToAll:isSharedToAll,metadata:{ResourceId:metadata.ResourceId,resourceId:metadata.resourceId},provisioningState:provisioningState' }
        'Authorization' { 'principalId:principalId,principalType:principalType,roleDefinitionId:roleDefinitionId,scope:scope,conditionPresent:condition != `null` && condition != `""`,createdOn:createdOn,updatedOn:updatedOn,permissions:permissions,principals:principals,excludePrincipals:excludePrincipals,doNotApplyToChildScopes:doNotApplyToChildScopes' }
        'Role' { 'roleName:roleName,type:type,permissions:permissions,assignableScopes:assignableScopes' }
        'Deployment' { 'provisioningState:provisioningState,model:{name:model.name,format:model.format,version:model.version}' }
        'Capability' { 'provisioningState:provisioningState,capabilityHostKind:capabilityHostKind,storageConnections:storageConnections,vectorStoreConnections:vectorStoreConnections,threadStorageConnections:threadStorageConnections' }
        'PrivateConnection' { 'privateEndpoint:privateEndpoint,privateLinkServiceConnectionState:privateLinkServiceConnectionState,groupIds:groupIds,provisioningState:provisioningState' }
        'Storage' { 'provisioningState:provisioningState,publicNetworkAccess:publicNetworkAccess,allowSharedKeyAccess:allowSharedKeyAccess,networkAcls:{defaultAction:networkAcls.defaultAction,bypass:networkAcls.bypass},primaryEndpoints:{blob:primaryEndpoints.blob}' }
        'Monitoring' { 'provisioningState:provisioningState,AppId:AppId,WorkspaceResourceId:WorkspaceResourceId,publicNetworkAccessForIngestion:publicNetworkAccessForIngestion,publicNetworkAccessForQuery:publicNetworkAccessForQuery,features:{enableLogAccessUsingOnlyResourcePermissions:features.enableLogAccessUsingOnlyResourcePermissions},privateLinkScopedResources:(PrivateLinkScopedResources || privateLinkScopedResources || `[]`)[].{resourceId:ResourceId || resourceId,scopeId:ScopeId || scopeId}' }
        'Network' { 'provisioningState:provisioningState,subnet:subnet,delegations:delegations,serviceAssociationLinks:serviceAssociationLinks,networkSecurityGroup:networkSecurityGroup,routeTable:routeTable,dhcpOptions:dhcpOptions,addressSpace:addressSpace,addressPrefix:addressPrefix,addressPrefixes:addressPrefixes,networkInterfaces:networkInterfaces,ipConfigurations:ipConfigurations,customDnsConfigs:customDnsConfigs,privateLinkServiceConnections:privateLinkServiceConnections,manualPrivateLinkServiceConnections:manualPrivateLinkServiceConnections,privateDnsZoneConfigs:privateDnsZoneConfigs,aRecords:aRecords,virtualNetwork:virtualNetwork,virtualNetworkLinkState:virtualNetworkLinkState,registrationEnabled:registrationEnabled,securityRules:securityRules,routes:routes' }
        default { 'provisioningState:provisioningState,endpoint:endpoint,endpoints:endpoints,networkInjections:networkInjections,publicNetworkAccess:publicNetworkAccess,disableLocalAuth:disableLocalAuth,documentEndpoint:documentEndpoint' }
    }
    $item = "{$base,$identity,properties:properties.{$properties}}"
    if ($Collection) { return "{value:value[].$item,nextLink:nextLink}" }
    return $item
}

function Invoke-CliMetadata {
    param($Context, [string[]]$Arguments)
    $bootstrap = @('account', 'show', '--query', '{tenantId:tenantId,cloud:environmentName}', '--output', 'json', '--only-show-errors')
    if (($Arguments -join "`0") -cne ($bootstrap -join "`0")) {
        if ($Arguments.Count -ne 10 -or $Arguments[0] -cne 'rest' -or $Arguments[1] -cne '--method' -or
            $Arguments[2] -cne 'get' -or $Arguments[3] -cne '--url' -or $Arguments[5] -cne '--query' -or
            $Arguments[7] -cne '--output' -or $Arguments[8] -cne 'json' -or $Arguments[9] -cne '--only-show-errors') {
            throw 'Unapproved Azure CLI command.'
        }
        $rule = Assert-ArmRequest $Arguments[4]
        if ($Arguments[6] -cnotin @((Get-MetadataProjection $rule.Kind $true), (Get-MetadataProjection $rule.Kind $false))) {
            throw 'Unapproved metadata projection.'
        }
    }
    # A child pwsh handles az.cmd without constructing a cmd.exe command line.
    # Only allowlisted non-secret arguments cross the process boundary.
    $invocation = @{ executable = $Context.Cli; arguments = @($Context.Prefix) + $Arguments } | ConvertTo-Json -Compress
    $encodedArguments = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($invocation))
    $script = @"
`$ErrorActionPreference = 'Stop'
`$i = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('$encodedArguments')) | ConvertFrom-Json
try {
    `$lines = & `$i.executable @(`$i.arguments) 2>&1
    `$exitCode = `$LASTEXITCODE
    `$text = (`$lines | ForEach-Object { `$_.ToString() }) -join [Environment]::NewLine
    if (`$exitCode -eq 0) {
        @{Code=200;Data=(`$text | ConvertFrom-Json -AsHashtable)} | ConvertTo-Json -Depth 80 -Compress
    } else {
        `$code = 0
        if (`$text -match 'Unauthorized|InvalidAuthenticationToken|\b401\b') { `$code = 401 }
        elseif (`$text -match 'AuthorizationFailed|Forbidden|\b403\b') { `$code = 403 }
        elseif (`$text -match 'ResourceNotFound|ResourceGroupNotFound|\b404\b') { `$code = 404 }
        elseif (`$text -match 'TooManyRequests|\b429\b') { `$code = 429 }
        elseif (`$text -match 'ServiceUnavailable|\b503\b') { `$code = 503 }
        elseif (`$text -match 'GatewayTimeout|\b504\b') { `$code = 504 }
        @{Code=`$code;Data=`$null} | ConvertTo-Json -Compress
    }
} catch { '{"Code":0,"Data":null}' }
"@
    $start = [Diagnostics.ProcessStartInfo]::new((Join-Path $PSHOME 'pwsh.exe'))
    if (!$IsWindows) { $start.FileName = Join-Path $PSHOME 'pwsh' }
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($arg in @('-NoProfile', '-NonInteractive', '-EncodedCommand', [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($script)))) {
        $start.ArgumentList.Add($arg)
    }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    try {
        $null = $process.Start()
        $output = $process.StandardOutput.ReadToEndAsync()
        $errors = $process.StandardError.ReadToEndAsync()
        if (!$process.WaitForExit($Context.TimeoutSeconds * 1000)) {
            $process.Kill($true)
            return @{ Code = 408; Data = $null }
        }
        $text = $output.GetAwaiter().GetResult()
        $null = $errors.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { return @{ Code = 0; Data = $null } }
        try { return ($text | ConvertFrom-Json -AsHashtable -ErrorAction Stop) }
        catch { return @{ Code = 0; Data = $null } }
    }
    finally { $process.Dispose() }
}

function New-DiagnosticContext {
    param([string]$FixturePath, [string]$Cli, [string[]]$Prefix, [int]$TimeoutSeconds = 25,
        [ValidateSet('AzureCli','AzurePowerShell')][string]$AuthenticationProvider = 'AzureCli', [string]$SubscriptionId)
    if ($Prefix.Count -and ($Prefix.Count -ne 2 -or $Prefix[0] -ne '-IBm' -or $Prefix[1] -ne 'azure.cli')) {
        throw 'Only the Python Azure CLI module prefix is supported.'
    }
    $context = @{
        Cli = $Cli; Prefix = $Prefix; TimeoutSeconds = $TimeoutSeconds; AuthenticationProvider = $AuthenticationProvider
        TimedOutTokenWorkers = [Collections.Generic.List[object]]::new()
        Fixture = $null; Offline = [bool]$FixturePath; Cache = @{}; Requests = [Collections.Generic.List[string]]::new()
        Checks = [Collections.Generic.List[object]]::new(); Endpoints = @{}
        HostContext = @{ location = 'Customer execution host; VNet membership unknown'; machine = [Environment]::MachineName }
    }
    if ($FixturePath) {
        $context.Fixture = Get-Content -LiteralPath $FixturePath -Raw | ConvertFrom-Json -AsHashtable
        if ($context.Fixture -isnot [Collections.IDictionary] -or $context.Fixture.responses -isnot [Collections.IDictionary]) {
            throw 'Offline fixture must contain a responses dictionary; never fall back to Azure.'
        }
        $context.HostContext = @{ location = 'Offline sanitized fixture'; machine = 'fixture' }
    }
    elseif ($AuthenticationProvider -eq 'AzurePowerShell') {
        Initialize-AzurePowerShellProvider $context $SubscriptionId
    }
    else {
        $null = Get-Command $Cli -ErrorAction Stop
        $bootstrap = Invoke-CliMetadata $context @('account', 'show', '--query', '{tenantId:tenantId,cloud:environmentName}', '--output', 'json', '--only-show-errors')
        if ($bootstrap.Code -ne 200 -or !$bootstrap.Data.tenantId -or $bootstrap.Data.cloud -ne 'AzureCloud') {
            throw 'Customer Azure CLI login to AzureCloud is required; sovereign clouds are not supported in this version.'
        }
        $context.TenantId = $bootstrap.Data.tenantId
    }
    return $context
}

function Read-Arm {
    param($Context, [string]$Id, [switch]$Collection)
    try {
        $rule = Get-ArmRule $Id
        $uri = "https://management.azure.com${Id}?api-version=$($rule.Version)"
        $null = Assert-ArmRequest $uri
    }
    catch { return @{ Code = 0; Data = $null; Reason = 'RejectedResourceIdOrOperation' } }
    $cacheKey = "$Id|$Collection"
    if ($Context.Cache.ContainsKey($cacheKey)) { return $Context.Cache[$cacheKey] }
    $items = [Collections.Generic.List[object]]::new()
    $seen = @{}
    $result = $null
    for ($page = 0; $page -lt 25; $page++) {
        try { $null = Assert-ArmRequest $uri -InitialPath $Id }
        catch { $result = @{ Code = 0; Data = $null; Reason = 'RejectedPaging' }; break }
        if ($seen.ContainsKey($uri)) { $result = @{ Code = 0; Data = $null; Reason = 'PagingCycle' }; break }
        $seen[$uri] = $true
        $Context.Requests.Add($uri)
        if ($Context.Offline) {
            $response = $Context.Fixture.responses[$uri]
            if (!$response) { $response = $Context.Fixture.responses[$Id] }
            if (!$response) { $response = @{ Code = 403; Data = $null } }
        }
        else {
            $projection = Get-MetadataProjection $rule.Kind ([bool]$Collection)
            for ($attempt = 0; $attempt -lt 3; $attempt++) {
                if ($Context.AuthenticationProvider -eq 'AzurePowerShell') {
                    $response = Invoke-AzurePowerShellMetadata $Context $uri ([bool]$Collection)
                }
                else {
                    $response = Invoke-CliMetadata $Context @('rest', '--method', 'get', '--url', $uri, '--query', $projection, '--output', 'json', '--only-show-errors')
                    if ($response.Code -eq 200) {
                        try { $response.Data = ConvertTo-ArmMetadata $response.Data $rule.Kind ([bool]$Collection) }
                        catch { $response = @{ Code = 0; Data = $null } }
                    }
                }
                if ($response.Code -notin @(429, 503, 504) -or $attempt -eq 2) { break }
                Start-Sleep -Seconds ($attempt + 1)
            }
        }
        if ($response.Code -ne 200) {
            $result = @{ Code = $response.Code; Data = $null; Reason = "ReadUnavailable:$($response.Code)" }
            break
        }
        if ($response.Data -isnot [Collections.IDictionary]) {
            $result = @{ Code = 0; Data = $null; Reason = 'InvalidMetadataShape' }; break
        }
        if (!$Collection) { $result = @{ Code = 200; Data = $response.Data; Reason = '' }; break }
        if (!$response.Data.ContainsKey('value') -or $null -eq $response.Data.value) {
            $result = @{ Code = 0; Data = $null; Reason = 'InvalidCollectionShape' }; break
        }
        foreach ($item in $response.Data.value) { $items.Add($item) }
        if (!$response.Data.nextLink) { $result = @{ Code = 200; Data = @($items.ToArray()); Reason = '' }; break }
        $uri = [string]$response.Data.nextLink
    }
    if (!$result) { $result = @{ Code = 0; Data = $null; Reason = 'PageLimit' } }
    $Context.Cache[$cacheKey] = $result
    return $result
}
