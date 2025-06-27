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
 * Example demonstrating agent creation with document capabilities
 * using Azure AI Agents Persistent SDK.
 * 
 * This sample shows how to create an agent and provide it with
 * document search capabilities.
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
            System.out.println("\nCreating agents client...");
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
            System.out.println("Sample document at " + tmpFile);
            String filePreview = Files.readString(tmpFile).substring(0, 200) + "...";
            System.out.println(filePreview);

            // Create the agent with proper configuration
            logger.info("Creating agent with name: {}, model: {}", agentName, modelName);
            System.out.println("\nCreating agent: " + agentName);
            PersistentAgent agent = adminClient.createAgent(
                new CreateAgentOptions(modelName)
                    .setName(agentName)
                    .setInstructions(instructions)
            );
            logger.info("Agent created successfully with ID: {}", agent.getId());
            System.out.println("Agent ID: " + agent.getId());

            // Start a thread and run on the general client
            logger.info("Creating thread and run with agent ID: {}", agent.getId());
            System.out.println("\nStarting thread/run...");
            ThreadRun threadRun = agentsClient.createThreadAndRun(
                new CreateThreadAndRunOptions(agent.getId())
            );
            logger.info("ThreadRun created with ThreadId: {}", threadRun.getThreadId());
            System.out.println("ThreadRun ID: " + threadRun.getThreadId());

            // Display success message
            logger.info("Demo completed successfully");
            System.out.println("\nDemo completed successfully!");

        } catch (HttpResponseException e) {
            // Handle service-specific errors with detailed information
            int statusCode = e.getResponse().getStatusCode();
            logger.error("Service returned error: Status code {}, Error message: {}", 
                statusCode, e.getMessage());
            logger.error("Refer to the Azure AI Agents documentation for troubleshooting information.");
            
            // Still print error to console for user visibility
            System.err.printf("Service error %d: %s%n", statusCode, e.getMessage());
            
        } catch (IOException e) {
            // Handle IO exceptions specifically for file operations
            logger.error("I/O error while creating sample document: {}", e.getMessage(), e);
            
            // Print simplified error to console
            System.err.println("I/O error: " + e.getMessage());
            
        } catch (Exception e) {
            // Handle general exceptions
            logger.error("Error in file search agent sample: {}", e.getMessage(), e);
            
            // Print simplified error to console
            System.err.println("Error: " + e.getMessage());
        }
    }

    /**
     * Creates a sample markdown document with cloud computing information.
     * 
     * @return Path to the created temporary file
     * @throws IOException if an I/O error occurs
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
