# Testing Azure AI Foundry Java Samples

This document provides instructions for running and testing the Java samples for Azure AI Foundry. These samples demonstrate the capabilities of the Azure AI SDKs for Java developers.

## Azure AI SDKs Used

These samples utilize the following Azure AI SDKs:

| SDK | Version | Description |
|-----|---------|-------------|
| Azure AI Agents Persistent SDK | 1.0.0-beta.2 | Provides APIs for creating, managing, and interacting with persistent agents |
| Azure AI Projects SDK | 1.0.0-beta.2 | Enables project creation and management for AI applications |
| Azure AI Inference SDK | 1.0.0-beta.5 | Offers direct access to AI model inference capabilities |
| OpenAI Java SDK | 2.7.0 | Provides direct access to OpenAI models (used in some samples) |

## Prerequisites

- Java 21 or higher
- Maven 3.99 or higher
- Azure CLI installed and configured (`az login`)
- An Azure account with access to Azure AI Foundry

## Environment Setup

Before running the tests, you need to set up your environment variables:

### Required Environment Variables

The samples use environment variables directly via `System.getenv()` with fallbacks to default values when possible.

#### Essential Variables:

- Either `PROJECT_ENDPOINT` or `AZURE_ENDPOINT` must be set to your Azure AI Foundry endpoint

#### Setting Environment Variables:

##### Windows (Command Prompt)
```cmd
set PROJECT_ENDPOINT=your_azure_ai_foundry_endpoint
set MODEL_DEPLOYMENT_NAME=gpt4o
```

##### Windows (PowerShell)
```powershell
$env:PROJECT_ENDPOINT = "your_azure_ai_foundry_endpoint"
$env:MODEL_DEPLOYMENT_NAME = "gpt4o"
```

##### Linux/macOS (Bash)
```bash
export PROJECT_ENDPOINT=your_azure_ai_foundry_endpoint
export MODEL_DEPLOYMENT_NAME=gpt4o
```

### Optional Environment Variables

| Variable | Default Value | Description |
|----------|---------------|-------------|
| `AZURE_MODEL_DEPLOYMENT_NAME` | `phi-4` | The model deployment name to use |
| `AZURE_MODEL_API_PATH` | `deployments` | API path segment used to construct the endpoint URL |
| `AZURE_AI_API_KEY` | *none* | API key for authentication (falls back to DefaultAzureCredential if not provided) |
| `CHAT_PROMPT` | *varies by sample* | The prompt to send to the chat |
| `STREAMING_WAIT_TIME` | `10000` | Wait time for streaming samples (in milliseconds) |
| `AGENT_NAME` | *auto-generated* | Name for the agent (for agent-related samples) |
| `AGENT_INSTRUCTIONS` | *varies by sample* | Instructions for the agent |
| `OPENAI_API_KEY` | *none* | Required only for ChatCompletionOpenAISample |

## Running the Tests

### Running All Tests

To run all the samples in sequence:

#### Windows
```cmd
testing.bat
```

#### Linux/macOS
```bash
./testing.sh
```

### Running a Specific Test

To run a specific sample, specify the sample class name:

#### Windows
```cmd
testing.bat OptionalChatCompletionSample
```

#### Linux/macOS
```bash
./testing.sh ChatCompletionSample
```

## Available Samples

| Sample Name | Description | Required Env Variables |
|-------------|-------------|------------------------|
| `CreateProject` | Creates a new AI Foundry project | PROJECT_ENDPOINT or AZURE_ENDPOINT |
| `AgentSample` | Creates and manages an AI agent | PROJECT_ENDPOINT or AZURE_ENDPOINT, optionally AZURE_MODEL_DEPLOYMENT_NAME |
| `ChatCompletionSample` | Basic chat completion using Inference SDK | PROJECT_ENDPOINT or AZURE_ENDPOINT, optionally AZURE_MODEL_DEPLOYMENT_NAME, AZURE_MODEL_API_PATH, AZURE_AI_API_KEY, CHAT_PROMPT |
| `ChatCompletionStreamingSample` | Streaming chat completion using Inference SDK | PROJECT_ENDPOINT or AZURE_ENDPOINT, optionally AZURE_MODEL_DEPLOYMENT_NAME, AZURE_MODEL_API_PATH, AZURE_AI_API_KEY, CHAT_PROMPT, STREAMING_WAIT_TIME |
| `ChatCompletionOpenAISample` | Direct chat using OpenAI SDK | OPENAI_API_KEY, optionally MODEL_DEPLOYMENT_NAME, CHAT_PROMPT |
| `ChatCompletionInferenceSample` | Chat using Azure AI Inference SDK | PROJECT_ENDPOINT or AZURE_ENDPOINT, optionally AZURE_MODEL_DEPLOYMENT_NAME, CHAT_PROMPT |
| `FileSearchAgentSample` | Demonstrates file search with agents | PROJECT_ENDPOINT or AZURE_ENDPOINT, optionally AZURE_MODEL_DEPLOYMENT_NAME |
| `EvaluateAgentSample` | Shows agent evaluation | PROJECT_ENDPOINT or AZURE_ENDPOINT, optionally AZURE_MODEL_DEPLOYMENT_NAME |

## SDK Features Overview

### Azure AI Projects SDK

The Azure AI Projects SDK (`com.azure:azure-ai-projects:1.0.0-beta.2`) enables developers to:

- Create and manage AI projects programmatically
- Organize AI resources within logical containers
- Deploy models and services within projects
- Manage settings and configurations for AI applications
- Track resource usage and quotas

The `CreateProject` sample demonstrates the basic usage of this SDK, showing how to establish the foundation for other AI services.

### Azure AI Agents Persistent SDK

The Azure AI Agents Persistent SDK (`com.azure:azure-ai-agents-persistent:1.0.0-beta.2`) provides capabilities to:

- Create intelligent agents that maintain conversation context
- Configure agent capabilities, tools, and instructions
- Send queries to agents and receive responses
- Enable file search and processing within agent conversations
- Evaluate agent performance on specific tasks

The `AgentSample`, `FileSearchAgentSample`, and `EvaluateAgentSample` demonstrate various aspects of this SDK.

### Azure AI Inference SDK

The Azure AI Inference SDK (`com.azure:azure-ai-inference:1.0.0-beta.5`) allows developers to:

- Access AI models directly for inference
- Send custom prompts to deployed models
- Control generation parameters like temperature and max tokens
- Stream responses for real-time applications
- Leverage advanced model capabilities

The `ChatCompletionSample` and `ChatCompletionStreamingSample` showcase this SDK's functionality with:

- Flexible endpoint URL construction using PROJECT_ENDPOINT + AZURE_MODEL_API_PATH + AZURE_MODEL_DEPLOYMENT_NAME
- Dual authentication options: API key (AZURE_AI_API_KEY) or DefaultAzureCredential
- Synchronous completions with `complete()` method (ChatCompletionSample)
- Token streaming with `completeStream()` method (ChatCompletionStreamingSample)
- Comprehensive error handling with HTTP status code interpretation
- Detailed logging using ClientLogger

### OpenAI Java SDK

Some samples also demonstrate direct integration with the OpenAI Java SDK (`com.openai:openai-java:2.7.0`), which provides:

- Direct access to OpenAI models without Azure middleware
- Alternative APIs for specific use cases
- Comparison point for Azure-integrated solutions

The `ChatCompletionOpenAISample` demonstrates this integration.

## Troubleshooting

### SDK Version Issues

The samples use specific versions of Azure AI SDKs as specified at the top of this document. Some features demonstrated might require newer SDK versions as the Azure AI services evolve.

- Azure AI Agents Persistent SDK v1.0.0-beta.2
- Azure AI Projects SDK v1.0.0-beta.2
- Azure AI Inference SDK v1.0.0-beta.5
- OpenAI Java SDK v2.7.0

> **Note for First-time Users**: These SDKs are in active development. If you encounter method or class not found errors, it's likely due to API changes between versions. Check the latest documentation for updated API signatures.

### Common Errors and Solutions

1. **Authentication Errors**:
   - Make sure you're logged in with `az login` using the Azure CLI
   - Verify your Azure AD credentials have appropriate permissions for Azure AI resources
   - Check that your subscription has access to Azure AI services
   - For OpenAI samples, ensure your API key is correctly configured

2. **Missing API Methods**:
   - Check for updated SDK versions in the Maven Central Repository
   - Review the Java SDK documentation for renamed or relocated methods
   - Some features may be in preview and not available in the current SDK version

3. **Connection Timeouts**:
   - Increase the `STREAMING_WAIT_TIME` environment variable (default: 10000ms)
   - Check your network connection and firewall settings
   - Verify VPN configurations aren't blocking Azure endpoints
   - Ensure Azure resource availability in your region

4. **Environment Variable Issues**:
   - Verify that at least `PROJECT_ENDPOINT` or `AZURE_ENDPOINT` is set
   - For OpenAI samples, make sure `OPENAI_API_KEY` is set
   - Variables are case-sensitive - double check spelling
   - On Windows, environment variables set in one command prompt won't be available in others

5. **Maven Build Issues**:
   - Ensure your Maven version is 3.9.0 or higher
   - Run `mvn clean compile` before testing to refresh dependencies
   - Check for Java version compatibility (Java 21+ recommended)

### For First-time Users

1. **Setting Up Your Environment**:
   - Start with the `CreateProject` sample to verify basic connectivity
   - Use the testing scripts (`testing.bat` or `testing.sh`) to quickly validate your setup
   - Check the console output for SDK version information and connection status

2. **Understanding the Chat Completion Samples**:
   - For beginners, start with `ChatCompletionSample` which demonstrates the basics
   - To see real-time responses, try `ChatCompletionStreamingSample` which shows tokens as they arrive
   - The full endpoint URL is constructed from:
     ```
     PROJECT_ENDPOINT + AZURE_MODEL_API_PATH + AZURE_MODEL_DEPLOYMENT_NAME
     ```
   - Authentication works in two ways:
     - With AZURE_AI_API_KEY: Uses AzureKeyCredential
     - Without AZURE_AI_API_KEY: Uses DefaultAzureCredential from az login
   - Both samples include comprehensive error handling with specific guidance

3. **Understanding the Samples**:
   - Each sample demonstrates different aspects of the Azure AI SDKs
   - Review the Javadoc comments in the source code for detailed explanations
   - The samples progress from basic connectivity to more advanced features

3. **Azure AI Studio Integration**:
   - Many samples interact with resources in the Azure AI Studio
   - You can view created agents, projects, and resources in the Azure AI Studio portal

### Reporting Issues

If you encounter issues that aren't related to SDK limitations, please report them through the GitHub Issues page for this repository. Include:
- SDK versions used
- Error messages (including stack traces)
- Steps to reproduce the issue
- Environment details (OS, Java version, etc.)

