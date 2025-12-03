# C# Getting Started Sample

This sample demonstrates how to use the AI Foundry platform with C#/.NET. It provides basic examples for authentication, accessing data, and performing common operations with the Foundry APIs.

## Prerequisites

- [.NET SDK](https://dotnet.microsoft.com/download) (version 9.0 or later recommended)
- Visual Studio 22 or Visual Studio Code

## Install Dependencies


## Setup

1. Clone this repository
2. Set up your Azure Ai Foundry account and secrets at the .env file

## NOTE

- The sample in SimpleInference.cs uses a diferent endpoint. In this case, you will need to set the environment variable `AZURE_AI_ENDPOINT` to the root of the AI Foundry endpoint, e.g. `https://{your-resource-name}.services.ai.azure.com/`. While the other samples use `AZURE_AI_ENDPOINT` which should be set to the full endpoint, e.g. `https://{your-resource-name}.services.ai.azure.com/api/projects/{project-id}`.

- The agent samples require the `AZURE_AI_MODEL` environment variable to be set to an OpenAI-compatible model, e.g. `gpt-4.1`, as not all models are supported for agent use cases, including tooling.

## Running the Sample
