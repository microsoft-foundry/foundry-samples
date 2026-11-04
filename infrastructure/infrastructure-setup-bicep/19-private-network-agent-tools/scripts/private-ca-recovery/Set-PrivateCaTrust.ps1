<#
.SYNOPSIS
    Registers version-pinned public CA certificate secrets on an existing Foundry account.

.DESCRIPTION
    Updates only properties.trustedCertificateSources, preserves unrelated references in the
    same vault, and waits for automatic project propagation. Certificate secret values and
    private keys are never read or printed.

.EXAMPLE
    .\Set-PrivateCaTrust.ps1 `
      -SubscriptionId "<subscription-id>" `
      -ResourceGroup "<resource-group>" `
      -AccountName "<foundry-account>" `
      -KeyVaultResourceId "<key-vault-resource-id>" `
      -CertificateReference @(
        "private-root-ca-pem=0123456789abcdef0123456789abcdef",
        "private-intermediate-ca-pem=fedcba9876543210fedcba9876543210"
      )
#>

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
    [Parameter(Mandatory = $true)]
    [string]$SubscriptionId,

    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string]$AccountName,

    [Parameter(Mandatory = $true)]
    [ValidatePattern("^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.KeyVault/vaults/[^/]+$")]
    [string]$KeyVaultResourceId,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string[]]$CertificateReference,

    [string]$AccountApiVersion = "2026-07-15-preview",

    [ValidateRange(1, 1800)]
    [int]$TimeoutSeconds = 1800,

    [string]$OutputPath = "$PSScriptRoot\.foundry-recovery\private-ca-trust.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$OutputPath =
    $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath(
        $OutputPath
    )

function Invoke-ArmJson {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("GET", "PATCH")]
        [string]$Method,

        [Parameter(Mandatory = $true)]
        [string]$Url,

        [object]$Body
    )

    $target = [uri]$Url
    if (-not $target.IsAbsoluteUri -or $target.Scheme -ne "https" -or
        $target.Host -ne "management.azure.com" -or $target.Port -ne 443 -or
        $target.UserInfo -or $target.Fragment) {
        throw "Unexpected ARM operation URL: $Url."
    }
    $token = & az account get-access-token --subscription $SubscriptionId `
        --resource https://management.azure.com/ --query accessToken `
        --only-show-errors --output tsv
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($token -join ""))) {
        throw "Could not obtain an ARM access token from Azure CLI."
    }
    $arguments = @{
        Method = $Method
        Uri = $Url
        Headers = @{ Authorization = "Bearer $(($token -join '').Trim())" }
        UseBasicParsing = $true
        MaximumRedirection = 0
        TimeoutSec = 60
    }
    if ($null -ne $Body) {
        $arguments.ContentType = "application/json"
        $arguments.Body = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 30))
    }
    $response = Invoke-WebRequest @arguments
    $result = $null
    if (-not [string]::IsNullOrWhiteSpace([string]$response.Content)) {
        $result = $response.Content | ConvertFrom-Json
    }
    return [pscustomobject]@{ Headers = $response.Headers; Body = $result }
}

function Get-TrustSources {
    param([object]$Account)

    $property = $Account.properties.PSObject.Properties["trustedCertificateSources"]
    if ($null -eq $property -or $null -eq $property.Value) {
        return
    }
    if ($property.Value -isnot [array]) {
        throw "Unexpected trustedCertificateSources value; review the account configuration."
    }
    foreach ($source in $property.Value) {
        if ($null -eq $source) {
            throw "Unexpected null trust source; review the account configuration."
        }
    }
    return $property.Value
}

function Get-HeaderValue {
    param([object]$Headers, [string]$Name)

    return [string](@($Headers[$Name])[0])
}

$certificates = @()
$seenNames = @{}
foreach ($reference in $CertificateReference) {
    if ($reference -notmatch "^(?<name>[A-Za-z0-9-]{1,127})=(?<version>[A-Za-z0-9]+)$") {
        throw "Invalid certificate reference '$reference'. Use <secret-name>=<secret-version>."
    }
    $name = $Matches["name"]
    $version = $Matches["version"]
    if ($seenNames.ContainsKey($name)) {
        throw "Duplicate certificate secret name: $name."
    }
    $seenNames[$name] = $true
    $certificates += [ordered]@{ secretName = $name; secretVersion = $version }
}

$accountId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/" +
    "Microsoft.CognitiveServices/accounts/$AccountName"
$accountUrl = "https://management.azure.com${accountId}?api-version=$AccountApiVersion"
$account = (Invoke-ArmJson -Method GET -Url $accountUrl).Body
$existingSources = @(Get-TrustSources -Account $account)
if ($existingSources.Count -gt 1) {
    throw "Only one Key Vault source is supported; review the account configuration."
}
$updatedSource = [ordered]@{
    type = "AzureKeyVault"
    resourceId = $KeyVaultResourceId
    certificateBundleReferences = @()
}
$existingCertificates = @()
if ($existingSources.Count -eq 1) {
    $source = $existingSources[0]
    if ($null -eq $source -or
        $null -eq $source.PSObject.Properties["type"] -or
        $source.type -cne "AzureKeyVault" -or
        $null -eq $source.PSObject.Properties["resourceId"] -or
        [string]$source.resourceId -ine $KeyVaultResourceId) {
        throw "Existing trust uses an unexpected source or another vault; refusing to replace it."
    }
    $bundleProperty = $source.PSObject.Properties["certificateBundleReferences"]
    if ($null -eq $bundleProperty -or $bundleProperty.Value -isnot [array]) {
        throw "Unexpected certificateBundleReferences; review the account configuration."
    }
    $existingNames = @{}
    foreach ($certificate in $bundleProperty.Value) {
        if ($null -eq $certificate -or
            $null -eq $certificate.PSObject.Properties["secretName"] -or
            [string]$certificate.secretName -notmatch "^[A-Za-z0-9-]{1,127}$" -or
            $null -eq $certificate.PSObject.Properties["secretVersion"] -or
            [string]$certificate.secretVersion -notmatch "^[A-Za-z0-9]+$") {
            throw "Unexpected certificate bundle reference; review the account configuration."
        }
        if ($existingNames.ContainsKey([string]$certificate.secretName)) {
            throw "Duplicate existing secret name: $($certificate.secretName)."
        }
        $existingNames[[string]$certificate.secretName] = $true
    }
    $existingCertificates = @($bundleProperty.Value)
    foreach ($property in $source.PSObject.Properties) {
        $updatedSource[$property.Name] = $property.Value
    }
}
$preserved = @(
    $existingCertificates |
        Where-Object { -not $seenNames.ContainsKey([string]$_.secretName) }
)
$updatedSource.certificateBundleReferences = @($preserved) + @($certificates)
if ($updatedSource.certificateBundleReferences.Count -gt 25) {
    throw "The update would exceed the account limit of 25 certificate bundle references."
}
$updatedSources = @($updatedSource)

if (-not $PSCmdlet.ShouldProcess(
    $accountId,
    "Replace properties.trustedCertificateSources while preserving unrelated references"
)) {
    return
}

$recheck = (Invoke-ArmJson -Method GET -Url $accountUrl).Body
$recheckedSources = @(Get-TrustSources -Account $recheck)
if ((ConvertTo-Json -InputObject $existingSources -Depth 30 -Compress) -cne
    (ConvertTo-Json -InputObject $recheckedSources -Depth 30 -Compress)) {
    throw "Trust configuration changed since the initial read; review and rerun. No update submitted."
}

$parent = Split-Path -Parent $OutputPath
if (-not [string]::IsNullOrWhiteSpace($parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}
$response = Invoke-ArmJson -Method PATCH -Url $accountUrl -Body @{
    properties = @{ trustedCertificateSources = $updatedSources }
}
$operationUrl = Get-HeaderValue -Headers $response.Headers -Name "Azure-AsyncOperation"
if ([string]::IsNullOrWhiteSpace($operationUrl)) {
    throw "No Azure-AsyncOperation URL returned. Completion is unknown; inspect the account before resubmitting."
}
$operationPath = "$OutputPath.operation.txt"
[IO.File]::WriteAllText($operationPath, $operationUrl, [Text.UTF8Encoding]::new($false))
$timer = [Diagnostics.Stopwatch]::StartNew()
try {
    while ($true) {
        $retryAfter = Get-HeaderValue -Headers $response.Headers -Name "Retry-After"
        $delay = 10
        if (-not [string]::IsNullOrWhiteSpace($retryAfter)) {
            if (-not [int]::TryParse($retryAfter, [ref]$delay) -or $delay -lt 0) {
                throw "Invalid Retry-After header: $retryAfter."
            }
            $delay = [Math]::Max(1, $delay)
        }
        if ($timer.Elapsed.TotalSeconds + $delay -ge $TimeoutSeconds) {
            throw "Monitoring timed out; completion is unknown."
        }
        Start-Sleep -Seconds $delay
        $response = Invoke-ArmJson -Method GET -Url $operationUrl
        $statusProperty = $null
        if ($null -ne $response.Body) {
            $statusProperty = $response.Body.PSObject.Properties["status"]
        }
        $status = if ($null -ne $statusProperty) { [string]$statusProperty.Value } else { "" }
        if ($status -eq "Succeeded") {
            break
        }
        if ($status -in @("Failed", "Canceled", "Cancelled")) {
            throw "Account update did not succeed: $($response.Body | ConvertTo-Json -Depth 30 -Compress)"
        }
        if ($status -notin @("Accepted", "NotStarted", "Running", "InProgress", "Updating")) {
            throw "Unexpected LRO response: $($response.Body | ConvertTo-Json -Depth 30 -Compress)"
        }
    }
}
catch {
    throw "$($_.Exception.Message) Operation URL saved in '$operationPath'. Monitoring does not cancel the update; check the operation before resubmitting."
}

$stored = (Invoke-ArmJson -Method GET -Url $accountUrl).Body
$storedSources = @(Get-TrustSources -Account $stored)
if ($storedSources.Count -ne 1 -or
    $storedSources[0].type -cne "AzureKeyVault" -or
    [string]$storedSources[0].resourceId -ine $KeyVaultResourceId -or
    @($storedSources[0].certificateBundleReferences).Count -ne $updatedSource.certificateBundleReferences.Count) {
    throw "Foundry didn't persist the intended trust source. Inspect the account before resubmitting."
}
foreach ($certificate in $updatedSource.certificateBundleReferences) {
    $match = @(
        $storedSources[0].certificateBundleReferences |
            Where-Object {
                [string]$_.secretName -ieq $certificate.secretName -and
                [string]$_.secretVersion -ceq $certificate.secretVersion
            }
    )
    if ($match.Count -ne 1) {
        throw "Foundry didn't persist $($certificate.secretName) at version $($certificate.secretVersion)."
    }
}

$report = [ordered]@{
    capturedAtUtc = [DateTime]::UtcNow.ToString("o")
    accountResourceId = $accountId
    accountApiVersion = $AccountApiVersion
    keyVaultResourceId = $KeyVaultResourceId
    certificates = $certificates
    trustedCertificateSources = $storedSources
    operationUrl = $operationUrl
    nextStep = "Trust propagates automatically to project capability hosts. Test managed-tool HTTPS; use a fresh sandbox for Hosted Agent direct HTTPS."
}
[IO.File]::WriteAllText(
    $OutputPath,
    ($report | ConvertTo-Json -Depth 30),
    [Text.UTF8Encoding]::new($false)
)
$report | ConvertTo-Json -Depth 30
