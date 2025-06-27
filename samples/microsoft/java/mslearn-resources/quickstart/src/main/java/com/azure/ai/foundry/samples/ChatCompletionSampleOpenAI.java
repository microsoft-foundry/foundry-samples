package com.azure.ai.foundry.samples;

import com.azure.core.util.logging.ClientLogger;
import com.openai.client.OpenAIClient;
import com.openai.client.okhttp.OpenAIOkHttpClient;
import com.openai.models.ChatModel;
import com.openai.models.chat.completions.ChatCompletion;
import com.openai.models.chat.completions.ChatCompletionCreateParams;

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
            prompt = "What is the OpenAI API? Explain in a short paragraph.";
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
            logger.info("Received response from model");
            System.out.println("\nResponse from AI assistant:\n" + content);
        } catch (Exception e) {
            logger.error("Error during chat completion", e);
            System.err.println("Error: " + e.getMessage());
        }
    }
}