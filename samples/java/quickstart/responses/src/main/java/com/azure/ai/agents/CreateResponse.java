package com.azure.ai.agents;

import com.azure.identity.DefaultAzureCredentialBuilder;
import com.openai.models.responses.Response;
import com.openai.models.responses.ResponseCreateParams;

public class CreateResponse {
    public static void main(String[] args) {
        // Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
        String ProjectEndpoint = System.getenv().getOrDefault("AZURE_AI_PROJECT_ENDPOINT", "your_project_endpoint");
        String ModelDeployment = System.getenv().getOrDefault("MODEL_DEPLOYMENT", "gpt-5-mini");

        // Create responses client to call Foundry API
        ResponsesClient responsesClient = new AgentsClientBuilder()
                .credential(new DefaultAzureCredentialBuilder().build())
                .endpoint(ProjectEndpoint)
                .buildResponsesClient();

        // Run a responses API call
        ResponseCreateParams responseRequest = new ResponseCreateParams.Builder()
                .input("What is the size of France in square miles?")
                .model(ModelDeployment)
                .build();
        Response response = responsesClient.getResponseService().create(responseRequest);
        System.out.println(response.output());
    }
}