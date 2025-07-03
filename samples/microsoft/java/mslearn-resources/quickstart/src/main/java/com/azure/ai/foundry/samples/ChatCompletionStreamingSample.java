
package com.azure.ai.foundry.samples;

import com.azure.ai.inference.ChatCompletionsClient;
import com.azure.ai.inference.ChatCompletionsClientBuilder;
import com.azure.ai.inference.models.ChatCompletionsOptions;
import com.azure.ai.inference.models.ChatRequestMessage;
import com.azure.ai.inference.models.ChatRequestSystemMessage;
import com.azure.ai.inference.models.ChatRequestUserMessage;
import com.azure.ai.inference.models.StreamingChatCompletionsUpdate;
import com.azure.ai.inference.models.StreamingChatResponseMessageUpdate;
import com.azure.core.credential.AzureKeyCredential;
import com.azure.core.exception.HttpResponseException;
import com.azure.core.util.CoreUtils;
import com.azure.core.util.IterableStream;
import com.azure.core.util.logging.ClientLogger;
import com.azure.identity.DefaultAzureCredentialBuilder;

import java.util.ArrayList;
import java.util.List;

/**
 * Sample demonstrating streaming chat completion functionality
 * using the Azure AI Inference SDK, wired to your AOAI project endpoint.
 *
 * Environment variables:
 * - PROJECT_ENDPOINT:           Required. Your Azure AI project endpoint.
 * - AZURE_AI_API_KEY:           Optional. Your API key (falls back to DefaultAzureCredential).
 * - AZURE_MODEL_DEPLOYMENT_NAME: Optional. Model deployment name (defaults to "phi-4").
 * - AZURE_MODEL_API_PATH:       Optional. API path segment (defaults to "deployments").
 * - CHAT_PROMPT:                Optional. The prompt to send (uses a default if not provided).
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
 * 
 */
 
 
public class ChatCompletionStreamingSample {
    private static final ClientLogger logger = new ClientLogger(ChatCompletionStreamingSample.class);

    public static void main(String[] args) {
        // 1) Read and validate the project endpoint
        String projectEndpoint = System.getenv("PROJECT_ENDPOINT");
        if (projectEndpoint == null || projectEndpoint.isBlank()) {
            logger.error("PROJECT_ENDPOINT is required but not set");
            return;
        }

        // 2) Read optional settings
        String apiKey          = System.getenv("AZURE_AI_API_KEY");
        String deploymentName  = System.getenv("AZURE_MODEL_DEPLOYMENT_NAME");
        String apiPath         = System.getenv("AZURE_MODEL_API_PATH");
        String prompt          = System.getenv("CHAT_PROMPT");

        if (deploymentName == null || deploymentName.isBlank()) {
            deploymentName = "phi-4";
            logger.info("No AZURE_MODEL_DEPLOYMENT_NAME provided, using default: {}", deploymentName);
        }
        if (apiPath == null || apiPath.isBlank()) {
            apiPath = "deployments";
            logger.info("No AZURE_MODEL_API_PATH provided, using default: {}", apiPath);
        }
        if (prompt == null || prompt.isBlank()) {
            prompt = "What best practices should I follow when asking an AI model to review Java code?";
            logger.info("No CHAT_PROMPT provided, using default prompt: {}", prompt);
        }

        try {
            // 3) Build the full inference endpoint URL
            String fullEndpoint = projectEndpoint.endsWith("/")
                ? projectEndpoint
                : projectEndpoint + "/";
            fullEndpoint += apiPath + "/" + deploymentName;
            logger.info("Using streaming inference endpoint: {}", fullEndpoint);

            // 4) Create the ChatCompletionsClient with key or token
            ChatCompletionsClient client;
            if (apiKey != null && !apiKey.isBlank()) {
                logger.info("Authenticating using API key");
                client = new ChatCompletionsClientBuilder()
                    .credential(new AzureKeyCredential(apiKey))
                    .endpoint(fullEndpoint)
                    .buildClient();
            } else {
                logger.info("Authenticating using DefaultAzureCredential");
                client = new ChatCompletionsClientBuilder()
                    .credential(new DefaultAzureCredentialBuilder().build())
                    .endpoint(fullEndpoint)
                    .buildClient();
            }

            // 5) Prepare the conversation messages
            List<ChatRequestMessage> chatMessages = new ArrayList<>();
            chatMessages.add(new ChatRequestSystemMessage("You are a helpful assistant providing clear and concise information."));
            chatMessages.add(new ChatRequestUserMessage(prompt));

            logger.info("Starting streaming chat completion with prompt: {}", prompt);
            System.out.println("\nResponse from AI assistant (streaming):");

            // 6) Fire off the streaming request
            ChatCompletionsOptions options = new ChatCompletionsOptions(chatMessages);
            IterableStream<StreamingChatCompletionsUpdate> stream = client.completeStream(options);

            // 7) Process each update
            stream.stream().forEach(update -> {
                if (CoreUtils.isNullOrEmpty(update.getChoices())) {
                    logger.atInfo().log("Received empty update");
                    return;
                }
                StreamingChatResponseMessageUpdate delta = update.getChoice().getDelta();
                if (delta.getRole() != null) {
                    logger.atInfo().log("Role: " + delta.getRole());
                }
                if (delta.getContent() != null) {
                    // print tokens as they arrive
                    System.out.print(delta.getContent());
                }
            });

            System.out.println("\n\nStreaming completed successfully");
            logger.info("Streaming demo completed");

        } catch (HttpResponseException e) {
            int status = e.getResponse().getStatusCode();
            logger.error("Service error {}: {}", status, e.getMessage());
            if (status == 401 || status == 403) {
                logger.error("Authentication failed. Check API key or Azure credentials.");
            } else if (status == 404) {
                logger.error("Deployment not found. Verify deployment name and endpoint.");
            } else if (status == 429) {
                logger.error("Rate limit exceeded. Please retry later.");
            }
        } catch (Exception e) {
            logger.error("Error in streaming chat completion: {}", e.getMessage(), e);
        }
    }
}
