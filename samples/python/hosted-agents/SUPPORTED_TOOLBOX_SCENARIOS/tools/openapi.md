# OpenAPI

Expose a REST API to the agent from its **OpenAPI 3.x spec**. The spec is embedded **inline** in the
toolbox tool entry. Each operation becomes a tool named `{name}___{operationId}`, so every operation
needs an `operationId`.

> This page covers only the **OpenAPI tool** parts — the inline spec and the auth fields. For the
shared toolbox flow (create → publish → copy the endpoint), see the
[README](../README.md#create-the-toolbox).


## Auth modes

The OpenAPI tool supports three authentication types. Pick the one that matches how the target API
authenticates callers.

| Auth type | `auth` object | Connection? | Use when |
|------|---------------|-------------|----------|
| Anonymous | `{ type: anonymous }` | No | Public API, no auth |
| API key / Bearer | `{ type: project_connection, security_scheme: { project_connection_id: <conn> } }` | Yes (`CustomKeys`; key name must match the spec's `securityScheme`) | Non-Microsoft API with a key or Bearer token |
| Managed identity | `{ type: managed_identity, security_scheme: { audience: <resource-uri> } }` | No (authorize the identity on the target) | Target accepts Microsoft Entra ID tokens |

Only **Managed identity** needs the extra Azure step in
[Configure managed-identity authorization](#configure-managed-identity-authorization-azure). It
authorizes two different ways depending on the target:

| Target | Audience | Authorize by |
|--------|----------|--------------|
| **RBAC — Azure resource with RBAC** (Storage, AI Search, Key Vault, ARM, …) | the service's well-known resource URI (e.g. `https://search.azure.com`, `https://storage.azure.com`) | granting the Foundry-managed identity an **RBAC role** (Reader or higher) on the resource |
| **App — API behind an Entra app registration** (Azure Functions / App Service Easy Auth, APIM with OAuth, custom Entra-app API) | the app registration's **Application ID URI** (`api://<client-id>`, from **Expose an API**) | **allow-listing** the identity's client ID on the server (*not* RBAC) |


## Create the tool & toolbox

### Foundry Toolkit in VS Code

1. Follow the README's [Create the toolbox](../README.md#create-the-toolbox) steps to open the **Select a tool** dialog, switch to the **Custom** tab, and select **OpenAPI tool**. The **Create an OpenAPI tool** dialog opens.
2. **Name** and **Description** are required for every auth method (**Description** tells the model
   when to call the tool). Then pick an **Authentication method**, fill its fields, and click **Create
   tool**.

   **1. Anonymous** — no auth fields; the schema needs no security block.

   | Field | Value |
   |-------|-------|
   | **Authentication method** | `Anonymous` |
   | **OpenAPI 3.0+ schema** | The OpenAPI 3.x spec (every operation needs an `operationId`). No `securitySchemes`/`security` needed. |

   ```yaml
   openapi: "3.0.0"
   info: { title: Cat Facts, version: "1.0.0" }
   servers: [{ url: https://catfact.ninja }]
   paths:
     /fact:
       get:
         operationId: getFact
         responses: { "200": { description: ok } }
   ```

   **2. Connection** (API key / Bearer) — pick a connection, enter the header credential, and the schema
   **must** declare the matching security scheme.

   | Field | Value |
   |-------|-------|
   | **Authentication method** | `Connection` |
   | **Connection** | Pick an existing `CustomKeys` connection, or **Add a new connection**. |
   | **Credentials** | Header name `:` value — e.g. `x-api-key` : `<api-key>`, or `Authorization` : `Bearer <token>`. The **key** must match the scheme's `name` in the schema below. |
   | **OpenAPI 3.0+ schema** | The spec **plus** a `securitySchemes` entry (type `apiKey`) and a top-level `security` list referencing it. Use exactly one scheme per tool. |

   ```yaml
   openapi: "3.0.0"
   info: { title: Weather, version: "1.0.0" }
   servers: [{ url: https://api.example.com }]
   paths:
     /weather:
       get:
         operationId: getWeather
         responses: { "200": { description: ok } }
   components:
     securitySchemes:
       apiKeyHeader:            # for a Bearer token, name it e.g. bearerAuth
         type: apiKey
         name: x-api-key        # for Bearer, use: Authorization  (must match the connection key)
         in: header
   security:
     - apiKeyHeader: []
   ```

   **3. Managed Identity** — add an **Audience**; the schema needs no security block (the Entra token is
   attached automatically).

   | Field | Value |
   |-------|-------|
   | **Authentication method** | `Managed Identity` |
   | **Audience** | The target's resource identifier — a service resource URI for *RBAC* (e.g. `https://search.azure.com`), or `api://<client-id>` for *App*. |
   | **OpenAPI 3.0+ schema** | Same plain spec as Anonymous — no `securitySchemes`/`security` needed. |

   Then complete [Configure managed-identity authorization](#configure-managed-identity-authorization-azure).

### `azd` CLI

Create the connection (API key only), then create the toolbox one of two ways:

- **Way A — standalone toolbox** (`azd ai toolbox create`): builds the toolbox on its own. Best for
  testing, or when the toolbox is shared across agents.
- **Way B — toolbox in an agent project** (`azure.yaml` + `azd deploy`): declares the toolbox next to
  your agent and ships them together. Best when the toolbox belongs to one agent project.

#### 1. Create the connection (API key / Bearer only)

```bash
azd ai connection create myapiconn \
  --kind remote-tool \
  --target https://api.example.com \
  --auth-type custom-keys \
  --custom-key "x-api-key=<api-key>" \
  --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
```

The inline `auth` block below is where you pick the auth type — the same block works for both ways:

```yaml
# --- pick ONE auth block ---
# Anonymous
auth:
  type: anonymous

# API key / Bearer (spec must also include security + securitySchemes; scheme name = connection key)
# auth:
#   type: project_connection
#   security_scheme:
#     project_connection_id: myapiconn

# Managed identity, RBAC (audience = the service's resource URI)
# auth:
#   type: managed_identity
#   security_scheme:
#     audience: https://search.azure.com

# Managed identity, App (audience = api://<client-id>)
# auth:
#   type: managed_identity
#   security_scheme:
#     audience: api://<client-id>
```

#### Way A — standalone toolbox (`toolbox.yaml`)

1. Write `toolbox.yaml` with the OpenAPI spec and one `auth` block:

   ```yaml
   # toolbox.yaml
   description: openapi toolbox
   tools:
     - type: openapi
       openapi:
         name: catfacts
         spec:
           openapi: "3.0.0"
           info: { title: Cat Facts, version: "1.0.0" }
           servers: [{ url: https://catfact.ninja }]
           paths:
             /fact:
               get:
                 operationId: getFact
                 responses: { "200": { description: ok } }
         auth:
           type: anonymous   # or API key / Managed identity — see the auth blocks above
   ```

2. Create the toolbox:

   ```bash
   azd ai toolbox create agent-tools --from-file ./toolbox.yaml --project-endpoint "$FOUNDRY_PROJECT_ENDPOINT"
   ```

3. Copy the versioned MCP endpoint it prints into your agent's `TOOLBOX_ENDPOINT`:

   ```bash
   azd env set TOOLBOX_ENDPOINT "https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/agent-tools/versions/1/mcp?api-version=v1"
   ```

#### Way B — toolbox in an agent project (`azure.yaml`)

1. Declare the toolbox and agent together in `azure.yaml` (uses the same `auth` blocks above):

   ```yaml
   # azure.yaml
   requiredVersions:
     azd: '>=1.34.2'
     extensions:
       azure.ai.agents: '>=1.0.0-beta.19'
   name: my-agent-project
   services:
     agent-tools:
       host: azure.ai.toolbox
       tools:
         - type: openapi
           openapi:
             name: catfacts
             spec:
               openapi: "3.0.0"
               info: { title: Cat Facts, version: "1.0.0" }
               servers: [{ url: https://catfact.ninja }]
               paths:
                 /fact:
                   get:
                     operationId: getFact
                     responses: { "200": { description: ok } }
             auth:
               type: anonymous   # or API key / Managed identity — see the auth blocks above
     my-agent:
       host: azure.ai.agent
       uses:
         - agent-tools
       env:
         TOOLBOX_NAME: agent-tools
   ```

2. Deploy the toolbox (and agent) — no `TOOLBOX_ENDPOINT` needed, the agent resolves it from `TOOLBOX_NAME`:

   ```bash
   azd deploy agent-tools
   ```


## Configure managed-identity authorization (Azure)

*Only the **Managed identity** auth type needs this. **Anonymous** and **API key / Bearer** are done
after [Create the tool & toolbox](#create-the-tool--toolbox).*

The agent calls the target with the **Foundry project's managed identity** — no stored key. For it to
work, two things must match:

- **Audience** — the resource identifier of the *target*, set on the tool. (It's **not** your Foundry
  endpoint. A mismatch is the usual cause of a `401` — decode the token at [jwt.ms](https://jwt.ms)
  and check the `aud` claim.)
- **Authorization** — the target must let this identity in. How you do that depends on the target:
  **[RBAC](#step-2a--rbac-azure-resource-with-rbac)** for an Azure resource, or
  **[App](#step-2b--app-your-own-api-behind-an-entra-app)** for your own API (Azure Functions, App
  Service, APIM…).

### Step 1 — get the identity's IDs

The agent calls the target with the **Foundry project's system-assigned managed identity** (minted
per project — *not* the Foundry account identity). Note two IDs: the **object ID** (used everywhere)
and the **application (client) ID** (used only for *App*).

**CLI:**

```bash
SUB=<sub>; RG=<rg>; ACCOUNT=<foundry-account>; PROJECT=<project>
# Object ID = the PROJECT's system-assigned principal (read from the project ARM resource)
PRINCIPAL=$(az rest --method get \
  --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.CognitiveServices/accounts/$ACCOUNT/projects/$PROJECT?api-version=2025-06-01" \
  --query "identity.principalId" -o tsv)                        # object ID
APP_ID=$(az ad sp show --id "$PRINCIPAL" --query appId -o tsv)  # client ID (for *App* only)
```

**Portal:** **Foundry project** → **Identity** → copy the **Object (principal) ID**. For the client
ID, search that object ID in **Microsoft Entra ID** → **Overview** → **Application ID**.

### Step 2A — RBAC (Azure resource with RBAC)

For an Azure service that uses **RBAC** (Storage, AI Search, Key Vault, ARM…): set the audience to
the service's resource URI and grant the identity a role. No app registration needed.

| Target | Audience | Example role |
|---|---|---|
| Azure AI Search | `https://search.azure.com` | Search Index Data Reader |
| Azure Storage (Blob) | `https://storage.azure.com` | Storage Blob Data Reader |
| Azure Key Vault | `https://vault.azure.net` | Key Vault Secrets User |
| Azure Resource Manager | `https://management.azure.com` | Reader |

**Portal:** target resource → **Access control (IAM)** → **Add role assignment** → pick the role →
**Managed identity** → the **Foundry project** identity → **Review + assign**.

**CLI:**

```bash
az role assignment create --assignee "$PRINCIPAL" \
  --role "Search Index Data Reader" \
  --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Search/searchServices/<search-service>"
```

### Step 2B — App (your own API behind an Entra app)

For **your own API** (Azure Functions / App Service **Easy Auth**, or APIM with OAuth), the server
checks the token itself. It accepts the call only when **all three** match:

1. **Audience** = the app registration's **Application ID URI** (`api://<client-id>`, from **Expose
   an API**) — set this as the tool's audience.
2. **Issuer** = `https://login.microsoftonline.com/<tenant-id>/v2.0`.
3. **Allowed application** = the Foundry identity's **client ID** on the server's allow-list. *This is
   the step people forget* — its absence is the usual cause of a `401`.

**Portal (Azure Functions / App Service Easy Auth):** in the app registration, open **Expose an API**
and set **Application ID URI** to `api://<client-id>`. Then, in the app, open **Authentication** →
**Add identity provider** → **Microsoft**. Set **Allowed token audiences** to that exact Application ID
URI. Set **Client application requirement** → *specific client applications* → add the identity's
**client ID**; **Identity requirement** → *specific identities* → add its **object ID**;
**Unauthenticated requests** → **HTTP 401**.

**CLI (Azure Functions / App Service Easy Auth):**

```bash
SUB=<sub>; RG=<app-rg>; APP=<app-name>
TENANT=$(az account show --query tenantId -o tsv)
FUNC_APP_ID=<app-registration-client-id>   # the app protecting your API
# $APP_ID and $PRINCIPAL from Step 1 (the Foundry identity)

cat > authv2.json <<EOF
{ "properties": {
  "platform": { "enabled": true },
  "globalValidation": { "requireAuthentication": true, "unauthenticatedClientAction": "Return401" },
  "identityProviders": { "azureActiveDirectory": {
    "enabled": true,
    "registration": { "openIdIssuer": "https://login.microsoftonline.com/$TENANT/v2.0", "clientId": "$FUNC_APP_ID" },
    "validation": {
      "allowedAudiences": [ "api://$FUNC_APP_ID" ],
      "defaultAuthorizationPolicy": {
        "allowedApplications": [ "$APP_ID" ],
        "allowedPrincipals": { "identities": [ "$PRINCIPAL" ] }
      }
    }
  }}
}}
EOF

az rest --method put \
  --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP/config/authsettingsV2?api-version=2022-03-01" \
  --body @authv2.json
```

**APIM with OAuth:** add a `validate-jwt` policy that checks `aud` = `api://<client-id>`, the issuer,
and a `required-claims` match on `appid`/`azp` = the Foundry identity's client ID. Use the same
`api://<client-id>` as the tool audience.

> **Security:** if you delete the app, also delete its app registration — an orphaned Application ID
> URI can be re-claimed by another app and used to obtain tokens your identity trusts.


## Notes

- Every operation needs an `operationId` (letters, `-`, `_` only).
- Multiple `openapi` entries in one toolbox are allowed only if each spec has a distinct
  `info.title`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| API key not sent | Spec missing `securitySchemes` / `security`, or scheme name ≠ connection key | Add both sections; make the scheme `name` match the connection key. |
| `401`, role assigned (RBAC) | Audience doesn't match the target's resource identifier | Set `audience` to the service's resource URI; decode the token at [jwt.ms](https://jwt.ms) and check `aud`. |
| `401` from your own server (App) | Audience/issuer mismatch, or the identity's client ID isn't allow-listed | Set `audience` to `api://<client-id>`, confirm the v2 issuer, and add the identity's **client ID** to the server's allow-list. |
| `403` (token accepted) | Identity lacks permission | Grant the required **RBAC role** (RBAC), or confirm the correct client ID / object ID is allow-listed (App). |
| Token rejected by target | Target doesn't accept Microsoft Entra ID tokens | Use API key / Bearer auth instead. |

## References

- [OpenAPI tool documentation](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/openapi)
- [Secure OpenAPI tool calls from Foundry Agent Service (App Service / Azure Functions)](https://learn.microsoft.com/azure/app-service/configure-authentication-ai-foundry-openapi-tool)
