# 48 — Bring Your Own Model behind a self-signed gateway (private-CA trust) — Bicep

Bicep port of the Terraform sample of the same name
(`infrastructure/infrastructure-setup-terraform/48-bring-own-model-private-ca`).

This sample stands up the infrastructure to **reproduce, then fix, a TLS
"certificate not trusted" failure** on the Foundry **connected-model
inferencing path**, when the model is fronted by a customer gateway that
presents a **self-signed certificate** on an **internal-only** domain.

The single-tenant **data proxy** (provisioned inside your VNet by the capability
host) is the TLS chokepoint under test.

## Real-world scenario

A customer runs their own AI gateway (e.g. AWS API Gateway) that fronts the
models. It is exposed on a **private VAN URL** — internal DNS only, not publicly
resolvable — and secured with a **self-signed certificate**. They want Foundry
to call the gateway, not the models directly. When Foundry inferences through a
connected model pointed at that gateway, the data proxy must trust the
self-signed cert — or TLS fails.

This sample recreates that shape with a **minimal nginx reverse proxy** standing
in for the customer gateway (self-signed cert on an internal-only domain), and a
real **gpt-4o-mini** deployment behind it.

## Why not APIM?

An earlier version used APIM as the gateway. APIM (StandardV2, public) *always*
enforces a **public CNAME ownership check** when you bind a custom domain — it
looks for `gateway.byomca.internal → <apim>.azure-api.net` in **public** DNS.
An internal-only zone can never satisfy that, and there is no bypass for the
public v2 gateway. Only a truly internal gateway (Developer/Premium Internal
VNet mode) skips the check.

A plain reverse proxy has **no custom-domain ownership check at all** — it just
serves whatever cert you give it — so an internal-only FQDN + self-signed cert
works directly. It is also far lighter (deploys in ~1–2 min vs ~40) and lets us
drop the APIM user-assigned identity, APIM private endpoint, and
`privatelink.azure-api.net` zone.

## Architecture

```
Foundry project ──connected model──▶ single-tenant data proxy ──TLS(self-signed)──▶ nginx gateway (ACI) ──▶ gpt-4o-mini
   (VNet-injected agent account)          ▲ (in your VNet)                              ▲                       (model account)
                                   TLS trust decision here            self-signed cert served here
```

- **Foundry agent account** — VNet-injected (`networkInjections` → delegated
  agent subnet). Injection is what provisions the data proxy inside your VNet.
- **Capability host** — project-level cap host (backed by BYO Storage / Cosmos /
  AI Search). Creating it provisions the data proxy. After an account trust
  update succeeds, Foundry propagates the trust configuration automatically to
  project capability hosts.
- **nginx gateway (Azure Container Instances)** — a single `nginx` container with
  a **private IP** in a delegated subnet. It terminates TLS with the self-signed
  cert on `gateway.byomca.internal` and reverse-proxies `/inference/…` to the
  model account's `/openai/…` endpoint. The connected model's connection uses
  `ProjectManagedIdentity` auth (audience `cognitiveservices`); nginx forwards
  that `Authorization` header straight through, and the **project MI** is granted
  `Cognitive Services User` on the model account — so no API key is needed.
- **Private CA + gateway leaf** — the trust material:
  - nginx serves the **gateway leaf** (as a fullchain: leaf + CA) on the TLS
    handshake (from PEM mounted as an ACI secret volume);
  - the **root CA public certificate** (PEM, no private key) is uploaded to Key
    Vault as a **secret** and registered into the account's
    `trustedCertificateSources` in the verify phase. The account configuration
    identifies the Key Vault and pins the secret name and version, so the
    customer never hands Foundry a private key.

## Files

| File | Purpose |
|------|---------|
| `bootstrap-cert.ps1` | **Pre-step.** Builds a small PKI with openssl — a self-signed **root CA** plus a **gateway leaf** signed by it — writes the leaf fullchain + key to `.gateway\` for nginx, and uploads the **root CA public PEM** to Key Vault as a **secret** (the trust anchor). Run this first. |
| `deploy.ps1` | Deploy wrapper. Reads `.gateway\` and passes the cert/key as secure params. `-Verify` flips to the trust-registered phase. |
| `roll-gateway-cert.ps1` | Optional negative test. Replaces only the gateway certificate with one signed by an unregistered CA, then restores the original certificate. |
| `main.bicep` | Everything else, at resource-group scope. |
| `main.bicepparam` | Parameter values (edit `location`, custom domain, etc.). |
| `.gitignore` | Excludes `.gateway\` (contains the private key). |
| `metadata.json` | Sample metadata. |

## Bicep-specific design notes (differences from the Terraform version)

1. **Private CA → `bootstrap-cert.ps1` pre-step.** ARM has no declarative
   Key Vault *certificate*/*secret* resource with generated material, and
   `deploymentScripts` provision a helper storage account with **shared-key
   auth**, which many subscription policies deny
   (`KeyBasedAuthenticationNotPermitted`). So the PKI is created **out of band**
   by `bootstrap-cert.ps1` (openssl → leaf PEM for nginx; root CA public PEM
   uploaded to Key Vault as a **secret** for the trust anchor). It prints the
   pinned Key Vault **secret** version used as `gatewayCaSecretVersion`.
2. **Gateway = nginx container, not APIM.** See "Why not APIM?" above. The cert
   and key are handed to nginx as base64 PEM via ACI **secret volumes**; the
   nginx config is rendered in Bicep and mounted the same way.
3. **Gateway DNS record → A record to the container IP.** The custom FQDN is an
   **A record → the ACI private IP** (`gatewayAci.properties.ipAddress.ip`),
   resolvable inside the VNet via the linked private DNS zone. SNI carries the
   custom FQDN, so nginx serves the self-signed cert bound to it.

## The two-phase test

Controlled by the `enablePrivateCaTrust` parameter (set for you by
`deploy.ps1`).

### Phase 0 — bootstrap the cert (run once)

```powershell
.\bootstrap-cert.ps1 -Subscription <sub-id> -ResourceGroup rg-byomca `
  -Location canadacentral -KeyVaultName byomca-kv-01 `
  -CustomDomainFqdn gateway.byomca.internal `
  -PrincipalObjectId <your-entra-object-id>
```

Writes `.gateway\{cert.b64,key.b64,certversion.txt}` and uploads the root CA
public PEM to Key Vault as a **secret**.

### Phase 1 — REPRO (`enablePrivateCaTrust = false`, default)

```powershell
.\deploy.ps1 -Subscription <sub-id> -ResourceGroup rg-byomca `
  -Location canadacentral -CosmosLocation eastus2 -KeyVaultName byomca-kv-01
```

Then run an inference through the connected model (Foundry portal model
playground, or the chat-completions API against the project).
**Expected: failure** — the data proxy cannot trust the self-signed cert, so the
call fails with a TLS / certificate-not-trusted error.

### Phase 2 — VERIFY (`enablePrivateCaTrust = true`)

```powershell
.\deploy.ps1 -Subscription <sub-id> -ResourceGroup rg-byomca `
  -Location canadacentral -CosmosLocation eastus2 -KeyVaultName byomca-kv-01 -Verify
```

Wait for the deployment and account update to succeed. The update pins the Key
Vault secret version, and Foundry propagates the trust configuration
automatically to project capability hosts. Inspect the stored references using
the account query below before testing inference.

Re-run the same inference. **Expected: success** — the gateway leaf now chains
to a trusted root CA, so the handshake validates and gpt-4o-mini responds.

For a deterministic post-configuration negative test, run
`roll-gateway-cert.ps1 -Mode Untrusted` with the deployment values requested by
the script. The gateway then presents a chain signed by an unregistered CA while
the account configuration remains unchanged, so inference should fail. Run the
script again with `-Mode Restore` to restore the original trusted chain.

## Why a private CA works (and a bare leaf does not)

The trust store expects a **CA certificate**, supplied as a **Key Vault secret**
holding the CA **public PEM**. The bootstrap builds a small PKI: a self-signed
**root CA** (`basicConstraints=CA:TRUE`, `keyUsage=keyCertSign,cRLSign`) and a
**gateway leaf** (`extendedKeyUsage=serverAuth`, `SAN=<fqdn>`) **signed by that
CA**. nginx serves the leaf (as a fullchain: leaf + CA); the account's
`trustedCertificateSources` registers the Key Vault and a pinned reference to the
**root CA public PEM secret**. Once the data proxy has the root in its trust
store it can chain the presented leaf up to it and hostname-validate against the
SAN.

The agent account uses API version `2026-11-15-preview` and registers the
trust source using this structure:

```bicep
trustedCertificateSources: [
  {
    type: 'AzureKeyVault'
    resourceId: keyVault.id
    certificateBundleReferences: [
      {
        secretName: gatewayCaSecretName
        secretVersion: gatewayCaSecretVersion
      }
    ]
  }
]
```

In the REPRO phase this property is omitted. After deploying the VERIFY phase,
inspect the saved configuration with the same account API version:

```powershell
az resource show --ids "<agent-account-resource-id>" `
  --api-version 2026-11-15-preview `
  --query properties.trustedCertificateSources
```

The account managed identity needs **Key Vault Secrets User** (`getSecret`) on
the vault so Foundry can read the PEM. The bundle must contain CA certificates:

- Reference a Key Vault **secret**, not a Key Vault certificate object.
- Register the **CA** rather than the leaf; a bare server-auth leaf is not a
  valid trust anchor.

The root CA must also **not** be publicly trusted, or the OS-trust branch
short-circuits and the private bundle is never exercised.

## Requirements to get right

- **Target the custom domain.** The connected-model target (`connectedModelTarget`
  output) is the self-signed FQDN, not the model account's own endpoint.
- **SAN = FQDN.** The certificate's SAN equals `<customDomainHost>.<customDomainZone>`;
  a mismatch yields a *hostname* error instead of the *trust* error under test.
- **Internal DNS.** The custom domain resolves (privately) to the nginx container
  via the `gateway` A record.
- **Pinned version.** Rotating the Key Vault secret does not update trust by
  itself. Upload the replacement bundle, then update
  `gatewayCaSecretVersion` (or rerun `deploy.ps1 -Verify`) so the account points
  to the new version. Wait for the account update to succeed, verify the stored
  references, and test inference.
- **Region.** Cosmos capacity is a per-subscription/region gate;
  `cosmosLocation` lets you place Cosmos in a different region (for example,
  `eastus2`) from the rest of the stack. Azure AI Search capacity can also vary
  by region; `searchLocation` places only the Search service elsewhere while
  its private endpoint remains in the primary-region VNet.

## Known caveats / things to confirm at runtime

- **Model-path egress hypothesis.** This sample assumes connected-model
  inferencing egresses the single-tenant data proxy the same way agent tools do.
  Confirming that is the *point* of the test: if inference reaches the model only
  after the trust is registered, the hypothesis holds.
- **nginx backend egress.** The container reaches the model account over its
  public endpoint (outbound internet from the ACI subnet). The model account
  keeps `disableLocalAuth` because auth is AAD (forwarded `Authorization`).
- **Preview API validation.** The `ProjectManagedIdentity` connection value is
  supported by the service but is not yet represented in the Bicep type index,
  so the template contains a targeted `BCP036` suppression on that property.
  The account API `2026-11-15-preview` also emits an expected `BCP081` warning
  because its resource types are not yet in the installed Bicep type index.
  Build and lint still succeed, but the compiler cannot validate that account's
  property schema. Validate the preview contract with a live deployment in a
  subscription where the preview API is enabled.
- **Feature availability.** Account CA trust is public preview in all Azure
  public cloud regions without subscription allowlisting for this feature.
  Other networking, model availability, quota, and preview API requirements
  still apply.
- **Update failures.** Inspect the account operation's error before retrying.
  A partial failure can leave the account on the new configuration while some
  projects retain old trust. An identical resubmission can be a no-op; fix the
  cause and change the configuration or pinned version, or contact support.

## Cleanup

```bash
az group delete -n rg-byomca --yes --no-wait
```

The injected account leaves a soft-deleted account + a subnet
serviceAssociationLink. If the delegated subnet later blocks deletion, purge the
soft-deleted account:

```bash
az cognitiveservices account purge -g rg-byomca -n <agentAccountName> -l canadacentral
```

## Credits

Test-bed topology adapted from the private-network agent + BYO-gateway samples
(16 / 19) and the single-tenant data-proxy private-CA design. Functional twin of
the Terraform sample `48-bring-own-model-private-ca` (which uses APIM; this
Bicep version swaps in an nginx container to sidestep the APIM custom-domain
ownership check).
