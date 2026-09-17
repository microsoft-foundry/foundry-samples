# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) hosted agent that performs data-plane operations on **two Azure services — Blob Storage and Service Bus —** using its **per-agent Microsoft Entra identity** (no connection strings, no shared keys).

The sample covers two services on purpose: Storage and Service Bus both use **standard Azure (ARM) RBAC** for data-plane authorization, but each requires a **different built-in role** scoped to a different resource. Working through both makes the per-agent identity pattern concrete.

## How It Works

### Per-Agent Identity

When you deploy a hosted agent to Foundry, the platform provisions a dedicated Microsoft Entra **service identity** for that agent. Every outbound call the agent makes can use `DefaultAzureCredential` and Foundry will inject the per-agent identity at runtime. To let the agent touch a downstream Azure resource, you assign that identity the appropriate data-plane RBAC role on the target resource.

### Tools

The tools are plain Python functions decorated with `@tool` and registered with the agent in [main.py](src/agent-framework-agent-downstream-azure-responses/main.py). Each tool builds its client with `DefaultAzureCredential()` so the same code works locally (your developer identity) and in Foundry (the per-agent identity).

| Service       | Tools                                                  | SDK                  |
| ------------- | ------------------------------------------------------ | -------------------- |
| Blob Storage  | `storage_put_blob`, `storage_get_blob`                 | `azure-storage-blob` |
| Service Bus   | `servicebus_send_message`, `servicebus_peek_messages`  | `azure-servicebus`   |

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

## Prerequisites

In addition to the prerequisites listed in the [parent README](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/README.md), this sample also requires:

- **Azure Blob Storage** — an existing storage account and container the agent will read/write.
- **Azure Service Bus** — an existing namespace and queue the agent will send to / peek from.

## Granting the agent data-plane access

Both services use standard Azure RBAC, so both assignments use `az role assignment create` against the resource's ARM id.

When running **locally** with `DefaultAzureCredential`, role assignments must be applied to **your developer principal** (the one `az login` was performed with). When running on **Foundry**, role assignments must be applied to the **per-agent identity**. The two principals also have different types — your user identity is a `User`, while the per-agent identity is a `ServicePrincipal` — and `az role assignment create` requires you to pass the right one via `--assignee-principal-type`.

Capture both values into shell variables, then reuse them in the assignment commands below.

**Local (your developer identity):**

```bash
PRINCIPAL_ID=$(az ad signed-in-user show --query id -o tsv)
PRINCIPAL_TYPE="User"
```

```powershell
$PRINCIPAL_ID = az ad signed-in-user show --query id -o tsv
$PRINCIPAL_TYPE = "User"
```

**Foundry (per-agent identity, after `azd deploy`):**

`azd ai agent show` returns the per-agent identity's object id under `instance_identity.principal_id`:

```bash
PRINCIPAL_ID=$(azd ai agent show -o json | jq -r '.instance_identity.principal_id')
PRINCIPAL_TYPE="ServicePrincipal"
```

```powershell
$PRINCIPAL_ID = (azd ai agent show -o json | ConvertFrom-Json).instance_identity.principal_id
$PRINCIPAL_TYPE = "ServicePrincipal"
```

### Blob Storage — Storage Blob Data Contributor

```bash
STORAGE_SCOPE=$(az storage account show \
  --name "$AZURE_STORAGE_ACCOUNT_NAME" \
  --query id -o tsv)/blobServices/default/containers/$AZURE_STORAGE_CONTAINER_NAME

az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type "$PRINCIPAL_TYPE" \
  --role "Storage Blob Data Contributor" \
  --scope "$STORAGE_SCOPE"
```

```powershell
$StorageScope = "$(az storage account show --name $env:AZURE_STORAGE_ACCOUNT_NAME --query id -o tsv)/blobServices/default/containers/$env:AZURE_STORAGE_CONTAINER_NAME"

az role assignment create `
  --assignee-object-id $PRINCIPAL_ID `
  --assignee-principal-type $PRINCIPAL_TYPE `
  --role "Storage Blob Data Contributor" `
  --scope $StorageScope
```

### Service Bus — Data Sender + Data Receiver

```bash
QUEUE_SCOPE=$(az servicebus queue show \
  --namespace-name "<namespace>" \
  --resource-group "<rg>" \
  --name "$AZURE_SERVICEBUS_QUEUE_NAME" \
  --query id -o tsv)

az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type "$PRINCIPAL_TYPE" \
  --role "Azure Service Bus Data Sender" \
  --scope "$QUEUE_SCOPE"

az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type "$PRINCIPAL_TYPE" \
  --role "Azure Service Bus Data Receiver" \
  --scope "$QUEUE_SCOPE"
```

```powershell
$QueueScope = az servicebus queue show --namespace-name "<namespace>" --resource-group "<rg>" --name $env:AZURE_SERVICEBUS_QUEUE_NAME --query id -o tsv

az role assignment create `
  --assignee-object-id $PRINCIPAL_ID `
  --assignee-principal-type $PRINCIPAL_TYPE `
  --role "Azure Service Bus Data Sender" `
  --scope $QueueScope

az role assignment create `
  --assignee-object-id $PRINCIPAL_ID `
  --assignee-principal-type $PRINCIPAL_TYPE `
  --role "Azure Service Bus Data Receiver" `
  --scope $QueueScope
```

Role assignments take a minute or two to propagate.

## Running the Agent Host

In addition to the standard environment variables described in the [parent README](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/README.md), this sample requires the following:

```bash
export AZURE_STORAGE_ACCOUNT_NAME="<storage-account-name>"
export AZURE_STORAGE_CONTAINER_NAME="<container-name>"
export AZURE_SERVICEBUS_FQDN="<namespace>.servicebus.windows.net"
export AZURE_SERVICEBUS_QUEUE_NAME="<queue-name>"
```

```powershell
$env:AZURE_STORAGE_ACCOUNT_NAME="<storage-account-name>"
$env:AZURE_STORAGE_CONTAINER_NAME="<container-name>"
$env:AZURE_SERVICEBUS_FQDN="<namespace>.servicebus.windows.net"
$env:AZURE_SERVICEBUS_QUEUE_NAME="<queue-name>"
```

Follow the instructions in the [Running the Agent Host Locally](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/README.md#running-the-agent-host-locally) section of the README in the parent directory to run the agent host.

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell), `azd`, or the **Agent Inspector** in the Foundry Toolkit VS Code extension. Please refer to the [parent README](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/README.md) for more details. Use this README for sample queries you can send to the agent.

**Blob Storage — write and read back:**

```powershell
azd ai agent invoke 'Upload a blob named hello.txt with the content "hi from the agent".'
azd ai agent invoke 'Read the blob hello.txt and tell me what it contains.'
```

**Service Bus — send and peek:**

```powershell
azd ai agent invoke 'Send a Service Bus message with the body {"orderId": 42}.'
azd ai agent invoke 'Peek the next message on the queue.'
```

Or hit the local endpoint directly:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Read the blob hello.txt and tell me what it contains."}'
```

```powershell
(Invoke-WebRequest -Uri http://localhost:8088/responses -Method POST -ContentType "application/json" -Body '{"input": "Read the blob hello.txt and tell me what it contains."}').Content
```

### Test in VS Code (Foundry Toolkit)

**Prerequisites**

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.

**Set up the Python virtual environment**

- With Python 3.13 or later and [pipx](https://pipx.pypa.io/stable/installation/), install uv outside the project environment, then let uv create and synchronize the locked environment:

  ```bash
  pipx install uv==0.11.7
  uv sync --frozen --python 3.13
  ```
- Open the Command Palette (`Ctrl+Shift+P`), run **Python: Select Interpreter**, and select the `.venv` created by uv.

**Run and debug the agent**

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

**Or run manually, then open the Inspector**

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `uv run --no-sync python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**.

Type the following in the Inspector:

```
Read the blob hello.txt and tell me what it contains.
```

## Deploying the Agent to Foundry

[azure.yaml](azure.yaml) declares the same four environment variables and binds each value to an `${...}` placeholder that `azd` resolves from the **azd environment** at deploy time (your shell's `export` / `$env:` values are not propagated to the deployed agent). Set them once with `azd env set` before deploying:

```powershell
azd env set AZURE_STORAGE_ACCOUNT_NAME "<storage-account-name>"
azd env set AZURE_STORAGE_CONTAINER_NAME "<container-name>"
azd env set AZURE_SERVICEBUS_FQDN "<namespace>.servicebus.windows.net"
azd env set AZURE_SERVICEBUS_QUEUE_NAME "<queue-name>"
```

Then follow the instructions in the [Deploying the Agent to Foundry](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/README.md#deploying-the-agent-to-foundry) section of the README in the parent directory. After deployment, apply the role assignments described in [Granting the agent data-plane access](#granting-the-agent-data-plane-access) to the **per-agent identity** before invoking the deployed agent.

### Deploying with the Foundry Toolkit VS Code Extension

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a tab-based **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate what it can.
2. If prompted, complete **Foundry Project Setup** to pick the subscription and Foundry project (or create a new one) to deploy to.
3. On the **Basics** tab, configure the core deployment settings:
   - **Deployment Method**: **Code** (upload as a ZIP) or **Container** (Docker image via ACR).
   - For **Code**, pick a packaging option: **Remote** or **Local**.
   - For **Container**, pick a registry option: default ACR, your own ACR, or a prebuilt ACR image.
   - **Hosted Agent Name**: confirm the name to register with the hosting service.
4. On the **Review + Deploy** tab, finalize the runtime and resources:
   - Confirm the auto-detected runtime details (language, entry point, or Dockerfile).
   - Pick a **CPU and Memory** size.
   - Click **Deploy**. Fields are validated inline, and the extension handles the build/upload, agent version creation, and RBAC role assignment.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Troubleshooting

### `AuthorizationPermissionMismatch` from Storage

The role assignment hasn't propagated yet, or the scope is wrong. Confirm the assignment with `az role assignment list --assignee "$PRINCIPAL_ID" --all` and verify the scope ends with `/containers/<your-container>`.

### `Unauthorized` from Service Bus

Make sure you assigned **both** Sender and Receiver if the agent does both send and peek/receive. Sender alone cannot peek.

### Local runs fail with credential errors

`DefaultAzureCredential` falls back to your developer identity locally. Run `az login` and assign your user the same roles on the same scopes.
