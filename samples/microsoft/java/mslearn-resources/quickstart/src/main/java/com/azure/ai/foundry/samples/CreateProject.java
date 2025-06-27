package com.azure.ai.foundry.samples;

import com.azure.ai.projects.AIProjectClientBuilder;
import com.azure.ai.projects.DeploymentsClient;
import com.azure.ai.projects.models.Deployment;
import com.azure.core.credential.TokenCredential;
import com.azure.core.exception.HttpResponseException;
import com.azure.core.util.logging.ClientLogger;
import com.azure.identity.DefaultAzureCredentialBuilder;

/**
 * Example demonstrating how to connect to an existing Azure AI Foundry project
 * and list deployments using the azure-ai-projects API.
 * 
 * This sample shows how to use the AIProjectClientBuilder to create specialized
 * clients for specific operations.
 */
public class CreateProject {
    private static final ClientLogger logger = new ClientLogger(CreateProject.class);
    
    public static void main(String[] args) {
        // Load environment variables with proper error handling
        String endpoint = System.getenv("AZURE_ENDPOINT");
        
        // Validate required environment variables
        if (endpoint == null) {
            String errorMessage = "Environment variable AZURE_ENDPOINT is required but not set";
            logger.error("ERROR: {}", errorMessage);
            logger.error("Please set your environment variables or create a .env file. See README.md for details.");
            return;
        }
        
        try {
            // Build credential with DefaultAzureCredentialBuilder for optimal authentication
            logger.info("Building DefaultAzureCredential");
            TokenCredential credential = new DefaultAzureCredentialBuilder().build();

            // Create the builder and get the operation-specific DeploymentsClient
            logger.info("Creating DeploymentsClient with endpoint: {}", endpoint);
            DeploymentsClient deploymentsClient = new AIProjectClientBuilder()
                .endpoint(endpoint)
                .credential(credential)
                .buildDeploymentsClient();  // Using the operation-specific client builder pattern

            // List all deployments in the project with proper pagination and error handling
            logger.info("Listing deployments");
            System.out.println("\nExisting model deployments:");
            int count = 0;
            for (Deployment d : deploymentsClient.listDeployments()) {
                count++;
                logger.info("Found deployment: {}, Type: {}", d.getName(), d.getType());
                System.out.printf("  • Name: %s, Type: %s%n",
                    d.getName(), 
                    d.getType());
            }
            
            if (count == 0) {
                logger.info("No deployments found in the project");
                System.out.println("  No deployments found. Please create deployments using the Azure AI Studio portal, CLI, or management SDK.");
            }
            
            logger.info("Deployments listing completed successfully with {} deployments found", count);
            System.out.println("\nDeployments listing completed successfully!");
            System.out.println("\nNote: To create new deployments, use the Azure AI Studio portal, CLI, or management SDK.");
            
        } catch (HttpResponseException e) {
            // Handle service-specific errors with detailed information
            int statusCode = e.getResponse().getStatusCode();
            logger.error("Service returned error: Status code {}, Error message: {}", 
                statusCode, e.getMessage());
            
            // Provide more helpful context based on error status code
            if (statusCode == 401 || statusCode == 403) {
                logger.error("Authentication error. Check your Azure credentials and permissions.");
            } else if (statusCode == 404) {
                logger.error("Resource not found. Check if the endpoint URL is correct.");
            }
            
            // Still print error to console for user visibility
            System.err.printf("Service error %d: %s%n", statusCode, e.getMessage());
            
        } catch (Exception e) {
            // Handle general exceptions
            logger.error("Error in CreateProject sample: {}", e.getMessage(), e);
            
            // Print simplified error to console
            System.err.println("Error: " + e.getMessage());
        }
    }
}