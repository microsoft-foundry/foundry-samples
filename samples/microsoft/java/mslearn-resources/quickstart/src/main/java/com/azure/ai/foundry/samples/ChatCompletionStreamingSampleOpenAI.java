package com.azure.ai.foundry.samples;

import com.azure.core.util.logging.ClientLogger;
import com.openai.client.OpenAIClient;
import com.openai.client.okhttp.OpenAIOkHttpClient;
import com.openai.core.http.StreamResponse;
import com.openai.models.chat.completions.ChatCompletionChunk;
import com.openai.models.chat.completions.ChatCompletionCreateParams;

/**
 * Sample demonstrating streaming chat completion functionality using the OpenAI Java SDK.
 * 
 * This sample shows how to:
 * - Set up authentication with OpenAI API key
 * - Create a streaming chat completion request with a user message
 * - Process and display streaming tokens as they arrive
 * - Handle the stream with proper resource management using try-with-resources
 * - Work with functional programming patterns for stream processing
 * 
 * Environment variables:
 * - OPENAI_API_KEY: Required. The API key for OpenAI authentication.
 * - OPENAI_MODEL: Required. The model name to use (e.g., "gpt-4o", "gpt-4-turbo").
 * - CHAT_PROMPT: Optional. The prompt to send to the model (uses a default if not provided).
 * 
 * Note: This sample uses the official OpenAI Java client library (com.openai:openai-java:2.7.0), 
 * which is different from the Azure AI Inference SDK used in other samples. It demonstrates streaming
 * interaction with OpenAI models rather than Azure-hosted models.
 * 
 * SDK Features Demonstrated:
 * - Creating an OpenAI client with API key authentication
 * - Using the StreamResponse<T> interface for handling streaming responses
 * - Processing token-by-token streaming responses in real time
 * - Proper resource management with try-with-resources pattern
 * - Using Java Stream API with functional programming for token processing
 * - Error handling for streaming connections
 */

public class ChatCompletionStreamingSampleOpenAI {
    private static final ClientLogger logger = new ClientLogger(ChatCompletionStreamingSampleOpenAI.class);

    public static void main(String[] args) {
        String apiKey   = System.getenv("OPENAI_API_KEY");
        String modelEnv = System.getenv("OPENAI_MODEL");
        String prompt   = System.getenv("CHAT_PROMPT");

        if (apiKey == null || apiKey.isBlank()) {
            logger.error("OPENAI_API_KEY is required but not set");
            return;
        }

        // Check if model is specified
        if (modelEnv == null || modelEnv.isBlank()) {
            logger.error("OPENAI_MODEL environment variable is required but not set");
            return;
        }

        // Use the model name directly instead of trying to convert to enum
        logger.info("Using model: {}", modelEnv);

        if (prompt == null || prompt.isBlank()) {
            prompt = "What best practices should I follow when asking an AI model to review Java code?";
            logger.info("No CHAT_PROMPT provided, using default: {}", prompt);
        }

        try {
            OpenAIClient client = OpenAIOkHttpClient.builder()
                .apiKey(apiKey)
                .build();

            ChatCompletionCreateParams params = ChatCompletionCreateParams.builder()
                .addUserMessage(prompt)
                .model(modelEnv)  // Use the model name string directly
                .build();

            logger.info("Starting streaming chat completion...");
            logger.info("\nResponse from AI assistant (streaming):");

            // Stream tokens as they arrive
            // Use try-with-resources to ensure the stream is properly closed
            // This is important for resource management with streaming responses
            try (StreamResponse<ChatCompletionChunk> stream = 
                     client.chat().completions().createStreaming(params)) {
                
                // Process the stream using Java Stream API:
                // 1. Convert to a stream of chunks
                // 2. Extract all choices from each chunk
                // 3. Extract content deltas from each choice
                // 4. Print each token as it arrives
                stream.stream()
                      .flatMap(ch -> ch.choices().stream())
                      .flatMap(choice -> choice.delta().content().stream())
                      .forEach(token -> logger.info("{}", token));
            }

            logger.info("Streaming demo completed successfully");
        } catch (Exception e) {
            logger.error("Error during streaming chat completion", e);
        }
    }
}