[CmdletBinding()]
param([Parameter(Mandatory)][switch] $ConfirmAuthorization)

$ErrorActionPreference = 'Stop'
if (-not $ConfirmAuthorization) { throw 'Explicit authorization confirmation is required.' }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'Rest.ps1')

$lines = azd -C $root env get-values
if ($LASTEXITCODE -ne 0) { throw 'Select the sample azd environment first.' }
$values = @{}
foreach ($line in $lines) {
    if ($line -match '^([A-Z][A-Z0-9_]*)="(.*)"$') {
        $values[$Matches[1]] = $Matches[2]
    }
}
foreach ($name in @(
    'AZURE_TENANT_ID', 'AZURE_SUBSCRIPTION_ID', 'GREETING_BLUEPRINT_ID',
    'GREETING_CLIENT_ID', 'GREETING_CLIENT_OBJECT_ID',
    'MCP_API_APPLICATION_ID', 'MCP_API_APPLICATION_OBJECT_ID', 'MCP_API_SCOPE_ID',
    'MCP_RESOURCE_URI')) {
    if ([string]::IsNullOrWhiteSpace($values[$name])) { throw "Missing azd environment value $name." }
}
$account = az account show -o json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $account.tenantId -ne $values.AZURE_TENANT_ID -or
    $account.id -ne $values.AZURE_SUBSCRIPTION_ID) {
    throw 'Azure CLI must be signed into the azd environment tenant and subscription.'
}

$graph = 'https://graph.microsoft.com/v1.0'
$blueprintId = $values.GREETING_BLUEPRINT_ID
$clientId = $values.GREETING_CLIENT_ID
$blueprintObjectId = az ad app show --id $blueprintId --query id -o tsv
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($blueprintObjectId)) {
    throw 'Unable to find the generated agent blueprint application.'
}
$blueprint = Invoke-AzureRest GET "$graph/applications/$blueprintObjectId" 'https://graph.microsoft.com'
$mcp = Invoke-AzureRest GET "$graph/applications/$($values.MCP_API_APPLICATION_OBJECT_ID)" 'https://graph.microsoft.com'
$client = Invoke-AzureRest GET "$graph/applications/$($values.GREETING_CLIENT_OBJECT_ID)" 'https://graph.microsoft.com'
if ($client.appId -ne $clientId -or $mcp.appId -ne $values.MCP_API_APPLICATION_ID -or
    $blueprint.appId -ne $blueprintId) {
    throw 'One of the application IDs has changed; no authorization was modified.'
}
$blueprintScope = @($blueprint.api.oauth2PermissionScopes | Where-Object {
    $_.value -ceq 'access_agent' -and $_.type -ceq 'User' -and $_.isEnabled
})
$mcpScope = @($mcp.api.oauth2PermissionScopes | Where-Object {
    $_.id -eq $values.MCP_API_SCOPE_ID -and $_.value -ceq 'Greeting.Read' -and
    $_.type -ceq 'User' -and $_.isEnabled
})
if ($blueprintScope.Count -ne 1 -or $mcpScope.Count -ne 1 -or
    "api://$blueprintId" -notin @($blueprint.identifierUris) -or
    $values.MCP_RESOURCE_URI -notin @($mcp.identifierUris)) {
    throw 'The two resource applications do not expose the expected delegated permissions.'
}

$existingAccess = @($client.requiredResourceAccess | Where-Object resourceAppId -eq $blueprintId)
if ($existingAccess.Count -gt 1) {
    throw 'The public client has a conflicting blueprint permission declaration.'
}
if ($existingAccess.Count -eq 0 -or @($existingAccess[0].resourceAccess | Where-Object {
    $_.id -eq $blueprintScope[0].id -and $_.type -eq 'Scope'
}).Count -eq 0) {
    az ad app permission add --id $clientId --api $blueprintId --api-permissions "$($blueprintScope[0].id)=Scope" --output none
    if ($LASTEXITCODE -ne 0) { throw 'Unable to add the blueprint scope to the public client.' }
}

$existingMcpAccess = @($blueprint.requiredResourceAccess | Where-Object resourceAppId -eq $mcp.appId)
if ($existingMcpAccess.Count -gt 1) {
    throw 'The agent blueprint has a conflicting MCP permission declaration.'
}
if ($existingMcpAccess.Count -eq 0 -or @($existingMcpAccess[0].resourceAccess | Where-Object {
    $_.id -eq $mcpScope[0].id -and $_.type -eq 'Scope'
}).Count -eq 0) {
    az ad app permission add --id $blueprintId --api $mcp.appId --api-permissions "$($mcpScope[0].id)=Scope" --output none
    if ($LASTEXITCODE -ne 0) { throw 'Unable to declare the MCP scope on the agent blueprint.' }
}

$inheritanceUri = "$graph/applications/microsoft.graph.agentIdentityBlueprint/$($blueprint.id)/inheritablePermissions"
$inheritance = Invoke-AzureRest GET $inheritanceUri 'https://graph.microsoft.com'
$matchingInheritance = @($inheritance.value | Where-Object resourceAppId -eq $mcp.appId)
if ($matchingInheritance.Count -gt 1) {
    throw 'The agent blueprint has conflicting MCP inheritance entries.'
}
$inheritanceSettings = @{
    inheritableScopes = @{ '@odata.type' = '#microsoft.graph.allAllowedScopes'; kind = 'allAllowed' }
    inheritableRoles = @{ '@odata.type' = '#microsoft.graph.noRoles'; kind = 'none' }
}
if ($matchingInheritance.Count -eq 0) {
    Invoke-AzureRest POST $inheritanceUri 'https://graph.microsoft.com' (@{ resourceAppId = $mcp.appId } + $inheritanceSettings) | Out-Null
}
elseif ($matchingInheritance[0].inheritableScopes.kind -ne 'allAllowed' -or
    $matchingInheritance[0].inheritableRoles.kind -ne 'none') {
    Invoke-AzureRest PATCH "$inheritanceUri/$($mcp.appId)" 'https://graph.microsoft.com' $inheritanceSettings | Out-Null
}

function Add-Preauthorization {
    param([object] $Application, [string] $AuthorizedClient, [string] $ScopeId)
    $entries = @($Application.api.preAuthorizedApplications | Where-Object { $null -ne $_ })
    $matching = @($entries | Where-Object appId -eq $AuthorizedClient)
    if ($matching.Count -gt 1) {
        throw "Conflicting preauthorization for client $AuthorizedClient. No authorization was modified."
    }
    if ($matching.Count -eq 0) {
        $entries += @{ appId = $AuthorizedClient; delegatedPermissionIds = @($ScopeId) }
    }
    elseif ($ScopeId -notin @($matching[0].delegatedPermissionIds)) {
        $matching[0].delegatedPermissionIds = @($matching[0].delegatedPermissionIds) + $ScopeId
    }
    else {
        return
    }
    $Application.api | Add-Member -NotePropertyName preAuthorizedApplications -NotePropertyValue $entries -Force
    Invoke-AzureRest PATCH "$graph/applications/$($Application.id)" 'https://graph.microsoft.com' @{
        api = $Application.api
    } | Out-Null
}

Add-Preauthorization $blueprint $clientId $blueprintScope[0].id

$entries = @($mcp.api.preAuthorizedApplications | Where-Object { $null -ne $_ })
$matching = @($entries | Where-Object appId -eq $blueprintId)
if ($matching.Count -gt 1) {
    throw 'Conflicting MCP preauthorization entries for the agent blueprint.'
}
if ($matching.Count -eq 1 -and $mcpScope[0].id -in @($matching[0].delegatedPermissionIds)) {
    $remaining = @($matching[0].delegatedPermissionIds | Where-Object { $_ -ne $mcpScope[0].id })
    if ($remaining.Count -eq 0) {
        $entries = @($entries | Where-Object appId -ne $blueprintId)
    }
    else {
        $matching[0].delegatedPermissionIds = $remaining
    }
    $mcp.api | Add-Member -NotePropertyName preAuthorizedApplications -NotePropertyValue $entries -Force
    Invoke-AzureRest PATCH "$graph/applications/$($mcp.id)" 'https://graph.microsoft.com' @{
        api = $mcp.api
    } | Out-Null
}

$blueprint = Invoke-AzureRest GET "$graph/applications/$($blueprint.id)" 'https://graph.microsoft.com'
$mcp = Invoke-AzureRest GET "$graph/applications/$($mcp.id)" 'https://graph.microsoft.com'
$client = Invoke-AzureRest GET "$graph/applications/$($client.id)" 'https://graph.microsoft.com'
$inheritance = Invoke-AzureRest GET $inheritanceUri 'https://graph.microsoft.com'
if (@($blueprint.api.preAuthorizedApplications | Where-Object {
    $_.appId -eq $clientId -and $blueprintScope[0].id -in @($_.delegatedPermissionIds)
}).Count -ne 1 -or
    @($mcp.api.preAuthorizedApplications | Where-Object {
        $_.appId -eq $blueprintId -and $mcpScope[0].id -in @($_.delegatedPermissionIds)
    }).Count -ne 0 -or
    @($blueprint.requiredResourceAccess | Where-Object {
        $_.resourceAppId -eq $mcp.appId -and @($_.resourceAccess | Where-Object {
            $_.id -eq $mcpScope[0].id -and $_.type -eq 'Scope'
        }).Count -eq 1
    }).Count -ne 1 -or
    @($inheritance.value | Where-Object {
        $_.resourceAppId -eq $mcp.appId -and $_.inheritableScopes.kind -eq 'allAllowed' -and
        $_.inheritableRoles.kind -eq 'none'
    }).Count -ne 1 -or
    @($client.requiredResourceAccess | Where-Object {
        $_.resourceAppId -eq $blueprintId -and @($_.resourceAccess | Where-Object {
            $_.id -eq $blueprintScope[0].id -and $_.type -eq 'Scope'
        }).Count -eq 1
    }).Count -ne 1) {
    throw 'The blueprint inheritance, permission declarations, or client preauthorization were not confirmed by Microsoft Graph readback.'
}
Write-Host 'The blueprint and interactive client are configured. The MCP scope requires user consent or an administrator-approved grant.'
