<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# Quickstart: Configure Session Idle Timeout for a Hosted Agent

This sample shows how to use **`sessionConfiguration.idleTimeoutSeconds`** in `azure.yaml` to control how long a hosted agent session stays alive after the last user interaction — and how to deploy it with the [Azure Developer CLI (`azd`)](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?view=foundry&pivots=azd).

## What it does

When users interact with a hosted agent, each conversation runs in a **session** — a stateful container that keeps the agent process alive between messages. By default, a session is terminated after **15 minutes (900 seconds)** of inactivity.

`sessionConfiguration.idleTimeoutSeconds` is a **deploy-time property** on the hosted agent. You declare it in `azure.yaml` and `azd` applies it when the agent version is created — no SDK code required.

| Use case | Recommended timeout |
|----------|-------------------|
| Quick Q&A agents | 300s (5 min) — saves resources |
| Interactive coding assistants | 1800s (30 min) — avoids mid-task resets |
| Long-running data analysis | 3600s (60 min) — maximum allowed |

## Key configuration

The idle timeout is set on the agent service in [`azure.yaml`](azure.yaml):

```yaml
services:
  hosted-agent-session-configuration:
    host: azure.ai.agent
    kind: hosted
    # ... other fields ...
    sessionConfiguration:
      idleTimeoutSeconds: 1800  # 30 minutes
```

### Valid range

| Property | Min | Default | Max |
|----------|-----|---------|-----|
| `idleTimeoutSeconds` | 300 | 900 | 3600 |

Values outside this range are rejected during provisioning/deployment.

## Prerequisites

1. **Azure Developer CLI (`azd`)**
   - [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) (1.34.2 or later) and the unified Foundry CLI extension: `azd ext install microsoft.foundry`
   - This sample requires the **`azure.ai.agents` extension `>=1.0.0-beta.19`** for `--template` / `-t` (declared in [`azure.yaml`](azure.yaml) under `requiredVersions`). If already installed, update it with `azd ext update azure.ai.agents`.
   - Authenticated: `azd auth login`
2. **Azure CLI** — installed and authenticated: `az login`
3. **Python 3.10 or higher** — verify with `python --version`

> [!NOTE]
> You do **not** need an existing [Microsoft Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/what-is-foundry?view=foundry) project or model deployment to get started — `azd provision` creates them for you.

## Run and deploy with `azd`

No cloning required. Create a new folder, point `azd` at the manifest on GitHub, and it downloads the sample and adopts its `azure.yaml` as the project manifest:

```bash
# Create a new folder for the agent and navigate into it
mkdir session-config-agent && cd session-config-agent

# Initialize from the manifest — azd reads it, downloads the sample,
# and adopts its azure.yaml as the project manifest
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/quickstart/hosted-agent-session-configuration/azure.yaml

# Provision Azure resources (Foundry project, model deployment, App Insights)
azd provision

# Run the agent locally (handles env vars, Docker build, and startup)
azd ai agent run
```

> [!NOTE]
> If you've already cloned this repository, pass a local path to the manifest instead:
> `azd ai agent init -t <path-to-repo>/samples/python/quickstart/hosted-agent-session-configuration/azure.yaml`
> Or change into this sample's directory and run `azd ai agent init` without `-t` to reuse its existing `azure.yaml`.

Invoke the local agent:

```bash
azd ai agent invoke --local "What is Microsoft Foundry?"
```

Deploy to Foundry — the configured idle timeout is applied to the created agent version:

```bash
# Build, push, and deploy the agent to Foundry
azd deploy

# Invoke the deployed agent
azd ai agent invoke "What is Microsoft Foundry?"
```

To change the timeout, edit `idleTimeoutSeconds` in `azure.yaml` and re-run `azd deploy`.

## Next steps

- [Hosted agents overview](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [azure.yaml reference for hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/azure-yaml-reference)
- [Deploy a hosted agent with azd](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent?view=foundry&pivots=azd)
