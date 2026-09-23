# What this sample demonstrates

A minimal echo agent hosted as a Foundry Hosted Agent using the **Invocations protocol** and the [Agent Framework](https://github.com/microsoft/agent-framework). The agent reads the request body as plain text, passes it through a custom `EchoAIAgent`, and writes the echoed text back in the response. No LLM or Azure credentials are required — this is the **Echo Agent (Invocations Protocol)** sample.

## How It Works

The agent registers a custom `EchoAIAgent` behind the Invocations protocol. When a request arrives at `/invocations`, the handler reads the request body as plain text and returns `Echo: <input>` as plain text. Because no model is involved, this sample requires no Azure OpenAI deployment or Foundry project endpoint, making it ideal for testing the hosting infrastructure in isolation.

See [Program.cs](src/invocations-echo-agent/Program.cs) and [EchoAIAgent.cs](src/invocations-echo-agent/EchoAIAgent.cs) for the full implementation.

## Prerequisites

1. **[.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)** or later. This sample does **not** call an LLM, so no Foundry project or model deployment is required — though `azd provision` (Option 1) is still available if you want to set up infrastructure for deployment.

### Environment variables

This agent does **not** require a model deployment — no `FOUNDRY_PROJECT_ENDPOINT` or `AZURE_AI_MODEL_DEPLOYMENT_NAME` is needed.

| Variable | Required | Description |
|----------|----------|-------------|
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Optional | Enables telemetry. Auto-injected in hosted containers; set manually for local dev. |

When using `azd ai agent run`, these are handled automatically.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
2. Install the Foundry extension:

   ```bash
   azd ext install microsoft.foundry
   ```

3. Authenticate:

   ```bash
   azd auth login
   ```

### Initialize the agent project

No cloning required. Create a new folder and initialize from the manifest:

```bash
mkdir echo-agent && cd echo-agent
azd ai agent init --deploy-mode container -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/agent-framework/invocations-echo-agent/azure.yaml
```

Follow the prompts to configure your project. If you don't have an existing Foundry project, `azd ai agent init` will guide you through creating one (not required for this LLM-free sample, but useful for deployment).

> If you already have a Foundry project, add `-p <project-id>` to `azd ai agent init` to target existing resources.

### Provision Azure resources (if needed)

Only needed if you plan to deploy:

```bash
azd provision
```

### Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

### Invoke the local agent

In a separate terminal, invoke the running agent:

```bash
azd ai agent invoke --local --protocol invocations "Hello, world!"
```

In PowerShell:

```powershell
azd ai agent invoke --local --protocol invocations "Hello, world!"
```

The server responds with `Echo: Hello, world!`. To inspect the unmodified response headers and body:

```bash
azd ai agent invoke --local --protocol invocations --output raw "Hello, world!"
```

Consecutive invokes reuse the saved session automatically. Pass `--new-session` when you want a new one:

```bash
azd ai agent invoke --local --protocol invocations "How are you?"
azd ai agent invoke --local --protocol invocations --new-session "Start over."
```

### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

### Invoke the deployed agent

```bash
azd ai agent invoke --protocol invocations "Hello, world!"
```

Stream logs from the running agent with `azd ai agent monitor`.

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. [C# Dev Kit](https://marketplace.visualstudio.com/items?itemName=ms-dotnettools.csdevkit) extension.
3. Command Palette (`Ctrl+Shift+P`) → **C#: Check Workspace Requirements** to confirm the toolchain is ready.

### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

### Or run manually, then open the Inspector

1. Restore dependencies:

   ```bash
   dotnet restore
   ```

2. Start the agent (listens on `http://localhost:8088`) — this LLM-free sample needs no environment variables or Azure sign-in to run locally:

   ```bash
   dotnet run
   ```

3. Open the Command Palette (`Ctrl+Shift+P`) → **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Troubleshooting

### Images built on Apple Silicon or other ARM64 machines do not work on our service

**Deploy with `azd deploy`**, which uses ACR remote build and always produces images with the correct architecture.

If you choose to **build locally**, and your machine is **not `linux/amd64`** (for example, an Apple Silicon Mac), the image will **not be compatible with our service**, causing runtime failures.

**Fix for local builds:**

```bash
docker build --platform=linux/amd64 -t image .
```

This forces the image to be built for the required `amd64` architecture.
