#!/usr/bin/env pwsh
# Docker migration runner with automatic token authentication
# This script handles token generation and Docker execution automatically
# REQUIRES: --production-resource, --production-subscription, --production-tenant

param(
    [Parameter(ValueFromRemainingArguments)]
    [string[]]$Arguments
)

# Colors for output
$Green = "`e[32m"
$Blue = "`e[34m"
$Yellow = "`e[33m"
$Red = "`e[31m"
$Reset = "`e[0m"

Write-Host "${Blue}🐳 Running v1 to v2 assistant migration in DOCKER with automatic authentication${Reset}"
Write-Host "======================================================================================"

# Check if Docker is running
try {
    docker info | Out-Null
    Write-Host "${Green}✅ Docker is running${Reset}"
} catch {
    Write-Host "${Red}❌ Docker is not running. Please start Docker Desktop and try again.${Reset}"
    exit 1
}

# Check if Azure CLI is available and authenticated
try {
    $account = az account show 2>$null | ConvertFrom-Json
    if ($account) {
        Write-Host "${Green}✅ Azure CLI authenticated as: $($account.user.name)${Reset}"
    } else {
        Write-Host "${Red}❌ Azure CLI not authenticated. Run 'az login' first.${Reset}"
        exit 1
    }
} catch {
    Write-Host "${Red}❌ Azure CLI not found. Install from https://docs.microsoft.com/cli/azure/${Reset}"
    exit 1
}

# Parse arguments - production parameters are REQUIRED
$productionTenant = $null
$sourceTenant = $null
$productionResource = $null
$productionSubscription = $null
$useConnectionString = $false

for ($i = 0; $i -lt $Arguments.Length; $i++) {
    if ($Arguments[$i] -eq "--production-tenant" -and ($i + 1) -lt $Arguments.Length) {
        $productionTenant = $Arguments[$i + 1]
    }
    if ($Arguments[$i] -eq "--source-tenant" -and ($i + 1) -lt $Arguments.Length) {
        $sourceTenant = $Arguments[$i + 1]
    }
    if ($Arguments[$i] -eq "--production-resource" -and ($i + 1) -lt $Arguments.Length) {
        $productionResource = $Arguments[$i + 1]
    }
    if ($Arguments[$i] -eq "--production-subscription" -and ($i + 1) -lt $Arguments.Length) {
        $productionSubscription = $Arguments[$i + 1]
    }
    if ($Arguments[$i] -eq "--project-connection-string") {
        $useConnectionString = $true
        Write-Host "${Blue}📝 Detected project connection string usage${Reset}"
    }
}

# Validate required production parameters
if (-not $productionResource -or -not $productionSubscription -or -not $productionTenant) {
    Write-Host "${Red}❌ Missing required production parameters!${Reset}"
    Write-Host ""
    Write-Host "REQUIRED parameters:"
    Write-Host "  --production-resource <resource-name>       (e.g., nextgen-eastus)"
    Write-Host "  --production-subscription <subscription-id> (e.g., b1615458-c1ea-49bc-8526-cafc948d3c25)"
    Write-Host "  --production-tenant <tenant-id>            (e.g., 33e577a9-b1b8-4126-87c0-673f197bf624)"
    Write-Host ""
    Write-Host "Example:"
    Write-Host "  .\run-migration-docker-auth.ps1 --use-api \" -ForegroundColor Yellow
    Write-Host "    --source-tenant 72f988bf-86f1-41af-91ab-2d7cd011db47 \" -ForegroundColor Yellow
    Write-Host "    --production-resource nextgen-eastus \" -ForegroundColor Yellow
    Write-Host "    --production-subscription b1615458-c1ea-49bc-8526-cafc948d3c25 \" -ForegroundColor Yellow
    Write-Host "    --production-tenant 33e577a9-b1b8-4126-87c0-673f197bf624 \" -ForegroundColor Yellow
    Write-Host "    asst_wBMH6Khnqbo1J7W1G6w3p1rN" -ForegroundColor Yellow
    exit 1
}

# Generate source token (still needed even with connection string - SDK requires credential)
$sourceToken = $null
if ($useConnectionString -and $sourceTenant) {
    Write-Host "${Blue}🔑 Generating source Azure AI token for project connection string (tenant: $sourceTenant)${Reset}"
    try {
        # Check current tenant
        $currentTenant = az account show --query tenantId -o tsv 2>$null
        
        if ($currentTenant -ne $sourceTenant) {
            Write-Host "${Yellow}🔄 Switching to source tenant: $sourceTenant${Reset}"
            az login --tenant $sourceTenant --only-show-errors
            if ($LASTEXITCODE -ne 0) {
                Write-Host "${Red}❌ Failed to authenticate with source tenant${Reset}"
                exit 1
            }
        }
        
        $sourceToken = az account get-access-token --scope https://ai.azure.com/.default --query accessToken -o tsv
        if ($sourceToken -and $sourceToken.Length -gt 100) {
            Write-Host "${Green}✅ Source token generated successfully (length: $($sourceToken.Length))${Reset}"
        } else {
            Write-Host "${Red}❌ Failed to generate source token or token is invalid${Reset}"
            exit 1
        }
    } catch {
        Write-Host "${Red}❌ Failed to generate source Azure token: $_${Reset}"
        exit 1
    }
} elseif ($useConnectionString) {
    Write-Host "${Blue}🔑 Generating source Azure AI token for project connection string (current tenant)${Reset}"
    try {
        $sourceToken = az account get-access-token --scope https://ai.azure.com/.default --query accessToken -o tsv
        if ($sourceToken -and $sourceToken.Length -gt 100) {
            Write-Host "${Green}✅ Source token generated successfully (length: $($sourceToken.Length))${Reset}"
        } else {
            Write-Host "${Red}❌ Failed to generate source token or token is invalid${Reset}"
            exit 1
        }
    } catch {
        Write-Host "${Red}❌ Failed to generate source Azure token: $_${Reset}"
        exit 1
    }
} elseif ($sourceTenant) {
    Write-Host "${Blue}🔑 Generating source Azure AI token for tenant: $sourceTenant${Reset}"
    try {
        # Check current tenant
        $currentTenant = az account show --query tenantId -o tsv 2>$null
        
        if ($currentTenant -ne $sourceTenant) {
            Write-Host "${Yellow}🔄 Switching to source tenant: $sourceTenant${Reset}"
            az login --tenant $sourceTenant --only-show-errors
            if ($LASTEXITCODE -ne 0) {
                Write-Host "${Red}❌ Failed to authenticate with source tenant${Reset}"
                exit 1
            }
        }
        
        $sourceToken = az account get-access-token --scope https://ai.azure.com/.default --query accessToken -o tsv
        if ($sourceToken -and $sourceToken.Length -gt 100) {
            Write-Host "${Green}✅ Source token generated successfully (length: $($sourceToken.Length))${Reset}"
        } else {
            Write-Host "${Red}❌ Failed to generate source token or token is invalid${Reset}"
            exit 1
        }
    } catch {
        Write-Host "${Red}❌ Failed to generate source Azure token: $_${Reset}"
        exit 1
    }
} else {
    Write-Host "${Blue}🔑 Generating source Azure AI token (current tenant)...${Reset}"
    try {
        $sourceToken = az account get-access-token --scope https://ai.azure.com/.default --query accessToken -o tsv
        if ($sourceToken -and $sourceToken.Length -gt 100) {
            Write-Host "${Green}✅ Source token generated successfully (length: $($sourceToken.Length))${Reset}"
        } else {
            Write-Host "${Red}❌ Failed to generate source token or token is invalid${Reset}"
            exit 1
        }
    } catch {
        Write-Host "${Red}❌ Failed to generate source Azure token: $_${Reset}"
        exit 1
    }
}

# Handle production authentication (REQUIRED)
$productionToken = $null
Write-Host "${Blue}🏭 Production v2 API Configuration:${Reset}"
Write-Host "${Blue}   � Resource: $productionResource${Reset}"
Write-Host "${Blue}   📋 Subscription: $productionSubscription${Reset}"
Write-Host "${Blue}   🔐 Tenant: $productionTenant${Reset}"

Write-Host "${Blue}🔐 Switching to production tenant: $productionTenant${Reset}"

try {
    # Check current tenant
    $currentTenant = az account show --query tenantId -o tsv 2>$null
    
    if ($currentTenant -eq $productionTenant) {
        Write-Host "${Green}✅ Already authenticated with production tenant${Reset}"
    } else {
        Write-Host "${Yellow}🔄 Switching from tenant $currentTenant to $productionTenant${Reset}"
        az login --tenant $productionTenant --only-show-errors
        if ($LASTEXITCODE -ne 0) {
            Write-Host "${Red}❌ Failed to authenticate with production tenant${Reset}"
            exit 1
        }
    }
    
    # Generate production token
    Write-Host "${Blue}🔑 Generating production Azure AI token...${Reset}"
    $productionToken = az account get-access-token --scope https://ai.azure.com/.default --query accessToken -o tsv
    if ($productionToken -and $productionToken.Length -gt 100) {
        Write-Host "${Green}✅ Production token generated successfully (length: $($productionToken.Length))${Reset}"
    } else {
        Write-Host "${Red}❌ Failed to generate production token${Reset}"
        exit 1
    }
    
    # Switch back to source tenant if different (for reading v1 assistants)
    if ($sourceTenant -and $currentTenant -ne $productionTenant) {
        Write-Host "${Blue}🔄 Switching back to source tenant for reading operations: $sourceTenant${Reset}"
        az login --tenant $sourceTenant --only-show-errors
        if ($LASTEXITCODE -ne 0) {
            Write-Host "${Yellow}⚠️  Warning: Could not switch back to source tenant${Reset}"
        }
    } elseif ($currentTenant -ne $productionTenant) {
        Write-Host "${Blue}🔄 Switching back to original tenant for reading operations${Reset}"
        az login --tenant $currentTenant --only-show-errors
        if ($LASTEXITCODE -ne 0) {
            Write-Host "${Yellow}⚠️  Warning: Could not switch back to original tenant${Reset}"
        }
    }
    
} catch {
    Write-Host "${Red}❌ Failed during production tenant authentication: $_${Reset}"
    exit 1
}

# Check if image exists
if (!(docker image inspect v1-to-v2-migration 2>$null)) {
    Write-Host "${Yellow}⚠️  Docker image 'v1-to-v2-migration' not found.${Reset}"
    Write-Host "${Blue}🔨 Building Docker image...${Reset}"
    docker build -t v1-to-v2-migration .
}

# Load environment variables from .env if it exists
if (Test-Path ".env") {
    Write-Host "${Green}✅ Loading environment variables from .env file${Reset}"
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^([^#=]+)=(.*)$") {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
} else {
    Write-Host "${Yellow}⚠️  No .env file found. Using environment variables or defaults.${Reset}"
}

# Run the container with token authentication
Write-Host "${Green}🏃 Running migration in Docker container with token authentication...${Reset}"
Write-Host "${Yellow}Arguments: $Arguments${Reset}"
Write-Host ""

try {
    # Prepare Docker environment variables
    $dockerEnvVars = @(
        "--network", "host"
        "-e", "DOCKER_CONTAINER=true"
        "-e", "AZ_TOKEN=$sourceToken"
    )
    
    # Add production token (required)
    $dockerEnvVars += "-e", "PRODUCTION_TOKEN=$productionToken"
    Write-Host "${Green}🏭 Passing both source and production tokens to container${Reset}"
    
    # Check if we need the beta version for project connection string
    $needsBetaVersion = $false
    for ($i = 0; $i -lt $Arguments.Length; $i++) {
        if ($Arguments[$i] -eq "--project-connection-string") {
            $needsBetaVersion = $true
            Write-Host "${Blue}🔍 Detected project connection string usage - beta version required${Reset}"
            break
        }
    }
    
    # All arguments are now passed to Python (source-tenant is supported)
    $filteredArguments = $Arguments
    
    # Add environment variable to indicate if beta version is needed
    if ($needsBetaVersion) {
        $dockerEnvVars += "-e", "NEED_BETA_VERSION=true"
        Write-Host "${Blue}🔧 Passing beta version requirement to container${Reset}"
    }
    
    docker run --rm -it `
        @dockerEnvVars `
        -e COSMOS_DB_CONNECTION_STRING="$env:COSMOS_DB_CONNECTION_STRING" `
        -e COSMOS_DB_DATABASE_NAME="$env:COSMOS_DB_DATABASE_NAME" `
        -e COSMOS_DB_CONTAINER_NAME="$env:COSMOS_DB_CONTAINER_NAME" `
        -e ASSISTANT_API_BASE="$env:ASSISTANT_API_BASE" `
        -e ASSISTANT_API_VERSION="$env:ASSISTANT_API_VERSION" `
        -e ASSISTANT_API_KEY="$env:ASSISTANT_API_KEY" `
        -e PROJECT_ENDPOINT_URL="$env:PROJECT_ENDPOINT_URL" `
        -e PROJECT_CONNECTION_STRING="$env:PROJECT_CONNECTION_STRING" `
        -e V2_API_BASE="$env:V2_API_BASE" `
        -e V2_API_VERSION="$env:V2_API_VERSION" `
        -e V2_API_KEY="$env:V2_API_KEY" `
        -e AZURE_TENANT_ID="$env:AZURE_TENANT_ID" `
        -e AZURE_CLIENT_ID="$env:AZURE_CLIENT_ID" `
        -e AZURE_CLIENT_SECRET="$env:AZURE_CLIENT_SECRET" `
        -e AZURE_SUBSCRIPTION_ID="$env:AZURE_SUBSCRIPTION_ID" `
        -e AZURE_RESOURCE_GROUP="$env:AZURE_RESOURCE_GROUP" `
        -e AZURE_PROJECT_NAME="$env:AZURE_PROJECT_NAME" `
        -v "$env:USERPROFILE\.azure:/home/migration/.azure" `
        v1-to-v2-migration `
        @filteredArguments
    
    $exitCode = $LASTEXITCODE
    
    if ($exitCode -eq 0) {
        Write-Host ""
        Write-Host "${Green}✅ Migration completed successfully!${Reset}"
    } else {
        Write-Host ""
        Write-Host "${Red}❌ Migration failed with exit code: $exitCode${Reset}"
    }
    
    exit $exitCode
} catch {
    Write-Host "${Red}❌ Failed to run Docker container: $_${Reset}"
    exit 1
}