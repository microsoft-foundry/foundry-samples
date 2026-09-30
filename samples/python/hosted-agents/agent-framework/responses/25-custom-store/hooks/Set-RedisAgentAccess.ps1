#!/usr/bin/env pwsh
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: MIT
#Requires -Version 7.0

<#
.SYNOPSIS
    Grants the deployed hosted agent identity access to Azure Managed Redis.
.DESCRIPTION
    Gets the deployed agent identity, then adds that identity to Redis
    authentication with the default access policy.
.EXAMPLE
    ./hooks/Set-RedisAgentAccess.ps1
.NOTES
    Runs automatically as the azd postdeploy hook.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Set-RedisAgentAccess {
    [CmdletBinding()]
    [OutputType([void])]
    param()

    $AzdValues = @{}
    azd env get-values | ForEach-Object {
        if ($_ -match '^([^=]+)="(.*)"$') {
            $AzdValues[$Matches[1]] = $Matches[2]
        }
    }
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to read the selected azd environment.'
    }

    $ProjectEndpoint = $AzdValues['AZURE_AI_PROJECT_ENDPOINT'] ??
        $AzdValues['FOUNDRY_PROJECT_ENDPOINT']
    $AgentName = $AzdValues.Keys |
        Where-Object { $_ -match '^AGENT_.*_NAME$' } |
        ForEach-Object { $AzdValues[$_] } |
        Select-Object -First 1
    $RedisDatabaseId = $AzdValues['REDIS_DATABASE_RESOURCE_ID']

    if ([string]::IsNullOrWhiteSpace($ProjectEndpoint) -or
        [string]::IsNullOrWhiteSpace($AgentName) -or
        [string]::IsNullOrWhiteSpace($RedisDatabaseId)) {
        throw 'Required project, agent, or Redis deployment values are missing.'
    }

    # 1. Get the deployed agent identity.
    $FoundryToken = az account get-access-token `
        --resource 'https://ai.azure.com' `
        --query accessToken `
        --output tsv
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to acquire a Foundry data-plane token.'
    }

    $AgentUri = "$($ProjectEndpoint.TrimEnd('/'))/agents/$AgentName`?api-version=v1"
    $Agent = Invoke-RestMethod `
        -Method Get `
        -Uri $AgentUri `
        -Headers @{ Authorization = "Bearer $FoundryToken" }
    $PrincipalId = $Agent.instance_identity.principal_id
    if ([string]::IsNullOrWhiteSpace($PrincipalId)) {
        throw 'The deployed agent identity has no principal ID.'
    }

    # 2. Add the identity to Redis authentication.
    $ManagementToken = az account get-access-token `
        --resource 'https://management.azure.com/' `
        --query accessToken `
        --output tsv
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to acquire an Azure management token.'
    }

    $AssignmentUri = 'https://management.azure.com{0}/accessPolicyAssignments/hostedAgent?api-version=2025-07-01' -f $RedisDatabaseId
    $Body = @{
        properties = @{
            accessPolicyName = 'default'
            user = @{ objectId = $PrincipalId }
        }
    } | ConvertTo-Json -Depth 4 -Compress

    Invoke-RestMethod `
        -Method Put `
        -Uri $AssignmentUri `
        -Headers @{ Authorization = "Bearer $ManagementToken" } `
        -ContentType 'application/json' `
        -Body $Body | Out-Null

    Write-Host "Granted Azure Managed Redis access to agent identity $PrincipalId." `
        -ForegroundColor Green
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        Set-RedisAgentAccess
        exit 0
    }
    catch {
        Write-Error -ErrorAction Continue "Redis agent access setup failed: $($_.Exception.Message)"
        exit 1
    }
}
