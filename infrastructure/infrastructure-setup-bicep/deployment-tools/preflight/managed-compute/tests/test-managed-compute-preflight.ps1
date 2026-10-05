$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Import-Module (Join-Path $PSScriptRoot '../ManagedComputePreflight.psm1') -Force

function Assert-Equal {
    param(
        [Parameter(Mandatory)]
        [object]$Actual,

        [Parameter(Mandatory)]
        [object]$Expected,

        [Parameter(Mandatory)]
        [string]$Message
    )

    if ($Actual -ne $Expected) {
        throw "$Message. Expected '$Expected', got '$Actual'."
    }
}

function Get-TestUsageResponse {
    param(
        [string]$AcceleratorType = 'A100_80GB',
        [int]$Current = 16,
        [int]$Limit = 24,
        [string]$OfferScope = 'Global'
    )

    return [pscustomobject]@{
        value = @(
            [pscustomobject]@{
                name = [pscustomobject]@{
                    value = "ManagedCompute.$OfferScope.$AcceleratorType"
                }
                offerScope  = $OfferScope
                currentValue = $Current
                limit       = $Limit
                unit        = 'AcceleratorCount'
            }
        )
    }
}

function Get-TestCapacityResponse {
    param(
        [string]$AcceleratorType = 'A100_80GB',
        [int]$AvailableAccelerators = 119,
        [object[]]$DeploymentSizes = @(
            [pscustomobject]@{
                modelInstanceAcceleratorCount = 1
                totalAvailableCapacity        = 119
                largestDeploymentCapacity     = 119
            }
        ),
        [string]$OfferScope = 'Global',
        [string]$ScopeId = ''
    )

    return [pscustomobject]@{
        value = @(
            [pscustomobject]@{
                name       = "$AcceleratorType.$OfferScope"
                properties = [pscustomobject]@{
                    acceleratorType         = $AcceleratorType
                    availableAccelerators   = $AvailableAccelerators
                    deploymentSizeCapacities = $DeploymentSizes
                    offerScope              = $OfferScope
                    scopeId                 = $ScopeId
                }
            }
        )
    }
}

foreach ($message in @(
    'ERROR: Not Found',
    'Code: NotFound',
    'ResourceNotFound',
    'Request failed with HTTP 404'
)) {
    Assert-Equal `
        (Test-ManagedComputeNotFoundError -Message $message) `
        $true `
        "Expected not-found match for '$message'"
}
Assert-Equal `
    (Test-ManagedComputeNotFoundError -Message 'Request failed with HTTP 403') `
    $false `
    'HTTP 403 should not match not-found detection'

$createResult = Get-ManagedComputePreflightResult `
    -UsageResponse (Get-TestUsageResponse) `
    -CapacityResponse (Get-TestCapacityResponse) `
    -AcceleratorType 'A100_80GB' `
    -OfferScope 'Global' `
    -TargetCapacity 2 `
    -AcceleratorsPerInstance 1
Assert-Equal $createResult.additionalInstancesRequired 2 'Create should require all target instances'
Assert-Equal $createResult.additionalAcceleratorsRequired 2 'Create accelerator calculation is incorrect'
Assert-Equal $createResult.sufficient $true 'Create should pass'

$scaleResult = Get-ManagedComputePreflightResult `
    -UsageResponse (Get-TestUsageResponse -Current 17) `
    -CapacityResponse (Get-TestCapacityResponse) `
    -AcceleratorType 'A100_80GB' `
    -OfferScope 'Global' `
    -TargetCapacity 2 `
    -CurrentCapacity 1 `
    -AcceleratorsPerInstance 1
Assert-Equal $scaleResult.additionalInstancesRequired 1 'Scale should require only the capacity delta'
Assert-Equal $scaleResult.additionalAcceleratorsRequired 1 'Scale accelerator calculation is incorrect'
Assert-Equal $scaleResult.sufficient $true 'Scale should pass'

$multiGpuSizes = @(
    [pscustomobject]@{
        modelInstanceAcceleratorCount = 1
        totalAvailableCapacity        = 8
        largestDeploymentCapacity     = 8
    },
    [pscustomobject]@{
        modelInstanceAcceleratorCount = 2
        totalAvailableCapacity        = 4
        largestDeploymentCapacity     = 3
    }
)
$multiGpuResult = Get-ManagedComputePreflightResult `
    -UsageResponse (Get-TestUsageResponse -AcceleratorType 'H100_80GB' -Current 2 -Limit 20) `
    -CapacityResponse (Get-TestCapacityResponse -AcceleratorType 'H100_80GB' -AvailableAccelerators 10 -DeploymentSizes $multiGpuSizes) `
    -AcceleratorType 'H100_80GB' `
    -OfferScope 'Global' `
    -TargetCapacity 3 `
    -AcceleratorsPerInstance 2
Assert-Equal $multiGpuResult.additionalAcceleratorsRequired 6 'Multi-GPU accelerator calculation is incorrect'
Assert-Equal $multiGpuResult.platformCapacity.modelInstanceAcceleratorCount 2 'Wrong deployment-size row selected'
Assert-Equal $multiGpuResult.sufficient $true 'Multi-GPU create should pass'

$quotaFailure = Get-ManagedComputePreflightResult `
    -UsageResponse (Get-TestUsageResponse -Current 23 -Limit 24) `
    -CapacityResponse (Get-TestCapacityResponse) `
    -AcceleratorType 'A100_80GB' `
    -OfferScope 'Global' `
    -TargetCapacity 2 `
    -AcceleratorsPerInstance 1
Assert-Equal $quotaFailure.quota.sufficient $false 'Insufficient quota should fail'
Assert-Equal $quotaFailure.sufficient $false 'Overall result should fail on quota'

$capacityFailure = Get-ManagedComputePreflightResult `
    -UsageResponse (Get-TestUsageResponse) `
    -CapacityResponse (Get-TestCapacityResponse -AvailableAccelerators 1) `
    -AcceleratorType 'A100_80GB' `
    -OfferScope 'Global' `
    -TargetCapacity 2 `
    -AcceleratorsPerInstance 1
Assert-Equal $capacityFailure.platformCapacity.sufficient $false 'Insufficient platform capacity should fail'
Assert-Equal $capacityFailure.sufficient $false 'Overall result should fail on platform capacity'

$scaleDown = Get-ManagedComputePreflightResult `
    -UsageResponse (Get-TestUsageResponse -Current 24 -Limit 24) `
    -CapacityResponse (Get-TestCapacityResponse -AvailableAccelerators 0) `
    -AcceleratorType 'A100_80GB' `
    -OfferScope 'Global' `
    -TargetCapacity 1 `
    -CurrentCapacity 2 `
    -AcceleratorsPerInstance 1
Assert-Equal $scaleDown.additionalAcceleratorsRequired 0 'Scale-down should require no additional accelerators'
Assert-Equal $scaleDown.sufficient $true 'Scale-down should pass without free quota or capacity'

$missingSizeFailed = $false
try {
    Get-ManagedComputePreflightResult `
        -UsageResponse (Get-TestUsageResponse) `
        -CapacityResponse (Get-TestCapacityResponse) `
        -AcceleratorType 'A100_80GB' `
        -OfferScope 'Global' `
        -TargetCapacity 1 `
        -AcceleratorsPerInstance 2 | Out-Null
}
catch {
    $missingSizeFailed = $true
}
Assert-Equal $missingSizeFailed $true 'A missing deployment-size row should fail'

$ambiguousCapacity = [pscustomobject]@{
    value = @(
        (Get-TestCapacityResponse).value[0],
        (Get-TestCapacityResponse).value[0]
    )
}
$ambiguousFailed = $false
try {
    Resolve-ManagedComputeCapacityRecord `
        -CapacityResponse $ambiguousCapacity `
        -AcceleratorType 'A100_80GB' `
        -OfferScope 'Global' | Out-Null
}
catch {
    $ambiguousFailed = $true
}
Assert-Equal $ambiguousFailed $true 'Ambiguous capacity records should fail'

$legacyCapacity = Get-TestCapacityResponse
$legacyCapacity.value[0].properties.PSObject.Properties.Remove('offerScope')
$legacyCapacity.value[0].properties.PSObject.Properties.Remove('scopeId')
$legacyMatch = Resolve-ManagedComputeCapacityRecord `
    -CapacityResponse $legacyCapacity `
    -AcceleratorType 'A100_80GB' `
    -OfferScope 'Global'
Assert-Equal $legacyMatch.name 'A100_80GB.Global' 'A single legacy capacity record should be accepted'

$aliasCapacity = [pscustomobject]@{
    value = @(
        [pscustomobject]@{
            name       = 'Azure.A100.Global'
            properties = [pscustomobject]@{
                acceleratorType         = 'Azure.A100'
                availableAccelerators   = 10
                deploymentSizeCapacities = $multiGpuSizes
                offerScope              = 'Global'
                scopeId                 = ''
            }
        },
        [pscustomobject]@{
            name       = 'Azure.A100.DataZone.US'
            properties = [pscustomobject]@{
                acceleratorType         = 'Azure.A100'
                availableAccelerators   = 5
                deploymentSizeCapacities = $multiGpuSizes
                offerScope              = 'DataZone'
                scopeId                 = 'US'
            }
        }
    )
}
$aliasMatch = Resolve-ManagedComputeCapacityRecord `
    -CapacityResponse $aliasCapacity `
    -AcceleratorType 'A100_80GB' `
    -OfferScope 'Global'
Assert-Equal $aliasMatch.name 'Azure.A100.Global' 'Scope should disambiguate an accelerator alias'

$dataZoneResult = Get-ManagedComputePreflightResult `
    -UsageResponse (Get-TestUsageResponse -OfferScope 'Datazone-US') `
    -CapacityResponse (Get-TestCapacityResponse -OfferScope 'DataZone' -ScopeId 'US') `
    -AcceleratorType 'A100_80GB' `
    -OfferScope 'DataZone' `
    -QuotaOfferScope 'Datazone-US' `
    -ScopeId 'US' `
    -TargetCapacity 1 `
    -AcceleratorsPerInstance 1
Assert-Equal $dataZoneResult.capacityOfferScope 'DataZone' 'Capacity offer scope is incorrect'
Assert-Equal $dataZoneResult.quotaOfferScope 'Datazone-US' 'Quota offer scope is incorrect'
Assert-Equal $dataZoneResult.sufficient $true 'Data Zone create should pass'

Write-Output 'Managed-compute preflight tests passed.'
