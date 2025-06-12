package com.azure.ai.foundry.samples;

import com.azure.ai.foundry.samples.utils.ConfigLoader;
import com.azure.ai.agents.persistent.PersistentAgentsAdministrationClient;
import com.azure.ai.agents.persistent.PersistentAgentsAdministrationClientBuilder;
import com.azure.ai.agents.persistent.models.CreateAgentOptions;
import com.azure.ai.agents.persistent.models.CreateThreadAndRunOptions;
import com.azure.ai.agents.persistent.models.PersistentAgent;
import com.azure.ai.agents.persistent.models.ThreadRun;
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Example demonstrating agent creation with document capabilities
 * using Azure AI Agents Persistent SDK.
 */
public class FileSearchAgentSample {
    public static void main(String[] args) {
        // Load environment variables
        String endpoint = ConfigLoader.getAzureEndpoint();
        String projectEndpoint = System.getenv("PROJECT_ENDPOINT");
        String modelName = System.getenv("MODEL_DEPLOYMENT_NAME");
        String agentName = System.getenv("AGENT_NAME");
        String instructions = System.getenv("AGENT_INSTRUCTIONS");

        // Validate required environment variables
        if (projectEndpoint == null) {
            if (endpoint == null) {
                System.err.println("ERROR: Neither PROJECT_ENDPOINT nor ConfigLoader.getAzureEndpoint() returned a value");
                System.err.println("Make sure .env file exists with AZURE_ENDPOINT defined or PROJECT_ENDPOINT is set");
                return;
            }
            projectEndpoint = endpoint;
            System.out.println("PROJECT_ENDPOINT not set, using AZURE_ENDPOINT: " + projectEndpoint);
        }
        
        if (modelName == null) {
            modelName = "gpt4o";  // Default to gpt4o
            System.out.println("MODEL_DEPLOYMENT_NAME not set, using default: " + modelName);
        }
        
        if (agentName == null) {
            agentName = "Document Assistant";
            System.out.println("AGENT_NAME not set, using default: " + agentName);
        }
        
        if (instructions == null) {
            instructions = "You are a document assistant that helps users find information in documents. " +
                           "You can provide summaries of document content and answer questions about documents.";
            System.out.println("AGENT_INSTRUCTIONS not set, using default instructions");
        }

        DefaultAzureCredential credential = new DefaultAzureCredentialBuilder().build();

        // Create the agent administration client
        System.out.println("\nCreating agent administration client...");
        PersistentAgentsAdministrationClient adminClient = new PersistentAgentsAdministrationClientBuilder()
            .endpoint(projectEndpoint)
            .credential(credential)
            .buildClient();

        try {
            // Create a sample document
            Path tmpFile = createSampleDocument();
            System.out.println("Created sample document: " + tmpFile);
            System.out.println("Document content:");
            System.out.println("--------------------------------------------------");
            System.out.println(Files.readString(tmpFile).substring(0, 200) + "...");
            System.out.println("--------------------------------------------------");

            // Information about document handling
            System.out.println("\nINFORMATION: This sample creates a document on your local system to demonstrate");
            System.out.println("document content that would be used with an agent. To use this document with");
            System.out.println("your agent, you would upload it in the Azure AI Studio portal and configure");
            System.out.println("the agent with the file search tool there.");

            // Create a document-focused agent 
            System.out.println("\nCreating agent: " + agentName);
            PersistentAgent agent = adminClient.createAgent(new CreateAgentOptions(modelName)
                .setName(agentName)
                .setInstructions(instructions));
            System.out.println("Agent created with ID: " + agent.getId());

            // Create thread and run
            System.out.println("\nCreating thread and run...");
            ThreadRun threadRun = adminClient.createThreadAndRun(new CreateThreadAndRunOptions(agent.getId()));
            String threadId = threadRun.getThreadId();
            System.out.println("Thread created with ID: " + threadId);

            // Print next steps
            System.out.println("\nNEXT STEPS:");
            System.out.println("1. Upload the sample document to your Azure AI project in the Azure AI Studio portal");
            System.out.println("2. Configure your agent with file search capability in the portal");
            System.out.println("3. Access the agent in the portal to interact with it and ask questions about your document");

            // Clean up the temporary file
            try {
                Files.deleteIfExists(tmpFile);
                System.out.println("\nTemporary document file deleted");
            } catch (IOException e) {
                System.err.println("Error deleting temporary file: " + e.getMessage());
            }

        } catch (IOException e) {
            System.err.println("I/O error: " + e.getMessage());
        } catch (Exception e) {
            System.err.println("Error: " + e.getMessage());
            e.printStackTrace();
        }
        
        System.out.println("\nDemo completed!");
    }

    private static Path createSampleDocument() throws IOException {
        String content = "# Cloud Computing Overview\n\n" +
            "Cloud computing is the delivery of computing services over the internet, including servers, " +
            "storage, databases, networking, software, and analytics.\n\n" +
            "## Key Benefits\n\n" +
            "1. **Cost Efficiency**: Pay only for the resources you use, reducing capital expenditure on hardware and infrastructure.\n\n" +
            "2. **Scalability**: Easily scale resources up or down based on demand, providing flexibility as your needs change.\n\n" +
            "3. **Global Reach**: Deploy applications globally in minutes, improving performance and user experience.\n\n" +
            "4. **Reliability**: Cloud services typically offer built-in redundancy and backup capabilities for improved business continuity.\n\n" +
            "5. **Security**: Major cloud providers invest heavily in security measures that many organizations couldn't afford on their own.\n\n";

        Path tempFile = Files.createTempFile("cloud-computing-doc", ".md");
        Files.writeString(tempFile, content);
        return tempFile;
    }
}