package com.azure.ai.foundry.samples;

import com.azure.ai.projects.AIProjectClientBuilder;
import com.azure.ai.projects.DeploymentsClient;
import com.azure.ai.projects.models.Deployment;
import com.azure.core.credential.TokenCredential;
import com.azure.core.exception.HttpResponseException;
import com.azure.core.util.logging.ClientLogger;
import com.azure.identity.DefaultAzureCredentialBuilder;

/**
 * Sample demonstrating how to connect to an existing Azure AI Foundry project
 * and list deployments using the Azure AI Projects SDK.
 * 
 * This sample shows how to:
 * - Set up authentication with Azure credentials
 * - Connect to an Azure AI Project using the provided endpoint
 * - Create a specialized DeploymentsClient using the builder pattern
 * - List and display available model deployments in the project
 * - Work with the deployment objects to access their properties
 * 
 * Environment variables:
 * - AZURE_ENDPOINT: Required. The endpoint URL for your Azure AI Project.
 * 
 * Note: This sample uses DefaultAzureCredential for authentication, which supports
 * multiple authentication methods including environment variables, managed identities,
 * and interactive browser login. It demonstrates how to access and inspect existing
 * deployments rather than creating new ones.
 * 
 * SDK Features Demonstrated:
 * - Using the Azure AI Projects SDK (com.azure:azure-ai-projects:1.0.0-beta.2)
 * - Creating an authenticated client with DefaultAzureCredential
 * - Using the AIProjectClientBuilder pattern for client instantiation
 * - Creating a specialized DeploymentsClient for specific operations
 * - Listing and iterating through deployments in a project
 * - Accessing deployment properties (name, type, etc.)
 * - Implementing proper error handling for Azure service interactions
 * - Using Azure Core logging patterns
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
            logger.info("\nExisting model deployments:");
            int count = 0;
            for (Deployment d : deploymentsClient.listDeployments()) {
                count++;
                logger.info("Found deployment: {}, Type: {}", d.getName(), d.getType());
                logger.info("  • Name: {}, Type: {}", d.getName(), d.getType());
            }
            
            if (count == 0) {
                logger.info("No deployments found in the project");
                logger.info("  No deployments found. Please create deployments using the Azure AI Studio portal, CLI, or management SDK.");
            }
            
            logger.info("\nDeployments listing completed successfully with {} deployments found!", count);
            logger.info("Note: To create new deployments, use the Azure AI Studio portal, CLI, or management SDK.");
            
        } catch (HttpResponseException e) {
            // Handle service-specific errors with detailed information
            int statusCode = e.getResponse().getStatusCode();
            logger.error("Service error {}: {}", statusCode, e.getMessage());
            
            // Provide more helpful context based on error status code
            if (statusCode == 401 || statusCode == 403) {
                logger.error("Authentication error. Check your Azure credentials and permissions.");
            } else if (statusCode == 404) {
                logger.error("Resource not found. Check if the endpoint URL is correct.");
            }
            
        } catch (Exception e) {
            // Handle general exceptions
            logger.error("Error in CreateProject sample: {}", e.getMessage(), e);
        }
    }
}