<#
.SYNOPSIS
  Pre-step for the 48-bring-own-model-private-ca Bicep sample.

  Builds a small two-level PKI (root CA + gateway leaf) and materializes it so the
  BYO-CA trust flow can be demonstrated end to end:

    1. Root CA (ca.crt/ca.key): a self-signed CA certificate (basicConstraints
       CA:TRUE, keyUsage keyCertSign+cRLSign, NO serverAuth EKU). This is the
       TRUST ANCHOR. Its PUBLIC certificate (ca.crt, PEM) is uploaded to Key
       Vault as a SECRET (content-type application/x-pem-file) and referenced by
       the Foundry account's properties.trustedCertificateSources in the VERIFY
       phase. The reference pins this secret's name and version, and the secret
       contains only public PEM material.

    2. Gateway leaf (server.crt/server.key): a normal TLS server certificate
       (SAN=<fqdn>, EKU=serverAuth) SIGNED BY the root CA. nginx serves the leaf
       (as a fullchain: leaf + CA) on the TLS handshake the single-tenant data
       proxy validates.

  Registering the CA as a trust anchor is what flips the data proxy from failure
  (unknown issuer) to success: it can then chain the gateway leaf up to a trusted
  root. IMPORTANT: the trust store expects the CA public certificate (as a PEM
  secret), not a bare serverAuth leaf -- registering the leaf itself does NOT work
  (the resolver rejects it and the capability-host create fails).

  Cert creation is done out-of-band (not via an ARM deploymentScript) because
  deploymentScripts require a helper storage account with shared-key auth, which
  some subscription policies deny.

.EXAMPLE
  .\bootstrap-cert.ps1 -Subscription <sub-id> `
    -ResourceGroup rg-byomca -Location eastus2 `
    -KeyVaultName byomca-kv-01 -CustomDomainFqdn gateway.byomca.internal `
    -PrincipalObjectId <entra-object-id>
#>
param(
  [Parameter(Mandatory = $true)][string]$Subscription,
  [Parameter(Mandatory = $true)][string]$ResourceGroup,
  [Parameter(Mandatory = $true)][string]$Location,
  [Parameter(Mandatory = $true)][string]$KeyVaultName,
  [Parameter(Mandatory = $true)][string]$CustomDomainFqdn,
  # Name of the ROOT CA public-cert PEM SECRET in Key Vault (the trust anchor
  # referenced by account.trustedCertificateSources). Must be the CA public cert, not
  # the gateway leaf.
  [string]$SecretName = 'trustedca-root-pem',
  # Your Entra object (principal) id. If omitted it is read from the ARM access
  # token's 'oid' claim (no Microsoft Graph call, so conditional-access policies
  # that block Graph do not matter).
  [string]$PrincipalObjectId = '',
  [ValidateSet('User', 'ServicePrincipal')]
  [string]$PrincipalType = 'User',
  # Where the base64 PEM material is written for deploy.ps1 to pick up.
  # Leave empty to default to '.gateway' next to this script.
  [string]$OutDir = ''
)

$ErrorActionPreference = 'Stop'

# Resolve the script directory robustly ($PSScriptRoot can be empty in some
# -File invocations); fall back to the invoked command path, then cwd.
$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $scriptDir) { $scriptDir = (Get-Location).Path }
if (-not $OutDir) { $OutDir = Join-Path $scriptDir '.gateway' }

# ---- Locate openssl (PATH, else Git for Windows) ----------------------------
$openssl = (Get-Command openssl -ErrorAction SilentlyContinue).Source
if (-not $openssl) {
  $gitSsl = 'C:\Program Files\Git\usr\bin\openssl.exe'
  if (Test-Path $gitSsl) { $openssl = $gitSsl }
}
if (-not $openssl) { throw "openssl not found. Install Git for Windows or add openssl to PATH." }
# Stop MSYS (Git) openssl from mangling the -subj '/CN=...' into a Windows path.
$env:MSYS_NO_PATHCONV = '1'
Write-Host "Using openssl: $openssl"

az account set --subscription $Subscription
if ($LASTEXITCODE -ne 0) { throw "Could not select subscription '$Subscription'." }

function Get-OidFromArmToken {
  $tok = az account get-access-token --query accessToken -o tsv
  $part = $tok.Split('.')[1].Replace('-', '+').Replace('_', '/')
  switch ($part.Length % 4) { 2 { $part += '==' } 3 { $part += '=' } }
  $json = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($part))
  return ($json | ConvertFrom-Json).oid
}

if (-not $PrincipalObjectId) { $PrincipalObjectId = Get-OidFromArmToken }
Write-Host "Using principal object id: $PrincipalObjectId"

# ---- Generate a small PKI: root CA + gateway leaf signed by it --------------
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$caKey     = Join-Path $OutDir 'ca.key'
$caCrt     = Join-Path $OutDir 'ca.crt'
$leafKey   = Join-Path $OutDir 'server.key'
$leafCsr   = Join-Path $OutDir 'server.csr'
$leafCrt   = Join-Path $OutDir 'server.crt'
$leafExt   = Join-Path $OutDir 'server.ext'
$fullChain = Join-Path $OutDir 'fullchain.crt'

Write-Host "==> [1/3] Generating self-signed ROOT CA (trust anchor) ..."
& $openssl req -x509 -newkey rsa:2048 -nodes `
  -keyout $caKey -out $caCrt -days 3650 `
  -subj "/CN=BYOMCA Test Root CA/O=BYOMCA Sample" `
  -addext "basicConstraints=critical,CA:TRUE" `
  -addext "keyUsage=critical,keyCertSign,cRLSign" `
  -addext "subjectKeyIdentifier=hash"
if ($LASTEXITCODE -ne 0) { throw "openssl req (CA) failed." }

Write-Host "==> [2/3] Generating gateway LEAF key + CSR (CN/SAN=$CustomDomainFqdn) ..."
& $openssl req -newkey rsa:2048 -nodes `
  -keyout $leafKey -out $leafCsr `
  -subj "/CN=$CustomDomainFqdn"
if ($LASTEXITCODE -ne 0) { throw "openssl req (leaf CSR) failed." }

# Leaf extensions: server cert purpose, SAN must match the host the data proxy
# connects to so hostname validation passes once the chain is trusted.
@"
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:$CustomDomainFqdn
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
"@ | Set-Content -Path $leafExt -Encoding ascii

Write-Host "==> [3/3] Signing the leaf with the root CA ..."
& $openssl x509 -req -in $leafCsr -CA $caCrt -CAkey $caKey -CAcreateserial `
  -out $leafCrt -days 3650 -sha256 -extfile $leafExt
if ($LASTEXITCODE -ne 0) { throw "openssl x509 (sign leaf) failed." }

# nginx presents the leaf plus the CA (fullchain) so the data proxy sees the
# whole path; the root is still the anchor it must have in its trust store.
Get-Content $leafCrt, $caCrt | Set-Content -Path $fullChain -Encoding ascii

# ---- Key Vault (idempotent) + RBAC ------------------------------------------
Write-Host "==> Ensuring Key Vault '$KeyVaultName' (RBAC) in $ResourceGroup / $Location ..."
$kvId = az keyvault show --name $KeyVaultName --resource-group $ResourceGroup --query id -o tsv 2>$null
if (-not $kvId) {
  $eap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  az keyvault create `
    --name $KeyVaultName `
    --resource-group $ResourceGroup `
    --location $Location `
    --enable-rbac-authorization true `
    --retention-days 7 `
    --public-network-access Enabled | Out-Null
  $ErrorActionPreference = $eap
  $kvId = az keyvault show --name $KeyVaultName --resource-group $ResourceGroup --query id -o tsv
}
if (-not $kvId) { throw "Key Vault '$KeyVaultName' not found and could not be created." }

Write-Host "==> Granting 'Key Vault Secrets Officer' on the vault (no Graph lookup) ..."
$eap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
az role assignment create `
  --assignee-object-id $PrincipalObjectId `
  --assignee-principal-type $PrincipalType `
  --role "Key Vault Secrets Officer" `
  --scope $kvId | Out-Null
$ErrorActionPreference = $eap
if ($LASTEXITCODE -ne 0) { throw "Could not grant Key Vault Secrets Officer to the bootstrap principal." }

Write-Host "==> Waiting 30s for RBAC to propagate ..."
Start-Sleep -Seconds 30

# ---- Upload the ROOT CA PUBLIC cert (PEM) into Key Vault as a SECRET ---------
# The trusted-cert resolver reads a KV SECRET (public PEM), so we upload ca.crt
# (public only, no private key) with content-type application/x-pem-file.
Write-Host "==> Uploading ROOT CA public PEM secret '$SecretName' into Key Vault ..."
$version = ""
$eap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
for ($i = 0; $i -lt 6; $i++) {
  $secId = az keyvault secret set --vault-name $KeyVaultName --name $SecretName `
    --file $caCrt --encoding utf-8 --content-type "application/x-pem-file" `
    --query id -o tsv 2>$null
  if ($secId) { $version = ($secId -split '/')[-1]; break }
  Write-Host "   attempt $($i+1) failed (RBAC may still be propagating); retrying in 20s ..."
  Start-Sleep -Seconds 20
}
$ErrorActionPreference = $eap
if (-not $version) { throw "Secret upload failed after retries." }

# ---- Emit base64 PEM material for deploy.ps1 --------------------------------
# nginx serves the LEAF fullchain (leaf + CA) and the LEAF private key.
# certversion.txt is the pinned ROOT CA SECRET version used by
# account.trustedCertificateSources.
$certB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($fullChain))
$keyB64  = [Convert]::ToBase64String([IO.File]::ReadAllBytes($leafKey))
Set-Content -Path (Join-Path $OutDir 'cert.b64') -Value $certB64 -NoNewline
Set-Content -Path (Join-Path $OutDir 'key.b64')  -Value $keyB64  -NoNewline
Set-Content -Path (Join-Path $OutDir 'certversion.txt') -Value $version -NoNewline
Set-Content -Path (Join-Path $OutDir 'secretname.txt') -Value $SecretName -NoNewline

# Clean up private-key-bearing artifacts (secrets); keep public certs + chain.
Remove-Item $caKey, $leafCsr, $leafExt -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "==================== BOOTSTRAP COMPLETE ===================="
Write-Host "KeyVaultName        : $KeyVaultName"
Write-Host "RootCaSecretName    : $SecretName"
Write-Host "trustAnchorVersion  : $version   (account.trustedCertificateSources -> pinned ROOT CA PEM secret)"
Write-Host "gatewayLeafFqdn     : $CustomDomainFqdn (SAN, signed by the root CA)"
Write-Host "nginx serves        : $OutDir\fullchain.crt (+ server.key)"
Write-Host "PEM material (b64)  : $OutDir\cert.b64, key.b64"
Write-Host ""
Write-Host "Next: run deploy.ps1 (it reads .gateway\ automatically), e.g.:"
Write-Host "  .\deploy.ps1 -Subscription $Subscription -ResourceGroup $ResourceGroup ``"
Write-Host "     -Location $Location -CosmosLocation eastus2 -KeyVaultName $KeyVaultName"
Write-Host "==========================================================="
