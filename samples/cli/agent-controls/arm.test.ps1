$ErrorActionPreference = 'Stop'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

$testState = @{
    AccountId = '/subscriptions/test/resourceGroups/sample/providers/Microsoft.CognitiveServices/accounts/sample'
    Requests = [Collections.Generic.List[hashtable]]::new()
    Conflict = $false
}

# All external commands are mocked; this test never contacts Azure.
function az {
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'account' -and $args[1] -eq 'get-access-token') {
        return 'synthetic-test-token'
    }
}

function Invoke-WebRequest {
    param($Method, $Uri, $Headers, $ContentType, $SkipHttpErrorCheck, $TimeoutSec, $Body)
    $testState.Requests.Add(@{ Method = $Method; Uri = $Uri; Headers = $Headers })
    if ($Method -eq 'PUT') {
        Assert-True ($Headers['If-None-Match'] -ceq '*') 'Account creation must be conditional.'
        if ($testState.Conflict) {
            return @{ StatusCode = 412; Headers = @{}; Content = '{"error":{"code":"PreconditionFailed"}}' }
        }
        return @{ StatusCode = 201; Headers = @{}; Content = '{}' }
    }
    if ($Method -eq 'GET' -and $testState.Requests.Count -eq 1) {
        return @{ StatusCode = 404; Headers = @{}; Content = '{"error":{"code":"ResourceNotFound"}}' }
    }
    if ($Method -eq 'GET') {
        return @{
            StatusCode = 200
            Headers = @{}
            Content = (@{
                id = $testState.AccountId
                identity = @{ principalId = 'synthetic-principal' }
                properties = @{
                    provisioningState = 'Succeeded'
                    endpoint = 'https://sample.cognitiveservices.azure.com/'
                }
            } | ConvertTo-Json -Depth 4 -Compress)
        }
    }
    throw "Unexpected request: $Method $Uri"
}

$parameters = @{
    SubscriptionId = 'test'
    ResourceGroup = 'sample'
    AccountName = 'sample'
    Location = 'westus'
}
$created = & "$PSScriptRoot/provision.ps1" @parameters
Assert-True ($created.AccountId -ceq $testState.AccountId) 'Provisioning did not return the created account.'
Assert-True ($testState.Requests.Count -eq 3) 'Expected one lookup, one creation, and one status read.'

$testState.Requests.Clear()
$testState.Conflict = $true
$failure = $null
try { $null = & "$PSScriptRoot/provision.ps1" @parameters } catch { $failure = $_ }
Assert-True ($null -ne $failure -and $failure.Exception.Message -match 'ARM HTTP 412') 'A creation race must fail closed.'
Assert-True ($testState.Requests.Count -eq 2) 'A creation conflict must not retry or clean up another account.'
Write-Output 'PASS: conditional account creation and concurrent-creation conflict.'
