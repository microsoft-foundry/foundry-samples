# Azure AI Foundry SDK Java Samples

This directory contains Java sample code for Azure AI services using the Azure AI Inference SDK, Azure AI Agents Persistent SDK, Azure AI Projects SDK, and OpenAI Java SDK.

## Key SDKs Used in These Samples

### 1. Azure AI Agents Persistent SDK
- **Maven Dependency**: `com.azure:azure-ai-agents-persistent:1.0.0-beta.2`
- **Purpose**: Create, manage, and interact with persistent AI agents capable of maintaining state and performing complex tasks
- **Key Features**:
  - Built-in conversation management and state tracking
  - Document search and retrieval capabilities
  - Agent evaluation and performance metrics
  - Integration with Azure AI models and services
  - Tool calling and function execution

### 2. Azure AI Projects SDK
- **Maven Dependency**: `com.azure:azure-ai-projects:1.0.0-beta.2`
- **Purpose**: Manage and interact with Azure AI Projects and their deployments
- **Key Features**:
  - List and manage project deployments
  - Access deployment information (model type, configuration)
  - Retrieve connection details for different AI resources
  - Unified interface for Azure AI Studio projects

### 3. Azure AI Inference SDK
- **Maven Dependency**: `com.azure:azure-ai-inference:1.0.0-beta.5`
- **Purpose**: Direct interaction with Azure-hosted AI models
- **Key Features**:
  - Synchronous and streaming completions
  - Support for multiple model providers
  - Consistent API across different model types

### 4. OpenAI Java SDK
- **Maven Dependency**: `com.openai:openai-java:2.7.0`
- **Purpose**: Direct integration with OpenAI platform models (not Azure-hosted)

## Available Samples

### Azure AI Inference SDK Samples
1. **ChatCompletionSample** - Shows how to use the Azure AI Inference SDK for synchronous chat completions with any Azure AI model
2. **ChatCompletionStreamingSample** - Demonstrates streaming chat completions using Azure AI Inference SDK for a more responsive user experience

### OpenAI SDK Samples
3. **ChatCompletionSampleOpenAI** - Shows how to use the official OpenAI Java SDK for chat completions with OpenAI models
4. **ChatCompletionStreamingSampleOpenAI** - Demonstrates streaming chat completions using the OpenAI Java SDK

### Azure AI Agents Persistent SDK Samples
5. **AgentSample** - Shows how to create and run a persistent agent using the Azure AI Agents SDK
6. **FileSearchAgentSample** - Demonstrates adding file search capabilities to an agent for document-based Q&A
7. **EvaluateAgentSample** - Shows how to evaluate agent performance with different metrics

### Azure AI Projects SDK Samples
8. **CreateProject** - Demonstrates connecting to an Azure AI Project and listing available model deployments

## Running the Samples

See the main [README.md](../../README.md) file for instructions on how to set up and run these samples.

For detailed testing procedures, including automated testing scripts, SDK features overview, and troubleshooting guidance for first-time users, refer to [TESTING.md](../../TESTING.md).

### Testing Scripts

We've provided automated testing scripts that can help you quickly validate your environment and run samples:
- **Windows**: Use `testing.bat [SampleClassName]` from the project root
- **Linux/macOS**: Use `./testing.sh [SampleClassName]` from the project root

These scripts provide SDK version information, environment validation, and clearly formatted output.
