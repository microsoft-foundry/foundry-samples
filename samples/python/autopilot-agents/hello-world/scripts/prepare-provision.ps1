$ErrorActionPreference = "Stop"
$script:nonInteractive = [Console]::IsInputRedirected -or $env:AZD_NON_INTERACTIVE -in @("true", "1")

function Get-AzdValue {
    param([Parameter(Mandatory)][string]$Name)

    # azd injects the selected environment into the hook process.
    return ([string][Environment]::GetEnvironmentVariable($Name)).Trim()
}

function Set-AzdValue {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][AllowEmptyString()][string]$Value
    )

    & azd env set $Name $Value --environment (Get-AzdValue -Name "AZURE_ENV_NAME") | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to save azd environment value $Name."
    }
    [Environment]::SetEnvironmentVariable($Name, $Value)
}

function Set-BooleanAzdValue {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][bool]$Value
    )

    Set-AzdValue -Name $Name -Value $Value.ToString().ToLowerInvariant()
}

function Get-AzureJson {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $result = & az @Arguments --output json --only-show-errors
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI failed: az $($Arguments -join ' '). Check your sign-in and resource access."
    }
    if ([string]::IsNullOrWhiteSpace(($result -join "`n"))) {
        throw "Azure CLI returned no JSON: az $($Arguments -join ' ')."
    }
    return ($result -join "`n") | ConvertFrom-Json -Depth 100
}

function Read-RequiredValue {
    param([Parameter(Mandatory)][string]$Prompt)

    if ($script:nonInteractive) {
        throw "Cannot prompt for '$Prompt'. Run 'azd provision' interactively or configure the environment first."
    }
    do {
        $value = (Read-Host $Prompt).Trim()
        if ([string]::IsNullOrWhiteSpace($value)) {
            Write-Host "A value is required."
        }
    } while ([string]::IsNullOrWhiteSpace($value))
    return $value
}

function Get-RequiredAzdValue {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Prompt
    )

    $value = Get-AzdValue -Name $Name
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = Read-RequiredValue -Prompt $Prompt
        Set-AzdValue -Name $Name -Value $value
    }
    return $value
}

function Select-Resource {
    param(
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][string]$ModeEnvironmentName,
        [Parameter(Mandatory)][string]$NameEnvironmentName,
        [string[]]$ExistingNames = @()
    )

    $mode = Get-AzdValue -Name $ModeEnvironmentName
    if ($mode -and $mode -notin @("reuse", "new")) {
        throw "$ModeEnvironmentName must be 'reuse' or 'new', not '$mode'."
    }
    $name = Get-AzdValue -Name $NameEnvironmentName
    $existingNames = @($ExistingNames | Sort-Object -Unique)
    if ([string]::IsNullOrWhiteSpace($name)) {
        Write-Host ""
        Write-Host "${Label}:"
        if ($existingNames.Count -eq 0) {
            Write-Host "  No existing options in the selected parent."
        } else {
            $existingNames | ForEach-Object { Write-Host "  - $_" }
        }
        $name = Read-RequiredValue -Prompt "$Label name (existing name to reuse, new name to create)"
    }

    $existingName = $existingNames | Where-Object { $_ -ieq $name } | Select-Object -First 1
    $exists = -not [string]::IsNullOrWhiteSpace($existingName)
    if ($exists) {
        $name = $existingName
        $mode = "reuse"
    } elseif ($mode -eq "reuse") {
        throw "Previously selected $Label '$name' no longer exists in this parent. Check the selected environment and resource names."
    } else {
        $mode = "new"
    }
    Write-Host "${Label} '$name': $mode"
    Set-AzdValue -Name $ModeEnvironmentName -Value $mode
    Set-AzdValue -Name $NameEnvironmentName -Value $name
    return [pscustomobject]@{ Name = $name; Exists = $exists }
}

function Get-AzureSubscriptionId {
    $subscriptions = @(Get-AzureJson -Arguments @(
        "account", "list", "--query", "[?state=='Enabled'].{Name:name,Id:id,IsDefault:isDefault}"
    ))
    if ($subscriptions.Count -eq 0) {
        throw "No enabled subscriptions found. Run 'az login' in the intended tenant."
    }
    $configuredId = Get-AzdValue -Name "AZURE_SUBSCRIPTION_ID"
    if ($configuredId) {
        $selected = $subscriptions | Where-Object { $_.Id -eq $configuredId } | Select-Object -First 1
        if ($null -eq $selected) {
            throw "AZURE_SUBSCRIPTION_ID does not identify an enabled subscription in Azure CLI. Check your tenant and sign-in."
        }
    } else {
        if ($script:nonInteractive) {
            throw "Missing AZURE_SUBSCRIPTION_ID. Run 'azd provision' interactively."
        }
        $default = $subscriptions | Where-Object { $_.IsDefault } | Select-Object -First 1
        do {
            if ($null -ne $default) {
                Write-Host "Default subscription: $($default.Name) [$($default.Id)]"
                $search = (Read-Host "Subscription name or ID (Enter accepts the default)").Trim()
            } else {
                $search = Read-RequiredValue -Prompt "Subscription name or ID"
            }
            if (-not $search -and $null -ne $default) {
                $selected = $default
                break
            }
            $matches = @($subscriptions | Where-Object {
                $_.Id -ieq $search -or $_.Name.IndexOf($search, [StringComparison]::OrdinalIgnoreCase) -ge 0
            })
            if ($matches.Count -eq 1) {
                $selected = $matches[0]
            } elseif ($matches.Count -eq 0) {
                Write-Host "No subscription matched '$search'."
            } else {
                $matches | ForEach-Object { Write-Host "  $($_.Name) [$($_.Id)]" }
                Write-Host "Enter a subscription ID or a more specific name."
            }
        } while ($null -eq $selected)
    }
    Set-AzdValue -Name "AZURE_SUBSCRIPTION_ID" -Value $selected.Id
    return $selected.Id
}

function Get-AzureLocation {
    param([Parameter(Mandatory)][string]$SubscriptionId)

    $locations = @(Get-AzureJson -Arguments @(
        "account", "list-locations", "--subscription", $SubscriptionId, "--query", "[].name"
    ))
    $location = Get-AzdValue -Name "AZURE_LOCATION"
    if (-not $location) {
        $location = Read-RequiredValue -Prompt "Azure region for new Foundry resources (for example, northcentralus)"
    }
    $matched = $locations | Where-Object { $_ -ieq $location } | Select-Object -First 1
    if (-not $matched) {
        throw "Azure region '$location' is not available in this subscription. Set AZURE_LOCATION to a valid region and retry."
    }
    return $matched
}

function Get-DefaultModelVersion {
    param(
        [Parameter(Mandatory)][string]$SubscriptionId,
        [Parameter(Mandatory)][string]$Location,
        [Parameter(Mandatory)][string]$ModelName
    )

    $catalog = Get-AzureJson -Arguments @(
        "rest", "--method", "get", "--url",
        "https://management.azure.com/subscriptions/$SubscriptionId/providers/Microsoft.CognitiveServices/locations/$Location/models?api-version=2025-06-01"
    )
    $versions = @($catalog.value | Where-Object {
        $_.model.format -eq "OpenAI" -and $_.model.name -ieq $ModelName -and
        $_.model.isDefaultVersion -eq $true -and "GlobalStandard" -in @($_.model.skus.name)
    } | ForEach-Object { $_.model.version } | Where-Object { $_ } | Sort-Object -Unique)
    if ($versions.Count -ne 1) {
        throw "Expected one default version of OpenAI model '$ModelName' supporting GlobalStandard in '$Location'; found $($versions.Count). Check the model catalog and quota."
    }
    return $versions[0]
}

if (-not (Get-AzdValue -Name "AZURE_ENV_NAME")) {
    throw "No azd environment is selected. Run 'azd env new' or 'azd env select', then 'azd provision'."
}

$subscriptionId = Get-AzureSubscriptionId
$groups = @(Get-AzureJson -Arguments @("group", "list", "--subscription", $subscriptionId, "--query", "[].name"))
$resourceGroup = Select-Resource -Label "Resource group" -ModeEnvironmentName "RESOURCE_GROUP_MODE" `
    -NameEnvironmentName "AZURE_RESOURCE_GROUP" -ExistingNames $groups

$accounts = @()
if ($resourceGroup.Exists) {
    $accounts = @(Get-AzureJson -Arguments @(
        "cognitiveservices", "account", "list", "--resource-group", $resourceGroup.Name,
        "--subscription", $subscriptionId, "--query", "[?kind=='AIServices'].name"
    ))
}
$foundryResource = Select-Resource -Label "Foundry resource" -ModeEnvironmentName "FOUNDRY_RESOURCE_MODE" `
    -NameEnvironmentName "AZURE_AI_ACCOUNT_NAME" -ExistingNames $accounts
$accountArgs = @("--name", $foundryResource.Name, "--resource-group", $resourceGroup.Name, "--subscription", $subscriptionId)

if ($foundryResource.Exists) {
    $account = Get-AzureJson -Arguments (@("cognitiveservices", "account", "show") + $accountArgs)
    if (-not $account.properties.allowProjectManagement) {
        throw "Foundry resource '$($foundryResource.Name)' does not support project management. Select a project-capable Foundry resource or create one."
    }
    $location = $account.location
    if ([string]::IsNullOrWhiteSpace($location)) {
        throw "The selected Foundry resource has no region."
    }
    Write-Host "Using the existing Foundry resource's region: $location"
} else {
    $location = Get-AzureLocation -SubscriptionId $subscriptionId
}
Set-AzdValue -Name "AZURE_LOCATION" -Value $location

$projects = @()
if ($foundryResource.Exists) {
    $projects = @(Get-AzureJson -Arguments (@(
        "cognitiveservices", "account", "project", "list", "--query", "[].name"
    ) + $accountArgs) | ForEach-Object { ($_ -split "/")[-1] })
}
$foundryProject = Select-Resource -Label "Foundry project" -ModeEnvironmentName "FOUNDRY_PROJECT_MODE" `
    -NameEnvironmentName "AZURE_AI_PROJECT_NAME" -ExistingNames $projects

$deployments = @()
if ($foundryResource.Exists) {
    $deployments = @(Get-AzureJson -Arguments (@(
        "cognitiveservices", "account", "deployment", "list", "--query", "[].name"
    ) + $accountArgs))
}
$modelDeployment = Select-Resource -Label "Model deployment" -ModeEnvironmentName "MODEL_DEPLOYMENT_MODE" `
    -NameEnvironmentName "AZURE_AI_MODEL_DEPLOYMENT_NAME" -ExistingNames $deployments

if ($modelDeployment.Exists) {
    $deployment = Get-AzureJson -Arguments (@(
        "cognitiveservices", "account", "deployment", "show", "--deployment-name", $modelDeployment.Name
    ) + $accountArgs)
    Set-AzdValue -Name "MODEL_NAME" -Value $deployment.properties.model.name
    Set-AzdValue -Name "MODEL_FORMAT" -Value $deployment.properties.model.format
    Set-AzdValue -Name "MODEL_VERSION" -Value $deployment.properties.model.version
    Set-AzdValue -Name "MODEL_SKU_NAME" -Value $deployment.sku.name
    Set-AzdValue -Name "MODEL_CAPACITY" -Value ([string]$deployment.sku.capacity)
} else {
    $modelName = Get-RequiredAzdValue -Name "MODEL_NAME" -Prompt "OpenAI model name (must support the Responses API)"
    $modelVersion = Get-DefaultModelVersion -SubscriptionId $subscriptionId -Location $location -ModelName $modelName
    Set-AzdValue -Name "MODEL_FORMAT" -Value "OpenAI"
    Set-AzdValue -Name "MODEL_VERSION" -Value $modelVersion
    Set-AzdValue -Name "MODEL_SKU_NAME" -Value "GlobalStandard"
    Set-AzdValue -Name "MODEL_CAPACITY" -Value "1"
    Write-Host "Using default model version '$modelVersion', GlobalStandard, capacity 1."
}

Set-BooleanAzdValue -Name "RESOURCE_GROUP_EXISTS" -Value $resourceGroup.Exists
Set-BooleanAzdValue -Name "FOUNDRY_RESOURCE_EXISTS" -Value $foundryResource.Exists
Set-BooleanAzdValue -Name "FOUNDRY_PROJECT_EXISTS" -Value $foundryProject.Exists
Set-BooleanAzdValue -Name "MODEL_DEPLOYMENT_EXISTS" -Value $modelDeployment.Exists

Write-Host ""
Write-Host "Provisioning plan:"
Write-Host "  Resource group '$($resourceGroup.Name)': $(if ($resourceGroup.Exists) { 'reuse' } else { 'create' })"
Write-Host "  Foundry resource '$($foundryResource.Name)': $(if ($foundryResource.Exists) { 'reuse' } else { 'create' })"
Write-Host "  Foundry project '$($foundryProject.Name)': $(if ($foundryProject.Exists) { 'reuse' } else { 'create' })"
Write-Host "  Model deployment '$($modelDeployment.Name)': $(if ($modelDeployment.Exists) { 'reuse' } else { 'create' })"
