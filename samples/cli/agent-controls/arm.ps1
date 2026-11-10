$ErrorActionPreference = 'Stop'

function Invoke-AgentControlArm {
    param(
        [Parameter(Mandatory)]
        [ValidateSet('GET', 'PUT', 'DELETE')][string]$Method,
        [Parameter(Mandatory)][string]$ResourceId,
        [string]$ApiVersion = '2026-11-15-preview',
        [hashtable]$Body,
        [hashtable]$Headers = @{},
        [switch]$AcceptNotFound
    )

    $token = & az account get-access-token --resource 'https://management.azure.com/' `
        --query accessToken --output tsv
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($token)) {
        throw 'Unable to obtain an ARM token. Check az login and the selected subscription.'
    }
    $requestHeaders = @{
        Authorization = "Bearer $token"
        'x-ms-client-request-id' = [guid]::NewGuid().ToString()
    }
    foreach ($key in $Headers.Keys) { $requestHeaders[$key] = $Headers[$key] }
    $request = @{
        Method = $Method
        Uri = "https://management.azure.com${ResourceId}?api-version=$ApiVersion"
        Headers = $requestHeaders
        ContentType = 'application/json'
        SkipHttpErrorCheck = $true
        TimeoutSec = 60
    }
    if ($null -ne $Body) {
        $request.Body = [Text.Encoding]::UTF8.GetBytes(
            ($Body | ConvertTo-Json -Depth 64 -Compress)
        )
    }
    $response = Invoke-WebRequest @request
    $parsed = if ([string]::IsNullOrWhiteSpace($response.Content)) {
        $null
    } else {
        $response.Content | ConvertFrom-Json -AsHashtable
    }
    if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) {
        if (-not ($Method -eq 'GET' -and $AcceptNotFound -and $response.StatusCode -eq 404)) {
            throw "ARM HTTP $($response.StatusCode): $($parsed.error.code): $($parsed.error.message)"
        }
    }
    [pscustomobject]@{
        StatusCode = [int]$response.StatusCode
        Body = $parsed
        ETag = [string]($response.Headers['ETag'] | Select-Object -First 1)
        Headers = $response.Headers
    }
}
