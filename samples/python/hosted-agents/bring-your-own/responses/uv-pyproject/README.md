<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# What this sample demonstrates

A minimal Bring Your Own hosted agent using the **Responses protocol** and an existing Python project managed with [`uv`](https://docs.astral.sh/uv/). It demonstrates how `azd ai agent init` detects `pyproject.toml`, how remote code deployment consumes `uv.lock`, and how `uv.toml` enables system TLS certificates during dependency installation.

## How it works

The agent forwards user input to a model deployed in Microsoft Foundry and returns the model response through the Responses protocol. The code is intentionally small so the dependency-management and existing-code initialization flow stays visible.

See [main.py](src/uv-pyproject-python-responses/main.py) for the implementation.

### Dependency management

The source directory contains:

| File | Purpose |
| --- | --- |
| `pyproject.toml` | Declares project metadata, Python compatibility, and dependencies. |
| `uv.lock` | Pins the complete dependency graph for reproducible remote builds. |
| `uv.toml` | Sets `system-certs = true` so uv uses the operating system certificate store. |

The committed `azure.yaml` selects `remote_build` dependency resolution. During deployment, the hosted build installs the dependencies declared by `pyproject.toml` using the lockfile and uv configuration.

If you change dependencies, update and verify the lockfile:

```bash
uv lock
uv sync --frozen
```

## Prerequisites

1. **Python 3.13 or later**
2. **uv** — [Install uv](https://docs.astral.sh/uv/getting-started/installation/)
3. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
4. **Azure CLI** — [Install Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
5. The unified Foundry extension:

   ```bash
   azd ext install microsoft.foundry
   ```

6. Authenticate:

   ```bash
   azd auth login
   az login
   ```

You do not need an existing Foundry project or model deployment. The `azd` flow can create them.

## Option 1: Initialize from existing code with `azd`

Clone the samples repository, then copy only the existing Python project to a new folder. This intentionally leaves out the committed `azure.yaml` so `azd` can create the agent project from code:

```bash
git clone https://github.com/microsoft-foundry/foundry-samples.git
cd foundry-samples
cp -R samples/python/hosted-agents/bring-your-own/responses/uv-pyproject/src/uv-pyproject-python-responses ../uv-pyproject-agent
cd ../uv-pyproject-agent
```

Verify the locked environment:

```bash
uv sync --frozen
```

Initialize the current directory:

```bash
azd ai agent init
```

Choose the following options when prompted:

1. **Use the code in the current directory**
2. **Code** deployment
3. Runtime **Python 3.13**
4. Entry point **main.py**
5. Dependency resolution **Remote build**

The generated `azure.yaml` references the current source directory while preserving `pyproject.toml`, `uv.lock`, and `uv.toml` for deployment.

### Provision, run, and invoke

```bash
azd provision
azd ai agent run
```

In another terminal:

```bash
azd ai agent invoke --local "What is Microsoft Foundry?"
```

### Deploy and invoke

```bash
azd deploy
azd ai agent invoke "What is Microsoft Foundry?"
```

## Option 2: Initialize directly from the sample manifest

To adopt the complete sample without copying the source directory first:

```bash
mkdir uv-pyproject-agent && cd uv-pyproject-agent
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/responses/uv-pyproject/azure.yaml
azd provision
azd ai agent run
```

## Option 3: Run manually or with the Foundry Toolkit

Install the locked environment:

```bash
cd src/uv-pyproject-python-responses
uv sync --frozen
```

Set the required environment variables:

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="<deployment-name>"
az login
```

Start the agent:

```bash
uv run --no-sync python main.py
```

The agent listens on `http://localhost:8088`. In VS Code, select the interpreter at `.venv`, press **F5**, and use the Foundry Toolkit Agent Inspector to send requests.

## Container build

The included Dockerfile also installs from `pyproject.toml` and `uv.lock`:

```bash
docker build --platform=linux/amd64 -t uv-pyproject-agent src/uv-pyproject-python-responses
docker run --rm -p 8088:8088 \
  -e FOUNDRY_PROJECT_ENDPOINT \
  -e AZURE_AI_MODEL_DEPLOYMENT_NAME \
  uv-pyproject-agent
```

## Troubleshooting

### uv reports a system certificate error during remote build

Keep `uv.toml` in the deployed source directory next to `pyproject.toml` and `uv.lock`:

```toml
system-certs = true
```

This allows uv to use system TLS certificates when resolving packages.

### The lockfile is out of date

If `uv sync --frozen` reports that `uv.lock` does not match `pyproject.toml`, regenerate and commit it:

```bash
uv lock
uv sync --frozen
```

## Next steps

- [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
- [uv projects documentation](https://docs.astral.sh/uv/concepts/projects/)
- [Hello World BYO Responses sample](../hello-world/)
