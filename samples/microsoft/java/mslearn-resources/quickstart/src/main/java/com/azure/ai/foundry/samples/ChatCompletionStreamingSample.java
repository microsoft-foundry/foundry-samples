package com.azure.ai.foundry.samples;

import com.azure.ai.foundry.samples.utils.ConfigLoader;
import com.azure.ai.projects.ProjectsClient;
import com.azure.ai.projects.ProjectsClientBuilder;
import com.azure.ai.projects.models.chat.ChatClient;
import com.azure.ai.projects.models.chat.ChatCompletionOptions;
import com.azure.ai.projects.models.chat.ChatMessage;
import com.azure.ai.projects.models.chat.ChatRole;
import com.azure.ai.projects.models.chat.ChatCompletionStreamResponse;
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import reactor.core.publisher.Flux;

import java.util.List;

/**
 * Sample demonstrating streaming chat completion functionality using the 
 * Azure AI Projects SDK.
 * 
 * Note: This sample directly uses the ProjectsClient and ChatClient from the SDK.
 * This approach may not be available in all SDK versions due to evolving APIs.
 */
public class ChatCompletionStreamingSample {
    public static void main(String[] args) {
        // Load environment variables
        String endpoint = ConfigLoader.getAzureEndpoint();
        String projectEndpoint = System.getenv("PROJECT_ENDPOINT");
        String modelName = System.getenv("MODEL_DEPLOYMENT_NAME");
        String prompt = System.getenv("CHAT_PROMPT");
        String waitTimeStr = System.getenv("STREAMING_WAIT_TIME");
        
        // Validate and set defaults for required environment variables
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
        
        if (prompt == null) {
            prompt = "Write a short poem about Azure AI Foundry and its capabilities.";
            System.out.println("CHAT_PROMPT not set, using default prompt");
        }
        
        // Parse wait time with default of 10 seconds
        int waitTime = 10_000;
        if (waitTimeStr != null) {
            try {
                waitTime = Integer.parseInt(waitTimeStr);
                // Convert to milliseconds if it looks like it was provided in seconds
                if (waitTime < 100) {
                    waitTime *= 1000;
                }
            } catch (NumberFormatException e) {
                System.out.println("Invalid STREAMING_WAIT_TIME format. Using default: 10 seconds");
            }
        }

        DefaultAzureCredential credential = new DefaultAzureCredentialBuilder().build();

        try {
            System.out.println("Creating ProjectsClient...");
            ProjectsClient client = new ProjectsClientBuilder()
                .endpoint(projectEndpoint)
                .credential(credential)
                .buildClient();
            
            System.out.println("Getting ChatClient for model: " + modelName);
            ChatClient chatClient = client.getChatClient(modelName);
            
            System.out.println("Preparing chat messages...");
            List<ChatMessage> messages = List.of(
                new ChatMessage(ChatRole.SYSTEM, "You are a helpful assistant providing clear and concise information."),
                new ChatMessage(ChatRole.USER, prompt)
            );
            
            ChatCompletionOptions options = new ChatCompletionOptions(messages)
                .setStream(true);
            
            System.out.println("\nSending streaming chat completion request...");
            System.out.println("User prompt: " + prompt);
            System.out.println("\nResponse from AI assistant (streaming):");
            
            // Subscribe to the stream of partial responses
            Flux<ChatCompletionStreamResponse> stream = chatClient.streamChatCompletion(options);
            stream.subscribe(chunk -> {
                var delta = chunk.getChoices().get(0).getDelta().getContent();
                if (delta != null) {
                    System.out.print(delta);
                }
            }, err -> {
                System.err.println("\nStream failed: " + err.getMessage());
                err.printStackTrace();
            }, () -> {
                System.out.println("\n\nStreaming completed!");
            });
            
            // Prevent the JVM from exiting immediately
            System.out.println("\nWaiting for streaming response to complete (timeout: " + (waitTime / 1000) + " seconds)...");
            try { 
                Thread.sleep(waitTime);
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
            
            System.out.println("\nNote: If the response was cut off, you can increase the wait time by setting the STREAMING_WAIT_TIME environment variable (in milliseconds).");
            System.out.println("\nDemo completed!");
        } catch (Exception e) {
            System.err.println("Error: " + e.getMessage());
            System.err.println("\nThe current SDK might not support direct chat completion streaming.");
            System.err.println("This could be due to missing or changed classes in the SDK version.");
            System.err.println("These errors help package developers understand what needs to be fixed.");
            e.printStackTrace();
        }
    }
}