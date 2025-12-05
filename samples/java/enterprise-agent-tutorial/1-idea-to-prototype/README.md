# Azure AI Foundry - Modern Workplace Assistant (Java)

**Tutorial 1** of the Azure AI Foundry enterprise tutorial series. This sample demonstrates how to build AI agents that combine internal knowledge (SharePoint) with external technical guidance (Microsoft Learn) for realistic business scenarios.

> **🚀 SDK Update**: This is the Java implementation using the Azure AI Agents SDK version 1.0.0-beta.1. It parallels the Python sample and demonstrates the same enterprise patterns in Java.

## 🎯 Business Scenario: Modern Workplace Assistant

This sample creates an AI assistant that helps employees with:
- **Company policies** (from SharePoint documents)
- **Technical implementation** (from Microsoft Learn)
- **Complete solutions** (combining both sources)

**Example Questions:**
- "What is our remote work security policy?" → *Uses SharePoint*
- "How do I set up Azure AD conditional access?" → *Uses Microsoft Learn*  
- "Our policy requires MFA - how do I implement it in Azure?" → *Uses both sources*

## 🚀 Quick Start

### Prerequisites

- **Java 11+** installed (`java -version`)
- **Maven 3.6+** installed (`mvn -version`)
- **Azure AI Foundry project** with a deployed model (e.g., `gpt-4o`)
- **SharePoint connection** configured in your Azure AI Foundry project (optional)
- **MCP server endpoint** (or use a placeholder for testing)
- **Azure CLI** authenticated (`az login`)

### Step 1: Install the Azure AI Agents SDK locally

First, install the preview SDK to your local Maven repository:

```bash
cd F:\git\agentsv2-preview\java

mvn install:install-file \
  -Dfile=package/azure-ai-agents-1.0.0-beta.1.jar \
  -DpomFile=package/azure-ai-agents-1.0.0-beta.1.pom
```

On Windows PowerShell:
```powershell
cd F:\git\agentsv2-preview\java

mvn install:install-file `
  -Dfile=package/azure-ai-agents-1.0.0-beta.1.jar `
  -DpomFile=package/azure-ai-agents-1.0.0-beta.1.pom
```

### Step 2: Environment Setup

1. **Copy the environment template:**

   ```bash
   cp .env.template .env
   ```

2. **Edit `.env` with your actual values:**

   ```properties
   PROJECT_ENDPOINT=https://your-project.aiservices.azure.com
   MODEL_DEPLOYMENT_NAME=gpt-4o
   SHAREPOINT_RESOURCE_NAME=your-sharepoint-connection
   MCP_SERVER_URL=https://learn.microsoft.com/api/mcp
   AI_FOUNDRY_TENANT_ID=your-tenant-id
   ```

### Step 3: Build the Project

```bash
mvn clean compile
```

### Step 4: Run the Main Sample

```bash
mvn exec:java -Dexec.mainClass="com.microsoft.azure.samples.ModernWorkplaceAssistant"
```

**Expected output:**
```text
🚀 Azure AI Foundry - Modern Workplace Assistant
Tutorial 1: Building Enterprise Agents with SharePoint + MCP Integration
======================================================================
🤖 Creating Modern Workplace Assistant...
✅ Agent created successfully: <agent-id>
```

### Step 5: Run Evaluation

```bash
mvn exec:java -Dexec.mainClass="com.microsoft.azure.samples.EvaluateAgent"
```

**Expected output:**
```text
🧪 Modern Workplace Assistant - Evaluation
==================================================
🧪 Running evaluation with 4 test questions...
📊 Evaluation Results: 3/4 questions passed
💾 Results saved to evaluation_results.json
```

## 📁 Sample Structure

This Java sample contains essential files for a complete implementation:

### Core Sample (2 Java classes)

- **`ModernWorkplaceAssistant.java`** - Complete Modern Workplace Assistant implementation
- **`EvaluateAgent.java`** - Business evaluation framework

### Configuration & Documentation (7 files)

- **`pom.xml`** - Maven project configuration with dependencies
- **`.env.template`** - Environment variables template
- **`questions.jsonl`** - Business test scenarios (4 questions)
- **`MCP_SERVERS.md`** - MCP server configuration guide
- **`SAMPLE_SHAREPOINT_CONTENT.md`** - Sample business documents
- **`README.md`** - This file
- **`.env`** - Your actual configuration (create from template)

## 📊 Key Java Implementation Details

### Agent Creation Pattern

```java
// Build clients
AgentsClientBuilder builder = new AgentsClientBuilder()
    .credential(new DefaultAzureCredentialBuilder().build())
    .endpoint(endpoint);

AgentsClient agentsClient = builder.buildClient();
ResponsesClient responsesClient = builder.buildResponsesClient();
ConversationsClient conversationsClient = builder.buildConversationsClient();

// Create agent with tools
PromptAgentDefinition definition = new PromptAgentDefinition(modelDeploymentName)
    .setInstructions(instructions)
    .setTools(availableTools);

AgentVersionObject agent = agentsClient.createAgentVersion(
    "Modern Workplace Assistant",
    definition
);
```

### Conversation Pattern

```java
// Create conversation
Conversation conversation = conversationsClient.getOpenAIClient().create();

// Add user message
conversationsClient.getOpenAIClient().items().create(
    ItemCreateParams.builder()
        .conversationId(conversation.id())
        .addItem(EasyInputMessage.builder()
            .role(EasyInputMessage.Role.USER)
            .content(message)
            .build())
        .build()
);

// Get response
AgentReference agentReference = new AgentReference(agentName);
Response response = responsesClient.createWithAgentConversation(
    agentReference,
    conversation.id()
);
```

## 🔧 Troubleshooting

### Common Issues

#### Authentication failed

- Run `az login` and ensure you're logged into the correct tenant
- Verify your `PROJECT_ENDPOINT` is correct
- Check that `AI_FOUNDRY_TENANT_ID` matches your tenant if specified

#### Maven cannot find azure-ai-agents dependency

- Ensure you've installed the SDK locally (see Step 1)
- Check that the version in `pom.xml` matches the installed version
- Run `mvn dependency:tree` to verify dependencies

#### SharePoint Connection Issues

**Option 1: Fix Existing Connection (Recommended)**
1. Go to [Azure AI Foundry portal](https://ai.azure.com) → Your Project
2. **Management Center** → **Connected Resources**
3. Find your SharePoint connection and update the Target URL
4. Use format: `https://company.sharepoint.com/teams/site-name`

**Option 2: MCP-Only Mode**
- Comment out SharePoint variables in `.env`
- Sample works perfectly with just Microsoft Learn integration

#### Java compilation errors

- Ensure Java 11+ is being used: `mvn -version`
- Clean and rebuild: `mvn clean compile`
- Check that all dependencies are resolved: `mvn dependency:resolve`

## 🎓 Learning Path

**Completed this sample?** Here's what to explore next:

1. **Add more tools**: Azure AI Search, Bing Web Search, Function Calling
2. **Advanced evaluation**: Custom metrics, A/B testing, human feedback
3. **Production setup**: Monitoring, logging, error handling
4. **Scale up**: RAG with vector stores, complex multi-agent workflows

## 📚 Resources

- [Azure AI Foundry Documentation](https://docs.microsoft.com/azure/ai-foundry)
- [Agent Service Overview](https://docs.microsoft.com/azure/ai-foundry/agents)
- [SharePoint Tool Guide](https://docs.microsoft.com/azure/ai-foundry/agents/tools/sharepoint)
- [MCP Integration](https://docs.microsoft.com/azure/ai-foundry/agents/tools/mcp)
- [Java SDK Documentation](https://learn.microsoft.com/java/api/overview/azure/ai-agents-readme)

## 🔄 Differences from Python Version

This Java implementation maintains feature parity with the Python version while following Java best practices:

- Uses Maven for dependency management instead of pip
- Implements builder patterns for client creation
- Uses try-with-resources for file operations
- Follows Java naming conventions (camelCase vs snake_case)
- Leverages Java streams for collection operations
- Uses Gson for JSON processing instead of Python's built-in json module
- Implements helper classes for data structures instead of dictionaries

## 🤝 Support

**Questions?**

- Check the [troubleshooting section](#-troubleshooting) above
- Review the [full tutorial](https://docs.microsoft.com/azure/ai-foundry/tutorials/developer-journey-stage-1)
- File issues in the Azure AI Foundry feedback portal

---

**Happy coding!** 🎉 This sample gets you from zero to working enterprise agent in Java.
