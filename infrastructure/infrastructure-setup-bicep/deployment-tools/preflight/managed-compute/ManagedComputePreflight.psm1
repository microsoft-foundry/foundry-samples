Set-StrictMode -Version Latest

function Test-ManagedComputeNotFoundError {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Message
    )

    return $Message -match '(?i)not[\s_-]*found|\b404\b'
}

function Get-ManagedComputePropertyValue {
    param(
        [Parameter(Mandatory)]
        [object]$InputObject,

        [Parameter(Mandatory)]
        [string]$PropertyName
    )

    $property = $InputObject.PSObject.Properties[$PropertyName]
    if ($null -eq $property) {
        return $null
    }
    return $property.Value
}

function Resolve-ManagedComputeQuotaRecord {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object]$UsageResponse,

        [Parameter(Mandatory)]
        [string]$AcceleratorType,

        [Parameter(Mandatory)]
        [string]$OfferScope
    )

    $suffix = ".$AcceleratorType"
    $matchingRecords = @(
        $UsageResponse.value | Where-Object {
            $_.offerScope -ieq $OfferScope -and
            $_.unit -eq 'AcceleratorCount' -and
            $_.name.value.EndsWith($suffix, [System.StringComparison]::OrdinalIgnoreCase)
        }
    )

    if ($matchingRecords.Count -eq 0) {
        throw "No quota record matched accelerator '$AcceleratorType' and offer scope '$OfferScope'."
    }
    if ($matchingRecords.Count -gt 1) {
        $names = ($matchingRecords | ForEach-Object { $_.name.value }) -join ', '
        throw "Multiple quota records matched accelerator '$AcceleratorType' and offer scope '$OfferScope': $names."
    }

    return $matchingRecords[0]
}

function Resolve-ManagedComputeCapacityRecord {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object]$CapacityResponse,

        [Parameter(Mandatory)]
        [string]$AcceleratorType,

        [Parameter(Mandatory)]
        [string]$OfferScope,

        [string]$ScopeId = ''
    )

    $values = @($CapacityResponse.value)
    $acceleratorMatches = @(
        $values | Where-Object {
            $returnedAccelerator = Get-ManagedComputePropertyValue `
                -InputObject $_.properties `
                -PropertyName 'acceleratorType'
            $returnedAccelerator -and $returnedAccelerator -ieq $AcceleratorType
        }
    )

    if ($acceleratorMatches.Count -eq 0) {
        $acceleratorMatches = $values
    }
    if ($acceleratorMatches.Count -eq 0) {
        throw "No capacity records were returned for accelerator '$AcceleratorType'."
    }

    $scopeMatches = @(
        $acceleratorMatches | Where-Object {
            $returnedScope = Get-ManagedComputePropertyValue `
                -InputObject $_.properties `
                -PropertyName 'offerScope'
            $returnedScope -and $returnedScope -ieq $OfferScope
        }
    )

    if ($scopeMatches.Count -eq 0) {
        $recordsWithoutScope = @(
            $acceleratorMatches | Where-Object {
                -not (Get-ManagedComputePropertyValue `
                    -InputObject $_.properties `
                    -PropertyName 'offerScope')
            }
        )
        if ($acceleratorMatches.Count -eq 1 -and $recordsWithoutScope.Count -eq 1) {
            $scopeMatches = $recordsWithoutScope
        }
        else {
            throw "No unambiguous capacity record matched offer scope '$OfferScope'."
        }
    }

    if ($ScopeId) {
        $scopeMatches = @(
            $scopeMatches | Where-Object {
                $returnedScopeId = Get-ManagedComputePropertyValue `
                    -InputObject $_.properties `
                    -PropertyName 'scopeId'
                $returnedScopeId -and $returnedScopeId -ieq $ScopeId
            }
        )
    }
    elseif ($OfferScope -ieq 'Global') {
        $globalMatches = @(
            $scopeMatches | Where-Object {
                -not (Get-ManagedComputePropertyValue `
                    -InputObject $_.properties `
                    -PropertyName 'scopeId')
            }
        )
        if ($globalMatches.Count -gt 0) {
            $scopeMatches = $globalMatches
        }
    }

    if ($scopeMatches.Count -eq 0) {
        throw "No capacity record matched offer scope '$OfferScope' and scope ID '$ScopeId'."
    }
    if ($scopeMatches.Count -gt 1) {
        $names = ($scopeMatches | ForEach-Object { $_.name }) -join ', '
        throw "Multiple capacity records matched accelerator '$AcceleratorType' and scope '$OfferScope': $names."
    }

    return $scopeMatches[0]
}

function Resolve-ManagedComputeDeploymentSize {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object]$CapacityRecord,

        [Parameter(Mandatory)]
        [ValidateRange(1, [int]::MaxValue)]
        [int]$AcceleratorsPerInstance
    )

    $matchingRecords = @(
        $CapacityRecord.properties.deploymentSizeCapacities | Where-Object {
            [int]$_.modelInstanceAcceleratorCount -eq $AcceleratorsPerInstance
        }
    )

    if ($matchingRecords.Count -eq 0) {
        throw "No deployment-size capacity row matched $AcceleratorsPerInstance accelerator(s) per model instance."
    }
    if ($matchingRecords.Count -gt 1) {
        throw "Multiple deployment-size capacity rows matched $AcceleratorsPerInstance accelerator(s) per model instance."
    }

    return $matchingRecords[0]
}

function Get-ManagedComputePreflightResult {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [object]$UsageResponse,

        [Parameter(Mandatory)]
        [object]$CapacityResponse,

        [Parameter(Mandatory)]
        [string]$AcceleratorType,

        [Parameter(Mandatory)]
        [string]$OfferScope,

        [string]$QuotaOfferScope = '',

        [string]$ScopeId = '',

        [Parameter(Mandatory)]
        [ValidateRange(1, [int]::MaxValue)]
        [int]$TargetCapacity,

        [ValidateRange(0, [int]::MaxValue)]
        [int]$CurrentCapacity = 0,

        [Parameter(Mandatory)]
        [ValidateRange(1, [int]::MaxValue)]
        [int]$AcceleratorsPerInstance
    )

    $resolvedQuotaOfferScope = if ($QuotaOfferScope) {
        $QuotaOfferScope
    }
    else {
        $OfferScope
    }

    $quotaRecord = Resolve-ManagedComputeQuotaRecord `
        -UsageResponse $UsageResponse `
        -AcceleratorType $AcceleratorType `
        -OfferScope $resolvedQuotaOfferScope
    $capacityRecord = Resolve-ManagedComputeCapacityRecord `
        -CapacityResponse $CapacityResponse `
        -AcceleratorType $AcceleratorType `
        -OfferScope $OfferScope `
        -ScopeId $ScopeId
    $deploymentSize = Resolve-ManagedComputeDeploymentSize `
        -CapacityRecord $capacityRecord `
        -AcceleratorsPerInstance $AcceleratorsPerInstance

    $additionalInstances = [Math]::Max(0, $TargetCapacity - $CurrentCapacity)
    $additionalAccelerators = $additionalInstances * $AcceleratorsPerInstance
    $quotaAvailable = [Math]::Max(0, [int]$quotaRecord.limit - [int]$quotaRecord.currentValue)
    $quotaSufficient = $quotaAvailable -ge $additionalAccelerators

    $availableAccelerators = [int]$capacityRecord.properties.availableAccelerators
    $totalAvailableCapacity = [int]$deploymentSize.totalAvailableCapacity
    $largestDeploymentCapacity = [int]$deploymentSize.largestDeploymentCapacity
    $capacitySufficient = (
        $availableAccelerators -ge $additionalAccelerators -and
        $totalAvailableCapacity -ge $additionalInstances -and
        $largestDeploymentCapacity -ge $additionalInstances
    )

    $failureReasons = @()
    if (-not $quotaSufficient) {
        $failureReasons += "Quota has $quotaAvailable accelerator(s) available but $additionalAccelerators additional accelerator(s) are required."
    }
    if ($availableAccelerators -lt $additionalAccelerators) {
        $failureReasons += "Platform capacity has $availableAccelerators accelerator(s) available but $additionalAccelerators additional accelerator(s) are required."
    }
    if ($totalAvailableCapacity -lt $additionalInstances) {
        $failureReasons += "The deployment-size pool has $totalAvailableCapacity model instance(s) available but $additionalInstances additional instance(s) are required."
    }
    if ($largestDeploymentCapacity -lt $additionalInstances) {
        $failureReasons += "The largest contiguous deployment capacity is $largestDeploymentCapacity but $additionalInstances additional instance(s) are required."
    }

    return [pscustomobject]@{
        acceleratorType              = $AcceleratorType
        capacityOfferScope           = $OfferScope
        quotaOfferScope              = $resolvedQuotaOfferScope
        scopeId                      = $ScopeId
        targetCapacity               = $TargetCapacity
        currentCapacity              = $CurrentCapacity
        acceleratorsPerInstance      = $AcceleratorsPerInstance
        additionalInstancesRequired  = $additionalInstances
        additionalAcceleratorsRequired = $additionalAccelerators
        quota                        = [pscustomobject]@{
            metricName = $quotaRecord.name.value
            current    = [int]$quotaRecord.currentValue
            limit      = [int]$quotaRecord.limit
            available  = $quotaAvailable
            sufficient = $quotaSufficient
        }
        platformCapacity             = [pscustomobject]@{
            resourceName               = $capacityRecord.name
            returnedAcceleratorType     = Get-ManagedComputePropertyValue `
                -InputObject $capacityRecord.properties `
                -PropertyName 'acceleratorType'
            availableAccelerators       = $availableAccelerators
            totalAvailableCapacity      = $totalAvailableCapacity
            largestDeploymentCapacity   = $largestDeploymentCapacity
            modelInstanceAcceleratorCount = [int]$deploymentSize.modelInstanceAcceleratorCount
            sufficient                  = $capacitySufficient
        }
        sufficient                   = ($quotaSufficient -and $capacitySufficient)
        failureReasons               = $failureReasons
        advisory                     = $true
    }
}

Export-ModuleMember -Function `
    Test-ManagedComputeNotFoundError, `
    Resolve-ManagedComputeQuotaRecord, `
    Resolve-ManagedComputeCapacityRecord, `
    Resolve-ManagedComputeDeploymentSize, `
    Get-ManagedComputePreflightResult
