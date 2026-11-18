# Connected model with the Responses API

Use an existing connected model through a Microsoft Foundry prompt agent, with
the connection configured to send **Responses API requests to the upstream
provider**.

Responses API support extends the connected-model path beyond Chat
Completions-only routing. It lets you use compatible models that require
Responses or are not compatible with the previous Chat Completions path.
Existing Chat Completions connections do not need to be changed.

This sample creates a uniquely named temporary prompt agent, references the model
as `connection-name/model-name`, invokes the agent, prints its answer, and deletes
the temporary agent version even if inference fails. The Python script does not
create, modify, or delete your connection or upstream model. An optional
connection-creation example is included below.

## Prerequisites

- Python 3.10 or later.
- Azure CLI installed and signed in with `az login`.
- A Foundry project where your identity can create, invoke, and delete prompt
  agents and use the connected model.
- The connected-model Responses API preview/feature flight enabled for your
  environment. If the setting below is missing, contact your feature owner.
- A connection to an OpenAI-compatible endpoint that supports the Responses API,
  with a model/alias registered on that connection. Use an existing connection or
  create one with the example below.

## Configure the connection

In your Foundry project's connection management experience, create or edit the
model connection:

1. Use the provider's versionless v1 base URL, not a complete `/responses` or
   `/chat/completions` operation URL.
2. Select **Use the Responses API for upstream requests**.
3. Configure the provider's authentication and save the connection with the
   model/alias you want to use.

Upstream credentials stay in the Foundry connection. Do not copy the provider's
API key into the Python script or commit it to source control.

### Optional: create a connection with Bicep

Use the existing
[ModelGateway connection template](../../../../infrastructure/infrastructure-setup-bicep/01-connections/model-gateway/README.md#upstream-responses-api-connection)
and its
[Responses parameter file](../../../../infrastructure/infrastructure-setup-bicep/01-connections/model-gateway/samples/parameters-responses.json).
This creates a project-scoped connection without duplicating connection
management in the Python script.

Edit the parameter file with your Foundry project resource ID, connection name,
and upstream deployment name. The example uses
`https://<upstream-resource-name>.openai.azure.com/openai/v1` as `targetUrl` and
sets `upstreamSurface` to `responses`. Do not append `/responses`,
`/chat/completions`, or a deployment path to the URL.

Follow the deployment instructions in the template README. You need permission
to write connections on the Foundry project and must deploy into that project's
resource group and subscription. Pass the upstream API key as the secure
deployment parameter, not in the parameter file.

For the example names, set
`CONNECTED_MODEL_CONNECTION_NAME=my-model-connection` and
`CONNECTED_MODEL_NAME=gpt-5-mini` in `.env`. The connection persists after the
Python script finishes; delete it separately when no longer needed.

### Confirm the upstream API selection

Calling a Foundry agent with `responses.create()` is not, by itself, proof that
the model provider receives a Responses request. Foundry agents already expose
the Responses API to callers; **the connection setting selects the upstream API**.

The saved connection metadata should contain `upstreamSurface: responses`.
If you have permission to read the connection's Azure resource, you can inspect
only that setting:

```shell
az resource show --ids "<connection-resource-id>" --query "properties.metadata.upstreamSurface" --output tsv
```

The expected value is `responses`. This checks the saved configuration, not a
live upstream request. To verify the actual upstream route, inspect your
provider/gateway request logs, where available.

## Setup

Run these commands from this sample directory.

```shell
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS/Linux
source .venv/bin/activate
```

Install the dependencies:

```shell
python -m pip install -r requirements.txt
az login
```

Copy `.env-template` to `.env` and set:

| Variable | Value |
| --- | --- |
| `AZURE_AI_PROJECT_ENDPOINT` | The project endpoint copied from Foundry. |
| `CONNECTED_MODEL_CONNECTION_NAME` | The saved connection name, for example `my-model-connection`. |
| `CONNECTED_MODEL_NAME` | The model name/alias saved on the connection, for example `my-model-alias`. |

For these example names, the agent's model reference is
`my-model-connection/my-model-alias`. If the gateway alias is
`provider/my-model-alias`, keep that entire alias in `CONNECTED_MODEL_NAME`; the
reference becomes `my-model-connection/provider/my-model-alias`.

Use the registered model name/alias, not its display name, the connection's
resource ID, or an underlying backend model name that was not registered.
The script loads `.env` beside the script without overriding environment
variables already set in your shell.

## Run

```shell
python connected-model-responses.py
```

Expected output has this shape; generated names, versions, and answers vary:

```text
Connected model: my-model-connection/my-model-alias
Temporary agent: connected-model-responses-<unique-suffix> (version <version>)
Response output: <the model's answer>
Temporary agent version deleted.
```

The script does not add model-specific options such as reasoning effort. Its
purpose is to demonstrate connected-model Responses routing, not parameter
support for a particular model.

## Troubleshooting and cleanup

- **Missing setting:** fill in all three variables in `.env` or your environment.
- **Model not found:** check the connection name and the exact registered
  model/alias. For an AI Gateway connection, ensure the alias is included in the
  connection's saved model selection.
- **Upstream errors:** confirm the provider supports Responses for the selected
  model, the connection's authentication is valid, and the saved upstream
  selection is `responses`.
- **Access denied:** check both your Foundry permissions and the connection's
  access to the upstream endpoint.
- **Cleanup failure or interrupted execution:** the agent name and version are
  printed before inference. Delete that temporary agent version in Foundry.
  The existing connection and upstream model are not sample-owned resources.

Running the sample creates an agent version and makes a live inference request,
which may incur charges.
