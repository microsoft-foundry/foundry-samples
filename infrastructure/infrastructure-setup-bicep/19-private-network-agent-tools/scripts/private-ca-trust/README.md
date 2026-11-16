# Private CA trust

Use `Set-PrivateCaTrust.ps1` to register or rotate version-pinned public CA
certificate secrets on an existing Foundry account. After the account update
succeeds, trust propagates automatically to project capability hosts.

## Prerequisites

- Windows PowerShell 5.1 or PowerShell 7 or later.
- Azure CLI authenticated to the tenant that contains the Foundry resource.
- Permissions to read and update the Foundry account through Azure Resource
  Manager.
- A Key Vault containing public root/intermediate CA certificates as
  PEM-formatted secrets. One secret can contain multiple CA certificates.
  Never upload private keys or use Key Vault certificate objects for trust.
- The Foundry account's primary attached user-assigned managed identity, or its
  system-assigned identity otherwise, has **Key Vault Secrets User** on the
  vault. The service does not use the project identity to retrieve CA secrets.
- For a restricted vault, enable the trusted Microsoft services firewall
  bypass (`networkAcls.bypass: AzureServices`). A private endpoint alone is not
  sufficient for the service's CA retrieval path. The template's new vault uses
  `publicNetworkAccess: Enabled`, `defaultAction: Deny`, no public IP rules, and
  that bypass. Existing vault firewall settings are not modified.

Upload secrets from a machine with authorized access to the vault. To verify
agent HTTPS afterward, use a client with access to the project endpoint, such as
a VPN-connected machine or jump host for a private Foundry account.

Account CA trust is public preview in all Azure public cloud regions without
subscription allowlisting for this feature. Hosted Agent preview access
requirements remain unchanged. Regional model availability, quotas, private
networking, and other service requirements still apply.

## Register or rotate CA trust

The account supports one `AzureKeyVault` source, up to 25 version-pinned secret
references, and at most 100 CA certificates across those secrets.

From this directory, run:

```powershell
.\Set-PrivateCaTrust.ps1 `
  -SubscriptionId "<subscription-id>" `
  -ResourceGroup "<resource-group>" `
  -AccountName "<foundry-account>" `
  -KeyVaultResourceId "<key-vault-resource-id>" `
  -CertificateReference @(
    "private-root-ca-pem=<exact-secret-version>",
    "private-intermediate-ca-pem=<exact-secret-version>"
  )
```

The script uses `2026-07-15-preview` by default, updates only
`properties.trustedCertificateSources`, preserves unrelated references in the
same vault, and replaces the pinned version for each explicitly named secret.
It refuses an unexpected source, another vault, malformed references, or an
update exceeding 25 references. It never reads or prints secret values.
The service validates certificate contents and the total certificate count.

Use `-WhatIf` to inspect the proposed action without submitting a PATCH.
Coordinate concurrent writers: the script rechecks the configuration before
PATCH, but the recheck is not an atomic concurrency lock.

## Wait for completion and test HTTPS

The script saves the `Azure-AsyncOperation` URL to
`<OutputPath>.operation.txt`, follows `Retry-After`, and monitors the long-running
operation (LRO), including the pending `Updating` status. After `Succeeded`, it
verifies all intended references, including preserved references, before writing
the JSON report. `-OutputPath` defaults to
`.private-ca-trust\private-ca-trust.json` beside the script; `-TimeoutSeconds`
defaults to 1800 (30 minutes). The included `.gitignore` excludes this report
directory.

Test a managed-tool HTTPS request after successful propagation. For Hosted Agent
direct HTTPS, use a newly provisioned sandbox; existing sessions or snapshots
can retain the old trust. Application-specific CA stores may need separate
configuration.

## Rotate or remove CA trust

Uploading a new secret version does not advance the pin. Rotate by invoking the
script with the same secret name and its new exact version, then wait for
completion and test HTTPS again. Leaf renewal under the same issuing CA chain
requires no account trust change.

ARM updates replace the entire trust array. To remove all customer CA
references, explicitly PATCH `{"properties":{"trustedCertificateSources":[]}}`
and monitor its LRO. The registration script intentionally doesn't clear trust.

## Troubleshooting

A timeout or monitoring error does not cancel the update: check the saved
operation before resubmitting. Failed/canceled operations and unknown statuses
stop with an error.

On partial failure, the account can hold the new configuration while some
projects retain old trust. Inspect the LRO errors and fix the cause. Identical
resubmission can be a no-op; change the configuration or pinned version, or
contact support.

## Local regression tests

From this directory, run the trust tests with PowerShell and Pester 5 or later:

```powershell
Invoke-Pester -Path .\Set-PrivateCaTrust.Tests.ps1 -CI
```

The tests mock Azure authentication, HTTP requests, and polling delays; they do
not contact Azure or read certificate secrets.
