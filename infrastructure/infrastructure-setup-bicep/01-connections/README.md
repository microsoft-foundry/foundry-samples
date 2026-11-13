# Connections Bicep Examples

Connections enable your AI applications to access tools and objects managed elsewhere in or outside of Azure.

This folder provides a set of examples for the most common connection categories.

## BYOM golden-path variants (non-VNet)

For the end-to-end **bring-your-own-model** golden path, these connections map to the
variants in [`../golden-path`](../golden-path/README.md):

| BYOM variant | Connection sample |
|--------------|-------------------|
| 1. APIM gateway + Foundry model in another project | [`public-byom-apim`](./public-byom-apim/) (creates the APIM gateway too) |
| 2. No separate gateway — model in another Foundry / Azure OpenAI account | [`model-gateway`](./model-gateway/) (`samples/parameters-foundryazureai.json`, `parameters-foundryopenai.json`, or `parameters-foundryanthropic.json`) — a **ModelGateway** connection pointed at the other account's inference endpoint |
| 3. Third-party model provider | [`model-gateway`](./model-gateway/) (`samples/parameters-openai.json`) |
| 4. BYOM + BYOG (your own 3P gateway) | [`model-gateway`](./model-gateway/) (custom `targetUrl`) |

> [!IMPORTANT]
> BYOM `<connection>/<model>` resolution works **only** for *gateway-category* connections —
> `ApiManagement` (variant 1) or `ModelGateway` (variants 2–4). A plain
> [`connection-azure-openai.bicep`](./connection-azure-openai.bicep) (`AzureOpenAI`) or
> [`connection-foundry.bicep`](./connection-foundry.bicep) (`CognitiveService`) connection is
> **not** resolvable by a prompt agent as `<connection>/<model>` — it fails with
> `Connection '<name>' not found`. Those connection types are for classic SDK / data-plane
> use, not gateway-routed agent inference.

### Using the model from an agent

After creating any of these connections, an agent references the model as
`<connectionName>/<modelName>`.

> [!IMPORTANT]
> A BYOM model works **only** with a *prompt agent* invoked through the **Responses API**.
> The classic Assistants API (`create_agent` + threads + runs) cannot resolve
> `<connection>/<model>` and fails with `Failed to resolve model info`.

The connection-agnostic script
[`public-byom-apim/samples/create-agent.py`](./public-byom-apim/samples/create-agent.py)
works for every variant — pass `--model <connectionName>/<modelName>`.
