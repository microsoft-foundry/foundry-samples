<!-- Begin standard disclaimer — do not modify -->
**IMPORTANT!** All samples and other resources made available in this GitHub repository ("samples") are designed to assist in accelerating development of agents, solutions, and agent workflows for various scenarios. Review all provided resources and carefully test output behavior in the context of your use case. AI responses may be inaccurate and AI actions should be monitored with human oversight. Learn more in the transparency note for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note).

Agents, solutions, or other output you create may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that any output created using those samples are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

Third-party samples contained in this folder are subject to their own designated terms, and they have not been tested or verified by Microsoft or its affiliates.

Microsoft has no responsibility to you or others with respect to any of these samples or any resulting output.
<!-- End standard disclaimer -->

# What this sample demonstrates

A voice-friendly hosted agent that combines the
[GitHub Copilot SDK](https://github.com/github/copilot-sdk), the Foundry
**Responses protocol**, and a bring-your-own Foundry model. The agent streams
assistant text and short tool-status messages that VoiceLive can synthesize while
Copilot is working.

## How it works

The hosted agent uses the Foundry project endpoint as an Azure provider for the
Copilot SDK. `DefaultAzureCredential` acquires a managed-identity token for
`https://ai.azure.com/.default`, so the default deployment does not require a
GitHub token or model API key.

Each Responses request is forwarded to a persistent Copilot session. Assistant
message deltas become Responses text deltas, tool starts become short status
messages, and a voice-mode instruction keeps the final answer concise and
speech-friendly. See
[`main.py`](src/github-copilot-responses-voicelive/main.py).

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FOUNDRY_PROJECT_ENDPOINT` | For BYOK | Foundry project endpoint. Injected automatically when hosted and configured by `azd ai agent run` locally. |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | For BYOK | Foundry model deployment name. The default `azure.yaml` provisions `gpt-5.4-mini`. |
| `GITHUB_TOKEN` | For GitHub model | Optional alternative to BYOK. Use a fine-grained PAT with **Copilot Requests: Read-only**. |
| `GITHUB_COPILOT_MODEL` | No | Optional Copilot model selection in GitHub-token mode. |
| `FOUNDRY_AGENT_SESSION_ID` | No | Session ID used to resume Copilot conversation state. |

If both modes are configured, the Foundry BYOK model takes precedence.

## Prerequisites

1. A Foundry project with a deployed model, or permission to create them with
   `azd provision`.
2. **Python 3.13 or later.**
3. [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.11.7 or later,
   installed and available on `PATH`.
4. Azure CLI authentication (`az login`) for local BYOK authentication.
5. The hosted agent's managed identity needs **Cognitive Services OpenAI User** on the Foundry account. The Copilot SDK provider sends requests to
   `/openai/v1/responses`, which requires the account-level
   `Microsoft.CognitiveServices/accounts/OpenAI/responses/write` data action.
   Assign the role to the hosted agent's `*-AgentIdentity` service principal
   after the first deployment, then allow time for RBAC propagation.

## Option 1: Azure Developer CLI (`azd`)

### Prerequisites

1. [Azure Developer CLI (`azd`)](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
   1.34.2 or later.
2. Install the Foundry extension:

   ```bash
   azd ext install microsoft.foundry
   ```

3. Verify uv is available:

   ```bash
   uv --version
   ```

4. Authenticate:

   ```bash
   azd auth login
   az login
   ```

### Initialize the agent project

```bash
mkdir github-copilot-responses-voicelive
cd github-copilot-responses-voicelive
azd ai agent init -t https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/bring-your-own/voicelive/github-copilot-responses-voicelive/azure.yaml
```

Follow the prompts to select an existing Foundry project and model deployment or
create new resources.

### Provision, run, and invoke locally

```bash
azd provision
azd ai agent run
```

In another terminal:

```bash
azd ai agent invoke --local "What is two plus two?"
```

The agent also accepts direct Responses requests:

```bash
curl -sS -N -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"What is two plus two?","stream":true}'
```

### Deploy and invoke

```bash
azd deploy
azd ai agent invoke "What is two plus two?"
```

To stream hosted logs:

```bash
azd ai agent monitor
```

## Option 2: VS Code (Foundry Toolkit)

1. Install the
   [Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)
   and the VS Code Python extension.
2. Install uv, sync the committed environment, and select its interpreter:

   ```bash
   python -m pip install uv
   cd src/github-copilot-responses-voicelive
   uv sync --frozen
   ```

   In VS Code, select `src/github-copilot-responses-voicelive/.venv` as the
   Python interpreter.
3. Configure the values from
   [`src/github-copilot-responses-voicelive/.env.example`](src/github-copilot-responses-voicelive/.env.example).
4. Press **F5**. The Toolkit generates local task files, starts the agent, and
   opens Agent Inspector.
5. Use **Foundry Toolkit: Deploy Hosted Agent** to deploy the code and select
   CPU and memory settings.

## Use the deployed agent with VoiceLive

After deployment, run the shared VoiceLive microphone client:

```bash
pip install "azure-ai-voicelive[aiohttp]==1.3.0b1" azure-identity pyaudio
curl -O https://raw.githubusercontent.com/microsoft-foundry/foundry-samples/main/samples/python/hosted-agents/bring-your-own/voicelive/client/voicelive_client.py
python voicelive_client.py \
  --endpoint "https://<account>.services.ai.azure.com" \
  --agent-name "github-copilot-responses-voicelive" \
  --project-name "<project-name>"
```

The client uses `DefaultAzureCredential`. Speak into the microphone and the
agent's Responses output is returned as synthesized speech.

## Use the GitHub Copilot model instead

For local development, comment out the Foundry variables in `.env` and set a
fine-grained `GITHUB_TOKEN`. For deployment, comment
`AZURE_AI_MODEL_DEPLOYMENT_NAME` and uncomment `GITHUB_TOKEN` in `azure.yaml`.

Classic `ghp_` tokens are not supported. Use a fine-grained `github_pat_`, OAuth
`gho_`, or GitHub App user `ghu_` token.

## Troubleshooting

**Provider returns HTTP 401:** find the hosted agent's `*-AgentIdentity` service
principal and assign it **Cognitive Services OpenAI User** at the Foundry
account scope. This role is required for the Copilot SDK provider's direct
`POST /openai/v1/responses` request. Allow time for RBAC propagation before
retrying.

**No assistant text appears:** confirm that the selected model supports the
Responses API and that `AZURE_AI_MODEL_DEPLOYMENT_NAME` exactly matches the
deployment name.

## Next steps

- [VoiceLive SDK](https://pypi.org/project/azure-ai-voicelive/)
- [GitHub Copilot SDK](https://github.com/github/copilot-sdk)
- [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
