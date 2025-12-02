package com.azure.ai.foundry.samples;

import com.azure.core.util.logging.ClientLogger;
import com.openai.client.OpenAIClient;
import com.openai.client.okhttp.OpenAIOkHttpClient;
import com.openai.models.ChatModel;
import com.openai.models.chat.completions.ChatCompletion;
import com.openai.models.chat.completions.ChatCompletionCreateParams;

/**
 * Sample demonstrating chat completion functionality using the OpenAI Java SDK.
 * 
 * This sample shows how to:
 * - Set up authentication with OpenAI API key
 * - Create a chat completion request with a user message
 * - Process and display the response from the model
 * - Work with the OpenAI Java SDK for direct platform access
 * 
 * Environment variables:
 * - OPENAI_API_KEY: Required. The API key for OpenAI authentication.
 * - OPENAI_MODEL: Required. The model name to use (e.g., "gpt-4o", "gpt-4-turbo").
 * - CHAT_PROMPT: Optional. The prompt to send to the model (uses a default if not provided).
 * 
 * Note: This sample uses the official OpenAI Java client library (com.openai:openai-java:2.7.0), 
 * which is different from the Azure AI Inference SDK used in other samples. It demonstrates direct
 * interaction with OpenAI models rather than Azure-hosted models.
 * 
 * SDK Features Demonstrated:
 * - Creating an OpenAI client with API key authentication
 * - Building chat completion parameters using the builder pattern
 * - Sending synchronous chat completion requests
 * - Processing JSON responses through strongly-typed objects
 * - Error handling for API interactions
 */

public class ChatCompletionSampleOpenAI {
    private static final ClientLogger logger = new ClientLogger(ChatCompletionSampleOpenAI.class);

    public static void main(String[] args) {
        // Load environment variables
        String apiKey    = System.getenv("OPENAI_API_KEY");
        String modelEnv  = System.getenv("OPENAI_MODEL");
        String prompt    = System.getenv("CHAT_PROMPT");

        // Validate API key
        if (apiKey == null || apiKey.isBlank()) {
            logger.error("OPENAI_API_KEY is required but not set");
            return;
        }

        // Check if model is specified
        if (modelEnv == null || modelEnv.isBlank()) {
            logger.error("OPENAI_MODEL environment variable is required but not set");
            return;
        }

        // Use the modelEnv directly as a string instead of trying to convert to enum
        logger.info("Using model: {}", modelEnv);

        // Default prompt if none provided
        if (prompt == null || prompt.isBlank()) {
            prompt = "What best practices should I follow when asking an AI model to review Java code?";
            logger.info("No CHAT_PROMPT provided, using default: {}", prompt);
        }

        try {
            // Build the client
            OpenAIClient client = OpenAIOkHttpClient.builder()
                .apiKey(apiKey)
                .build();

            // Prepare request parameters
            ChatCompletionCreateParams params = ChatCompletionCreateParams.builder()
                .addUserMessage(prompt)
                .model(modelEnv)  // Use the model name string directly
                .build();

            logger.info("Sending chat completion request...");
            ChatCompletion completion = client.chat().completions().create(params);

            // Extract and print the assistant's reply
            // Handle Optional<String> by using orElse for null safety
            String content = completion.choices().get(0).message().content().orElse("No response content");
            logger.info("\nResponse from AI assistant:\n{}", content);
        } catch (Exception e) {
            logger.error("Error during chat completion", e);
        }
    }
}