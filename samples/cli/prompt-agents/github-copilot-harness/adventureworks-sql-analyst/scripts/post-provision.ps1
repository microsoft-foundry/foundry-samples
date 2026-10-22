Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Get-Command sqlcmd -ErrorAction SilentlyContinue)) {
  throw 'sqlcmd is required. Install it from https://learn.microsoft.com/sql/tools/sqlcmd/sqlcmd-download-install'
}

$sqlServerFqdn = azd env get-value SQL_SERVER_FQDN
$sqlServerName = azd env get-value SQL_SERVER_NAME
$sqlDatabaseName = azd env get-value SQL_DATABASE_NAME
$namespaceName = azd env get-value CONNECTOR_NAMESPACE_NAME
$namespacePrincipalId = azd env get-value CONNECTOR_NAMESPACE_PRINCIPAL_ID
$subscriptionId = azd env get-value AZURE_SUBSCRIPTION_ID
$resourceGroupName = azd env get-value AZURE_FOUNDRY_RESOURCE_GROUP
$deployerIpAddress = $env:DEPLOYER_IP_ADDRESS

if (-not $sqlServerFqdn -or -not $sqlServerName -or -not $sqlDatabaseName -or -not $namespaceName -or -not $namespacePrincipalId -or -not $subscriptionId -or -not $resourceGroupName) {
    throw 'Required SQL or Connector Namespace outputs are missing.'
}

$firewallRuleCleanupRequired = $false
$operationError = $null
$cleanupErrorMessage = $null

$grantSql = @"
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'$namespaceName')
BEGIN
  CREATE USER [$namespaceName] FROM EXTERNAL PROVIDER WITH OBJECT_ID = '$namespacePrincipalId';
END;
IF ISNULL(IS_ROLEMEMBER('db_datareader', '$namespaceName'), 0) = 0
BEGIN
  ALTER ROLE db_datareader ADD MEMBER [$namespaceName];
END;
GRANT VIEW DEFINITION TO [$namespaceName];
"@

try {
  if (-not $deployerIpAddress) {
    $probeOutput = sqlcmd -S $sqlServerFqdn -d $sqlDatabaseName -G -b -Q 'SELECT 1;' 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0) {
      Write-Host 'Local Azure SQL access is already allowed; no temporary firewall rule is needed.'
    }
    else {
      $match = [regex]::Match($probeOutput, "Client with IP address '((?:[0-9]{1,3}\.){3}[0-9]{1,3})'")
      $parsedAddress = $null
      if (-not $match.Success -or -not [System.Net.IPAddress]::TryParse($match.Groups[1].Value, [ref]$parsedAddress) -or $parsedAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
        Write-Error $probeOutput -ErrorAction Continue
        throw 'Could not determine the client IPv4 address from the Azure SQL firewall response. Set DEPLOYER_IP_ADDRESS or add your client IP in Azure SQL networking, then rerun azd up.'
      }
      $deployerIpAddress = $parsedAddress.ToString()
    }
  }

  if ($deployerIpAddress) {
    $firewallRuleCleanupRequired = $true
    az sql server firewall-rule create `
      --subscription $subscriptionId `
      --resource-group $resourceGroupName `
      --server $sqlServerName `
      --name AllowDeployerIp `
      --start-ip-address $deployerIpAddress `
      --end-ip-address $deployerIpAddress `
      --only-show-errors | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw 'Failed to create the temporary deployer IP firewall rule.'
    }
  }

  sqlcmd -S $sqlServerFqdn -d $sqlDatabaseName -G -b -Q $grantSql
  if ($LASTEXITCODE -ne 0) {
    throw 'Local Azure SQL access failed. Set DEPLOYER_IP_ADDRESS in the azd environment or add your client IP in Azure SQL networking, then rerun azd up.'
  }

  $productCount = sqlcmd -S $sqlServerFqdn -d $sqlDatabaseName -G -h -1 -W -Q 'SET NOCOUNT ON; SELECT COUNT(*) FROM SalesLT.Product;'
  if ($LASTEXITCODE -ne 0) {
    throw 'Failed to verify AdventureWorksLT sample data.'
  }
}
catch {
  $operationError = $_
}
finally {
  if ($firewallRuleCleanupRequired) {
    az sql server firewall-rule delete `
      --subscription $subscriptionId `
      --resource-group $resourceGroupName `
      --server $sqlServerName `
      --name AllowDeployerIp `
      --only-show-errors | Out-Null
    if ($LASTEXITCODE -ne 0) {
      $cleanupErrorMessage = "Failed to remove temporary Azure SQL firewall rule AllowDeployerIp. Remove it manually: az sql server firewall-rule delete --subscription $subscriptionId --resource-group $resourceGroupName --server $sqlServerName --name AllowDeployerIp"
    }
  }
}

if ($operationError -and $cleanupErrorMessage) {
  throw "$($operationError.Exception.Message) Cleanup also failed: $cleanupErrorMessage"
}
if ($operationError) {
  throw $operationError
}
if ($cleanupErrorMessage) {
  throw $cleanupErrorMessage
}

Write-Host "AdventureWorksLT is ready with $($productCount.Trim()) products."
