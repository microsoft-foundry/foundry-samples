<#
.SYNOPSIS
  Deterministic "untrusted cert" test for the 48-bring-own-model-private-ca sample.

  Rolls ONLY the gateway nginx ACI to present a DIFFERENT leaf, without touching
  the Foundry account trustedCertificateSources configuration. This is the
  clean, single-run proof that the single-tenant data proxy actually validates
  the gateway chain against the registered trust anchor:

    -Mode Untrusted : mint a brand-new CA-B (never registered) + leaf, redeploy
                      the ACI to serve it. account trust still = CA-A.
                      EXPECT: agent inference FAILS (unknown issuer / 424) at the
                      data proxy TLS handshake -- enforcement proven.

    -Mode Restore   : redeploy the ACI with the ORIGINAL CA-A leaf material that
                      bootstrap-cert.ps1 wrote to .gateway\ (cert.b64/key.b64).
                      EXPECT: agent inference SUCCEEDS again (back to green).

  Why ACI is deleted + recreated: Azure Container Instances secret volumes are
  immutable; you cannot patch the cert in place. We recreate the SAME container
  group (same image/command/subnet/nginx.conf) with new cert secret volumes, then
  re-point the private-DNS A record at the (possibly new) private IP.

  IMPORTANT: this does NOT rely on trust *removal* (which is non-deterministic due
  to the 12h success cache + warm proxy). It changes the *leaf the gateway serves*,
  so the very next TLS handshake presents a chain that cannot be validated -> fails
  immediately and reproducibly.

.EXAMPLE
  # Prove enforcement (expect failure after this)
  .\roll-gateway-cert.ps1 -Mode Untrusted

.EXAMPLE
  # Roll back to the trusted CA-A leaf (expect success after this)
  .\roll-gateway-cert.ps1 -Mode Restore
#>
param(
  [ValidateSet('Untrusted', 'Restore')]
  [string]$Mode = 'Untrusted',

  [Parameter(Mandatory = $true)][string]$Subscription,
  [Parameter(Mandatory = $true)][string]$ResourceGroup,
  [Parameter(Mandatory = $true)][string]$Location,
  [Parameter(Mandatory = $true)][string]$AciName,
  [Parameter(Mandatory = $true)][string]$SubnetId,
  [Parameter(Mandatory = $true)][string]$Fqdn,
  [Parameter(Mandatory = $true)][string]$ModelHost,
  [string]$ApiPath        = 'inference',
  [string]$DnsZone        = 'byomca.internal',
  [string]$DnsRecord      = 'gateway',
  [string]$Image          = 'mcr.microsoft.com/cbl-mariner/base/nginx:1.22'
)

$ErrorActionPreference = 'Stop'
$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $scriptDir) { $scriptDir = (Get-Location).Path }

az account set --subscription $Subscription

# ---- 1. Obtain the leaf cert + key to serve (base64 PEM) ---------------------
if ($Mode -eq 'Restore') {
  $certB64File = Join-Path $scriptDir '.gateway\cert.b64'
  $keyB64File  = Join-Path $scriptDir '.gateway\key.b64'
  foreach ($f in @($certB64File, $keyB64File)) {
    if (-not (Test-Path $f)) { throw "Missing $f (the original CA-A material from bootstrap-cert.ps1)." }
  }
  $certB64 = (Get-Content -Raw $certB64File).Trim()
  $keyB64  = (Get-Content -Raw $keyB64File).Trim()
  Write-Host "==> Restore: serving the ORIGINAL trusted CA-A leaf from .gateway\"
}
else {
  # Locate openssl (PATH, else Git for Windows).
  $openssl = (Get-Command openssl -ErrorAction SilentlyContinue).Source
  if (-not $openssl) {
    $gitSsl = 'C:\Program Files\Git\usr\bin\openssl.exe'
    if (Test-Path $gitSsl) { $openssl = $gitSsl }
  }
  if (-not $openssl) { throw "openssl not found. Install Git for Windows or add openssl to PATH." }
  $env:MSYS_NO_PATHCONV = '1'

  $out = Join-Path $scriptDir '.gateway-untrusted'
  New-Item -ItemType Directory -Force -Path $out | Out-Null
  $caKey = Join-Path $out 'caB.key'; $caCrt = Join-Path $out 'caB.crt'
  $lfKey = Join-Path $out 'server.key'; $lfCsr = Join-Path $out 'server.csr'
  $lfCrt = Join-Path $out 'server.crt'; $lfExt = Join-Path $out 'server.ext'
  $chain = Join-Path $out 'fullchain.crt'

  Write-Host "==> Minting UNTRUSTED root CA-B (never registered) ..."
  & $openssl req -x509 -newkey rsa:2048 -nodes -keyout $caKey -out $caCrt -days 3650 `
    -subj "/CN=BYOMCA UNTRUSTED Root CA-B/O=BYOMCA Sample" `
    -addext "basicConstraints=critical,CA:TRUE" `
    -addext "keyUsage=critical,keyCertSign,cRLSign" `
    -addext "subjectKeyIdentifier=hash"
  if ($LASTEXITCODE -ne 0) { throw "openssl req (CA-B) failed." }

  Write-Host "==> Minting gateway leaf (SAN=$Fqdn) signed by CA-B ..."
  & $openssl req -newkey rsa:2048 -nodes -keyout $lfKey -out $lfCsr -subj "/CN=$Fqdn"
  if ($LASTEXITCODE -ne 0) { throw "openssl req (leaf CSR) failed." }
@"
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:$Fqdn
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
"@ | Set-Content -Path $lfExt -Encoding ascii
  & $openssl x509 -req -in $lfCsr -CA $caCrt -CAkey $caKey -CAcreateserial -out $lfCrt -days 3650 -sha256 -extfile $lfExt
  if ($LASTEXITCODE -ne 0) { throw "openssl x509 (sign leaf) failed." }

  Get-Content $lfCrt, $caCrt | Set-Content -Path $chain -Encoding ascii
  $certB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($chain))
  $keyB64  = [Convert]::ToBase64String([IO.File]::ReadAllBytes($lfKey))
  Write-Host "==> CA-B leaf ready (SAN matches, but issuer is NOT a registered anchor)."
}

# ---- 2. Rebuild nginx.conf (identical to main.bicep) + base64 ----------------
$nginxConf = @"
worker_processes 1;
error_log /dev/stderr warn;
pid /tmp/nginx.pid;
events { worker_connections 1024; }
http {
  include /etc/nginx/mime.types;
  default_type application/octet-stream;
  access_log /dev/stdout;
  proxy_http_version 1.1;
  server {
    listen 443 ssl;
    server_name $Fqdn;
    ssl_certificate     /mnt/certs/server.crt;
    ssl_certificate_key /mnt/certs/server.key;
    location /$ApiPath/ {
      proxy_pass https://$ModelHost/openai/;
      proxy_set_header Host $ModelHost;
      proxy_ssl_server_name on;
    }
    location / { return 200 'gateway-ok'; }
  }
}
"@
$nginxB64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($nginxConf))

# ---- 3. Write the ACI YAML (secret volumes carry base64 PEM) -----------------
$yaml = @"
apiVersion: 2023-05-01
location: $Location
name: $AciName
type: Microsoft.ContainerInstance/containerGroups
properties:
  sku: Standard
  osType: Linux
  restartPolicy: Always
  subnetIds:
    - id: $SubnetId
  ipAddress:
    type: Private
    ports:
      - protocol: TCP
        port: 443
  volumes:
    - name: certs
      secret:
        server.crt: $certB64
        server.key: $keyB64
    - name: conf
      secret:
        nginx.conf: $nginxB64
  containers:
    - name: gateway
      properties:
        image: $Image
        command:
          - nginx
          - -c
          - /mnt/conf/nginx.conf
          - -g
          - "daemon off;"
        ports:
          - protocol: TCP
            port: 443
        resources:
          requests:
            cpu: 1
            memoryInGB: 1
        volumeMounts:
          - name: certs
            mountPath: /mnt/certs
            readOnly: true
          - name: conf
            mountPath: /mnt/conf
            readOnly: true
"@
$yamlPath = Join-Path $scriptDir 'gw-roll.yaml'
Set-Content -Path $yamlPath -Value $yaml -Encoding ascii
Write-Host "==> Wrote $yamlPath"

# ---- 4. Delete + recreate the ACI (secret volumes are immutable) ------------
Write-Host "==> Deleting existing container group '$AciName' ..."
az container delete --resource-group $ResourceGroup --name $AciName --yes | Out-Null

Write-Host "==> Recreating container group '$AciName' from YAML ..."
az container create --resource-group $ResourceGroup --file $yamlPath | Out-Null

# ---- 5. Re-point the private-DNS A record at the (possibly new) IP -----------
$newIp = az container show --resource-group $ResourceGroup --name $AciName --query "ipAddress.ip" -o tsv
Write-Host "==> New gateway private IP: $newIp"

$curIp = az network private-dns record-set a show --resource-group $ResourceGroup --zone-name $DnsZone --name $DnsRecord --query "aRecords[0].ipv4Address" -o tsv 2>$null
if ($curIp -and $curIp -ne $newIp) {
  Write-Host "==> Updating A record $DnsRecord.$DnsZone : $curIp -> $newIp"
  az network private-dns record-set a remove-record --resource-group $ResourceGroup --zone-name $DnsZone --record-set-name $DnsRecord --ipv4-address $curIp | Out-Null
}
if ($curIp -ne $newIp) {
  az network private-dns record-set a add-record --resource-group $ResourceGroup --zone-name $DnsZone --record-set-name $DnsRecord --ipv4-address $newIp | Out-Null
}
Write-Host "==> A record $DnsRecord.$DnsZone -> $newIp"

Write-Host ""
Write-Host "==================== ROLL COMPLETE ($Mode) ===================="
if ($Mode -eq 'Untrusted') {
  Write-Host "Gateway now serves a leaf signed by UNREGISTERED CA-B."
  Write-Host "account.trustedCertificateSources is unchanged (still CA-A)."
  Write-Host "NEXT: invoke the agent. EXPECT: inference FAILS (cert not trusted / 424) at the data proxy."
}
else {
  Write-Host "Gateway restored to the ORIGINAL trusted CA-A leaf."
  Write-Host "NEXT: invoke the agent. EXPECT: inference SUCCEEDS (back to green)."
}
Write-Host "=============================================================="
