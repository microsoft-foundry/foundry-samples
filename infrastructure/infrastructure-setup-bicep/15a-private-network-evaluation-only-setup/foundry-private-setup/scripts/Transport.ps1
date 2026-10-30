#Requires -Version 7.2
. (Join-Path $PSScriptRoot 'Toolchain.ps1')

function Get-SetupErrorStatus {
    param([string]$Text)
    if ($Text -match 'ResourceNotFound|ResourceGroupNotFound|ParentResourceNotFound|DeploymentNotFound|RoleAssignmentNotFound|\b404\b|(?m)^ERROR:\s+Not Found\b') { return 404 }
    if ($Text -match 'Conflict|AlreadyExists|RoleAssignmentExists|\b409\b') { return 409 }
    if ($Text -match 'PreconditionFailed|\b412\b') { return 412 }
    if ($Text -match 'AuthorizationFailed|Forbidden|\b403\b') { return 403 }
    if ($Text -match 'Unauthorized|InvalidAuthenticationToken|\b401\b') { return 401 }
    if ($Text -match 'TooManyRequests|\b429\b') { return 429 }
    if ($Text -match 'InternalServerError|\b500\b') { return 500 }
    if ($Text -match 'BadGateway|\b502\b') { return 502 }
    if ($Text -match 'ServiceUnavailable|\b503\b') { return 503 }
    if ($Text -match 'GatewayTimeout|\b504\b') { return 504 }
    return 0
}

function Get-SetupErrorDetail {
    param([string]$Text)
    $lines = @(($Text -split "`r?`n") | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    if (!$lines.Count) { return 'Azure CLI returned no error text' }
    $errors = @($lines | Where-Object { $_ -match '^ERROR:' })
    $detail = if ($errors.Count) { $errors[0] } else { $lines[0] }
    $detail = $detail -replace '(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+', '$1<redacted>' `
        -replace 'eyJ[A-Za-z0-9._-]{10,}', '<redacted>' `
        -replace '(?i)((?:sig|key|token|secret|password)=)[^&\s"'']+', '$1<redacted>'
    if ($detail.Length -gt 300) { $detail = $detail.Substring(0, 300) + '...' }
    return $detail
}

function Invoke-SetupCli {
    param([string[]]$Arguments,[scriptblock]$OnStart)
    $tools = Get-SetupToolchain
    $args = @($tools.prefix) + $Arguments + @('--only-show-errors','--output','json')
    $result = Invoke-NativeProcess (New-CleanProcess $tools.executable $args) $tools.manifest.budgets.nativeSeconds $OnStart
    if ($result.code -ne 0) {
        $errorCode = if ($result.stderr -match '"code"\s*:\s*"([a-zA-Z0-9_.-]{1,80})"') { $Matches[1] } else { 'CliFailure' }
        return @{ Code = $(if ($result.code -eq 408) { 408 } else { Get-SetupErrorStatus $result.stderr }); Data = $null; ErrorCode = $errorCode
            Detail = (Get-SetupErrorDetail $result.stderr) }
    }
    if ([string]::IsNullOrWhiteSpace($result.stdout)) { return @{ Code = 200; Data = @{} } }
    return @{ Code = 200; Data = (ConvertFrom-SetupJson $result.stdout) }
}

function Assert-SetupContext {
    param($Config)
    $context = Invoke-SetupCli @('account', 'show', '--query', '{id:id,cloud:environmentName,state:state}')
    if ($context.Code -ne 200 -or $context.Data.id -ine $Config.subscriptionId -or
        $context.Data.cloud -ne 'AzureCloud' -or $context.Data.state -ne 'Enabled') {
        throw 'Active AzureCloud subscription must match input-config.json. No subscription switch was performed.'
    }
}

function Get-SetupApi {
    param([string]$Id)
    if ($Id -match '/providers/Microsoft.Authorization/roleAssignments(?:/|$)') { return '2022-04-01' }
    if ($Id -match '/providers/Microsoft.CognitiveServices/') { return '2025-04-01-preview' }
    if ($Id -match '/providers/Microsoft.Storage/') { return '2023-05-01' }
    if ($Id -match '/providers/Microsoft.Network/privateDnsZones') { return '2020-06-01' }
    if ($Id -match '/providers/Microsoft.Network/') { return '2024-05-01' }
    if ($Id -match '/providers/Microsoft.Insights/privateLinkScopes') { return '2021-07-01-preview' }
    if ($Id -match '/providers/Microsoft.Insights/components') { return '2020-02-02' }
    if ($Id -match '/providers/Microsoft.OperationalInsights/workspaces') { return '2023-09-01' }
    if ($Id -match '/providers/Microsoft.Resources/deployments/') { return '2022-09-01' }
    if ($Id -match '^/subscriptions/[^/]+/resourceGroups/[^/]+$') { return '2022-09-01' }
    throw 'Resource is not in the setup API allowlist.'
}

function Invoke-SetupArm {
    param([string]$Method, [string]$Id, $Body = $null, [string]$ETag = '',[scriptblock]$OnStart)
    if (($Id -notmatch '^/subscriptions/[0-9a-fA-F-]{36}(?:/resourceGroups/[a-zA-Z0-9_.()-]+)?/providers/[a-zA-Z0-9./_()-]+$' -and
        $Id -notmatch '^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[a-zA-Z0-9_.()-]+$') -or
        $Id -match '/\.\.?(/|$)|//') { throw 'Invalid ARM path.' }
    if ($Method -cnotin @('GET', 'PUT', 'PATCH')) { throw 'Unsupported setup operation.' }
    $api = Get-SetupApi $Id
    $args = @('rest', '--method', $Method, '--url', "https://management.azure.com${Id}?api-version=$api")
    if ($Method -eq 'GET' -and $Id -match '/connections(?:/[^/]+)?$') {
        $item = '{id:id,name:name,properties:{category:properties.category,target:properties.target,authType:properties.authType,isSharedToAll:properties.isSharedToAll,metadata:properties.metadata,provisioningState:properties.provisioningState}}'
        $args += @('--query', $(if ($Id -match '/connections$') { "{value:value[].$item,nextLink:nextLink}" } else { $item }))
    } elseif ($Method -eq 'GET' -and $Id -match '/Microsoft.CognitiveServices/accounts/[^/]+/deployments$') {
        $item = '{id:id,name:name,type:type,sku:sku,tags:tags,properties:merge(properties,{model:merge(properties.model,{source:`null`,sourceAccount:`null`,sourceConfigured:properties.model.source != `null`,sourceAccountConfigured:properties.model.sourceAccount != `null`})})}'
        $args += @('--query', "{value:value[].$item,nextLink:nextLink}")
    } elseif ($Id -match '/components/[^/]+$') {
        $args += @('--query', '{id:id,name:name,location:location,kind:kind,tags:tags,properties:{Application_Type:properties.Application_Type,WorkspaceResourceId:properties.WorkspaceResourceId,publicNetworkAccessForIngestion:properties.publicNetworkAccessForIngestion,publicNetworkAccessForQuery:properties.publicNetworkAccessForQuery,provisioningState:properties.provisioningState,PrivateLinkScopedResources:properties.PrivateLinkScopedResources}}')
    }
    $file = $null
    try {
        if ($Method -ne 'GET') {
            $file = [IO.Path]::GetTempFileName()
            $Body | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $file -Encoding utf8NoBOM
            $args += @('--body', "@$file")
            if ($ETag) { $args += @('--headers', "If-Match=$ETag") }
        }
        return Invoke-SetupCli $args -OnStart $OnStart
    } finally {
        if ($file) { Remove-Item -LiteralPath $file -Force }
    }
}

function Get-SetupResource {
    param([string]$Id, [switch]$Optional)
    # Read-only GETs retry transient failures (code 0 = the CLI produced no HTTP status).
    for ($attempt = 1; ; $attempt++) {
        $result = Invoke-SetupArm GET $Id
        if ($result.Code -notin @(0, 408, 429, 500, 502, 503, 504) -or $attempt -ge $script:SetupReadAttempts) { break }
        Start-Sleep -Seconds $script:SetupReadRetrySeconds
    }
    if ($Optional -and $result.Code -eq 404) { return $null }
    if ($result.Code -ne 200) {
        $reason = if ($result.Contains('ErrorCode')) { $result.ErrorCode } else { 'ReadUnavailable' }
        $detail = if ($result.Contains('Detail') -and $result.Detail) { " Detail: $($result.Detail)." } else { '' }
        throw "ARM read failed ($($result.Code), $reason) after $attempt attempt(s): $Id.$detail This read changed nothing. Fix the cause if the detail names one (sign-in, permission, network), then rerun the same Run command; it reconciles any unconfirmed write before retrying."
    }
    return $result.Data
}
$script:SetupReadAttempts = 3
$script:SetupReadRetrySeconds = 5

function Get-SetupCollection {
    param([string]$Id)
    $result = Get-SetupResource $Id
    if (!$result.Contains('value') -or $result.Contains('nextLink') -and $result.nextLink) {
        throw "Collection is incomplete or paged: $Id. Reconcile before proceeding."
    }
    return ,@($result.value)
}

function Wait-SetupResource {
    param([string]$Id, [int]$TimeoutSeconds = 900, [int]$PollSeconds = 10, [switch]$AllowMissingState)
    $timer = [Diagnostics.Stopwatch]::StartNew()
    do {
        $response = Invoke-SetupArm GET $Id
        if ($response.Code -eq 200) {
            $resource = $response.Data
            $hasState = $resource.Contains('properties') -and $resource.properties.Contains('provisioningState')
            $state = if ($hasState) { $resource.properties.provisioningState } else { '' }
            if ($state -eq 'Succeeded' -or (!$hasState -and $AllowMissingState)) { return $resource }
            if ($state -in @('Failed', 'Canceled', 'Deleting')) { throw "Provisioning $state at $Id. Reconcile before a new preview." }
        } elseif ($response.Code -notin @(0, 404, 408, 429, 500, 502, 503, 504)) {
            # Code 0 means the CLI produced no HTTP status (transient local/transport failure); read-only GETs retry until the deadline.
            $reason = if ($response.Contains('ErrorCode')) { $response.ErrorCode } else { 'ReadUnavailable' }
            $detail = if ($response.Contains('Detail') -and $response.Detail) { " Detail: $($response.Detail)." } else { '' }
            throw "Readback unresolved ($($response.Code), $reason) at $Id.$detail No write was repeated."
        }
        if ($timer.Elapsed.TotalSeconds -ge $TimeoutSeconds) { throw "Incomplete: bounded readiness timeout at $Id. The write might still complete." }
        Start-Sleep -Seconds $PollSeconds
    } while ($true)
}
