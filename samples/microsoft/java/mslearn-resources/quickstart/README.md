# Java QuickStart for Azure AI Foundry SDK

This quickstart guide demonstrates how to use the Azure AI Foundry SDK with Java to create projects, run chat completions, create agents, add file search capabilities, and evaluate agent runs.

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

### Rename .env.template to .env

Rename the `.env.template` file to `.env` and fill in your Azure credentials:

```properties
AZURE_ENDPOINT=your_endpoint_here
AZURE_DEPLOYMENT=your_deployment_name_here
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

## Create a Project and Model Deployment


```java
// Import necessary packages for working with Azure AI Foundry
import com.azure.ai.projects.ProjectsClient;
import com.azure.ai.projects.ProjectsClientBuilder;
import com.azure.ai.projects.models.Project;
import com.azure.ai.projects.models.deployment.Deployment;
import com.azure.ai.projects.models.deployment.DeploymentOptions;
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;

// Create a DefaultAzureCredential for authentication
// This automatically uses the most appropriate authentication method based on the environment
// For local development, this will use your Azure CLI credentials (az login)
DefaultAzureCredential credential = new DefaultAzureCredentialBuilder().build();

// Create a ProjectsClient to interact with Azure AI Foundry services
// This client requires an authentication credential and an endpoint URL
ProjectsClient client = new ProjectsClientBuilder()
    .credential(credential)
    .endpoint(System.getenv("AZURE_ENDPOINT"))
    .buildClient();

// Create a new project with a name and description
// Projects serve as containers for AI resources like model deployments and agents
System.out.println("Creating project...");
Project project = client.createProject("My Sample Project", "A project created using the Java SDK");
System.out.println("Project created successfully!");
System.out.println("Project Name: " + project.getName() + " with ID: " + project.getId());

// Configure a model deployment in the project
// The deployment makes a specific AI model available for use in this project
System.out.println("\nConfiguring model deployment...");
DeploymentOptions deploymentOptions = new DeploymentOptions()
    .setName("my-deployment")          // Descriptive name for the deployment
    .setModel("gpt-4")                 // Specify which model to deploy
    .setDescription("Sample model deployment");

// Create the deployment with the configured options
Deployment deployment = client.createDeployment(project.getId(), deploymentOptions);
System.out.println("Model deployed successfully!");
System.out.println("Deployment Name: " + deployment.getName() + " with ID: " + deployment.getId());

// Store deployment ID for later use in other samples
System.out.println("\nSet DEPLOYMENT_ID=" + deployment.getId() + " in your .env file to use this deployment in other samples");
```

## Chat Completion

```java
// Import necessary packages for chat completion
import com.azure.ai.projects.ProjectsClient;
import com.azure.ai.projects.ProjectsClientBuilder;
import com.azure.ai.projects.models.chat.ChatClient;
import com.azure.ai.projects.models.chat.ChatCompletion;
import com.azure.ai.projects.models.chat.ChatCompletionOptions;
import com.azure.ai.projects.models.chat.ChatMessage;
import com.azure.ai.projects.models.chat.ChatRole;
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import java.util.Arrays;
import java.util.List;

// Create a DefaultAzureCredential for authentication
// This automatically uses the most appropriate authentication method based on the environment
// For local development, this will use your Azure CLI credentials (az login)
DefaultAzureCredential credential = new DefaultAzureCredentialBuilder().build();

// Create a ProjectsClient to interact with Azure AI Foundry services
ProjectsClient client = new ProjectsClientBuilder()
    .credential(credential)
    .endpoint(System.getenv("AZURE_ENDPOINT"))
    .buildClient();

// Get a ChatClient for the specified model deployment
// This client provides access to chat completion functionality
ChatClient chatClient = client.getChatClient(System.getenv("AZURE_DEPLOYMENT"));

// Create a list of messages to form the conversation
// This includes a system message that defines the assistant's behavior
// and a user message containing the user's question or prompt
List<ChatMessage> messages = Arrays.asList(
    new ChatMessage(ChatRole.SYSTEM, "You are a helpful assistant specialized in Azure cloud services."),
    new ChatMessage(ChatRole.USER, "Explain the benefits of Azure AI Foundry in 3-4 paragraphs.")
);

// Configure chat completion options to control the response
// - Temperature controls randomness (higher = more creative, lower = more deterministic)
// - MaxTokens limits the length of the response (1 token ≈ 4 characters in English)
ChatCompletionOptions options = new ChatCompletionOptions(messages)
    .setTemperature(0.7)  // Balanced between deterministic and creative
    .setMaxTokens(800);   // Limit response length to avoid very long outputs

System.out.println("Sending chat completion request...");

// Send the request and get the AI-generated completion
ChatCompletion completion = chatClient.getChatCompletion(options);

// Display the model's response
System.out.println("\nResponse from AI assistant:");
System.out.println(completion.getChoices().get(0).getMessage().getContent());

// Output usage statistics, which can be helpful for monitoring token consumption
System.out.println("\nToken Usage Statistics:");
System.out.println("Prompt Tokens: " + completion.getUsage().getPromptTokens());
System.out.println("Completion Tokens: " + completion.getUsage().getCompletionTokens());
System.out.println("Total Tokens: " + completion.getUsage().getTotalTokens());
```

## Create and Run an Agent

```java
// Import necessary packages for working with agents
import com.azure.ai.projects.ProjectsClient;
import com.azure.ai.projects.ProjectsClientBuilder;
import com.azure.ai.projects.models.agent.Agent;
import com.azure.ai.projects.models.agent.AgentClient;
import com.azure.ai.projects.models.agent.AgentMessage;
import com.azure.ai.projects.models.agent.AgentOptions;
import com.azure.ai.projects.models.agent.AgentRole;
import com.azure.ai.projects.models.agent.AgentRun;
import com.azure.ai.projects.models.agent.AgentRunStatus;
import com.azure.ai.projects.models.agent.AgentThread;
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;

// Create a DefaultAzureCredential for authentication
// This automatically uses the most appropriate authentication method based on the environment
// For local development, this will use your Azure CLI credentials (az login)
DefaultAzureCredential credential = new DefaultAzureCredentialBuilder().build();

// Create a ProjectsClient to interact with Azure AI Foundry services
ProjectsClient client = new ProjectsClientBuilder()
    .credential(credential)
    .endpoint(System.getenv("AZURE_ENDPOINT"))
    .buildClient();

// Get an AgentClient, which provides operations for working with AI agents
// This includes creating, configuring, and running agents
AgentClient agentClient = client.getAgentClient();

// Create a new agent with specialized capabilities and instructions
// The agent is configured with a name, description, and instructions that define its behavior
System.out.println("Creating agent...");
Agent agent = agentClient.createAgent(new AgentOptions()
    .setName("Research Assistant")                       // Descriptive name for the agent
    .setDescription("An agent that helps with research tasks")  // Brief description of the agent's purpose
    .setInstructions("You are a research assistant. Help users find information and summarize content.") // Detailed instructions
    .setModel(System.getenv("AZURE_DEPLOYMENT")));       // The underlying AI model to power the agent

System.out.println("Agent created successfully!");
System.out.println("Agent Name: " + agent.getName());
System.out.println("Agent ID: " + agent.getId());

// Create a thread for the conversation with the agent
// Threads maintain conversation history and state across multiple interactions
System.out.println("\nCreating conversation thread...");
AgentThread thread = agentClient.createThread();
System.out.println("Thread created with ID: " + thread.getId());

// Create a user message with the task for the agent
// This defines what we want the agent to help us with
System.out.println("\nCreating user message...");
AgentMessage userMessage = new AgentMessage()
    .setRole(AgentRole.USER)                            // Message is from the user
    .setContent("Research the benefits of cloud computing and list the top 3 advantages");  // The user's request

// Run the agent by creating a run with the thread ID, agent ID, and user message
// This starts the agent's processing of the user's request
System.out.println("Starting agent run...");
AgentRun run = agentClient.createRun(thread.getId(), agent.getId(), userMessage);
System.out.println("Run started with ID: " + run.getId());

// Wait for the run to complete
// Agent runs are asynchronous, so we need to poll for completion
System.out.println("\nWaiting for agent to complete the task...");
while (run.getStatus() != AgentRunStatus.COMPLETED && 
       run.getStatus() != AgentRunStatus.FAILED && 
       run.getStatus() != AgentRunStatus.CANCELLED) {
    try {
        // Wait a bit before checking again to avoid excessive API calls
        Thread.sleep(1000);
        run = agentClient.getRun(thread.getId(), run.getId());
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new RuntimeException("Thread was interrupted", e);
    }
}

// Check if the run completed successfully
if (run.getStatus() == AgentRunStatus.COMPLETED) {
    System.out.println("Agent run completed successfully!");
    
    // Retrieve all messages from the thread to get the agent's response
    List<AgentMessage> messages = agentClient.getMessages(thread.getId());
    
    // Display the conversation
    System.out.println("\nConversation:");
    for (AgentMessage message : messages) {
        System.out.println(message.getRole() + ": " + message.getContent());
    }
} else {
    System.out.println("Agent run failed with status: " + run.getStatus());
}
```

## Add File Search to Agent

Add file search capabilities to your agent:

```java
// Import necessary packages for file search functionality
import com.azure.ai.projects.ProjectsClient;
import com.azure.ai.projects.ProjectsClientBuilder;
import com.azure.ai.projects.models.agent.Agent;
import com.azure.ai.projects.models.agent.AgentClient;
import com.azure.ai.projects.models.agent.AgentMessage;
import com.azure.ai.projects.models.agent.AgentOptions;
import com.azure.ai.projects.models.agent.AgentRole;
import com.azure.ai.projects.models.agent.AgentRun;
import com.azure.ai.projects.models.agent.AgentRunStatus;
import com.azure.ai.projects.models.agent.AgentThread;
import com.azure.ai.projects.models.agent.FileTool;
import com.azure.ai.projects.models.file.File;
import com.azure.ai.projects.models.file.FileClient;
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import java.nio.file.Files;
import java.nio.file.Path;

// Create a DefaultAzureCredential for authentication
DefaultAzureCredential credential = new DefaultAzureCredentialBuilder().build();

// Create a ProjectsClient to interact with Azure AI Foundry services
ProjectsClient client = new ProjectsClientBuilder()
    .credential(credential)
    .endpoint(System.getenv("AZURE_ENDPOINT"))
    .buildClient();

// First, create a document for the agent to search through
// In a real application, you would use your own existing documents
Path tempFile = Files.createTempFile("cloud-computing-doc", ".md");
String content = "# Cloud Computing Overview\n\n" +
    "Cloud computing is the delivery of computing services over the internet, including servers, " +
    "storage, databases, networking, software, and analytics.\n\n" +
    "## Key Benefits\n\n" +
    "1. **Cost Efficiency**: Pay only for the resources you use, reducing capital expenditure on hardware and infrastructure.\n\n" +
    "2. **Scalability**: Easily scale resources up or down based on demand, providing flexibility as your needs change.\n\n" +
    "3. **Global Reach**: Deploy applications globally in minutes, improving performance and user experience.\n\n" +
    "4. **Reliability**: Cloud services typically offer built-in redundancy and backup capabilities for improved business continuity.\n\n" +
    "5. **Security**: Major cloud providers invest heavily in security measures that many organizations couldn't afford on their own.\n\n";
Files.writeString(tempFile, content);
    .endpoint(System.getenv("AZURE_ENDPOINT"))
    .buildClient();

// Get an agent client
AgentClient agentClient = client.getAgentClient();

// Upload a file for search
FileClient fileClient = client.getFileClient();
File uploadedFile = fileClient.uploadFile("path/to/your/document.pdf");

// Add file search capability to the agent
Agent agent = agentClient.createAgent(new AgentOptions()
    .setName("Document Assistant")
    .setDescription("An agent that helps with document searching")
    .setInstructions("You are a document assistant. Help users find information in their documents.")
    .setModel(System.getenv("AZURE_DEPLOYMENT"))
    .addTool(new FileTool()
        .addFile(uploadedFile.getId())));

// Run the agent with a file search query
AgentThread thread = agentClient.createThread();
AgentMessage userMessage = new AgentMessage()
    .setRole(AgentRole.USER)
    .setContent("Find information about cloud computing in my document");

AgentRun run = agentClient.createRun(thread.getId(), agent.getId(), userMessage);

// Wait for the run to complete, similar to other agent examples
System.out.println("\nWaiting for agent run with file search to complete...");
while (run.getStatus() != AgentRunStatus.COMPLETED && 
       run.getStatus() != AgentRunStatus.FAILED && 
       run.getStatus() != AgentRunStatus.CANCELLED) {
    try {
        Thread.sleep(1000);
        run = agentClient.getRun(thread.getId(), run.getId());
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new RuntimeException("Thread was interrupted", e);
    }
}

// Check if the run completed successfully and display the results
if (run.getStatus() == AgentRunStatus.COMPLETED) {
    System.out.println("Agent run with file search completed successfully!");
    
    // Get all messages from the thread to display the conversation
    List<AgentMessage> messages = agentClient.getMessages(thread.getId());
    
    System.out.println("\nConversation with file search results:");
    for (AgentMessage message : messages) {
        System.out.println(message.getRole() + ": " + message.getContent());
    }
    
    // In a real application, remember to clean up temporary files when done
    Files.deleteIfExists(tempFile);
} else {
    System.out.println("Agent run with file search failed with status: " + run.getStatus());
}
```

## Evaluate Agent Run

Evaluate how well the agent performed on a given task:

```java
// Import necessary packages for evaluation
import com.azure.ai.projects.ProjectsClient;
import com.azure.ai.projects.ProjectsClientBuilder;
import com.azure.ai.projects.models.evaluation.AgentEvaluation;
import com.azure.ai.projects.models.evaluation.EvaluationClient;
import com.azure.ai.projects.models.evaluation.EvaluationMetric;
import com.azure.ai.projects.models.evaluation.EvaluationOptions;
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import java.util.Map;

// Create a DefaultAzureCredential for authentication
DefaultAzureCredential credential = new DefaultAzureCredentialBuilder().build();

// Create a ProjectsClient to interact with Azure AI Foundry services
ProjectsClient client = new ProjectsClientBuilder()
    .credential(credential)
    .endpoint(System.getenv("AZURE_ENDPOINT"))
    .buildClient();

// Get an EvaluationClient to assess agent performance
// This client provides operations to evaluate how well an agent performed on different tasks
EvaluationClient evaluationClient = client.getEvaluationClient();

// Get the ID of the agent run you want to evaluate
// In a real-world scenario, you would use an actual run ID from a previous agent execution
// For this example, we'll assume you have a run ID from a previous section
String agentRunId = "your-previous-agent-run-id"; // Replace with actual run ID

// Configure evaluation options to specify which metrics to measure
// Different metrics assess different aspects of agent performance:
// - HELPFULNESS: measures how helpful the responses are to users
// - ACCURACY: measures factual correctness of the responses
// - SAFETY: measures how well the agent avoids harmful content
System.out.println("Creating evaluation for agent run: " + agentRunId);
EvaluationOptions evaluationOptions = new EvaluationOptions()
    .addMetric(EvaluationMetric.HELPFULNESS)  // Evaluate how helpful the responses were
    .addMetric(EvaluationMetric.ACCURACY);    // Evaluate how accurate the information was

// Start the evaluation process
AgentEvaluation evaluation = evaluationClient.evaluateAgentRun(
    agentRunId,           // The ID of the run to evaluate
    evaluationOptions     // The metrics to evaluate
);

// Display the evaluation results with detailed scores
System.out.println("\nEvaluation results:");
Map<EvaluationMetric, Double> scores = evaluation.getScores();

System.out.println("Helpfulness score: " + scores.get(EvaluationMetric.HELPFULNESS) + 
    " (Higher scores indicate more helpful responses)");
System.out.println("Accuracy score: " + scores.get(EvaluationMetric.ACCURACY) + 
    " (Higher scores indicate more factually accurate responses)");

// You can also retrieve detailed feedback about why the agent received these scores
System.out.println("\nDetailed evaluation feedback:");
System.out.println(evaluation.getFeedback());
```

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

