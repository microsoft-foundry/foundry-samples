Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-AzdEnvironmentValue {
  param([Parameter(Mandatory)][string] $Name)

  $value = azd env get-value $Name
  $text = ($value | Out-String).Trim()
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($text)) {
    throw "Failed to read required azd environment value $Name."
  }
  return $text
}

$projectEndpoint = Get-AzdEnvironmentValue FOUNDRY_PROJECT_ENDPOINT
$projectId = Get-AzdEnvironmentValue AZURE_AI_PROJECT_ID
$agentName = Get-AzdEnvironmentValue AGENT_CSV_CHART_ANALYST_NAME

$agentPrincipalId = az rest `
  --method GET `
  --url "$projectEndpoint/agents/$agentName`?api-version=v1" `
  --resource https://ai.azure.com `
  --query instance_identity.principal_id `
  --output tsv
$agentPrincipalId = ($agentPrincipalId | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($agentPrincipalId)) {
  throw 'Failed to retrieve the Agent identity principal ID.'
}

$assignmentCount = az role assignment list `
  --assignee-object-id $agentPrincipalId `
  --role 'Foundry User' `
  --scope $projectId `
  --fill-principal-name false `
  --query 'length(@)' `
  --output tsv
$assignmentCountText = ($assignmentCount | Out-String).Trim()
$assignmentCountValue = 0
if ($LASTEXITCODE -ne 0 -or -not [int]::TryParse($assignmentCountText, [ref]$assignmentCountValue)) {
  throw 'Failed to check the Foundry User role assignment.'
}

if ($assignmentCountValue -eq 0) {
  az role assignment create `
    --assignee-object-id $agentPrincipalId `
    --assignee-principal-type ServicePrincipal `
    --role 'Foundry User' `
    --scope $projectId `
    --output none
  if ($LASTEXITCODE -ne 0) {
    throw 'Failed to assign Foundry User to the Agent identity.'
  }
}

Write-Host "Foundry User is assigned to agent identity $agentPrincipalId at project scope."
