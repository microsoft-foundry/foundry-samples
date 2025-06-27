package com.azure.ai.foundry.samples;

import com.azure.ai.inference.ChatCompletionsClient;
import com.azure.ai.inference.ChatCompletionsClientBuilder;
import com.azure.ai.inference.models.ChatCompletions;
import com.azure.core.credential.AzureKeyCredential;
import com.azure.core.credential.TokenCredential;
import com.azure.core.exception.HttpResponseException;
import com.azure.core.util.logging.ClientLogger;
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;

/**
 * Sample demonstrating non-streaming chat completion functionality using the Azure AI Inference SDK.
 * 
 * This sample shows how to:
 * - Set up authentication with either API key or Azure credentials
 * - Configure a custom endpoint for any Azure AI model
 * - Make a simple chat completion request with a single prompt
 * - Process and handle the synchronous response
 * - Work with the ChatCompletionsClient for basic AI interactions
 * 
 * Environment variables:
 * - AZURE_ENDPOINT: Required. The base endpoint for your Azure AI service.
 * - AZURE_AI_API_KEY: Optional. The API key for authentication (falls back to DefaultAzureCredential if not provided).
 * - AZURE_MODEL_DEPLOYMENT_NAME: Optional. The model deployment name (defaults to "phi-4").
 * - AZURE_MODEL_API_PATH: Optional. The API path segment (defaults to "deployments").
 * - CHAT_PROMPT: Optional. The prompt to send to the model (uses a default if not provided).
 * 
 * SDK Features Demonstrated:
 * - Using the Azure AI Inference SDK (com.azure:azure-ai-inference:1.0.0-beta.5)
 * - Creating a ChatCompletionsClient with Azure or API key authentication
 * - Configuring endpoint paths for different model deployments
 * - Using the simplified complete() method for quick completions
 * - Accessing response content through strongly-typed objects
 * - Implementing proper error handling for service requests
 * - Choosing between DefaultAzureCredential and AzureKeyCredential
 */
public class ChatCompletionSample {
    private static final ClientLogger logger = new ClientLogger(ChatCompletionSample.class);
    
    public static void main(String[] args) {
        // Load environment variables with proper error handling
        String endpoint = System.getenv("AZURE_ENDPOINT");
        String apiKey = System.getenv("AZURE_AI_API_KEY");
        String deploymentName = System.getenv("AZURE_MODEL_DEPLOYMENT_NAME");
        String apiPath = System.getenv("AZURE_MODEL_API_PATH");
        String prompt = System.getenv("CHAT_PROMPT");
        
        // Validate required environment variables
        if (endpoint == null) {
            String errorMessage = "Environment variable AZURE_ENDPOINT is required but not set";
            logger.error("ERROR: {}", errorMessage);
            logger.error("Please set your environment variables or create a .env file. See README.md for details.");
            return;
        }
        
        // Set defaults for optional parameters
        if (deploymentName == null) {
            deploymentName = "phi-4";  // Default to phi-4
            logger.info("No AZURE_MODEL_DEPLOYMENT_NAME provided, using default: {}", deploymentName);
        }
        
        // Set default API path if not provided
        if (apiPath == null) {
            apiPath = "deployments";
            logger.info("No AZURE_MODEL_API_PATH provided, using default: {}", apiPath);
        }
        
        if (prompt == null) {
            prompt = "What best practices should I follow when asking an AI model to review Java code?";
            logger.info("No CHAT_PROMPT provided, using default prompt: {}", prompt);
        }

        try {
            logger.info("Creating ChatCompletions client with endpoint: {}", endpoint);
            
            // Construct the full endpoint URL including deployment name
            String fullEndpoint = endpoint;
            if (!fullEndpoint.endsWith("/")) {
                fullEndpoint += "/";
            }
            fullEndpoint += apiPath + "/" + deploymentName;
            logger.info("Using full endpoint URL: {}", fullEndpoint);
            
            ChatCompletionsClient client;
            
            // Create client using either API key or Azure credentials with proper error handling
            if (apiKey != null && !apiKey.isEmpty()) {
                logger.info("Using API key authentication");
                client = new ChatCompletionsClientBuilder()
                    .credential(new AzureKeyCredential(apiKey))
                    .endpoint(fullEndpoint)
                    .buildClient();
            } else {
                logger.info("Using Azure credential authentication with DefaultAzureCredential");
                DefaultAzureCredential credential = new DefaultAzureCredentialBuilder().build();
                client = new ChatCompletionsClientBuilder()
                    .credential(credential)
                    .endpoint(fullEndpoint)
                    .buildClient();
            }
            
            logger.info("Sending chat completion request with prompt: {}", prompt);
            
            // Call the API with the simple prompt interface
            ChatCompletions completions = client.complete(prompt);
            
            // Print response
            String content = completions.getChoice().getMessage().getContent();
            logger.info("Received response from model");
            logger.info("\nResponse from AI assistant:\n{}", content);
            
        } catch (HttpResponseException e) {
            // Handle service-specific errors with detailed information
            int statusCode = e.getResponse().getStatusCode();
            logger.error("Service error {}: {}", statusCode, e.getMessage());
            
            // Provide more helpful context based on error status code
            if (statusCode == 401 || statusCode == 403) {
                logger.error("Authentication error. Check your API key or Azure credentials.");
            } else if (statusCode == 404) {
                logger.error("Resource not found. Check if the deployment name and endpoint are correct.");
            } else if (statusCode == 429) {
                logger.error("Rate limit exceeded. Try again later or adjust your request rate.");
            }
            
        } catch (Exception e) {
            // Handle general exceptions
            logger.error("Error in chat completion: {}", e.getMessage(), e);
            logger.error("Make sure the Azure AI Inference SDK dependency is correct (using beta.5)");
        }
    }
}