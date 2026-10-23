<#
.SYNOPSIS
    Checks managed-compute accelerator quota and platform capacity.

.DESCRIPTION
    Performs advisory, read-only checks before creating or scaling a Microsoft
    Foundry managed-compute deployment. The service operation remains
    authoritative because quota and platform capacity aren't reserved.

.PARAMETER AccountId
    Full ARM resource ID of the existing Microsoft Foundry AIServices account.

.PARAMETER AcceleratorType
    Managed-compute accelerator type, such as A100_80GB.

.PARAMETER TargetCapacity
    Target number of model instances.

.PARAMETER AcceleratorsPerInstance
    Accelerators required by one model instance. Required for create. For scale,
    this value is read from the existing deployment and any conflicting supplied
    value is rejected.

.PARAMETER DeploymentId
    Existing managed-compute deployment ARM ID for scale checks. When supplied,
    the helper reads current capacity and requests capacity for the deployment's
    hosting region.

.PARAMETER SkuName
    Managed-compute SKU. GlobalManagedCompute maps to offer scope Global.

.PARAMETER OfferScope
    Explicit offer scope. Required only when SkuName doesn't have a known mapping.

.PARAMETER ScopeId
    Optional data-zone scope ID. Empty for Global.

.PARAMETER QuotaOfferScope
    Quota offer scope when it differs from the capacity offer scope. When
    omitted, Global maps to Global and DataZone plus ScopeId maps to
    Datazone-{ScopeId}.

.PARAMETER Offer
    Capacity offer name. Defaults to MaaP.

.PARAMETER OutputFormat
    table or json.

.PARAMETER RequireDeploymentRegionCapacity
    For scale checks, fail if Azure can't return capacity for the deployment's
    hosting region instead of falling back to the broader offer/scope snapshot.

.EXAMPLE
    ./managed-compute-check.ps1 `
      -AccountId "/subscriptions/.../accounts/my-foundry" `
      -AcceleratorType "A100_80GB" `
      -TargetCapacity 1 `
      -AcceleratorsPerInstance 1

.EXAMPLE
    ./managed-compute-check.ps1 `
      -AccountId "/subscriptions/.../accounts/my-foundry" `
      -AcceleratorType "A100_80GB" `
      -TargetCapacity 2 `
      -DeploymentId "/subscriptions/.../managedComputeDeployments/my-deployment" `
      -OutputFormat json
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$AccountId,

    [Parameter(Mandatory)]
    [string]$AcceleratorType,

    [Parameter(Mandatory)]
    [ValidateRange(1, [int]::MaxValue)]
    [int]$TargetCapacity,

    [ValidateRange(0, [int]::MaxValue)]
    [int]$AcceleratorsPerInstance = 0,

    [string]$DeploymentId = '',

    [string]$SkuName = 'GlobalManagedCompute',

    [string]$OfferScope = '',

    [string]$ScopeId = '',

    [string]$QuotaOfferScope = '',

    [string]$Offer = 'MaaP',

    [ValidateSet('table', 'json')]
    [string]$OutputFormat = 'table',

    [switch]$RequireDeploymentRegionCapacity
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module (Join-Path $PSScriptRoot 'ManagedComputePreflight.psm1') -Force

function Invoke-AzJson {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $maxAttempts = 3
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        $errorFile = [System.IO.Path]::GetTempFileName()
        try {
            $output = & az @Arguments 2> $errorFile
            if ($LASTEXITCODE -eq 0) {
                return (($output -join [Environment]::NewLine) | ConvertFrom-Json -Depth 100)
            }

            $details = Get-Content -Raw -Path $errorFile
            $isTransient = $details -match '(?i)connection reset|connection aborted|temporarily unavailable|too many requests|\b429\b|\b5\d\d\b'
            if (-not $isTransient -or $attempt -eq $maxAttempts) {
                throw "Azure CLI failed: $details"
            }
        }
        finally {
            Remove-Item -Force -ErrorAction SilentlyContinue $errorFile
        }

        Start-Sleep -Seconds ([Math]::Pow(2, $attempt - 1))
    }
}

function Resolve-OfferScope {
    param(
        [string]$RequestedOfferScope,
        [string]$RequestedSkuName
    )

    if ($RequestedOfferScope) {
        return $RequestedOfferScope
    }

    switch ($RequestedSkuName) {
        'GlobalManagedCompute' { return 'Global' }
        default {
            throw "No offer-scope mapping is defined for SKU '$RequestedSkuName'. Supply -OfferScope explicitly."
        }
    }
}

function Resolve-QuotaOfferScope {
    param(
        [string]$RequestedQuotaOfferScope,
        [string]$CapacityOfferScope,
        [string]$RequestedScopeId
    )

    if ($RequestedQuotaOfferScope) {
        return $RequestedQuotaOfferScope
    }
    if ($CapacityOfferScope -ieq 'Global') {
        return 'Global'
    }
    if ($CapacityOfferScope -ieq 'DataZone' -and $RequestedScopeId) {
        return "Datazone-$RequestedScopeId"
    }

    throw "Quota offer scope can't be derived from capacity offer scope '$CapacityOfferScope' and scope ID '$RequestedScopeId'. Supply -QuotaOfferScope explicitly."
}

try {
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
        throw "Azure CLI wasn't found. Install Azure CLI and run 'az login'."
    }

    $accountPattern = '^/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/Microsoft\.CognitiveServices/accounts/([^/]+)$'
    if ($AccountId -notmatch $accountPattern) {
        throw "AccountId isn't a valid Microsoft.CognitiveServices/accounts ARM resource ID."
    }
    $subscriptionId = $Matches[1]
    $resourceGroup = $Matches[2]
    $accountName = $Matches[3]
    $resolvedOfferScope = Resolve-OfferScope `
        -RequestedOfferScope $OfferScope `
        -RequestedSkuName $SkuName
    $resolvedQuotaOfferScope = Resolve-QuotaOfferScope `
        -RequestedQuotaOfferScope $QuotaOfferScope `
        -CapacityOfferScope $resolvedOfferScope `
        -RequestedScopeId $ScopeId

    $account = Invoke-AzJson -Arguments @(
        'cognitiveservices', 'account', 'show',
        '--subscription', $subscriptionId,
        '--resource-group', $resourceGroup,
        '--name', $accountName,
        '--only-show-errors',
        '--output', 'json'
    )
    if ($account.kind -ne 'AIServices') {
        throw "Account '$accountName' has kind '$($account.kind)', not AIServices."
    }
    if ($account.properties.provisioningState -ne 'Succeeded') {
        throw "Account '$accountName' provisioning state is '$($account.properties.provisioningState)', not Succeeded."
    }

    $currentCapacity = 0
    if ($DeploymentId) {
        $expectedPrefix = "$AccountId/managedComputeDeployments/"
        if (-not $DeploymentId.StartsWith($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "DeploymentId must identify a managed-compute deployment under AccountId."
        }
        $deploymentName = $DeploymentId.Substring($expectedPrefix.Length)
        if (-not $deploymentName -or $deploymentName.Contains('/')) {
            throw "DeploymentId contains unexpected path segments."
        }

        $deploymentUrl = "https://management.azure.com${DeploymentId}?api-version=2026-07-15-preview"
        $deployment = Invoke-AzJson -Arguments @(
            'rest', '--method', 'get',
            '--url', $deploymentUrl,
            '--only-show-errors',
            '--output', 'json'
        )
        if ($deployment.properties.acceleratorType -ne $AcceleratorType) {
            throw "Deployment accelerator '$($deployment.properties.acceleratorType)' doesn't match '$AcceleratorType'."
        }
        if ($deployment.sku.name -ne $SkuName) {
            throw "Deployment SKU '$($deployment.sku.name)' doesn't match '$SkuName'."
        }

        $currentCapacity = [int]$deployment.sku.capacity
        $deploymentAcceleratorsPerInstance = [int]$deployment.properties.acceleratorsPerInstance
        if ($AcceleratorsPerInstance -gt 0 -and $AcceleratorsPerInstance -ne $deploymentAcceleratorsPerInstance) {
            throw "AcceleratorsPerInstance '$AcceleratorsPerInstance' conflicts with deployment value '$deploymentAcceleratorsPerInstance'."
        }
        $AcceleratorsPerInstance = $deploymentAcceleratorsPerInstance
    }
    elseif ($AcceleratorsPerInstance -lt 1) {
        throw "AcceleratorsPerInstance is required and must be at least 1 for a create check."
    }

    $apiVersion = '2026-07-15-preview'
    $location = [string]$account.location
    $usageUrl = "https://management.azure.com/subscriptions/$subscriptionId/providers/Microsoft.CognitiveServices/locations/$([uri]::EscapeDataString($location))/managedComputeUsages?api-version=$apiVersion"
    $baseCapacityUrl = "https://management.azure.com/subscriptions/$subscriptionId/providers/Microsoft.CognitiveServices/managedComputeCapacities?api-version=$apiVersion&offer=$([uri]::EscapeDataString($Offer))&acceleratorType=$([uri]::EscapeDataString($AcceleratorType))"
    $capacityUrl = $baseCapacityUrl
    $capacityLookup = 'bestAvailable'
    $warnings = @()
    if ($DeploymentId) {
        $capacityUrl += "&deploymentId=$([uri]::EscapeDataString($DeploymentId))"
        $capacityLookup = 'deploymentRegion'
    }

    $usageResponse = Invoke-AzJson -Arguments @(
        'rest', '--method', 'get',
        '--url', $usageUrl,
        '--only-show-errors',
        '--output', 'json'
    )
    try {
        $capacityResponse = Invoke-AzJson -Arguments @(
            'rest', '--method', 'get',
            '--url', $capacityUrl,
            '--only-show-errors',
            '--output', 'json'
        )
    }
    catch {
        if ($DeploymentId -and (Test-ManagedComputeNotFoundError -Message $_.Exception.Message)) {
            if ($RequireDeploymentRegionCapacity) {
                throw "Azure could not return capacity for the deployment's hosting region and RequireDeploymentRegionCapacity was specified."
            }
            $capacityLookup = 'bestAvailableFallback'
            $warnings += "Azure could not return capacity for the deployment's hosting region. Platform capacity uses the broader '$resolvedOfferScope' offer/scope snapshot."
            $capacityResponse = Invoke-AzJson -Arguments @(
                'rest', '--method', 'get',
                '--url', $baseCapacityUrl,
                '--only-show-errors',
                '--output', 'json'
            )
        }
        else {
            throw
        }
    }

    $result = Get-ManagedComputePreflightResult `
        -UsageResponse $usageResponse `
        -CapacityResponse $capacityResponse `
        -AcceleratorType $AcceleratorType `
        -OfferScope $resolvedOfferScope `
        -QuotaOfferScope $resolvedQuotaOfferScope `
        -ScopeId $ScopeId `
        -TargetCapacity $TargetCapacity `
        -CurrentCapacity $currentCapacity `
        -AcceleratorsPerInstance $AcceleratorsPerInstance

    $resultWithContext = [ordered]@{
        accountId       = $AccountId
        accountLocation = $location
        deploymentId    = $DeploymentId
        skuName         = $SkuName
        offer           = $Offer
        capacityLookup  = $capacityLookup
        acceleratorType = $result.acceleratorType
        capacityOfferScope = $result.capacityOfferScope
        quotaOfferScope = $result.quotaOfferScope
        scopeId         = $result.scopeId
        targetCapacity  = $result.targetCapacity
        currentCapacity = $result.currentCapacity
        acceleratorsPerInstance = $result.acceleratorsPerInstance
        additionalInstancesRequired = $result.additionalInstancesRequired
        additionalAcceleratorsRequired = $result.additionalAcceleratorsRequired
        quota           = $result.quota
        platformCapacity = $result.platformCapacity
        sufficient      = $result.sufficient
        failureReasons  = $result.failureReasons
        warnings        = $warnings
        advisory        = $true
    }

    if ($OutputFormat -eq 'json') {
        $resultWithContext | ConvertTo-Json -Depth 10
    }
    else {
        Write-Output "Managed-compute preflight (advisory)"
        Write-Output "Account: $AccountId"
        Write-Output "Location: $location"
        Write-Output "Accelerator: $AcceleratorType"
        Write-Output "Capacity offer scope: $($result.capacityOfferScope)"
        Write-Output "Quota offer scope: $($result.quotaOfferScope)"
        Write-Output "Instances: $currentCapacity -> $TargetCapacity"
        Write-Output "Additional accelerators required: $($result.additionalAcceleratorsRequired)"
        Write-Output "Capacity lookup: $capacityLookup"
        Write-Output ""
        Write-Output "Quota: $($result.quota.current)/$($result.quota.limit) used; $($result.quota.available) available"
        Write-Output "Platform accelerators available: $($result.platformCapacity.availableAccelerators)"
        Write-Output "Deployment-size instances available: $($result.platformCapacity.totalAvailableCapacity)"
        Write-Output "Largest contiguous deployment capacity: $($result.platformCapacity.largestDeploymentCapacity)"
        Write-Output ""
        if ($result.sufficient) {
            Write-Output "[PASS] Quota and platform capacity are sufficient for this request."
        }
        else {
            foreach ($reason in $result.failureReasons) {
                Write-Output "[FAIL] $reason"
            }
        }
        foreach ($warning in $warnings) {
            Write-Warning $warning
        }
        Write-Output "This check doesn't reserve quota or capacity; the deployment operation remains authoritative."
    }

    if (-not $result.sufficient) {
        exit 1
    }
    exit 0
}
catch {
    [Console]::Error.WriteLine("Managed-compute preflight failed: $($_.Exception.Message)")
    exit 2
}
