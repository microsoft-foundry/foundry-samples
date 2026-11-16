using './main.bicep'

// Region for the sample resources.
param location = 'eastus2'

// Override when Azure AI Search lacks capacity in the primary region.
param searchLocation = 'eastus2'

param namePrefix = 'byomca'

// Backend model behind the gateway.
param foundryModelName = 'gpt-4.1'
param foundryModelVersion = '2025-04-14'
param foundryModelCapacity = 40

// Spoke VNet.
param vnetAddressSpace = '172.24.0.0/16'
param agentSubnetPrefix = '172.24.1.0/24'
param peSubnetPrefix = '172.24.2.0/24'
param aciSubnetPrefix = '172.24.3.0/24'

// Self-signed gateway custom domain (internal-only). The cert SAN is
// <customDomainHost>.<customDomainZone>.
param customDomainZone = 'byomca.internal'
param customDomainHost = 'gateway'

param inferenceApiVersion = '2024-10-21'

// keyVaultName is required. Set it here to the vault created by
// bootstrap-cert.ps1 (or override on the CLI with -p keyVaultName=...).
param keyVaultName = 'byomca-kv-ach01'

// gatewayCaSecretVersion is only needed for the VERIFY phase; deploy.ps1 reads
// it from the bootstrap output and passes it to the template.
param gatewayCaSecretVersion = ''

// Two-phase test switch:
//   false = REPRO  (expect TLS certificate-not-trusted at the data proxy)
//   true  = VERIFY (register the pinned CA bundle and expect success after propagation)
param enablePrivateCaTrust = false
