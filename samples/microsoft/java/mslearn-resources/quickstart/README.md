# Java QuickStart for Azure AI Services

This quickstart guide demonstrates how to use Azure AI services with Java through multiple SDKs:

1. **Azure AI Inference SDK** - For interacting with Azure-hosted AI models (Azure OpenAI and other models)
2. **Azure AI Agents Persistent SDK** - For creating, running, and evaluating AI agents
3. **Azure AI Projects SDK** - For connecting to Azure AI Projects and accessing deployments
4. **OpenAI Java SDK** - For direct integration with OpenAI platform models

The samples showcase chat completions (both synchronous and streaming), agent creation with document search capabilities, and connecting to Azure AI Projects.

## Understanding the Different SDKs

### Azure AI Inference SDK
- **Use when**: You're working with any Azure AI model (including Azure OpenAI, Phi, or other hosted models)
- **Benefits**: Consistent API across different model types, Azure authentication options, integration with Azure ecosystem
- **Authentication**: Supports both API key and Azure authentication (DefaultAzureCredential)
- **Examples**: `ChatCompletionSample.java`, `ChatCompletionStreamingSample.java`

### Azure AI Agents Persistent SDK
- **Use when**: You need to create agents that can perform complex tasks, access tools, or search documents
- **Benefits**: Persistent agents that maintain state, tool integration, complex conversation management
- **Authentication**: Azure authentication (DefaultAzureCredential)
- **Features**:
  - Create and manage AI agents with different capabilities
  - Configure agent instructions and behavior
  - Add document search capabilities for grounding
  - Evaluate agent performance with metrics and analytics
  - Support for conversation history and context management
  - Tool calling and function execution capabilities
  - Integration with Azure AI Studio agent projects
  - Seamless deployment of production-ready agents
  - Built-in conversation analytics and insights
- **Maven Dependency**:
  ```xml
  <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-ai-agents-persistent</artifactId>
      <version>1.0.0-beta.2</version>
  </dependency>
  ```
- **Examples**: `AgentSample.java`, `FileSearchAgentSample.java`, `EvaluateAgentSample.java`

### Azure AI Projects SDK
- **Use when**: You need to connect to Azure AI Projects and access model deployments
- **Benefits**: Easy access to project resources, deployment information, and managed models
- **Authentication**: Azure authentication (DefaultAzureCredential)
- **Features**:
  - List available model deployments in a project
  - Get deployment details (model type, name, etc.)
  - Access deployment-specific configurations
  - Manage AI project resources programmatically
  - Retrieve connection information for deployments
  - Support for different deployment types (models, agents, etc.)
  - Integration with Azure AI Studio projects
  - Consistent API for accessing different AI resources
- **Maven Dependency**:
  ```xml
  <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-ai-projects</artifactId>
      <version>1.0.0-beta.2</version>
  </dependency>
  ```
- **Examples**: `CreateProject.java`

### OpenAI Java SDK
- **Use when**: You're working directly with the OpenAI platform (not Azure-hosted models)
- **Benefits**: Direct access to OpenAI's latest models and features
- **Authentication**: OpenAI API key only
- **Examples**: `ChatCompletionSampleOpenAI.java`, `ChatCompletionStreamingSampleOpenAI.java`

## Prerequisites 

- Java Development Kit (JDK) 21 or later
    - We recommend the [Microsoft Build of OpenJDK](https://learn.microsoft.com/en-us/java/openjdk/download), which provides free Long-Term Support (LTS)
- Maven 3.9.9 or later
    - Download from the [Apache Maven website](https://maven.apache.org/download.cgi)
- An Azure subscription with access to Azure AI services
    - Free account: [Create an Azure account](https://azure.microsoft.com/free/)
- Access to [Azure AI Foundry](https://ai.azure.com)
- Install the [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)

## Setup

### Development Environment

#### Visual Studio Code Setup (Recommended)

1. **Install Visual Studio Code**
   - Download and install from [VS Code website](https://code.visualstudio.com/)

2. **Install Java Extensions**
   - Install the [Extension Pack for Java](https://marketplace.visualstudio.com/items?itemName=vscjava.vscode-java-pack) which includes:
     - Language Support for Java by Red Hat
     - Debugger for Java
     - Test Runner for Java
     - Maven for Java
     - Project Manager for Java
     - Visual Studio IntelliCode
   
3. **Configure Java in VS Code**
   - Set JAVA_HOME environment variable pointing to your JDK installation
   - Follow the [VS Code Java setup guide](https://code.visualstudio.com/docs/languages/java) for detailed instructions

4. **Install Additional Helpful Extensions**
   - [Azure Tools](https://marketplace.visualstudio.com/items?itemName=ms-vscode.vscode-node-azure-pack) for Azure integration
   - [GitHub Pull Requests](https://marketplace.visualstudio.com/items?itemName=GitHub.vscode-pull-request-github) for GitHub integration

#### Other IDEs
You can also use other IDEs such as:
- [IntelliJ IDEA](https://www.jetbrains.com/idea/) (Community or Ultimate edition)
- [Eclipse](https://www.eclipse.org/downloads/) with the Maven plugin

### Set Environment Variables

You need to set up environment variables for authentication and configuration. Different samples may require different environment variables depending on the SDK they use. Below are instructions for different environments.

#### Bash/Linux/macOS

```bash
# Azure AI Inference SDK Variables (for ChatCompletionSample and ChatCompletionStreamingSample)
export AZURE_ENDPOINT="https://your-resource-name.openai.azure.com"
export AZURE_AI_API_KEY="your-azure-api-key"  # Optional: If not using DefaultAzureCredential
export AZURE_MODEL_DEPLOYMENT_NAME="phi-4"  # Or other model like "gpt-4o"
export AZURE_MODEL_API_PATH="deployments"  # Usually "deployments" for Azure OpenAI

# Azure AI Agents SDK Variables (for AgentSample, FileSearchAgentSample, and EvaluateAgentSample)
export PROJECT_ENDPOINT="https://your-project-endpoint.region.ai.azure.com"  # Only if different from AZURE_ENDPOINT
export MODEL_DEPLOYMENT_NAME="gpt-4o"  # Model to use for agent, e.g., "gpt-4o"
export AGENT_NAME="Java Sample Agent"  # Optional name for the created agent
export AGENT_INSTRUCTIONS="You are a helpful AI assistant that provides clear and concise information."

# OpenAI SDK Variables (for ChatCompletionSampleOpenAI and ChatCompletionStreamingSampleOpenAI)
export OPENAI_API_KEY="your-openai-api-key"  # OpenAI platform API key, not Azure API key
export OPENAI_MODEL="gpt-4o"  # OpenAI model name like "gpt-4o", "gpt-4-turbo"

# General Sample Input
export CHAT_PROMPT="Explain the benefits of Azure AI services for Java developers"
```

#### Windows Command Prompt

```cmd
REM Azure AI Inference SDK Variables (for ChatCompletionSample and ChatCompletionStreamingSample)
set AZURE_ENDPOINT=https://your-resource-name.openai.azure.com
set AZURE_AI_API_KEY=your-azure-api-key
set AZURE_MODEL_DEPLOYMENT_NAME=phi-4
set AZURE_MODEL_API_PATH=deployments

REM Azure AI Agents SDK Variables (for AgentSample, FileSearchAgentSample, and EvaluateAgentSample)
set PROJECT_ENDPOINT=https://your-project-endpoint.region.ai.azure.com
set MODEL_DEPLOYMENT_NAME=gpt-4o
set AGENT_NAME=Java Sample Agent
set AGENT_INSTRUCTIONS=You are a helpful AI assistant that provides clear and concise information.

REM OpenAI SDK Variables (for ChatCompletionSampleOpenAI and ChatCompletionStreamingSampleOpenAI)
set OPENAI_API_KEY=your-openai-api-key
set OPENAI_MODEL=gpt-4o

REM General Sample Input
set CHAT_PROMPT=Explain the benefits of Azure AI services for Java developers
```

### Authentication Setup

This sample uses `DefaultAzureCredential` for authentication, which provides a simpler way to authenticate with Azure services.

1. Install the [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
2. Log in to Azure using the CLI:
   ```bash
   az login
   ```
   
DefaultAzureCredential attempts to authenticate via the following mechanisms in order:
1. Environment credentials
2. Managed Identity credentials
3. Visual Studio Code credentials
4. Azure CLI credentials
5. IntelliJ/Azure Toolkit for IntelliJ credentials
6. Azure PowerShell credentials

For local development, Azure CLI authentication (az login) is the simplest option.

3. Add Maven dependencies:

Download [POM.XML](samples\microsoft\java\mslearn-resources\quickstart\pom.xml) to your Java IDE

## Project Dependencies

This project uses the following key Maven dependencies:

```xml
<!-- Azure AI Agents Persistent SDK -->
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-ai-agents-persistent</artifactId>
    <version>1.0.0-beta.2</version>
</dependency>

<!-- Azure AI Projects SDK -->
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-ai-projects</artifactId>
    <version>1.0.0-beta.2</version>
</dependency>

<!-- Azure AI Inference SDK -->
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-ai-inference</artifactId>
    <version>1.0.0-beta.5</version>
</dependency>

<!-- OpenAI Java SDK -->
<dependency>
    <groupId>com.openai</groupId>
    <artifactId>openai-java</artifactId>
    <version>2.7.0</version>
</dependency>

<!-- Azure Identity for authentication -->
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
    <version>1.10.4</version>
</dependency>
```

These dependencies are already included in the project's pom.xml file.

## Sample Descriptions and Usage

### 1. Connecting to Azure AI Projects

The `CreateProject.java` sample demonstrates how to use the Azure AI Projects SDK to:
- Connect to an existing Azure AI Project
- List available model deployments in the project
- Provide detailed information about each deployment (name, type, etc.)

**Key features:**
```java
// Create client with DefaultAzureCredential (recommended for Azure services)
TokenCredential credential = new DefaultAzureCredentialBuilder().build();

// Create a DeploymentsClient to list available model deployments
DeploymentsClient deploymentsClient = new AIProjectClientBuilder()
    .endpoint(endpoint)
    .credential(credential)
    .buildDeploymentsClient();

// List deployments with proper error handling
for (Deployment d : deploymentsClient.listDeployments()) {
    logger.info("Found deployment: {}, Type: {}", d.getName(), d.getType());
}
```

**Environment variables needed:**
- `AZURE_ENDPOINT`: The endpoint URL for your Azure AI Project

**Key SDK capabilities demonstrated:**
- Creating an authenticated connection to Azure AI Projects using DefaultAzureCredential
- Utilizing the AIProjectClientBuilder to access deployment information
- Listing and iterating through available deployments
- Accessing deployment properties like name, type, and other metadata
- Following Azure SDK for Java patterns and best practices

The Azure AI Projects SDK (`com.azure:azure-ai-projects:1.0.0-beta.2`) provides a comprehensive client library for interacting with Azure AI Projects programmatically. It allows developers to discover and connect to AI resources that have been deployed to Azure AI Studio projects.

### 2. Azure AI Inference SDK - Chat Completion

The `ChatCompletionSample.java` sample demonstrates how to:
- Set up authentication with either API key or Azure credentials
- Configure an endpoint for any Azure AI model
- Create a synchronous chat completion request with a prompt
- Process and handle the model's response

**Key features:**
```java
// Configure endpoint with correct format for Azure AI models
String fullEndpoint = endpoint;
if (!fullEndpoint.endsWith("/")) {
    fullEndpoint += "/";
}
fullEndpoint += apiPath + "/" + deploymentName;

// Create client with either API key or Azure credentials
ChatCompletionsClient client;
if (apiKey != null && !apiKey.isEmpty()) {
    client = new ChatCompletionsClientBuilder()
        .credential(new AzureKeyCredential(apiKey))
        .endpoint(fullEndpoint)
        .buildClient();
} else {
    DefaultAzureCredential credential = new DefaultAzureCredentialBuilder().build();
    client = new ChatCompletionsClientBuilder()
        .credential(credential)
        .endpoint(fullEndpoint)
        .buildClient();
}

// Call the API with a simple prompt and get response
ChatCompletions completions = client.complete(prompt);
String content = completions.getChoice().getMessage().getContent();
```

**Environment variables needed:**
- `AZURE_ENDPOINT`: Required. The base endpoint for your Azure AI service
- `AZURE_AI_API_KEY`: Optional. The API key for authentication (if not using DefaultAzureCredential)
- `AZURE_MODEL_DEPLOYMENT_NAME`: Optional. The model deployment name (defaults to "phi-4")
- `AZURE_MODEL_API_PATH`: Optional. The API path segment (defaults to "deployments")
- `CHAT_PROMPT`: Optional. The prompt to send to the model

### 3. Azure AI Inference SDK - Streaming Chat Completion

The `ChatCompletionStreamingSample.java` sample demonstrates how to:
- Set up a streaming chat completion client with authentication options
- Process incoming tokens in real-time as they arrive
- Collect the complete response for final processing

**Key features:**
```java
// Create a streaming-enabled client similar to the non-streaming version
// Client setup is identical to ChatCompletionSample.java

// Create message list for the chat conversation
List<ChatRequestMessage> chatMessages = new ArrayList<>();
chatMessages.add(new ChatRequestSystemMessage("You are a helpful assistant providing clear and concise information."));
chatMessages.add(new ChatRequestUserMessage(prompt));

// Configure and start the streaming completion request
ChatCompletionsOptions options = new ChatCompletionsOptions(chatMessages);
// options.setTemperature(0.7); // Optional: Adjust creativity level
// options.setMaxTokens(1000);  // Optional: Limit response length

// Get the stream of updates
IterableStream<StreamingChatCompletionsUpdate> chatCompletionsStream = client.completeStream(options);

// Process streaming updates as they arrive
StringBuilder contentBuilder = new StringBuilder();
chatCompletionsStream.stream().forEach(chatCompletions -> {
    // Skip empty updates
    if (CoreUtils.isNullOrEmpty(chatCompletions.getChoices())) {
        return;
    }
    
    StreamingChatResponseMessageUpdate delta = chatCompletions.getChoice().getDelta();
    
    // First update usually contains just the role
    if (delta.getRole() != null) {
        logger.info("Role: " + delta.getRole());
    }
    
    // Process content tokens as they arrive
    if (delta.getContent() != null) {
        String token = delta.getContent();
        logger.info(token); // Display each token
        contentBuilder.append(token); // Build complete response
    }
});
```

**Environment variables needed:**
- Same as ChatCompletionSample.java

### 4. OpenAI SDK - Chat Completion

The `ChatCompletionSampleOpenAI.java` sample demonstrates how to:
- Use the official OpenAI Java SDK to interact with OpenAI platform models
- Create a client authenticated with an OpenAI API key
- Send a completion request and process the response

**Key features:**
```java
// Build the OpenAI client - note this is different from Azure OpenAI
OpenAIClient client = OpenAIOkHttpClient.builder()
    .apiKey(apiKey)
    .build();

// Prepare request parameters
ChatCompletionCreateParams params = ChatCompletionCreateParams.builder()
    .addUserMessage(prompt)
    .model(modelEnv)  // Use the model name directly
    .build();

// Send request and get response
ChatCompletion completion = client.chat().completions().create(params);

// Extract and process the content
String content = completion.choices().get(0).message().content().orElse("No response content");
```

**Environment variables needed:**
- `OPENAI_API_KEY`: Required. The API key for OpenAI authentication
- `OPENAI_MODEL`: Required. The model to use (e.g., "gpt-4o", "gpt-4-turbo")
- `CHAT_PROMPT`: Optional. The prompt to send

### 5. OpenAI SDK - Streaming Chat Completion

The `ChatCompletionStreamingSampleOpenAI.java` sample demonstrates how to:
- Use the OpenAI Java SDK for streaming completions
- Process tokens as they arrive in real-time
- Manage the stream with proper resource handling

**Key features:**
```java
// Client setup similar to ChatCompletionSampleOpenAI.java

// Configure streaming parameters
ChatCompletionCreateParams params = ChatCompletionCreateParams.builder()
    .addUserMessage(prompt)
    .model(modelEnv)
    .build();

// Use try-with-resources to ensure the stream is properly closed
try (StreamResponse<ChatCompletionChunk> stream = 
         client.chat().completions().createStreaming(params)) {
    
    // Process the stream using Java Stream API with functional operations
    stream.stream()
          .flatMap(ch -> ch.choices().stream())
          .flatMap(choice -> choice.delta().content().stream())
          .forEach(token -> logger.info("{}", token));
}
```

**Environment variables needed:**
- Same as ChatCompletionSampleOpenAI.java

### 6. Azure AI Agents - Creating and Running an Agent

The `AgentSample.java` sample demonstrates how to use the Azure AI Agents Persistent SDK to:
- Create a persistent agent that maintains state between interactions
- Configure the agent with custom instructions and a model
- Create a thread and run with the agent
- Access and display agent properties

**Key features:**
```java
// Create Azure credential with DefaultAzureCredentialBuilder
TokenCredential credential = new DefaultAzureCredentialBuilder().build();

// Build the general agents client
PersistentAgentsClient agentsClient = new PersistentAgentsClientBuilder()
    .endpoint(projectEndpoint)
    .credential(credential)
    .buildClient();

// Get the administration client for agent management
PersistentAgentsAdministrationClient adminClient =
    agentsClient.getPersistentAgentsAdministrationClient();

// Create an agent with name, model, and instructions
PersistentAgent agent = adminClient.createAgent(
    new CreateAgentOptions(modelName)
        .setName(agentName)
        .setInstructions(instructions)
);

// Get model information
logger.info("Agent model: {}", agent.getModel());

// Start a thread/run on the general client
ThreadRun runResult = agentsClient.createThreadAndRun(
    new CreateThreadAndRunOptions(agent.getId())
);
```

**Environment variables needed:**
- `PROJECT_ENDPOINT` or `AZURE_ENDPOINT`: Required. The endpoint for your Azure AI service
- `MODEL_DEPLOYMENT_NAME`: Optional. The model to use (defaults to "gpt-4o")
- `AGENT_NAME`: Optional. The name for the created agent
- `AGENT_INSTRUCTIONS`: Optional. Instructions that define the agent's behavior

**Key SDK capabilities demonstrated:**
- Using the `azure-ai-agents-persistent` SDK (version 1.0.0-beta.2) for agent management
- Creating a PersistentAgentsClient with secure authentication
- Working with agent administration operations
- Configuring agent properties (name, model, instructions)
- Creating and running agent threads for conversation
- Managing agent state across interactions
- Retrieving agent run results and messages

The Azure AI Agents Persistent SDK provides a comprehensive client library for creating, configuring, and running AI agents that maintain state between user interactions. This enables more complex and context-aware agent behaviors compared to stateless chat completions.

### 7. Azure AI Agents - File Search Agent

The `FileSearchAgentSample.java` sample demonstrates how to use the Azure AI Agents Persistent SDK to:
- Create a temporary document file for demonstration purposes
- Create an agent that can access and search through document content
- Start a thread to interact with the document-aware agent
- Configure knowledge sources for grounded responses

**Key features:**
```java
// Create sample document with cloud computing information
Path tmpFile = createSampleDocument();
String filePreview = Files.readString(tmpFile).substring(0, 200) + "...";
logger.info("{}", filePreview);

// Create the agent with proper configuration
PersistentAgent agent = adminClient.createAgent(
    new CreateAgentOptions(modelName)
        .setName(agentName)
        .setInstructions(instructions)
);

// Start a thread and run on the general client
ThreadRun threadRun = agentsClient.createThreadAndRun(
    new CreateThreadAndRunOptions(agent.getId())
);
```

**Key SDK capabilities demonstrated:**
- Using the `azure-ai-agents-persistent` SDK (version 1.0.0-beta.2) for advanced agent features
- Adding and configuring document knowledge sources for agents
- Creating temporary files for agent access with proper lifecycle management
- Enabling document search capabilities within agent conversations
- Building agents that can answer questions based on document content
- Using agent-based retrieval augmented generation techniques

### 8. Azure AI Agents - Agent Evaluation

The `EvaluateAgentSample.java` sample demonstrates how to use the Azure AI Agents Persistent SDK to:
- Set up and configure an agent for evaluation purposes
- Understand the evaluation capabilities in the Azure AI Agents SDK
- Create a thread and run with the agent
- Explore evaluation-related methods and models available in the SDK

**Key features:**
```java
// Create an agent with proper error handling
PersistentAgent agent = agentClient.createAgent(new CreateAgentOptions(modelName)
    .setName(agentName)
    .setInstructions(instructions)
);

// Create a thread and run with the agent
ThreadRun runResult = agentsClient.createThreadAndRun(new CreateThreadAndRunOptions(agent.getId()));

// Display information about evaluation capabilities
logger.info("Displaying evaluation capabilities in the latest Azure AI SDK");
logger.info("\nEvaluation capabilities in PersistentAgentsAdministrationClient:");
logger.info("- evaluateAgent(String agentId, EvaluateAgentOptions options)");
logger.info("- getEvaluation(String evaluationId)");
logger.info("- getEvaluations(String agentId)");
logger.info("- cancelEvaluation(String evaluationId)");

// Display evaluation-related models and options
logger.info("\nEvaluation-related models and options:");
```

**Key SDK capabilities demonstrated:**
- Using the `azure-ai-agents-persistent` SDK (version 1.0.0-beta.2) for agent evaluation
- Understanding the evaluation framework within the SDK
- Accessing evaluation methods in the PersistentAgentsAdministrationClient
- Creating and configuring agents for evaluation purposes
- Examining available metrics and assessment options
- Working with various evaluation-related models in the API
logger.info("- EvaluateAgentOptions - Configuration for agent evaluation");
logger.info("- AgentEvaluation - Contains evaluation results");
logger.info("- EvaluationMetrics - Performance metrics from evaluation");
logger.info("- EvaluationStatus - Status of an evaluation");
```

**Environment variables needed:**
- Same as AgentSample.java

## Running the Samples

Each sample is a standalone Java program that demonstrates specific functionality. You can run them using your preferred Java development environment:

### Using Maven from Command Line

1. Navigate to the quickstart directory containing the `pom.xml` file
2. Set the required environment variables for the sample you want to run
3. Run the sample using Maven:

```bash
# For example, to run the ChatCompletionSample
mvn compile exec:java -Dexec.mainClass="com.azure.ai.foundry.samples.ChatCompletionSample"

# Run the streaming sample
mvn compile exec:java -Dexec.mainClass="com.azure.ai.foundry.samples.ChatCompletionStreamingSample"

# Run the agent sample
mvn compile exec:java -Dexec.mainClass="com.azure.ai.foundry.samples.AgentSample"
```

### Using Visual Studio Code

1. Open the project in VS Code
2. Set the required environment variables in your `.env` file or system environment
3. Open the Java file you want to run
4. Click the "Run" button that appears above the `main` method, or use the Run menu

### Using Testing Scripts

For convenience, we've provided automated testing scripts that can run any or all samples:

- **Windows**: `testing.bat [SampleClassName]`
- **Linux/macOS**: `./testing.sh [SampleClassName]`

Running without a sample name will execute all samples in sequence.

These testing scripts will:
- Display information about the SDK versions being used (1.0.0-beta.2 for Agents/Projects)
- Validate your environment configuration before running the tests
- Provide formatted output with clear success/failure indicators
- Handle common setup tasks for you

For detailed testing instructions, SDK features overview, and troubleshooting tips for first-time users, refer to [TESTING.md](TESTING.md).

### Common Issues and Troubleshooting

#### Authentication Problems
- If you see 401 (Unauthorized) errors, check that your API key or Azure credentials are valid
- For DefaultAzureCredential, ensure you're logged in with `az login` and have proper permissions

#### Endpoint Format Issues
- Ensure your endpoint URL follows the correct format (e.g., `https://your-resource-name.openai.azure.com`)
- For the Inference SDK, the deployment name should be added to the path (the samples do this automatically)

#### Model Availability
- If you see 404 (Not Found) errors, verify that the model deployment exists in your Azure resource
- Some models may not be available in all regions or subscriptions

## Understanding Azure Authentication with DefaultAzureCredential

This sample uses `DefaultAzureCredential` for authentication with Azure services, which provides a more secure and flexible approach compared to API keys. Below is an explanation of how it works and why it's the recommended approach:

### What is DefaultAzureCredential?

`DefaultAzureCredential` is part of the Azure Identity library and provides a simplified way to authenticate with Azure services. It tries multiple authentication methods in sequence until one succeeds, making your application work in different environments without code changes.

### Authentication Methods (in order)

1. **Environment Variables** - Checks for credentials in environment variables
2. **Managed Identity** - Used in Azure-hosted environments like VMs, App Service, or Azure Functions
3. **Visual Studio Code** - Uses credentials from VS Code's Azure extension
4. **Azure CLI** - Uses credentials from your `az login` session
5. **Azure PowerShell** - Uses credentials from your PowerShell login
6. **Interactive Browser** - Opens a browser for interactive login (if enabled)

### Benefits of Using DefaultAzureCredential

1. **Better Security** - No need to store API keys in your code or configuration files
2. **Flexibility** - Your code works in different environments (local development, Azure-hosted) without changes
3. **Simplified Management** - Leverage existing Azure identity management features
4. **Compliance** - Supports enterprise security policies and auditing requirements
5. **Access Control** - Fine-grained RBAC (Role-Based Access Control) with Azure AD

### How to Set Up for Local Development

For local development, the easiest approach is to use Azure CLI authentication:

1. Install the Azure CLI: [https://docs.microsoft.com/cli/azure/install-azure-cli](https://docs.microsoft.com/cli/azure/install-azure-cli)
2. Login to Azure:
   ```bash
   az login
   ```
3. If you have multiple subscriptions, set your active subscription:
   ```bash
   az account set --subscription <subscription-id-or-name>
   ```
4. Your Java code will automatically use these credentials when you create a DefaultAzureCredential.

### Troubleshooting Authentication

If you encounter authentication issues:

1. Ensure you're logged in via Azure CLI (`az login`)
2. Check that your account has the necessary permissions for Azure AI Foundry
3. For multiple subscriptions, verify you're using the correct one (`az account show`)
4. If needed, you can set the `AZURE_SUBSCRIPTION_ID` environment variable

### For Production Use

In production environments:

1. **Azure-hosted apps** - Use Managed Identity when possible
2. **Other environments** - Consider service principals with client ID/secret or certificates
3. Always apply the principle of least privilege when assigning permissions

For more information, see the [Azure Identity library documentation](https://docs.microsoft.com/java/api/overview/azure/identity-readme).

## SDK Comparison Summary

This quickstart demonstrates the use of multiple Azure AI SDKs, each with specific strengths:

### Azure AI Agents Persistent SDK (1.0.0-beta.2)
- **Primary purpose**: Creating and managing AI agents with persistent state
- **When to use**: For building agents that can maintain context, use tools, access documents
- **Key strengths**: Conversation management, document search, agent evaluation
- **Authentication**: DefaultAzureCredential (recommended) or API key

### Azure AI Projects SDK (1.0.0-beta.2)
- **Primary purpose**: Connecting to Azure AI Projects and accessing deployments
- **When to use**: For programmatically managing AI resources deployed via Azure AI Studio
- **Key strengths**: Project-level organization, deployment discovery
- **Authentication**: DefaultAzureCredential

### Azure AI Inference SDK
- **Primary purpose**: Direct interaction with Azure-hosted AI models
- **When to use**: For basic chat completion or content generation needs
- **Key strengths**: Unified API for different model types, streaming support
- **Authentication**: DefaultAzureCredential or API key

### OpenAI Java SDK
- **Primary purpose**: Interaction with OpenAI platform models
- **When to use**: When targeting OpenAI platform directly (not Azure)
- **Key strengths**: Latest OpenAI features, no Azure dependency
- **Authentication**: OpenAI API key only

## Next Steps

After exploring these samples, you can:

1. Integrate these SDKs into your own applications
2. Explore the Azure AI Studio to create and deploy more complex agents
3. Combine multiple SDKs to create sophisticated AI experiences
4. Deploy your agents and completions to production environments

For the latest documentation and updates, visit the [Azure AI documentation](https://docs.microsoft.com/azure/ai-services/) and [Azure AI Foundry](https://ai.azure.com).

