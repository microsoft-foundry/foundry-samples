# APIM connection with project identity and a secret header

Add a model connection to an **existing** Foundry project whose gateway requires
both project-managed-identity authentication and an APIM subscription key.
The key is a secret HTTP header value, not an asymmetric private key.

This sample creates two project-scoped connections using API `2026-07-01`:

| Connection | Authentication | Contents |
|---|---|---|
| `apim-private-header` (configurable) | `ProjectManagedIdentity` | Gateway URL, audience, model metadata, and a reference to the secret header |
| `secret-headers-<deterministic-suffix>` | `CustomKeys` | `credentials.keys.header0` containing the subscription key and `metadata.secretHeadersFor` identifying the parent |

Both use the same target and `isSharedToAll: false`. The model connection's
`metadata.secretHeaders` is a JSON string mapping `Ocp-Apim-Subscription-Key` to
`{ "connection": "<companion-name>", "key": "header0" }`. It contains no secret
value, and `customHeaders` remains `'{}'`. Referencing the companion resource
creates an ARM dependency so the companion is created before its parent.

For a direct Foundry connection without a gateway or secret header, see
[`foundry-model-connection`](../foundry-model-connection/). For provisioning an
APIM gateway, see [`public-byom-apim`](../public-byom-apim/).

## Prerequisites

- An existing Foundry account and project with managed identity. Deploy into
  that account's resource group using an identity with permission to write
  both connections.
- An existing, reachable APIM gateway with a model API accepting the project's
  identity token and the subscription-key header. Its Entra validation policy
  must accept the supplied audience and project identity.
- Existing backend deployment and gateway-to-backend authentication/RBAC.
  This template does **not** create gateway policies, model deployments, role
  assignments, or network infrastructure.
- Secret-header support enabled in the consuming Foundry environment. Creating
  these ARM resources alone does not enable runtime or flighted UI support
  (`admin_connected_secret_headers`).
- Azure CLI and Bicep, and API `2026-07-01` availability in the target environment.

Bicep 0.41.2 reports `BCP081` because its bundled type definitions do not include
the `2026-07-01` connection API. Compilation still succeeds, but cannot validate
that API's resource properties. This version matches the exported connection
example; deployment and runtime verification are still required.

The endpoint in the parameter file is an AzureCloud placeholder. Supply the
actual gateway URL and audience for your environment; no cloud host is inferred.
The gateway application audience is independent of the subscription key and is
not necessarily the Cognitive Services audience.

## Deploy

Copy `samples/parameters.json` to an untracked local file and replace the
placeholders. Keep `subscriptionKey` as an ARM Key Vault reference rather than
placing the key in a committed file or command line. The vault must allow ARM
template deployment (`enabledForTemplateDeployment`), and the deploying identity
must have `Microsoft.KeyVault/vaults/deploy/action` on it. This template does not
change vault settings or permissions.

```bash
az login
az account set --subscription "<source-subscription>"
az bicep build --file main.bicep --outfile azuredeploy.json

az deployment group create \
  --resource-group "<source-resource-group>" \
  --name apim-secret-headers \
  --template-file main.bicep \
  --parameters @parameters.local.json
```

`subscriptionKey` is a required `@secure()` parameter with no default. It flows
only into the companion's `credentials.keys.header0`; it is not emitted in
outputs or model metadata. Do not print connection secrets, enable verbose
payload logging, or commit populated parameter files. Normal ARM exports/GETs
can omit credentials: an exported companion without `credentials.keys` is not
a complete redeployable secret configuration.

The sample uses a static model list. Set `modelDeploymentName` to the gateway's
deployment name and `modelName`/`modelVersion` to its actual catalog metadata.
The endpoint is deployment-path based (`deploymentInPath: 'true'`), matching
the APIM example; it is not the `/openai/v1` body-model configuration used by
the direct Foundry sample.

## Verify and use

Verify that both connections exist, have matching targets and project scope,
and that the parent references the companion's exact name and `header0`.
Do not retrieve the secret just to verify the relationship.

Use the existing prompt-agent Responses script with your project endpoint:

```bash
python ../public-byom-apim/samples/create-agent.py \
  --endpoint "<project-endpoint>" \
  --model "apim-private-header/<gateway-deployment-name>" \
  --agent-name apim-secret-header-sample-agent
```

See the [shared agent instructions](../public-byom-apim/samples/create-agent.py)
for Python dependencies. Invocation incurs model usage charges and creates
an agent version and conversation. A successful response verifies runtime
resolution; Bicep compilation or ARM deployment alone does not.

If authentication fails, check **both** the gateway's Entra policy/audience and
its subscription-key requirement. A correct PMI token does not substitute for
a required key, and a correct key does not substitute for a valid identity.

## CI deployment fixture

The root `main.bicepparam` selects `tests/deploy.bicep` for the repository's
ephemeral deployment check. It creates a disposable account and project, then
deploys the **actual** `main.bicep` with a non-secret fixture key and a reserved
`.invalid` gateway hostname. It verifies ARM creation of the two connections,
not APIM authentication or inference; no real gateway or model is deployed.
The pipeline owns resource-group cleanup. Do not use this parameter file for
an existing project: follow the deployment instructions above instead.

## Updates and cleanup

The companion name is deterministic for the project and parent name. Redeploying
with a new key updates that companion in place, affecting the existing parent
immediately, even if a subsequent parent update fails. This minimal template
does not implement the UX's fresh-companion replacement behavior. For isolated
testing or replacement, deploy with a new parent connection name, verify it,
and retire the old pair only after checking consumers.

Delete the model connection before its companion, and only after ensuring no
other connection references it. Outputs include both resource IDs for scoped
cleanup, never the key. Separately remove any test agents/conversations you
created. Do not delete the existing project, gateway, Key Vault secret, or
resource group. Deleting a deployment record does not delete its resources.
