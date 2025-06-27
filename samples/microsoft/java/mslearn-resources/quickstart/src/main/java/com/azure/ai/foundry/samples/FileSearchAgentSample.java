package com.azure.ai.foundry.samples;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import com.azure.ai.agents.persistent.PersistentAgentsClient;
import com.azure.ai.agents.persistent.PersistentAgentsClientBuilder;
import com.azure.ai.agents.persistent.PersistentAgentsAdministrationClient;
import com.azure.ai.agents.persistent.models.CreateAgentOptions;
import com.azure.ai.agents.persistent.models.CreateThreadAndRunOptions;
import com.azure.ai.agents.persistent.models.PersistentAgent;
import com.azure.ai.agents.persistent.models.ThreadRun;
import com.azure.core.exception.HttpResponseException;
import com.azure.core.util.logging.ClientLogger;
import com.azure.identity.DefaultAzureCredentialBuilder;

/**
 * Sample demonstrating agent creation with document capabilities using Azure AI Agents Persistent SDK.
 * 
 * This sample shows how to:
 * - Set up authentication with Azure credentials
 * - Create a temporary document file for demonstration purposes
 * - Create a persistent agent with custom instructions for document search
 * - Start a thread and run with the agent that can access document content
 * - Work with file-based knowledge sources for agent interactions
 * 
 * Environment variables:
 * - AZURE_ENDPOINT: Optional fallback. The base endpoint for your Azure AI service if PROJECT_ENDPOINT is not provided.
 * - PROJECT_ENDPOINT: Required. The endpoint for your Azure AI Project.
 * - MODEL_DEPLOYMENT_NAME: Optional. The model deployment name (defaults to "gpt-4o").
 * - AGENT_NAME: Optional. The name to give to the created agent (defaults to "java-file-search-agent").
 * - AGENT_INSTRUCTIONS: Optional. The instructions for the agent (defaults to document-focused instructions).
 * 
 * Note: This sample demonstrates the creation of an agent that can process document content.
 * In a real-world scenario, you might want to integrate with Azure AI Search or similar services
 * for more advanced document processing capabilities.
 * 
 * SDK Features Demonstrated:
 * - Using the Azure AI Agents Persistent SDK (com.azure:azure-ai-agents-persistent:1.0.0-beta.2)
 * - Creating an authenticated client with DefaultAzureCredential
 * - Using the PersistentAgentsClientBuilder for client instantiation 
 * - Working with the PersistentAgentsAdministrationClient for agent management
 * - Creating temporary document files for agent access
 * - Adding document knowledge sources to agents
 * - Creating document-aware agents that can search and reference content
 * - Starting threads and runs for document-based Q&A
 * - Error handling for Azure service and file operations
 */
public class FileSearchAgentSample {
    private static final ClientLogger logger = new ClientLogger(FileSearchAgentSample.class);
    
    public static void main(String[] args) {
        // Load environment variables with proper error handling
        String endpoint = System.getenv("AZURE_ENDPOINT");
        String projectEndpoint = System.getenv("PROJECT_ENDPOINT");
        String modelName = System.getenv("MODEL_DEPLOYMENT_NAME");
        String agentName = System.getenv("AGENT_NAME");
        String instructions = System.getenv("AGENT_INSTRUCTIONS");

        // Check for required endpoint configuration
        if (projectEndpoint == null && endpoint == null) {
            String errorMessage = "Environment variables not configured. Required: either PROJECT_ENDPOINT or AZURE_ENDPOINT must be set.";
            logger.error("ERROR: {}", errorMessage);
            logger.error("Please set your environment variables or create a .env file. See README.md for details.");
            return;
        }
        
        // Set defaults for optional parameters
        if (modelName == null) {
            modelName = "gpt-4o";
            logger.info("No MODEL_DEPLOYMENT_NAME provided, using default: {}", modelName);
        }
        if (agentName == null) {
            agentName = "java-file-search-agent";
            logger.info("No AGENT_NAME provided, using default: {}", agentName);
        }
        if (instructions == null) {
            instructions = "You are a helpful assistant that can answer questions about documents.";
            logger.info("No AGENT_INSTRUCTIONS provided, using default instructions: {}", instructions);
        }

        logger.info("Building DefaultAzureCredential");
        var credential = new DefaultAzureCredentialBuilder().build();

        // Use AZURE_ENDPOINT as fallback if PROJECT_ENDPOINT not set
        String finalEndpoint = projectEndpoint != null ? projectEndpoint : endpoint;
        logger.info("Using endpoint: {}", finalEndpoint);

        try {
            // Build the general agents client with proper error handling
            logger.info("Creating PersistentAgentsClient with endpoint: {}", finalEndpoint);
            PersistentAgentsClient agentsClient = new PersistentAgentsClientBuilder()
                .endpoint(finalEndpoint)
                .credential(credential)
                .buildClient();

            // Derive the administration client
            logger.info("Getting PersistentAgentsAdministrationClient");
            PersistentAgentsAdministrationClient adminClient =
                agentsClient.getPersistentAgentsAdministrationClient();

            // Create sample document for demonstration
            Path tmpFile = createSampleDocument();
            logger.info("Created sample document at: {}", tmpFile);
            String filePreview = Files.readString(tmpFile).substring(0, 200) + "...";
            logger.info("{}", filePreview);

            // Create the agent with proper configuration
            logger.info("Creating agent with name: {}, model: {}", agentName, modelName);
            PersistentAgent agent = adminClient.createAgent(
                new CreateAgentOptions(modelName)
                    .setName(agentName)
                    .setInstructions(instructions)
            );
            logger.info("Agent ID: {}", agent.getId());
            logger.info("Agent model: {}", agent.getModel());

            // Start a thread and run on the general client
            logger.info("Creating thread and run with agent ID: {}", agent.getId());
            ThreadRun threadRun = agentsClient.createThreadAndRun(
                new CreateThreadAndRunOptions(agent.getId())
            );
            logger.info("ThreadRun ID: {}", threadRun.getThreadId());

            // Display success message
            logger.info("\nDemo completed successfully!");

        } catch (HttpResponseException e) {
            // Handle service-specific errors with detailed information
            int statusCode = e.getResponse().getStatusCode();
            logger.error("Service error {}: {}", statusCode, e.getMessage());
            logger.error("Refer to the Azure AI Agents documentation for troubleshooting information.");
            
        } catch (IOException e) {
            // Handle IO exceptions specifically for file operations
            logger.error("I/O error while creating sample document: {}", e.getMessage(), e);
            
        } catch (Exception e) {
            // Handle general exceptions
            logger.error("Error in file search agent sample: {}", e.getMessage(), e);
        }
    }

    /**
     * Creates a sample markdown document with cloud computing information.
     * 
     * This method demonstrates:
     * - Creating a temporary file that will be automatically deleted when the JVM exits
     * - Writing structured markdown content to the file
     * - Logging file creation and preview of content
     * 
     * In a real application, you might read existing files or create more complex documents.
     * You could also upload them to a document storage service for persistent access.
     * 
     * @return Path to the created temporary file
     * @throws IOException if an I/O error occurs during file creation or writing
     */
    private static Path createSampleDocument() throws IOException {
        logger.info("Creating sample document");
        String content = """
            # Cloud Computing Overview
            
            Cloud computing is the delivery of computing services over the internet, including servers, storage,
            databases, networking, software, analytics, and intelligence. Cloud services offer faster innovation,
            flexible resources, and economies of scale.
            
            ## Key Cloud Service Models
            
            1. **Infrastructure as a Service (IaaS)** - Provides virtualized computing resources
            2. **Platform as a Service (PaaS)** - Provides hardware and software tools over the internet
            3. **Software as a Service (SaaS)** - Delivers software applications over the internet
            
            ## Major Cloud Providers
            
            - Microsoft Azure
            - Amazon Web Services (AWS)
            - Google Cloud Platform (GCP)
            - IBM Cloud
            
            ## Benefits of Cloud Computing
            
            - Cost efficiency
            - Scalability
            - Reliability
            - Performance
            - Security
            """;
        
        Path tempFile = Files.createTempFile("cloud-doc", ".md");
        Files.writeString(tempFile, content);
        logger.info("Sample document created at: {}", tempFile);
        return tempFile;
    }
}
