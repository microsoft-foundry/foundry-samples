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
 * Example demonstrating chat completion with Azure AI Inference SDK.
 * 
 * This sample shows how to interact with Azure OpenAI to perform chat completions
 * using the Azure AI Inference SDK with the synchronous client.
 */
public class ChatCompletionSample {
    private static final ClientLogger logger = new ClientLogger(ChatCompletionSample.class);
    
    public static void main(String[] args) {
        // Load environment variables with proper error handling
        String endpoint = System.getenv("AZURE_ENDPOINT");
        String apiKey = System.getenv("AZURE_OPENAI_API_KEY");
        String deploymentName = System.getenv("AZURE_OPENAI_DEPLOYMENT_NAME");
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
            deploymentName = "gpt-4o";  // Default to gpt-4o
            logger.info("No AZURE_OPENAI_DEPLOYMENT_NAME provided, using default: {}", deploymentName);
        }
        
        if (prompt == null) {
            prompt = "What is Azure AI? Explain in a short paragraph.";
            logger.info("No CHAT_PROMPT provided, using default prompt: {}", prompt);
        }

        try {
            logger.info("Creating ChatCompletions client with endpoint: {}", endpoint);
            
            // Construct the full endpoint URL including deployment name
            String fullEndpoint = endpoint;
            if (!fullEndpoint.endsWith("/")) {
                fullEndpoint += "/";
            }
            fullEndpoint += "openai/deployments/" + deploymentName;
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
            
            // Still print the AI response to console for user to see
            System.out.println("\nResponse from AI assistant:");
            System.out.println(content);
            
            logger.info("Demo completed successfully");
            
        } catch (HttpResponseException e) {
            // Handle service-specific errors with detailed information
            logger.error("Service returned error: Status code {}, Error message: {}", 
                e.getResponse().getStatusCode(), e.getMessage());
            
            // Provide more helpful context based on error status code
            int statusCode = e.getResponse().getStatusCode();
            if (statusCode == 401 || statusCode == 403) {
                logger.error("Authentication error. Check your API key or Azure credentials.");
            } else if (statusCode == 404) {
                logger.error("Resource not found. Check if the deployment name and endpoint are correct.");
            } else if (statusCode == 429) {
                logger.error("Rate limit exceeded. Try again later or adjust your request rate.");
            }
            
            // Still print error to console for user visibility
            System.err.printf("Service error %d: %s%n", statusCode, e.getMessage());
            
        } catch (Exception e) {
            // Handle general exceptions
            logger.error("Error in chat completion: {}", e.getMessage(), e);
            logger.error("Make sure the Azure AI Inference SDK dependency is correct (using beta.5)");
            
            // Print simplified error to console
            System.err.println("Error: " + e.getMessage());
        }
    }
}