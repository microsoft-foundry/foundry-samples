<#
.SYNOPSIS
  Deploys the 48-bring-own-model-private-ca Bicep sample, wiring the self-signed
  cert material produced by bootstrap-cert.ps1 into the nginx gateway container.

  Run bootstrap-cert.ps1 FIRST; it writes .gateway\{cert.b64,key.b64,certversion.txt}.

  REPRO (default):  self-signed cert is NOT trusted -> inference expected to FAIL
                    at the single-tenant data proxy (certificate-not-trusted).
  VERIFY (-Verify): registers the pinned CA bundle in
                    account.trustedCertificateSources. After the account update
                    succeeds, trust propagates automatically; test inference.

.EXAMPLE
  # Phase 1 - REPRO
  .\deploy.ps1 -Subscription <sub-id> `
    -ResourceGroup rg-byomca -Location eastus2 `
    -CosmosLocation eastus2 -KeyVaultName byomca-kv-01

.EXAMPLE
  # Phase 2 - VERIFY
  .\deploy.ps1 -Subscription <sub-id> `
    -ResourceGroup rg-byomca -Location eastus2 `
    -CosmosLocation eastus2 -KeyVaultName byomca-kv-01 -Verify
#>
param(
  [Parameter(Mandatory = $true)][string]$Subscription,
  [Parameter(Mandatory = $true)][string]$ResourceGroup,
  [Parameter(Mandatory = $true)][string]$Location,
  [Parameter(Mandatory = $true)][string]$KeyVaultName,
  [string]$CosmosLocation = $Location,
  [string]$SearchLocation = $Location,
  [string]$ModelName = 'gpt-4o-mini',
  [string]$ModelVersion = '2024-07-18',
  [switch]$Verify,
  [string]$DeploymentName = '',
  [string]$CertDir = ''
)

$ErrorActionPreference = 'Stop'
$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $scriptDir) { $scriptDir = (Get-Location).Path }
if (-not $CertDir) { $CertDir = Join-Path $scriptDir '.gateway' }
$bicep = Join-Path $scriptDir 'main.bicep'
$bicepparam = Join-Path $scriptDir 'main.bicepparam'

$certB64 = Join-Path $CertDir 'cert.b64'
$keyB64  = Join-Path $CertDir 'key.b64'
$verFile = Join-Path $CertDir 'certversion.txt'
foreach ($f in @($certB64, $keyB64, $verFile)) {
  if (-not (Test-Path $f)) { throw "Missing $f. Run bootstrap-cert.ps1 first." }
}
$cert = (Get-Content -Raw $certB64).Trim()
$key  = (Get-Content -Raw $keyB64).Trim()
$ver  = (Get-Content -Raw $verFile).Trim()

if (-not $DeploymentName) { $DeploymentName = $(if ($Verify) { 'byomca-verify' } else { 'byomca-repro' }) }

$args = @(
  'deployment','group','create',
  '--subscription', $Subscription,
  '-g', $ResourceGroup,
  '-f', $bicep,
  '-p', $bicepparam,
  '-p', "location=$Location",
  '-p', "cosmosLocation=$CosmosLocation",
  '-p', "searchLocation=$SearchLocation",
  '-p', "foundryModelName=$ModelName",
  '-p', "foundryModelVersion=$ModelVersion",
  '-p', "keyVaultName=$KeyVaultName",
  '-p', "gatewayCertPemB64=$cert",
  '-p', "gatewayKeyPemB64=$key",
  '-n', $DeploymentName
)

if ($Verify) {
  Write-Host "==> VERIFY phase: registering trustedCertificateSources (pinned version $ver)"
  $args += @('-p', 'enablePrivateCaTrust=true', '-p', "gatewayCaSecretVersion=$ver")
} else {
  Write-Host "==> REPRO phase: trustedCertificateSources NOT registered (expect TLS failure)"
}

Write-Host "==> az $($args -join ' ' -replace [regex]::Escape($cert),'<cert-b64>' -replace [regex]::Escape($key),'<key-b64>')"
az @args
