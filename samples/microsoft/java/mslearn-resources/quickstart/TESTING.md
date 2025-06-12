# Testing Azure AI Foundry Java Samples

This document provides instructions for running and testing the Java samples for Azure AI Foundry.

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
| `MODEL_DEPLOYMENT_NAME` | `gpt4o` | The model deployment name to use |
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
testing.bat ChatCompletionSample
```

#### Linux/macOS
```bash
./testing.sh ChatCompletionSample
```

## Available Samples

| Sample Name | Description | Required Env Variables |
|-------------|-------------|------------------------|
| `CreateProject` | Creates a new AI Foundry project | PROJECT_ENDPOINT or AZURE_ENDPOINT |
| `AgentSample` | Creates and manages an AI agent | PROJECT_ENDPOINT or AZURE_ENDPOINT, optionally MODEL_DEPLOYMENT_NAME |
| `ChatCompletionSample` | Basic chat completion via agents | PROJECT_ENDPOINT or AZURE_ENDPOINT, optionally MODEL_DEPLOYMENT_NAME, CHAT_PROMPT |
| `ChatCompletionStreamingSample` | Streaming chat completion | PROJECT_ENDPOINT or AZURE_ENDPOINT, optionally MODEL_DEPLOYMENT_NAME, CHAT_PROMPT, STREAMING_WAIT_TIME |
| `ChatCompletionOpenAISample` | Direct chat using OpenAI SDK | OPENAI_API_KEY, optionally MODEL_DEPLOYMENT_NAME, CHAT_PROMPT |
| `ChatCompletionInferenceSample` | Chat using Azure AI Inference SDK | PROJECT_ENDPOINT or AZURE_ENDPOINT, optionally MODEL_DEPLOYMENT_NAME, CHAT_PROMPT |
| `FileSearchAgentSample` | Demonstrates file search with agents | PROJECT_ENDPOINT or AZURE_ENDPOINT, optionally MODEL_DEPLOYMENT_NAME |
| `EvaluateAgentSample` | Shows agent evaluation | PROJECT_ENDPOINT or AZURE_ENDPOINT, optionally MODEL_DEPLOYMENT_NAME |

## Troubleshooting

### SDK Version Issues

Some samples might fail due to missing classes or methods in the current SDK version. These errors are intentionally not handled with reflection or workarounds to highlight API gaps for package developers.

### Common Errors and Solutions

1. **Authentication Errors**:
   - Make sure you're logged in with `az login`
   - Verify your Azure AD credentials have appropriate permissions

2. **Missing API Methods**:
   - Check for updated SDK versions
   - Some features may not be available in the current SDK version

3. **Connection Timeouts**:
   - Increase the STREAMING_WAIT_TIME for streaming samples
   - Check your network connection and firewall settings

4. **Environment Variable Issues**:
   - Verify that at least PROJECT_ENDPOINT or AZURE_ENDPOINT is set
   - For specific samples like ChatCompletionOpenAISample, make sure OPENAI_API_KEY is set

### Reporting Issues

If you encounter issues that aren't related to SDK limitations, please report them through the appropriate channels.

