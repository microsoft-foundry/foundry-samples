package com.azure.ai.foundry.samples;

import com.azure.ai.inference.ChatCompletionsClient;
import com.azure.ai.inference.ChatCompletionsClientBuilder;
import com.azure.ai.inference.models.ChatCompletions;
import com.azure.core.credential.AzureKeyCredential;
import com.azure.core.credential.TokenCredential;
import com.azure.core.exception.HttpResponseException;
import com.azure.core.util.logging.ClientLogger;
import com.azure.identity.DefaultAzureCredentialBuilder;

/**
 * Sample demonstrating non-streaming chat completion functionality
 * using the Azure AI Inference SDK, wired to your AOAI project endpoint.
 *
 * Environment variables:
 * - PROJECT_ENDPOINT:          Required. Your Azure AI project endpoint.
 * - AZURE_AI_API_KEY:          Optional. Your API key (falls back to DefaultAzureCredential).
 * - AZURE_MODEL_DEPLOYMENT_NAME: Optional. Model deployment name (default: "phi-4").
 * - AZURE_MODEL_API_PATH:      Optional. API path segment (default: "deployments").
 * - CHAT_PROMPT:               Optional. The prompt to send (uses a default if not provided).
 * 
 * SDK Features Demonstrated:
 * - Using the Azure AI Inference SDK (com.azure:azure-ai-inference:1.0.0-beta.5)
 * - Creating a ChatCompletionsClient with Azure or API key authentication
 * - Configuring endpoint paths for different model deployments
 * - Using the simplified complete() method for quick completions
 * - Accessing response content through strongly-typed objects
 * - Implementing proper error handling for service requests
 * - Choosing between DefaultAzureCredential and AzureKeyCredential
 * 
 */

public class ChatCompletionSample {
    private static final ClientLogger logger = new ClientLogger(ChatCompletionSample.class);

    public static void main(String[] args) {
        // 1) Read and validate the project endpoint
        String projectEndpoint = System.getenv("PROJECT_ENDPOINT");
        if (projectEndpoint == null || projectEndpoint.isBlank()) {
            logger.error("PROJECT_ENDPOINT is required but not set");
            return;
        }

        // 2) Optional auth + model settings
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
            logger.info("Using inference endpoint: {}", fullEndpoint);

            // 4) Create the client with key or token credential :contentReference[oaicite:0]{index=0}
            ChatCompletionsClient client;
            if (apiKey != null && !apiKey.isBlank()) {
                logger.info("Authenticating using API key");
                client = new ChatCompletionsClientBuilder()
                    .credential(new AzureKeyCredential(apiKey))
                    .endpoint(fullEndpoint)
                    .buildClient();
            } else {
                logger.info("Authenticating using DefaultAzureCredential");
                TokenCredential credential = new DefaultAzureCredentialBuilder().build();
                client = new ChatCompletionsClientBuilder()
                    .credential(credential)
                    .endpoint(fullEndpoint)
                    .buildClient();
            }

            // 5) Send a simple chat completion request
            logger.info("Sending chat completion request with prompt: {}", prompt);
            ChatCompletions completions = client.complete(prompt);

            // 6) Process the response
            String content = completions.getChoice().getMessage().getContent();
            logger.info("Received response from model");
            System.out.println("\nResponse from AI assistant:\n" + content);
        } catch (HttpResponseException e) {
            // Handle API errors
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
            // Handle all other exceptions
            logger.error("Error in chat completion: {}", e.getMessage(), e);
        }
    }
}
