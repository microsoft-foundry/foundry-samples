# Ingestion Client v2

An event-driven Azure Speech transcription sample. Upload an audio file to Azure Storage and receive its transcript in a separate output storage account.

Supports three transcription engines in one deployment:

| Upload folder | Engine |
|---|---|
| `audio-input/fast/` | Fast transcription |
| `audio-input/batch/` | Asynchronous batch transcription |
| `audio-input/llm/` | LLM Speech |

The folder determines which engine processes the file. No redeployment is needed to switch engines.

## How it works

Azure Storage → Event Grid → Service Bus → Azure Functions → Azure Speech

The deployment includes storage, a Foundry resource, managed identity authentication and monitoring. Batch jobs are submitted and polled automatically.

## Prerequisites

- An Azure subscription with permission to deploy resources and assign roles.
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) and [Azure Developer CLI](https://aka.ms/azd).
- A local copy of this repository.

Choose a region supporting both [LLM Speech](https://learn.microsoft.com/azure/ai-services/speech-service/regions?tabs=llmspeech) and [Azure Functions Flex Consumption](https://learn.microsoft.com/azure/azure-functions/flex-consumption-how-to#view-currently-supported-regions) if you want all three engines.

**Deploying this sample creates billable Azure resources.**

## Deploy

Sign in:

```powershell
az login
azd auth login
```

From the root of your `foundry-samples` checkout:

```powershell
cd samples\python\ingestion-client-v2
azd up
```

Follow the prompts to choose an environment name, subscription and region.

Deployment provisions the resources, publishes the function and uploads the default engine configurations.

If deployment fails because Event Grid cannot yet deliver to Service Bus, wait briefly and rerun `azd up`. Role assignments can take time to propagate.

## Use

Upload an audio file to the input storage account using Azure Storage Explorer, the Azure portal or your own application.

For example:

```text
Input:  audio-input/fast/call.wav
Output: transcriptions/fast/call.wav.json
```

Results appear in the output storage account. Files uploaded outside the recognised engine folders are moved to `quarantine`.

## Configuration

Default settings are provided in the [`config`](config) folder.

To change an engine's settings, edit its JSON file in the input storage account's `config` container:

- `fast.json`
- `batch.json`
- `llm.json`

Changes take effect within about a minute without redeployment. The included [JSON schemas](config/schemas) describe the available settings.

## Important notes

- Each engine returns its native transcript JSON format.
- Service availability and quotas vary by engine and region.
- Private endpoints and Function VNet integration are not included. Additional networking work is needed for a fully private deployment.
- Planned features are separate from this initial contribution.

## Clean up

From this sample's directory:

```powershell
azd down --purge
```

This deletes the resources created by the deployment. Save any audio or transcripts you need first.

## Source and licence

Originally developed in [stephenadam5/ingestion-client-v2](https://github.com/stephenadam5/ingestion-client-v2).

Licensed under the [MIT License](LICENSE).
