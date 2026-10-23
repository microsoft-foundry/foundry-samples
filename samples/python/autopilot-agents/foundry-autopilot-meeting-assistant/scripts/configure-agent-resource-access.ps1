param(
    [Parameter(Mandatory = $true)]
    [string]$ServiceName
)

$ErrorActionPreference = "Stop"

function Get-AzdEnvironmentValue {
    param([Parameter(Mandatory = $true)][string]$Key)

    $output = & azd env get-value $Key --no-prompt
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to read azd environment value '$Key'."
    }
    $value = ($output | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "azd environment value '$Key' is required after deployment."
    }
    return $value
}

function Grant-RoleAssignment {
    param(
        [Parameter(Mandatory = $true)][string]$PrincipalId,
        [Parameter(Mandatory = $true)][string]$Scope,
        [Parameter(Mandatory = $true)][string]$Role,
        [Parameter(Mandatory = $true)][string]$RoleName
    )

    Write-Host "Granting $RoleName to the Agent Instance identity on $Scope..."
    $assignmentOutput = az role assignment create `
        --assignee-object-id $PrincipalId `
        --assignee-principal-type ServicePrincipal `
        --role $Role `
        --scope $Scope `
        --only-show-errors 2>&1 | Out-String

    if ($LASTEXITCODE -ne 0 -and $assignmentOutput -notmatch "RoleAssignmentExists") {
        throw "Failed to grant ${RoleName} to the Agent Instance identity: $assignmentOutput"
    }

    if ($assignmentOutput -match "RoleAssignmentExists") {
        Write-Host "$RoleName role assignment already exists."
    } else {
        Write-Host "$RoleName role assignment created."
    }
}

$serviceKey = $ServiceName.ToUpper().Replace("-", "_").Replace(" ", "_")
$principalId = Get-AzdEnvironmentValue `
    "AGENT_${serviceKey}_INSTANCE_IDENTITY_PRINCIPAL_ID"
$deployedModelBySample = Get-AzdEnvironmentValue "deployedModelBySample"

if ($deployedModelBySample -eq "true") {
    $modelAccountId = Get-AzdEnvironmentValue "deployedModelAccountId"
    Grant-RoleAssignment `
        -PrincipalId $principalId `
        -Scope $modelAccountId `
        -Role "Cognitive Services User" `
        -RoleName "Cognitive Services User"
} else {
    $endpoint = Get-AzdEnvironmentValue "azureOpenAIResponsesEndpoint"
    $deployment = Get-AzdEnvironmentValue "modelDeploymentName"

    Write-Warning @"
This sample is using an existing model, so model access was not changed automatically.
Grant the Agent Instance identity access to the Azure OpenAI or Foundry account that owns the endpoint.

Agent Instance identity principal ID:
  $principalId

Responses endpoint:
  $endpoint

Model deployment:
  $deployment

Run this command with the existing model account resource ID:
  az role assignment create --assignee-object-id "$principalId" --assignee-principal-type ServicePrincipal --role "Cognitive Services User" --scope "<MODEL_ACCOUNT_RESOURCE_ID>"
"@
}

$meetingDelegateStorageScope = Get-AzdEnvironmentValue "meetingDelegateStorageAccountId"
Grant-RoleAssignment `
    -PrincipalId $principalId `
    -Scope $meetingDelegateStorageScope `
    -Role "ba92f5b4-2d11-453d-a403-e96b0029c9fe" `
    -RoleName "Storage Blob Data Contributor"
