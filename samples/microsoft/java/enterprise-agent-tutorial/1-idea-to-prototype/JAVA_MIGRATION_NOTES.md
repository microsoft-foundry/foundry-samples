# Java Migration Notes

This document provides a mapping between the Python and Java implementations to help developers understand the parallel structure.

## File Mapping

| Python File | Java Equivalent | Description |
|-------------|-----------------|-------------|
| `main.py` | `ModernWorkplaceAssistant.java` | Main application with agent creation and demo scenarios |
| `evaluate.py` | `EvaluateAgent.java` | Evaluation framework for testing agent quality |
| `requirements.txt` | `pom.xml` | Dependency management |
| `.env.template` | `.env.template` | Environment configuration (identical) |
| `questions.jsonl` | `questions.jsonl` | Test questions (identical) |
| `README.md` | `README.md` | Documentation (Java-specific) |
| `MCP_SERVERS.md` | `MCP_SERVERS.md` | MCP server options (identical) |
| `SAMPLE_SHAREPOINT_CONTENT.md` | `SAMPLE_SHAREPOINT_CONTENT.md` | SharePoint sample content (identical) |

## Code Structure Mapping

### Python: `main.py` → Java: `ModernWorkplaceAssistant.java`

| Python Function/Class | Java Equivalent | Notes |
|----------------------|-----------------|-------|
| `create_workplace_assistant()` | `createWorkplaceAssistant()` | Returns `AgentCreationResult` instead of tuple |
| `demonstrate_business_scenarios()` | `demonstrateBusinessScenarios()` | Uses `List<BusinessScenario>` instead of list of dicts |
| `chat_with_assistant()` | `chatWithAssistant()` | Returns `ChatResult` instead of tuple |
| `interactive_mode()` | `interactiveMode()` | Uses `Scanner` for input instead of `input()` |
| `main()` | `main(String[] args)` | Standard Java entry point |

### Python: `evaluate.py` → Java: `EvaluateAgent.java`

| Python Function/Class | Java Equivalent | Notes |
|----------------------|-----------------|-------|
| `load_test_questions()` | `loadTestQuestions()` | Uses Gson for JSON parsing |
| `run_evaluation()` | `runEvaluation()` | Uses Java streams for filtering |
| `main()` | `main(String[] args)` | Standard Java entry point |

## Key Differences

### 1. Dependency Management

**Python (`requirements.txt`):**
```txt
azure-ai-projects>=2.0.0a20251015001
azure-ai-agents>=2.0.0a20251015001
azure-identity
python-dotenv
```

**Java (`pom.xml`):**
```xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-ai-agents</artifactId>
    <version>1.0.0-beta.1</version>
</dependency>
<dependency>
    <groupId>io.github.cdimascio</groupId>
    <artifactId>dotenv-java</artifactId>
    <version>3.0.0</version>
</dependency>
```

### 2. Environment Variable Loading

**Python:**
```python
from dotenv import load_dotenv
load_dotenv()
endpoint = os.environ["PROJECT_ENDPOINT"]
```

**Java:**
```java
import io.github.cdimascio.dotenv.Dotenv;
Dotenv dotenv = Dotenv.configure().ignoreIfMissing().load();
String endpoint = dotenv.get("PROJECT_ENDPOINT");
```

### 3. Client Creation

**Python:**
```python
project_client = AIProjectClient(
    endpoint=os.environ["PROJECT_ENDPOINT"],
    credential=credential,
)
```

**Java:**
```java
AgentsClientBuilder builder = new AgentsClientBuilder()
    .credential(credential)
    .endpoint(endpoint);
    
agentsClient = builder.buildClient();
responsesClient = builder.buildResponsesClient();
conversationsClient = builder.buildConversationsClient();
```

### 4. Agent Creation

**Python:**
```python
agent = project_client.agents.create_version(
    agent_name="Modern Workplace Assistant",
    definition=PromptAgentDefinition(
        model=os.environ["MODEL_DEPLOYMENT_NAME"],
        instructions=instructions,
        tools=available_tools,
    )
)
```

**Java:**
```java
PromptAgentDefinition definition = new PromptAgentDefinition(modelDeploymentName)
    .setInstructions(instructions)
    .setTools(availableTools);

AgentVersionObject agent = agentsClient.createAgentVersion(
    "Modern Workplace Assistant",
    definition
);
```

### 5. Conversation Handling

**Python:**
```python
openai_client = project_client.get_openai_client()

conversation = openai_client.conversations.create(
    items=[{
        "type": "message",
        "role": "user",
        "content": message
    }]
)

response = openai_client.responses.create(
    conversation=conversation.id,
    extra_body={"agent": AgentReference(name=agent_name).as_dict()}
)
```

**Java:**
```java
Conversation conversation = conversationsClient.getOpenAIClient().create();

conversationsClient.getOpenAIClient().items().create(
    ItemCreateParams.builder()
        .conversationId(conversation.id())
        .addItem(EasyInputMessage.builder()
            .role(EasyInputMessage.Role.USER)
            .content(message)
            .build())
        .build()
);

AgentReference agentReference = new AgentReference(agentName);
Response response = responsesClient.createWithAgentConversation(
    agentReference,
    conversation.id()
);
```

### 6. Data Structures

**Python (dictionaries):**
```python
scenario = {
    "title": "Policy Question",
    "question": "What is our policy?",
    "context": "Employee needs info",
    "expected_source": "SharePoint",
    "learning_point": "Internal retrieval"
}
```

**Java (classes):**
```java
class BusinessScenario {
    String title;
    String question;
    String context;
    String expectedSource;
    String learningPoint;
    
    BusinessScenario(String title, String question, String context, 
                     String expectedSource, String learningPoint) {
        this.title = title;
        this.question = question;
        this.context = context;
        this.expectedSource = expectedSource;
        this.learningPoint = learningPoint;
    }
}
```

### 7. JSON Processing

**Python:**
```python
import json
with open("questions.jsonl", 'r') as f:
    for line in f:
        q = json.loads(line.strip())
```

**Java:**
```java
import com.google.gson.Gson;
import com.google.gson.JsonParser;

try (BufferedReader reader = new BufferedReader(new FileReader("questions.jsonl"))) {
    String line;
    while ((line = reader.readLine()) != null) {
        JsonObject json = JsonParser.parseString(line).getAsJsonObject();
    }
}
```

## Running the Samples

### Python
```bash
python main.py
python evaluate.py
```

### Java
```bash
mvn exec:java -Dexec.mainClass="com.microsoft.azure.samples.ModernWorkplaceAssistant"
mvn exec:java -Dexec.mainClass="com.microsoft.azure.samples.EvaluateAgent"
```

## Package Installation

### Python
```bash
pip install --pre -r requirements.txt
```

### Java
```bash
# First install the preview SDK locally
cd F:\git\agentsv2-preview\java
mvn install:install-file \
  -Dfile=package/azure-ai-agents-1.0.0-beta.1.jar \
  -DpomFile=package/azure-ai-agents-1.0.0-beta.1.pom

# Then build the project
cd F:\git\foundry-samples\samples\microsoft\Java\enterprise-agent-tutorial\1-idea-to-prototype
mvn clean compile
```

## Best Practices Applied

### Java-Specific Best Practices
1. **Builder Pattern**: Used for creating clients and parameters
2. **Try-with-resources**: Used for automatic resource management
3. **Streams API**: Used for collection operations
4. **Helper Classes**: Used instead of dictionaries for type safety
5. **camelCase**: Used for method and variable names
6. **Proper Exception Handling**: Try-catch blocks with meaningful error messages

### Common Patterns
1. **Graceful Degradation**: Both handle missing SharePoint gracefully
2. **Error Messages**: Both provide diagnostic information
3. **Interactive Mode**: Both support user testing
4. **Evaluation Framework**: Both include test harness

## Notes for Developers

1. **Type Safety**: Java version uses strong typing, catching errors at compile time
2. **Verbosity**: Java code is more verbose but explicit about types and operations
3. **Performance**: Both versions have similar runtime performance for agent operations
4. **Maintainability**: Java's type system makes refactoring safer
5. **Debugging**: Java IDEs provide better debugging support with breakpoints and inspection

## Future Enhancements

Both Python and Java versions can be extended with:
- Additional MCP tools
- Custom function calling
- Advanced evaluation metrics
- Production monitoring and logging
- Multi-agent orchestration patterns
