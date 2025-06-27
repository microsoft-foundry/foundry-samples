package com.azure.ai.foundry.samples;

import com.azure.core.util.logging.ClientLogger;
import com.openai.client.OpenAIClient;
import com.openai.client.okhttp.OpenAIOkHttpClient;
import com.openai.core.http.StreamResponse;
import com.openai.models.chat.completions.ChatCompletionChunk;
import com.openai.models.chat.completions.ChatCompletionCreateParams;

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
            prompt = "Write a short poem about AI in Java.";
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
            System.out.println("\nResponse from AI assistant (streaming):");

            // Stream tokens as they arrive
            try (StreamResponse<ChatCompletionChunk> stream = 
                     client.chat().completions().createStreaming(params)) {
                stream.stream()
                      .flatMap(ch -> ch.choices().stream())
                      .flatMap(choice -> choice.delta().content().stream())
                      .forEach(System.out::print);
            }

            System.out.println("\n\nStreaming completed!");
            logger.info("Streaming demo completed successfully");
        } catch (Exception e) {
            logger.error("Error during streaming chat completion", e);
            System.err.println("Error: " + e.getMessage());
        }
    }
}