# 48 — Hub → gateway → spoke: a private-CA model gateway behind private DNS

This sample shows how a **VNet-injected Foundry project in a workload spoke**
calls a model through an **enterprise gateway in a platform hub**, where the
gateway:

- is reachable only on a **hostname that resolves through private DNS**
  (`gateway.byomca.internal` by default — not publicly resolvable), and
- presents a TLS certificate issued by a **private (non-public) root CA**.

Foundry trusts the gateway because the private root CA is registered on the
Foundry account with `trustedCertificateSources`. Everything on the inference
path — data proxy, gateway, APIM, and model — stays private.

## Architecture

```text
 Workload spoke VNet (172.24.0.0/16)            Platform hub VNet (172.25.0.0/16)
┌──────────────────────────────────────┐       ┌───────────────────────────────────────────────┐
│ Foundry agent account (injected)     │       │ Application Gateway (private IP 172.25.2.10)  │
│  └ project ─ connection "gateway"    │       │   serves leaf + chain from private root CA    │
│      target https://gateway.<zone>/  │  VNet │                 │                             │
│ snet-agent: data proxy ──────────────┼─peer──┼──▶ TLS (validated against registered root CA) │
│ snet-pe:   Foundry + BYO store PEs   │       │                 ▼                             │
│            (Storage, Cosmos, Search) │       │ APIM Standard v2 (private endpoint, inbound)  │
└──────────────────────────────────────┘       │   validate Entra token (project oid)          │
                                               │                 │ VNet integration (outbound) │
         Private DNS zones (linked to          │                 ▼                             │
         BOTH VNets):                          │ Foundry model account (PNA disabled, PE)      │
           <zone>  gateway → 172.25.2.10       │                                               │
           privatelink.azure-api.net           │ Key Vault: gateway PFX + root CA PEM secret   │
           privatelink.openai/cognitive/...    └───────────────────────────────────────────────┘
```

### Request path

1. The project's `ApiManagement` connection targets
   `https://gateway.<zone>/inference`.
2. The **data proxy** (provisioned in the spoke's delegated `snet-agent` by
   network injection) resolves `gateway.<zone>` through the spoke-linked private
   DNS zone to the hub Application Gateway's private IP and connects over VNet
   peering.
3. Application Gateway presents the **gateway leaf + private root CA chain**.
   The data proxy validates it against the trust bundle loaded from
   `trustedCertificateSources`.
4. Application Gateway forwards to APIM's default hostname, which resolves to
   the APIM private endpoint through the hub-linked `privatelink.azure-api.net`
   zone.
5. APIM validates the caller's Entra token (tenant, audience, and the project
   managed identity's `oid`), then calls the **private** model account through
   its outbound VNet integration and the model's private endpoint.

### Why Application Gateway fronts APIM

APIM validates custom-hostname ownership against **publicly resolvable DNS**.
Binding an internal-only name such as `gateway.byomca.internal` to APIM fails
with `CustomHostnameOwnershipCheckFailed`, even with a CNAME in a VNet-linked
private DNS zone. Application Gateway has no such check, so it serves the
private-CA certificate on the internal hostname, and APIM keeps its default
hostname behind a private endpoint.

## What gets deployed

| Location | Resources |
|---|---|
| **Spoke VNet** | Delegated `snet-agent` (`Microsoft.App/environments`); `snet-pe` with private endpoints for the Foundry agent account and the BYO agent stores |
| **Hub VNet** | `snet-appgw` (Application Gateway Standard_v2); `snet-pe` with private endpoints for APIM and the model account; `snet-apim` delegated to `Microsoft.Web/serverFarms` with an NSG for APIM outbound VNet integration |
| **Peering** | Hub ↔ spoke, bidirectional |
| **Private DNS** | `privatelink` zones for Cognitive Services, OpenAI, AI Services, APIM, Blob, Cosmos DB, AI Search, plus the gateway zone — **all linked to both VNets** |
| **Foundry** | Network-injected agent account with `trustedCertificateSources`, project, BYO Storage / Cosmos DB / AI Search connections, project capability host, `gateway` connection |
| **Model** | Foundry model account (public network access disabled) with one deployment |
| **PKI + Key Vault** | Generated private root CA and gateway leaf (`pki.tf`); gateway PFX imported as a Key Vault certificate; root CA public PEM stored as a Key Vault **secret** |
| **Observability** | Log Analytics + Application Insights (APIM diagnostics) |

## Certificate trust

Three pieces must line up:

| Piece | In this sample |
|---|---|
| Gateway leaf certificate (SAN = gateway FQDN), signed by the private CA | `tls_locally_signed_cert.gateway`, served by Application Gateway as leaf + chain |
| Root CA public certificate (`CA:TRUE`, no private key) | Key Vault secret `private-root-ca-pem` (`application/x-pem-file`) |
| Trust registration on the Foundry account | `properties.trustedCertificateSources` (account API `2026-11-15-preview`) |

The registration uses the public-preview contract with a **pinned** secret
version:

```json
"trustedCertificateSources": [
  {
    "type": "AzureKeyVault",
    "resourceId": "<key-vault-resource-id>",
    "certificateBundleReferences": [
      { "secretName": "private-root-ca-pem", "secretVersion": "<version>" }
    ]
  }
]
```

Requirements:

- **Register the root CA, not the gateway leaf.** Each reference resolves to a
  PEM bundle of CA certificates.
- **Store it as a Key Vault secret**, not a certificate object. The resolver
  reads the secret; a certificate object returns a PKCS#12 bundle.
- **Grant the Foundry account identity `Key Vault Secrets User`.**
- **Trust loads on a capability-host lifecycle event.** The capability host is
  created only after the account identity can read the secret, and Terraform
  recreates it whenever the registered trust sources change.

The sample generates the PKI with the `tls` provider and packages the PFX with
the community `chilicat/pkcs12` provider for convenience, so **private keys are
stored in Terraform state**. Use a protected remote backend, or issue the
gateway certificate from your enterprise PKI in production.

## Prerequisites

- Terraform `>= 1.10, < 2.0` and an authenticated Azure CLI session.
- Permission to create resources **and role assignments** in the target scope
  (for example Owner, or Contributor plus Role Based Access Control
  Administrator).
- A region where your model is offered with `GlobalStandard`. Base `gpt-4.1`
  `GlobalStandard` is not offered in `canadacentral`; set
  `foundry_model_name`, `foundry_model_version`, and (for reasoning models such
  as `gpt-5.1`) `inference_api_version = "2025-04-01-preview"`.
- Avoid `uksouth`; trusted-certificate registration has a known issue there.

## Deploy

Run from the `code` directory:

```bash
cp terraform.tfvars.example terraform.tfvars   # set subscription, tenant, email
terraform init
terraform plan -out="tfplan"
terraform apply tfplan
```

On PowerShell, use `Copy-Item terraform.tfvars.example terraform.tfvars`.
Do not commit `terraform.tfvars`, state, or saved plans.

To deploy into an existing resource group, set `existing_resource_group_name`.
Terraform reads the group without managing it, so cleanup preserves it.

## Test

The Foundry account is private by default. To test from your workstation
without a VPN or jump box, allow-list your **public egress IP** (Entra ID
authentication is still required):

```hcl
foundry_allowed_ip_ranges = ["203.0.113.25"]
```

This only affects how you reach Foundry; the inference path stays private.
Then, in the Foundry portal, open the project and send a message using the
connected model `gateway/<model>` (for example `gateway/gpt-5.1`).

| Result | Meaning |
|---|---|
| Model responds | DNS, peering, gateway TLS trust, APIM, and the private model path all work |
| `The SSL connection could not be established` with `targetService` = gateway FQDN | The data proxy reached the gateway but rejected its chain. Check the items under **Troubleshooting** |
| `401` from the gateway | APIM rejected the token; the caller's `oid` is not the project identity |
| `404` from the gateway | TLS succeeded; the request used an operation APIM does not expose (this sample exposes chat completions) |

## Certificate rotation

- **Gateway leaf, same CA:** the leaf is re-issued when it nears expiry
  (`early_renewal_hours`) and imported as a new Key Vault certificate version.
  Terraform tags Application Gateway with that version so it serves the new
  leaf immediately instead of waiting for its periodic Key Vault refresh. No
  Foundry change or capability-host recreate is required.
- **New or additional root CA:** updating the root creates a new secret
  version. Terraform updates `trustedCertificateSources` and recreates the
  capability host so the data proxy reloads trust. For zero downtime, first
  register the new CA alongside the old one (add a second
  `certificateBundleReferences` entry to `local.trusted_certificate_sources`),
  then switch the gateway to a leaf issued by the new CA.

## Troubleshooting

| Check | Fix |
|---|---|
| Is the **root CA**, not the leaf, registered? | Point `trustedCertificateSources` at the CA PEM secret |
| Is it a Key Vault **secret** with `application/x-pem-file`? | Re-upload as a secret |
| Does the account identity have **Key Vault Secrets User**? | Grant it, wait for propagation |
| Was the capability host recreated after the trust change? | `terraform apply -replace='azapi_resource.project_capability_host'` |
| Does the gateway serve the **full chain** (leaf + CA)? | Rebuild the PFX with the CA chain |
| Does the leaf SAN match the connection hostname? | Re-issue the leaf with the correct SAN |
| Does `gateway.<zone>` resolve from the **spoke**? | Link the gateway zone to the spoke VNet |
| Does the persisted account show `trustedCertificateSources`? | `az rest --method get --url "<account-id>?api-version=2026-11-15-preview" --query properties.trustedCertificateSources` |

## Notes

- **Application Gateway public IP.** Application Gateway v2 requires a public
  frontend IP unless the subscription registers
  `EnableApplicationGatewayNetworkIsolation`. The sample creates one but
  attaches **no listener** to it.
- **APIM public network access** stays enabled by default so creation ordering
  is simple; the gateway reaches APIM only through its private endpoint. Set
  `apim_public_network_access_enabled = false` once the private endpoint exists.
- **Key Vault** keeps public network access so the deploying client and
  Application Gateway can reach it; access is controlled by Entra ID RBAC.
- **Cross-subscription hub/spoke.** This sample keeps both VNets in one
  subscription. See [sample 47](../47-bring-your-own-models-platform-lob/README.md)
  for the platform/workload split across subscriptions.

## Cleanup

```bash
terraform destroy
```

The injected account leaves a soft-deleted account and a subnet
service association link; a destroy-time purge action clears it (after a
cooldown) so the delegated subnet can be removed.
