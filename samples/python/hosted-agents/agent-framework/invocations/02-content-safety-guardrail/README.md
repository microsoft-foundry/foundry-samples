# Content safety guardrail (Invocations protocol)

An [Agent Framework](https://github.com/microsoft/agent-framework) agent hosted on Microsoft Foundry using the **Invocations protocol**, with a Responsible AI (RAI) **content safety guardrail** attached. The guardrail screens the prompts the agent receives and the responses it returns against an RAI policy, so harmful content is filtered according to your safety configuration.

## How it works

The guardrail is **not** code; it's a definition-level setting. The agent declares a `policies` list with a `rai_policy` entry that points to an RAI policy by its full Azure Resource Manager (ARM) resource ID.

The invocations protocol adds one requirement that the [Responses protocol sample](../../responses/16-content-safety-guardrail/) doesn't have. On the Responses protocol the platform knows the message shape, so it can find the text on its own. **The invocations protocol carries a request and response body that your agent defines**, so the platform can't guess which fields hold model text. You tell it, with `invocationsModeration`:

```yaml
policies:
  - type: rai_policy
    raiPolicyName: /subscriptions/<subscription-id>/.../raiPolicies/<policy-name>
    invocationsModeration:
      responseMode: both
      inputContentType: json
      outputContentType: json
      inputPaths:
        - $.message
      outputPaths:
        - $.response
      streamSelectors:
        - eventType: message.delta
          textField: text
```

Those values match this agent's wire shape in [main.py](src/agent-framework-content-safety-guardrail-invocations/main.py):

| Traffic | Shape | Screened by |
| --- | --- | --- |
| Request | `{"message": "...", "stream": false}` | `inputPaths: [$.message]` |
| Buffered response | `{"response": "..."}` | `outputPaths: [$.response]` |
| Streamed response frame | `{"type": "message.delta", "text": "..."}` | `streamSelectors: [{eventType: message.delta, textField: text}]` |

### Settings

| Setting | Required | Description |
| --- | --- | --- |
| `responseMode` | Always | `non_streaming`, `streaming`, or `both`. Declares the response shapes your agent can return. |
| `inputContentType` | Defaults to `json` | `json` or `text`. |
| `outputContentType` | Defaults to `json` | `json` or `text`. |
| `inputPaths` | When `inputContentType` is `json` | Selector expressions locating prompt text in the request body. |
| `outputPaths` | When `responseMode` includes non-streaming and `outputContentType` is `json` | Selector expressions locating text in a buffered response body. |
| `streamSelectors` | When `responseMode` includes streaming and `outputContentType` is `json` | Pairs of `eventType` and `textField` that locate text in streamed events. |

#### Selectors and field names

`inputPaths` and `outputPaths` are **selector expressions**, not a full JSONPath
implementation. They support `$` for the document root, dotted members, array indexes,
and `[*]` wildcards — for example `$.messages[*].content`. Constructs outside that
subset, such as filters or recursive descent, are not supported.

`textField` is **not** a selector: it is the plain **name of a field** on the streamed
frame, so this sample uses `text` rather than `$.text`. A `$`-prefixed value matches
nothing, which silently leaves streamed output unscreened.

`responseMode: both` declares a **capability**, not "input and output". At runtime the platform inspects the response's actual `Content-Type` and runs exactly one output gate. If the response shape contradicts what the agent declared, the request fails closed with `HTTP 502` — an agent can't disable its own guardrail by flipping `Content-Type`.

### Why this sample streams structured frames

The [basic invocations sample](../01-basic/) streams bare text chunks. This one wraps each chunk in a JSON object with a `type`, because `streamSelectors` matches on the `type` field of each frame. If your agent streams bare text, set `outputContentType: text` instead and omit `streamSelectors` — the platform then screens the raw stream.

> [!IMPORTANT]
> `textField` is a **field name** on the event payload, not a path expression. Use `text`, not
> `$.text`. `eventType` and `textField` are exact, case-sensitive matches against top-level
> properties of the frame; you can't select a nested field. A selector that matches nothing
> contributes no text to moderation, so a mistyped `textField` silently leaves streamed output
> unscreened while the agent still reports the policy as attached.

For a conceptual overview, see [Add a content safety guardrail to a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/add-hosted-agent-guardrails).

> [!WARNING]
> Guardrails on this path fail **open**, and there are three independent ways to end up with an
> agent that reports `active` with no filtering:
>
> 1. `raiPolicyName` points at a policy that doesn't exist — including the `<subscription-id>`
>    placeholder that ships in [azure.yaml](azure.yaml).
> 1. The `invocationsModeration` block is missing. The policy attaches, but nothing on the
>    invocations path is screened.
> 1. A path or selector matches nothing — a wrong `inputPaths` entry, or a `textField` that
>    isn't a real field on your frames.
>
> Always run [Verify the guardrail](#verify-the-guardrail) before you rely on this agent's
> content safety.

## Prerequisites

1. An RAI policy created on your Foundry resource, and its full ARM resource ID. To create one, see [Configure guardrails and controls](https://learn.microsoft.com/en-us/azure/foundry/guardrails/how-to-create-guardrails). The ARM resource ID has this form:

   ```text
   /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<account>/raiPolicies/<policy-name>
   ```

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd), then install the AI agent extension and authenticate:

   ```bash
   azd ext install azure.ai.agents
   azd auth login
   ```

   `invocationsModeration` requires **azure.ai.agents 1.0.0-beta.12 or later**. Earlier versions reject the block as an unknown field.

## Configure the guardrail

Set `raiPolicyName` to your RAI policy's full ARM resource ID in [azure.yaml](azure.yaml). Use the full ARM resource ID, not the bare policy name.

If you change the agent's request or response shape, update `inputPaths`, `outputPaths`, and `streamSelectors` to match. `azd` validates the block's structure when it packages the agent, but it can't know your agent's field names — a well-formed block that points at the wrong fields deploys cleanly and screens nothing.

## Option 1: Azure Developer CLI (`azd`)

### Initialize the agent project

No cloning required. Create a new folder and initialize from the manifest:

```bash
mkdir my-guardrail-agent && cd my-guardrail-agent

azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/invocations/02-content-safety-guardrail/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an existing Foundry project, `azd ai agent init` guides you through creating one.

> [!NOTE]
> After init, confirm that `raiPolicyName` in the generated `azure.yaml` holds your policy's full ARM resource ID.

### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployment:

```bash
azd provision
```

> [!IMPORTANT]
> If you provisioned a new Foundry project, it doesn't have your RAI policy yet. Before you deploy, [create an RAI policy](https://learn.microsoft.com/en-us/azure/foundry/guardrails/how-to-create-guardrails) on the provisioned account, then set `raiPolicyName` in the generated `azure.yaml` to that policy's full ARM resource ID.

### Deploy to Foundry

```bash
azd deploy
```

The platform applies the guardrail when it creates the agent version. For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

The Invocations protocol uses a `{"message": "..."}` payload:

```bash
azd ai agent invoke '{"message": "Write a short friendly hello message."}'
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

### Set up the Python virtual environment

- With Python 3.13 or later and [pipx](https://pipx.pypa.io/stable/installation/), install uv outside the project environment, then let uv create and synchronize the locked environment:

  ```bash
  pipx install uv==0.11.7
  uv sync --frozen --python 3.13
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select the `.venv` created by uv.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Set `raiPolicyName` in `azure.yaml` to your policy's full ARM resource ID.
2. Run **Foundry Toolkit: Deploy Hosted Agent** and follow the wizard to deploy.

## Verify the guardrail

The guardrail runs as two independent gates. Check both — a working input gate says nothing about the output gate, which depends on different settings.

### Input stage

Send a prompt that violates your policy. The platform screens it before the agent runs and returns `HTTP 400`:

```json
{
  "error": {
    "code": "content_filter",
    "message": "The request was blocked due to content safety policy violation at input stage. [Request ID: <request-id>]",
    "type": "content_safety_error"
  }
}
```

A prompt that passes the policy returns `HTTP 200` with the agent's response.

To confirm that screening is scoped to the fields you declared, send the same violating text in a field that **isn't** listed in `inputPaths`. It returns `HTTP 200` — the platform screens only what you declared, not the whole request body.

### Output stage

A blocked **buffered** response also returns `HTTP 400`, with a message naming the output stage:

```json
{
  "error": {
    "code": "content_filter",
    "message": "The response was blocked due to content safety policy violation at output stage.",
    "type": "content_safety_error"
  }
}
```

A blocked **streamed** response is different. Response headers are already sent before the agent's output is screened, so the status stays `HTTP 200`. The platform discards the events it was holding, sends a single error event, and ends the stream:

```text
event: error
data: {"type":"error","code":"content_filter","message":"The response was blocked due to content safety policy violation."}
```

Handle this event in your client and treat it as terminal. **A `200` status alone doesn't mean the response passed the policy.**

### If nothing is blocked

Check in this order:

1. `raiPolicyName` names a policy that **actually exists** on your account. List the policies and confirm the final segment matches one of them:

   ```bash
   az rest --method get \
     --url "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<account>/raiPolicies?api-version=2024-10-01" \
     --query "value[].name" -o tsv
   ```

1. The deployed agent version actually carries `invocationsModeration`. Fetch the agent version and confirm the block round-trips.
1. Your policy filters the category and severity you're testing, at the severity threshold you expect. Content that's detected but scores below the threshold isn't blocked.
1. `inputPaths` and `outputPaths` match your agent's real field names, and each `eventType` matches the `type` value your agent sends. `textField` is a bare field name such as `text`, not `$.text`.

## Next steps

- [Add a content safety guardrail to a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/add-hosted-agent-guardrails) — set a guardrail with `azd`, the Python SDK, or REST
- [Guardrails and controls overview](https://learn.microsoft.com/en-us/azure/foundry/guardrails/guardrails-overview) — what guardrails are and the risks they detect
- [Content safety guardrail (Responses protocol)](../../responses/16-content-safety-guardrail/) — the same guardrail on a protocol where the platform knows the message shape
- [Basic invocations agent](../01-basic/) — the agent this sample builds on
- [Manage hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent) — monitor and manage deployed agents
