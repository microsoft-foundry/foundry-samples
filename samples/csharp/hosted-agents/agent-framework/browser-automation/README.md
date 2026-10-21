# Browser Automation Agent (C#, Agent Framework)

This sample hosts a C# Agent Framework agent over the Responses protocol and gives it the GA Azure Playwright browser tools through a Foundry Toolbox MCP connection.

## What this sample demonstrates

- Runtime browser-tool discovery through Foundry Toolbox MCP
- Browser-session reuse through `browserSessionId`
- Exact live-view URL delivery outside model-generated text
- Browser lifecycle, scraping, and form-filling guidance through prompts and skills
- Automated Playwright workspace, connection, toolbox, and RBAC setup

No browser tool schema is hardcoded in the application, and no local browser CLI or CDP attachment is required.

## How it works

1. Deployment hooks provision or reuse an Azure Playwright workspace.
2. The hooks create a Foundry project connection targeting the workspace's GA MCP endpoint and publish a Toolbox with a `browser_automation` tool.
3. `AddFoundryToolboxes` discovers the browser tools at runtime.
4. The model uses the discovered create-session tool and passes its `browserSessionId` to subsequent browser calls.
5. Middleware removes `liveViewUrl` from model-visible tool output and streams the exact URL directly to the user.

## Key files

| Path | Purpose |
| --- | --- |
| `src/bat-csharp-maf/Program.cs` | Builds and hosts the Agent Framework agent. |
| `src/bat-csharp-maf/utils/Middlewares.cs` | Logs calls and injects exact live-view links. |
| `src/bat-csharp-maf/prompts/base.md` | Browser lifecycle and automation behavior. |
| `src/bat-csharp-maf/skills/` | Browser automation procedures loaded by the agent. |
| `hooks/setup-toolbox.*` | Publishes the GA browser automation toolbox. |
| `infra-modules/playwright-connection.bicep` | Creates the GA MCP project connection. |

## Prerequisites

- An Azure AI Foundry project with a deployed chat model
- Azure CLI and Azure Developer CLI
- .NET 10 SDK for local development
- Docker for local container builds

The provisioning hook can create a Playwright workspace when the current identity has permission. Set `PLAYWRIGHT_SERVICE_RESOURCE_ID` to reuse an existing workspace.

## Configuration

For local development, copy `.env.example` to `.env` or set:

```dotenv
FOUNDRY_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4.1
TOOLBOX_NAME=browser-automation-tools
```

Run `az login` before starting locally so `DefaultAzureCredential` can authenticate model and Toolbox calls.

## Option 1: Azure Developer CLI

Initialize from a directory outside the sample:

```bash
azd ai agent init -t ./browser-automation/azure.yaml
azd provision
```

The `postprovision` hook creates or reuses the Playwright workspace, creates the GA MCP connection, and publishes the `browser_automation` toolbox.

Run and invoke locally:

```bash
azd ai agent run
azd ai agent invoke --local --new-session "Open https://example.com and report the page title."
azd ai agent invoke --local "Follow the first link using the same browser session."
```

Deploy and invoke:

```bash
azd deploy
azd ai agent invoke --new-session "Open https://example.com and report the page title."
```

The `postdeploy` hook assigns the browser role required by the configured project or hosted-agent identity.

## Option 2: VS Code

Install the Foundry Toolkit and C# Dev Kit extensions. After initializing the sample, press **F5** to run the agent and open Agent Inspector. To run manually:

```bash
cd src/bat-csharp-maf
dotnet restore
dotnet run
```

Use **Foundry Toolkit: Deploy Hosted Agent** to deploy from VS Code.

## Browser lifecycle

Agent Framework discovers the browser tools through MCP `tools/list`. The agent uses the discovered tools to create and close sessions, reusing the returned `browserSessionId` for later calls and requests.

Live-view URLs are emitted by middleware so their signed fragments remain unchanged.

Keep the browser open after successful tasks and while waiting for user input, approval, CAPTCHA, MFA, or manual browser steps. A completed response is not a request to close the browser. Resume in the same session after the user replies, and close only when the user explicitly asks.

This is an agent behavior policy, not an indefinite browser-lifetime guarantee. Hosted compute and browser-service idle limits still apply.

## CI and non-interactive provisioning

Set at least one of the following before `azd provision --no-prompt`:

```bash
azd env set PLAYWRIGHT_SERVICE_RESOURCE_ID "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.LoadTestService/playwrightWorkspaces/<name>"
azd env set PLAYWRIGHT_AUTH_TYPE "ProjectManagedIdentity"
```

To create a workspace instead:

```bash
azd env set PLAYWRIGHT_REGION "eastus"
azd env set PLAYWRIGHT_AUTH_TYPE "ProjectManagedIdentity"
```

Supported authentication values are `ProjectManagedIdentity`, `AgenticIdentityToken`, and interactive `ApiKey`.

## Customize the sample

- Change agent behavior in `prompts/base.md`.
- Add procedures under `skills/`.
- Adjust live-view and browser-session handling in `utils/Middlewares.cs`.
- Change hosted resources in `azure.yaml`.
