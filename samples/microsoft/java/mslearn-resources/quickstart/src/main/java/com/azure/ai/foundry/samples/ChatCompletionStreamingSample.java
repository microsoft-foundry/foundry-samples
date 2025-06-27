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
 * This sample shows how to perform streaming chat completions with Azure OpenAI
 * and process the streaming responses token by token.
 */
public class ChatCompletionStreamingSample {
    private static final ClientLogger logger = new ClientLogger(ChatCompletionStreamingSample.class);

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
        
        // Set defaults for optional parameters with informative logging
        if (deploymentName == null) {
            deploymentName = "gpt-4o";  // Default to gpt-4o
            logger.info("No AZURE_OPENAI_DEPLOYMENT_NAME provided, using default: {}", deploymentName);
        }
        
        if (prompt == null) {
            prompt = "Write a short poem about Azure AI and its capabilities.";
            logger.info("No CHAT_PROMPT provided, using default prompt: {}", prompt);
        }

        try {
            logger.info("Creating ChatCompletions client for streaming with endpoint: {}", endpoint);
            
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
            
            logger.info("Preparing chat messages");
            
            // Create message list for ChatCompletionsOptions
            List<ChatRequestMessage> chatMessages = new ArrayList<>();
            chatMessages.add(new ChatRequestSystemMessage("You are a helpful assistant providing clear and concise information."));
            chatMessages.add(new ChatRequestUserMessage(prompt));
            
            logger.info("Sending streaming chat completion request with prompt: {}", prompt);
            System.out.println("\nResponse from AI assistant (streaming):");
            
            // Create options and start streaming with proper retry and error handling configuration
            ChatCompletionsOptions options = new ChatCompletionsOptions(chatMessages);
            IterableStream<StreamingChatCompletionsUpdate> chatCompletionsStream = client.completeStream(options);
            
            StringBuilder contentBuilder = new StringBuilder();
            
            // Process streaming updates with proper error handling
            chatCompletionsStream
                .stream()
                .forEach(chatCompletions -> {
                    if (CoreUtils.isNullOrEmpty(chatCompletions.getChoices())) {
                        logger.atInfo().log("Received update with empty choices");
                        return;
                    }
    
                    StreamingChatResponseMessageUpdate delta = chatCompletions.getChoice().getDelta();
    
                    if (delta.getRole() != null) {
                        logger.atInfo().log("Received role update: " + delta.getRole());
                    }
    
                    if (delta.getContent() != null) {
                        String content = delta.getContent();
                        System.out.print(content);
                        contentBuilder.append(content);
                    }
                });
            
            logger.info("Streaming completed successfully");
            logger.atInfo().log("Complete response:\n" + contentBuilder);
            System.out.println("\n\nStreaming completed!");
            
        } catch (HttpResponseException e) {
            // Handle service-specific errors with detailed information
            int statusCode = e.getResponse().getStatusCode();
            logger.error("Service returned error: Status code {}, Error message: {}", 
                statusCode, e.getMessage());
            
            // Provide more helpful context based on error status code
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
            logger.error("Error in streaming chat completion: {}", e.getMessage(), e);
            logger.error("Make sure the Azure AI Inference SDK dependency is correct (using beta.5)");
            
            // Print simplified error to console
            System.err.println("Error: " + e.getMessage());
        }
    }
}