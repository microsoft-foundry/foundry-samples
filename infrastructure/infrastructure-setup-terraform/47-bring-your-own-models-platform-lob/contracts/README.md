# Contracts

Non-secret published artifacts. Hub-owned roots write files here; LoB-owned roots read them.

## Files

| File | Written by | Consumed by |
|---|---|---|
| `hub-workload.contract.json` | `04-hub-workload/` | `05-spoke-workload-project/` |

## `hub-workload.contract.json` — schema

```json
{
  "$schema": "https://example.com/contoso/hub-workload-contract-v1.json",
  "version": "1",
  "generated_at": "2026-08-27T12:00:00Z",

  "gateway": {
    "private_url": "https://<apim-name>.azure-api.net/inference",
    "audience": "https://cognitiveservices.azure.com",
    "inference_api_version": "2024-10-21"
  },

  "catalog": {
    "version": "1",
    "aliases": [
      { "alias": "gpt-4.1",     "vendor": "microsoft-foundry", "upstream_model": "gpt-4.1" },
      { "alias": "gemini-flash","vendor": "google-gemini",     "upstream_model": "gemini-2.5-flash" },
      { "alias": "llama-3-70b", "vendor": "groq-llama",        "upstream_model": "llama-3.3-70b-versatile" }
    ]
  }
}
```

### Field semantics

- **`version`** — bumped on breaking change to the contract shape. Consumers pin the version they support.
- **`gateway.private_url`** — APIM gateway URL. **The hostname is the public `<apim>.azure-api.net`, not `.privatelink.azure-api.net`**, because APIM StandardV2's managed TLS cert covers only the `.azure-api.net` suffix. Callers inside the VNet still resolve this FQDN to APIM's private endpoint IP via the linked `privatelink.azure-api.net` DNS zone (CNAME chain), so the path stays private from within the VNet. Callers outside the VNet resolve to APIM's public IP; authorization is enforced by APIM's inbound JWT + `oid` allowlist policy.
- **`gateway.audience`** — required by the Foundry `ProjectManagedIdentity` connection body. Must match the APIM `validate-azure-ad-token` policy audience exactly.
- **`gateway.inference_api_version`** — API version the Foundry ApiManagement connection sends to APIM.
- **`catalog.aliases`** — non-secret catalog. `alias` is what appears in the Foundry portal and the request URL path; the routing/branding is stamped by APIM policy.

## Non-goals

- The contract intentionally does **not** carry the JWT `oid` allowlist. That handshake goes the other direction (spoke → hub) via a PR into `06-hub-allowlist/allowlist.auto.tfvars`.
- No secrets (provider keys, subscription keys). Those live in Key Vault and never leave the hub subscription.
- No RG names or subscription IDs. Consumers reference the gateway by its public contract, not by its ARM path.

## Versioning

Consumers pin the contract version. When 04-hub-workload publishes v2, 05-spoke-workload-project continues to consume v1 until it has been updated to the new shape. Both files can coexist during a migration:

```
contracts/
  hub-workload.contract.v1.json
  hub-workload.contract.v2.json    (added when v2 lands)
```
