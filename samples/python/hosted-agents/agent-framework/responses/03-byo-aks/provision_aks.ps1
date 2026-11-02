#Requires -Version 5.1

<#
.SYNOPSIS
Provisions an AKS cluster and Kata sandbox node pool for Foundry BYO-AKS evaluation.

.DESCRIPTION
Without -Apply, prints the resolved plan only. With -Apply, reuses the resource
group supplied by name, then provisions any missing AKS cluster and sandbox node
pool. Existing clusters and pools are not updated or fully validated.

This script does not create ACR resources, enable Azure Policy, or configure an
ACR image-admission policy on the AKS cluster.
#>

[CmdletBinding()]
param(
    [switch]$Apply,
    [Alias("resource-group")]
    [string]$ResourceGroup = "",
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Usage {
    @"
Usage: `$env:AKS_NAME=<name>; `$env:AZURE_SUBSCRIPTION_ID=<id>; `$env:RESOURCE_GROUP=<name>; `$env:AZURE_LOCATION=<region>; .\provision_aks.ps1 [-Apply]

Without -Apply, prints the resolved plan only. With -Apply, reuses the
resource group supplied by name, then provisions any missing AKS cluster and
sandbox node pool. Existing clusters/pools are not updated or fully validated.
This script does not create ACR resources, enable Azure Policy, or configure an
ACR image-admission policy on the AKS cluster.

Options:
  -ResourceGroup <name>  Existing resource group name; overrides RESOURCE_GROUP.
                         Alias: -resource-group
  -Apply                 Provision resources (Azure charges may apply).
  -Help                  Show this help.

Environment overrides:
  AZURE_SUBSCRIPTION_ID  Required target Azure subscription ID.
  RESOURCE_GROUP         Required existing resource group name.
  AZURE_LOCATION         Required supported private preview Azure region.
  AKS_NAME               Required target AKS cluster name.
  KUBERNETES_VERSION     1.35
  SYSTEM_NODE_VM_SIZE    Optional explicit size; otherwise selected by region.
  SANDBOX_NODE_VM_SIZE   Optional explicit size; otherwise selected by region.

The source's AKS create command does not reference the separately created
agent VNet/subnet; this extraction preserves that behavior. Azure CLI provisions
AKS networking. This script alone does not complete Foundry BYO-AKS onboarding.
"@ | Write-Host
}

function Stop-WithUsageError {
    param([Parameter(Mandatory)][string]$Message)

    [Console]::Error.WriteLine($Message)
    exit 2
}

function Get-EnvironmentVariableOrDefault {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][AllowEmptyString()][string]$Default
    )

    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrEmpty($value)) {
        return $Default
    }

    return $value
}

function Get-RequiredEnvironmentVariable {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Message
    )

    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        Stop-WithUsageError -Message $Message
    }

    return $value.Trim()
}

function Format-CommandArgument {
    param([Parameter(Mandatory)][string]$Argument)

    if ($Argument -match '\s|''|"') {
        return "'" + ($Argument -replace "'", "''") + "'"
    }

    return $Argument
}

function Invoke-LoggedCommand {
    param(
        [Parameter(Mandatory)][string]$Command,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    $displayArguments = $Arguments | ForEach-Object { Format-CommandArgument -Argument $_ }
    Write-Host "+ $Command $($displayArguments -join ' ')"
    & $Command @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "$Command failed with exit code $exitCode."
    }
}

function Invoke-NativeCaptureAllowFailure {
    param(
        [Parameter(Mandatory)][string]$Command,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $nativeErrorPreference = Get-Variable `
        -Name "PSNativeCommandUseErrorActionPreference" `
        -ErrorAction SilentlyContinue
    $previousNativeErrorPreference = $false

    try {
        $ErrorActionPreference = "Continue"
        if ($null -ne $nativeErrorPreference) {
            $previousNativeErrorPreference = $PSNativeCommandUseErrorActionPreference
            $PSNativeCommandUseErrorActionPreference = $false
        }

        $output = & $Command @Arguments 2>$null
        return @{
            ExitCode = $LASTEXITCODE
            Output = (($output | ForEach-Object { "$_" }) -join [Environment]::NewLine).Trim()
        }
    }
    finally {
        if ($null -ne $nativeErrorPreference) {
            $PSNativeCommandUseErrorActionPreference = $previousNativeErrorPreference
        }
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Test-AzCommand {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $result = Invoke-NativeCaptureAllowFailure -Command "az" -Arguments $Arguments
    return $result.ExitCode -eq 0
}

function Get-AvailableVmSkus {
    param([Parameter(Mandatory)][string]$Location)

    $query = "[].{Name:name,Vcpus:capabilities[?name=='vCPUs'].value | [0],MemoryGB:capabilities[?name=='MemoryGB'].value | [0],PremiumIO:capabilities[?name=='PremiumIO'].value | [0],AcceleratedNetworking:capabilities[?name=='AcceleratedNetworkingEnabled'].value | [0],HyperVGenerations:capabilities[?name=='HyperVGenerations'].value | [0],Architecture:capabilities[?name=='CpuArchitectureType'].value | [0]}"
    Write-Host "Searching VM SKUs available to this subscription in $Location..."
    $result = Invoke-NativeCaptureAllowFailure -Command "az" -Arguments @(
        "vm", "list-skus",
        "--location", $Location,
        "--resource-type", "virtualMachines",
        "--query", $query,
        "--output", "json"
    )
    if ($result.ExitCode -ne 0) {
        throw "Failed to list VM SKUs in $Location."
    }
    if ([string]::IsNullOrWhiteSpace($result.Output)) {
        throw "Azure returned no available VM SKUs in $Location."
    }

    try {
        $skus = @($result.Output | ConvertFrom-Json)
    }
    catch {
        throw "Azure returned invalid VM SKU data for ${Location}: $($_.Exception.Message)"
    }
    if ($skus.Count -eq 0) {
        throw "Azure returned no available VM SKUs in $Location."
    }

    return $skus
}

function Resolve-NodeVmSize {
    param(
        [Parameter(Mandatory)][string]$Label,
        [AllowEmptyString()][string]$RequestedSize,
        [Parameter(Mandatory)][string]$PreferredSize,
        [Parameter(Mandatory)][int]$MinimumVcpus,
        [Parameter(Mandatory)][double]$MinimumMemoryGB,
        [Parameter(Mandatory)][object[]]$AvailableSkus,
        [Parameter(Mandatory)][string]$Location
    )

    if (-not [string]::IsNullOrWhiteSpace($RequestedSize)) {
        $match = $AvailableSkus | Where-Object { $_.Name -eq $RequestedSize } | Select-Object -First 1
        if ($null -eq $match) {
            throw "$Label VM size $RequestedSize is not available to this subscription in $Location."
        }
        return $RequestedSize
    }

    $rankedSkus = foreach ($sku in $AvailableSkus) {
        $name = [string]$sku.Name
        $vcpus = if ($null -eq $sku.Vcpus) { 0 } else { [double]$sku.Vcpus }
        $memoryGB = if ($null -eq $sku.MemoryGB) { 0 } else { [double]$sku.MemoryGB }
        $architecture = [string]$sku.Architecture
        $hyperVGenerations = [string]$sku.HyperVGenerations

        if (
            $name -notmatch '^Standard_[DE][0-9]' -or
            $name -match 'Promo' -or
            $vcpus -lt $MinimumVcpus -or
            $memoryGB -lt $MinimumMemoryGB -or
            (-not [string]::IsNullOrWhiteSpace($architecture) -and $architecture -ne "x64") -or
            (-not [string]::IsNullOrWhiteSpace($hyperVGenerations) -and $hyperVGenerations -notmatch 'V2')
        ) {
            continue
        }

        $score = ($vcpus - $MinimumVcpus) * 10000
        $score += ($memoryGB - $MinimumMemoryGB) * 100
        if ($name -match '^Standard_E') { $score += 50 }
        if ([string]$sku.PremiumIO -ne "True") { $score += 20 }
        if ([string]$sku.AcceleratedNetworking -ne "True") { $score += 10 }

        $generationPenalty = 100
        if ($name -match '_v(\d+)$') {
            $generation = [int]$Matches[1]
            $generationPenalty = if ($generation -ge 5) { $generation - 5 } else { (5 - $generation) * 10 }
        }
        $score += $generationPenalty
        if ($name -eq $PreferredSize) { $score = -1 }

        [PSCustomObject]@{
            Name = $name
            Score = $score
        }
    }

    $selected = $rankedSkus | Sort-Object -Property Score, Name | Select-Object -First 1
    if ($null -eq $selected) {
        throw "No suitable $Label VM size is available in ${Location}; require at least $MinimumVcpus vCPU and $MinimumMemoryGB GiB. Set the corresponding *_NODE_VM_SIZE environment variable to override automatic selection."
    }

    return $selected.Name
}

function Wait-ForProvisioningState {
    param(
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][string[]]$AzArguments
    )

    $attempts = 60
    $state = ""

    for ($attempt = 1; $attempt -le $attempts; $attempt++) {
        $result = Invoke-NativeCaptureAllowFailure -Command "az" -Arguments $AzArguments
        if ($result.ExitCode -eq 0) {
            $state = $result.Output.Trim()
        }
        else {
            $state = ""
        }

        switch ($state) {
            "Succeeded" { return }
            "Failed" { throw "$Label reached terminal state $state." }
            "Canceled" { throw "$Label reached terminal state $state." }
        }

        $stateDisplay = if ([string]::IsNullOrWhiteSpace($state)) { "not found" } else { $state }
        Write-Host "Waiting for ${Label}: $stateDisplay ($attempt/$attempts)"
        Start-Sleep -Seconds 15
    }

    $lastState = if ([string]::IsNullOrWhiteSpace($state)) { "unknown" } else { $state }
    throw "Timed out waiting for $Label. Last state: $lastState"
}

if ($Help) {
    Write-Usage
    exit 0
}

$subscriptionId = Get-RequiredEnvironmentVariable `
    -Name "AZURE_SUBSCRIPTION_ID" `
    -Message "Set AZURE_SUBSCRIPTION_ID to the target Azure subscription ID."

if ([string]::IsNullOrWhiteSpace($ResourceGroup)) {
    $ResourceGroup = Get-RequiredEnvironmentVariable `
        -Name "RESOURCE_GROUP" `
        -Message "Set RESOURCE_GROUP to the existing resource group name."
}
else {
    $ResourceGroup = $ResourceGroup.Trim()
}

$location = Get-RequiredEnvironmentVariable `
    -Name "AZURE_LOCATION" `
    -Message "Set AZURE_LOCATION to a supported private preview Azure region."
$aksName = Get-RequiredEnvironmentVariable `
    -Name "AKS_NAME" `
    -Message "Set AKS_NAME to the target AKS cluster name."
$kubernetesVersion = Get-EnvironmentVariableOrDefault -Name "KUBERNETES_VERSION" -Default "1.35"
$systemNodeVmSize = Get-EnvironmentVariableOrDefault -Name "SYSTEM_NODE_VM_SIZE" -Default ""
$sandboxNodeVmSize = Get-EnvironmentVariableOrDefault -Name "SANDBOX_NODE_VM_SIZE" -Default ""
$systemNodeVmSizeDisplay = if ([string]::IsNullOrWhiteSpace($systemNodeVmSize)) { "auto (minimum 4 vCPU / 16 GiB)" } else { $systemNodeVmSize }
$sandboxNodeVmSizeDisplay = if ([string]::IsNullOrWhiteSpace($sandboxNodeVmSize)) { "auto (minimum 8 vCPU / 32 GiB)" } else { $sandboxNodeVmSize }
$resourceGroupScope = "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup"
$foundryResourceGroupId = $resourceGroupScope
$aksScope = "$resourceGroupScope/providers/Microsoft.ContainerService/managedClusters/$aksName"
$mode = if ($Apply) { "apply" } else { "preview" }

@"
Mode:                    $mode
Subscription:            $subscriptionId
Location:                $location
Resource group:          $ResourceGroup
AKS cluster:             $aksName
Kubernetes version:      $kubernetesVersion
System node VM size:     $systemNodeVmSizeDisplay
Sandbox node VM size:    $sandboxNodeVmSizeDisplay
Sandbox node pool:       sandbox (AzureLinux / KataVmIsolation)
Image admission policy:  not configured by this script

FOUNDRY_RESOURCE_GROUP_ID=$foundryResourceGroupId
AKS_RESOURCE_ID=$aksScope
"@ | Write-Host

if (-not $Apply) {
    Write-Host ""
    Write-Host "Preview only. Re-run with -Apply to provision the AKS cluster and sandbox pool."
    exit 0
}

# Step 0: verify the existing resource group first.
Invoke-LoggedCommand -Command "az" -Arguments @("account", "set", "--subscription", $subscriptionId)
# RESOURCE_GROUP refers to an existing group; fail rather than create a replacement.
Invoke-LoggedCommand -Command "az" -Arguments @("group", "show", "--subscription", $subscriptionId, "--name", $ResourceGroup, "--output", "none")
Write-Host "Reusing resource group: $resourceGroupScope"

# Step 1: AKS and sandbox-pool provisioning.
$availableVmSkus = @(Get-AvailableVmSkus -Location $location)
$systemNodeVmSize = Resolve-NodeVmSize `
    -Label "system node pool" `
    -RequestedSize $systemNodeVmSize `
    -PreferredSize "Standard_D4ds_v5" `
    -MinimumVcpus 4 `
    -MinimumMemoryGB 16 `
    -AvailableSkus $availableVmSkus `
    -Location $location
$sandboxNodeVmSize = Resolve-NodeVmSize `
    -Label "sandbox node pool" `
    -RequestedSize $sandboxNodeVmSize `
    -PreferredSize "Standard_D8as_v5" `
    -MinimumVcpus 8 `
    -MinimumMemoryGB 32 `
    -AvailableSkus $availableVmSkus `
    -Location $location
Write-Host "Selected system node VM size:  $systemNodeVmSize"
Write-Host "Selected sandbox node VM size: $sandboxNodeVmSize"

if (-not (Test-AzCommand -Arguments @("aks", "show", "-g", $ResourceGroup, "-n", $aksName, "--output", "none"))) {
    Invoke-LoggedCommand -Command "az" -Arguments @(
        "aks", "create",
        "-g", $ResourceGroup,
        "-n", $aksName,
        "--location", $location,
        "--kubernetes-version", $kubernetesVersion,
        "--node-vm-size", $systemNodeVmSize,
        "--node-count", "1",
        "--network-plugin", "azure",
        "--network-plugin-mode", "overlay",
        "--enable-managed-identity",
        "--enable-oidc-issuer",
        "--enable-workload-identity",
        "--enable-aad",
        "--enable-azure-rbac",
        "--no-ssh-key",
        "--output", "none",
        "--no-wait"
    )
}

Wait-ForProvisioningState `
    -Label "AKS cluster $aksName" `
    -AzArguments @("aks", "show", "-g", $ResourceGroup, "-n", $aksName, "--query", "provisioningState", "-o", "tsv")

if (-not (Test-AzCommand -Arguments @("aks", "nodepool", "show", "-g", $ResourceGroup, "--cluster-name", $aksName, "-n", "sandbox", "--output", "none"))) {
    Invoke-LoggedCommand -Command "az" -Arguments @(
        "aks", "nodepool", "add",
        "-g", $ResourceGroup,
        "--cluster-name", $aksName,
        "-n", "sandbox",
        "--mode", "User",
        "--node-count", "1",
        "--node-vm-size", $sandboxNodeVmSize,
        "--os-sku", "AzureLinux",
        "--workload-runtime", "KataVmIsolation",
        "--labels", "agents.ai.azure.com/sandbox-node=true",
        "--ssh-access", "disabled",
        "--output", "none",
        "--no-wait"
    )
}

Wait-ForProvisioningState `
    -Label "AKS node pool sandbox" `
    -AzArguments @("aks", "nodepool", "show", "-g", $ResourceGroup, "--cluster-name", $aksName, "-n", "sandbox", "--query", "provisioningState", "-o", "tsv")

Write-Host ""
Write-Host "AKS provisioning complete. Cluster/pool report Succeeded."
Write-Host "This script did not create ACR resources or configure an ACR image-admission policy."
Write-Host "Before deploying agents, verify Ready nodes and complete the remaining Foundry BYO-AKS prerequisites."
Write-Host "FOUNDRY_RESOURCE_GROUP_ID=$foundryResourceGroupId"
Write-Host "AKS_RESOURCE_ID=$aksScope"