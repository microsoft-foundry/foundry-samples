# What this sample demonstrates

This sample hosts an Agent Framework agent with steerable conversations enabled. If a second input
arrives while a stored background response is still running on the same conversation, Foundry queues
the new input instead of returning `conversation_locked`.

## How it works

`Program.cs` registers the agent with:

```csharp
builder.Services.AddFoundryResponses(
    agent,
    configure: options => options.SteerableConversations = true);
```

The option is host-wide and must be set on the first `AddFoundryResponses` call. The active turn is
allowed to finish or stop at a safe boundary, then the queued input runs on the same persisted agent
session.

Steering and crash recovery are separate capabilities. This sample enables steering only. See the
[resilient-workflow](../resilient-workflow/) sample for background recovery after process replacement.

## Prerequisites

1. An existing Foundry project with a deployed model, or create them during Option 1.
2. [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0) or later.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

1. [Azure Developer CLI (`azd`)](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) 1.27.1 or later.
2. Install the Foundry extension:

   ```bash
   azd ext install microsoft.foundry
   ```

3. Authenticate:

   ```bash
   azd auth login
   ```

### Initialize the agent project

```bash
mkdir steering-agent && cd steering-agent
azd ai agent init \
  -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/csharp/hosted-agents/agent-framework/steering/azure.yaml \
  --deploy-mode container
```

The explicit deployment mode ensures `azd` builds the included `Dockerfile` instead of using its
default ZIP-based code deployment. Follow the prompts to select or create a Foundry project and
model deployment. The command creates a `steering` subdirectory containing the initialized project:

```bash
cd steering
```

### Provision, run, and invoke

```bash
azd provision
azd ai agent run
azd ai agent invoke --local "Reply briefly and preserve [STEERING-READY]."
```

### Deploy and invoke

```bash
azd deploy
azd ai agent invoke "Reply briefly and preserve [STEERING-READY]."
```

## Option 2: VS Code (Foundry Toolkit)

### Prerequisites

1. VS Code with the [Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio) extension.
2. The [C# Dev Kit](https://marketplace.visualstudio.com/items?itemName=ms-dotnettools.csdevkit) extension.
3. Azure CLI authenticated with `az login`.

### Run and debug

Press **F5**. The agent starts and Agent Inspector opens automatically.

For a manual run, copy `.env.example` to `.env`, fill in the values, then run:

```bash
dotnet restore
dotnet run
```

Open **Foundry Toolkit: Open Agent Inspector** to chat with the running agent.

### Deploy

Run **Foundry Toolkit: Deploy Hosted Agent**, select **Container** as the deployment method, select
the Foundry project, confirm the deployment settings, and deploy.

## Exercise steering

Steering requires two stored background requests on the same active conversation. Use a Responses
API client that exposes `background`, `store`, and `conversation`.

1. Start a request with `background=true`, `store=true`, and a conversation ID.
2. Before that response finishes, send a second request with the same conversation ID.
3. Confirm the second response is returned with `status=queued`.
4. Poll both response IDs until they reach `completed`.

The `background=true` request must also be stored. Setting `store=false` is invalid for a background
response and prevents durable queueing.

## Troubleshooting

**The second request returns after the first response has already completed.** Use a prompt that
produces a longer first response and submit the second request immediately. Steering applies only
while the first conversation turn is active.

**The request is rejected as locked.** Confirm both requests use the same conversation ID and that
the deployed sample includes `SteerableConversations = true`.

**The CLI returns no visible assistant text.** Inspect the complete Responses event stream:

```bash
azd ai agent invoke --new-session --new-conversation --output raw "Hello"
```

Check the final `response.completed` or `response.failed` event. The friendly CLI output can be empty
for a failed response even when the command itself exits successfully.

## Next steps

- [Resilient workflow sample](../resilient-workflow/)
- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
