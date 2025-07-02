# Voice Live Agent

This sample showcases how to voice-enable any agents built with Azure AI Foundry Agent Service, utilizing Azure AI Voice Live API.

**IMPORTANT NOTE:** Starter templates, instructions, code samples and resources in this msft-agent-samples file (“samples”) are designed to assist in accelerating development of agents for specific scenarios. It is important that you review all provided resources and carefully test Agent behavior in the context of your use case: ([Learn More](https://learn.microsoft.com/en-us/legal/cognitive-services/agents/transparency-note?context=%2Fazure%2Fai-services%2Fagents%2Fcontext%2Fcontext)).

Certain Agent offerings may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that Agents or other output created using that sample are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.

## Use cases

Voice-enabled agents are high in demand, now more than ever. Voice agents are agents that users can interact with naturally and conversationally using just their voice. From an end-user perspective, voice is becoming the preferred mode of interaction, as it enables speed, accessibility, and multitasking.

We see increasing demand across several key use-cases including:

**Customer service** – think about getting support from your favorite department store, your bank, your travel agency, or even your government;

**Automotive** – think about in-car assistants with hands-free interaction;

**Learning and education** – think about a learning companion to learn a new topic or a new language;

And many more…

## Architecture overview

The system consists of:

- An AI Agent created with Azure AI Agent Service. You can create an agent using any of the templates provided in agent-catalog/azure-ai-agent-service-blueprints at main · microsoft/agent-catalog

- An Azure Voice Live API request. You can set up your Voice Live API request following the instructions in this document and code sample.

```text
+-----------------+
|   User Query    |
| (Speech Input)  |
+-------+---------+
        |
        v
+---------------------+           invokes          +----------------------------+
|  Voice Live Agent   | ------------------------>  |       Azure AI Agent       |
|                     | <------------------------  |   + Knowledge + Actions    |
+---------------------+           results          +----------------------------+
        |
        v
+-------------------+
|   Agent Response  |
|  (Speech Output)  |
+-------------------+
```

## Voice Live API introduction

Azure AI Voice Live API (preview) is an innovative, unified single API that enables streaming interactions with the foundation model of your choice, for both speech input and output. It includes advanced features such as customizable speech recognition, diverse text-to-speech options, brand voices, avatars, audio enhancement, among other functionalities. With Voice Live API, you can add real-time speech interaction capabilities to any agent built with the Azure AI Agent Service.

Learn more about Voice Live API (preview) here.

This sample shows how to create a demo tool that allows you to add real-time voice interaction capabilities to any agents created.

A live demo (<https://aka.ms/voice-agent/demo>) is also available to experience the Voice Live API, together with a mode to ‘bring your own agents’. WebSocket messages can be observed through the browser developer tools.

## Setup instructions

### Prerequisites

**Set up an agent**. Follow [the templates](../) to create an agent using the Azure AI Agent Service.

**Resource and authentication**. An Azure AI Foundry resource is required to access the Voice Live API. To learn how to create an Azure AI Foundry resource, please see: <https://learn.microsoft.com/azure/ai-services/multi-service-resource>.

Note: The resource must be in the `eastus2` or `swedencentral` regions at this time. Other regions are not supported.

For the recommended keyless authentication with Microsoft Entra ID, you need to:

- Assign the `Azure AI User` role to your user account or a managed identity. You can assign roles in the Azure portal under **Access control (IAM)** > **Add role assignment**.
- Generate a token using the Azure CLI or Azure SDKs. The token must be generated with the `https://ai.azure.com/.default` scope.
- Use the token in the `Authorization` header of the WebSocket connection request, with the format `Bearer <token>`.

## Set Agent Info

You are supposed to specify the agent info in the WebSocket endpoint URL.

| Parameter            | Description                                                                                                                                                                                                              |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `agent-project-name` | The Azure AI project name which the agent belongs to.                                                                                                                                                                    |
| `agent-id`           | The ID of the agent to use.                                                                                                                                                                                              |
| `agent-access-token` | The Entra access token to access the agent. Make sure the identity has access to Azure AI Project, You can grant the built-in role `Azure AI User` to the identity. The scope should be `https://ai.azure.com/.default`. |

> Note: The token must be generated with the `https://ai.azure.com/.default` scope. e.g., `az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv`.
A sample endpoint is `wss://<your-ai-foundry-resource-name>.cognitiveservices.azure.com/voice-live/realtime?api-version=2025-05-01-preview&agent-project-name=<agent-project-name>&agent-id=<agent-id>&agent-access-token=<access-token>`.

## Interact with the Voice Live API

Refer to the [full documentation of Voice Live API](https://learn.microsoft.com/azure/ai-services/<placeholder>) for more details on how to interact with the Voice Live API.

## Getting started

Follow the instructions [here](./samples/react/README.md) to get started with this sample.
