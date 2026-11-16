param(
    [Parameter(Mandatory)]
    [ValidatePattern('^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.CognitiveServices/accounts/[^/]+$')]
    [string]$AccountId,
    [Parameter(Mandatory)][string]$TemplateDirectory,
    [ValidatePattern('^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$')][string]$PolicyName
)

. "$PSScriptRoot\arm.ps1"

$directory = (Resolve-Path -LiteralPath $TemplateDirectory).Path
if (-not $PolicyName) { $PolicyName = Split-Path -Leaf $directory }
if ($PolicyName -cnotmatch '^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$') {
    throw 'Use a policy name of 2-64 letters, digits, periods, underscores, or hyphens, starting with a letter or digit.'
}
$policyBody = Get-Content -LiteralPath "$directory\policy.json" -Raw |
    ConvertFrom-Json -AsHashtable
$rego = Get-Content -LiteralPath "$directory\policy.rego" -Raw
if ($policyBody.properties.format -ne 'ACS' -or
    $policyBody.properties.acsRegos.Count -ne 1 -or
    [string]::IsNullOrWhiteSpace($rego)) {
    throw 'The sample requires an ACS policy body and exactly one nonempty Rego module.'
}
$policyBody.properties.acsRegos[0].regoName = $PolicyName
$regoId = "$AccountId/raiRegos/$PolicyName"
$policyId = "$AccountId/raiPolicies/$PolicyName"

$existing = Invoke-AgentControlArm -Method GET -ResourceId $policyId -AcceptNotFound
if ($existing.StatusCode -ne 404) {
    throw 'The policy already exists. Choose a new PolicyName for a new version.'
}
$regoResult = Invoke-AgentControlArm -Method PUT -ResourceId $regoId `
    -Headers @{ 'If-None-Match' = '*' } `
    -Body @{ properties = @{ encoding = 'None'; rego = $rego } }
if (-not $regoResult.ETag) { throw 'Rego creation returned no ETag.' }

$policyResult = Invoke-AgentControlArm -Method PUT -ResourceId $policyId `
    -Headers @{ 'If-None-Match' = '*' } -Body $policyBody
if (-not $policyResult.ETag) { throw 'Policy creation returned no ETag.' }
$saved = Invoke-AgentControlArm -Method GET -ResourceId $policyId
if ($saved.Body.properties.format -ne 'ACS' -or -not $saved.ETag) {
    throw 'Policy read-back did not return ACS format and an ETag.'
}
[pscustomobject]@{
    PolicyId = $saved.Body.id
    PolicyETag = $saved.ETag
    RegoId = $regoId
    RegoETag = $regoResult.ETag
}
