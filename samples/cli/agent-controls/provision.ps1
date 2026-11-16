param(
    [Parameter(Mandatory)][string]$SubscriptionId,
    [Parameter(Mandatory)][string]$ResourceGroup,
    [Parameter(Mandatory)][string]$AccountName,
    [Parameter(Mandatory)][string]$Location
)

. "$PSScriptRoot\arm.ps1"

& az account set --subscription $SubscriptionId
if ($LASTEXITCODE -ne 0) { throw 'Unable to select the subscription.' }
& az provider register --namespace Microsoft.CognitiveServices --wait --output none
if ($LASTEXITCODE -ne 0) { throw 'Unable to register Microsoft.CognitiveServices.' }
& az group create --name $ResourceGroup --location $Location --output none
if ($LASTEXITCODE -ne 0) { throw 'Unable to create the resource group.' }

$AccountId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.CognitiveServices/accounts/$AccountName"
$existing = Invoke-AgentControlArm -Method GET -ResourceId $AccountId -AcceptNotFound
if ($existing.StatusCode -ne 404) {
    throw 'The account already exists. Use a new account name or follow the existing-account instructions.'
}
$body = @{
    location = $Location
    kind = 'ContentSafety'
    sku = @{ name = 'S0' }
    identity = @{ type = 'SystemAssigned' }
    properties = @{ customSubDomainName = $AccountName }
}
$null = Invoke-AgentControlArm -Method PUT -ResourceId $AccountId -Body $body `
    -Headers @{ 'If-None-Match' = '*' }

$deadline = [DateTime]::UtcNow.AddMinutes(10)
do {
    $account = Invoke-AgentControlArm -Method GET -ResourceId $AccountId
    $state = $account.Body.properties.provisioningState
    if ($state -in @('Failed', 'Canceled', 'Cancelled')) {
        throw "Account provisioning failed: $state."
    }
    if ($state -eq 'Succeeded') { break }
    Start-Sleep -Seconds 5
} while ([DateTime]::UtcNow -lt $deadline)
if ($state -ne 'Succeeded') { throw 'Account provisioning did not finish within ten minutes.' }
if (-not $account.Body.properties.endpoint) { throw 'The account has no data-plane endpoint.' }

[pscustomobject]@{
    AccountId = $account.Body.id
    Endpoint = $account.Body.properties.endpoint.TrimEnd('/')
    ServingPrincipalId = $account.Body.identity.principalId
}
