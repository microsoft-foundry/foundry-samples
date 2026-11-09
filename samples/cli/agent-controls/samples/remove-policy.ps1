param(
    [Parameter(Mandatory)]
    [ValidatePattern('^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.CognitiveServices/accounts/[^/]+/raiPolicies/[^/]+$')]
    [string]$PolicyId,
    [Parameter(Mandatory)]
    [ValidatePattern('^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.CognitiveServices/accounts/[^/]+/raiRegos/[^/]+$')]
    [string]$RegoId
)

. "$PSScriptRoot\arm.ps1"

$policyAccount = $PolicyId.Substring(0, $PolicyId.LastIndexOf('/raiPolicies/', [StringComparison]::OrdinalIgnoreCase))
$regoAccount = $RegoId.Substring(0, $RegoId.LastIndexOf('/raiRegos/', [StringComparison]::OrdinalIgnoreCase))
if (-not $policyAccount.Equals($regoAccount, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'The policy and Rego must belong to the same account.'
}

function Remove-AgentControlResource {
    param([Parameter(Mandatory)][string]$ResourceId)

    $current = Invoke-AgentControlArm -Method GET -ResourceId $ResourceId -AcceptNotFound
    if ($current.StatusCode -eq 404) { return }
    if (-not $current.ETag) { throw "No ETag returned for $ResourceId." }
    $deleted = Invoke-AgentControlArm -Method DELETE -ResourceId $ResourceId `
        -Headers @{ 'If-Match' = $current.ETag }
    if ($deleted.StatusCode -eq 202) {
        $operationUrl = [string]($deleted.Headers['Azure-AsyncOperation'] | Select-Object -First 1)
        if (-not $operationUrl) {
            throw 'The asynchronous deletion returned no Azure-AsyncOperation URL. Check its status before continuing.'
        }
        $operation = [Uri]$operationUrl
        if ($operation.Scheme -ne 'https' -or $operation.Host -ne 'management.azure.com') {
            throw 'The asynchronous operation URL is not an expected ARM endpoint.'
        }
        $deadline = [DateTime]::UtcNow.AddMinutes(10)
        do {
            Start-Sleep -Seconds 5
            $output = & az rest --method get --url $operationUrl --output json
            if ($LASTEXITCODE -ne 0) { throw 'Unable to read the deletion operation.' }
            $status = ($output -join "`n" | ConvertFrom-Json -AsHashtable).status
            if ($status -in @('Failed', 'Canceled', 'Cancelled')) {
                throw "Resource deletion ended with status $status."
            }
            if ($status -eq 'Succeeded') { break }
        } while ([DateTime]::UtcNow -lt $deadline)
        if ($status -ne 'Succeeded') { throw 'Resource deletion did not finish within ten minutes.' }
    }
    $remaining = Invoke-AgentControlArm -Method GET -ResourceId $ResourceId -AcceptNotFound
    if ($remaining.StatusCode -ne 404) { throw "The resource still exists: $ResourceId." }
}

Remove-AgentControlResource -ResourceId $PolicyId
Remove-AgentControlResource -ResourceId $RegoId
Write-Output 'Deleted the specified policy and Rego resources.'
