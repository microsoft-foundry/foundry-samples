package com.azure.ai.foundry.samples;

import com.azure.ai.inference.ChatCompletionsClient;
import com.azure.ai.inference.ChatCompletionsClientBuilder;
import com.azure.ai.inference.models.ChatCompletionsOptions;
import com.azure.ai.inference.models.ChatRequestMessage;
import com.azure.ai.inference.models.ChatRequestAssistantMessage;
import com.azure.ai.inference.models.ChatRequestSystemMessage;
import com.azure.ai.inference.models.ChatRequestUserMessage;
import com.azure.ai.inference.models.StreamingChatCompletionsUpdate;
import com.azure.ai.inference.models.StreamingChatResponseMessageUpdate;
import com.azure.core.credential.AzureKeyCredential;
import com.azure.core.exception.HttpResponseException;
import com.azure.core.util.CoreUtils;
import com.azure.core.util.IterableStream;
import com.azure.core.util.logging.ClientLogger;
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;

import java.util.ArrayList;
import java.util.List;

/**
 * Sample demonstrating streaming chat completion functionality using the Azure AI Inference SDK.
 * 
 * This sample shows how to:
 * - Set up authentication with either API key or Azure credentials
 * - Configure a custom endpoint for any Azure AI model
 * - Create a chat completion request with system and user messages
 * - Process and display streaming responses token by token
 * - Collect the complete response in a StringBuilder
 * - Work with streaming API patterns for responsive UI experiences
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
 * - Creating ChatRequestMessage objects for conversation history
 * - Using completeStream() method for streaming responses
 * - Processing IterableStream<StreamingChatCompletionsUpdate> for token-by-token responses
 * - Incrementally building responses with StringBuilder
 * - Handling streaming responses with proper resource management
 * - Using the functional stream() API for processing streaming content
 */
public class ChatCompletionStreamingSample {
    private static final ClientLogger logger = new ClientLogger(ChatCompletionStreamingSample.class);

    public static void main(String[] args) {
        // Load configuration from environment variables
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
            deploymentName = "phi-4";  // A lightweight but capable model
            logger.info("No AZURE_MODEL_DEPLOYMENT_NAME provided, using default: {}", deploymentName);
        }
        
        // Set default API path - this may be different based on your Azure AI service type
        if (apiPath == null) {
            apiPath = "deployments";  // Standard path for Azure OpenAI
            logger.info("No AZURE_MODEL_API_PATH provided, using default: {}", apiPath);
        }
        
        if (prompt == null) {
            prompt = "What best practices should I follow when asking an AI model to review Java code?";
            logger.info("No CHAT_PROMPT provided, using default prompt: {}", prompt);
        }

        try {
            logger.info("Creating ChatCompletions client for streaming with endpoint: {}", endpoint);
            
            // Construct the full endpoint URL by combining:
            // 1. Base endpoint (e.g., https://your-resource.openai.azure.com)
            // 2. API path (e.g., "deployments")
            // 3. Deployment name (e.g., "phi-4")
            String fullEndpoint = endpoint;
            if (!fullEndpoint.endsWith("/")) {
                fullEndpoint += "/";
            }
            fullEndpoint += apiPath + "/" + deploymentName;
            logger.info("Using full endpoint URL: {}", fullEndpoint);
            
            ChatCompletionsClient client;
            
            // Create client using either API key or Azure credentials
            // The SDK supports two authentication methods:
            // 1. API key - simpler but less secure for production environments
            // 2. DefaultAzureCredential - supports multiple authentication methods including 
            //    environment variables, managed identities, and interactive browser login
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
            
            logger.info("Preparing chat messages");
            
            // Create message list for the chat conversation
            // 1. SystemMessage - Sets the behavior and context for the AI assistant
            // 2. UserMessage - Contains the actual query from the user
            // You can also add multiple messages to create a conversation history
            List<ChatRequestMessage> chatMessages = new ArrayList<>();
            chatMessages.add(new ChatRequestSystemMessage("You are a helpful assistant providing clear and concise information."));
            chatMessages.add(new ChatRequestUserMessage(prompt));
            
            logger.info("Sending streaming chat completion request with prompt: {}", prompt);
            logger.info("\nResponse from AI assistant (streaming):");
            
            // Configure and start the streaming completion request
            // You can customize options like temperature, max_tokens, etc. here
            ChatCompletionsOptions options = new ChatCompletionsOptions(chatMessages);
            // options.setTemperature(0.7); // Uncomment to adjust creativity (0.0-1.0)
            // options.setMaxTokens(1000);  // Uncomment to limit response length
            
            IterableStream<StreamingChatCompletionsUpdate> chatCompletionsStream = client.completeStream(options);
            
            // We'll collect the complete response here for later use
            StringBuilder contentBuilder = new StringBuilder();
            
            // Process streaming updates as they arrive
            // The response comes in small chunks (tokens) that we process one by one
            chatCompletionsStream
                .stream()
                .forEach(chatCompletions -> {
                    // Skip any empty updates
                    if (CoreUtils.isNullOrEmpty(chatCompletions.getChoices())) {
                        logger.atInfo().log("Received update with empty choices");
                        return;
                    }
    
                    StreamingChatResponseMessageUpdate delta = chatCompletions.getChoice().getDelta();
    
                    // The first update usually contains just the role (assistant)
                    if (delta.getRole() != null) {
                        logger.atInfo().log("Received role update: " + delta.getRole());
                    }
    
                    // Process content tokens as they arrive
                    if (delta.getContent() != null) {
                        String content = delta.getContent();
                        logger.info(content); // Log each token
                        contentBuilder.append(content); // Append to our complete response
                    }
                });
            
            logger.info("Streaming completed successfully");
            logger.atInfo().log("Complete response:\n" + contentBuilder);
            
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
            logger.error("Error in streaming chat completion: {}", e.getMessage(), e);
            logger.error("Make sure the Azure AI Inference SDK dependency is correct (using beta.5)");
        }
    }
}