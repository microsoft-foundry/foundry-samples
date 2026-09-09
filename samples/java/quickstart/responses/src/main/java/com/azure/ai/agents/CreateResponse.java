package com.azure.ai.agents;

import com.azure.identity.DefaultAzureCredentialBuilder;
import com.openai.models.responses.Response;
import com.openai.models.responses.ResponseCreateParams;

public class CreateResponse {
    public static void main(String[] args) {
        // Format: "https://resource_name.services.ai.azure.com/api/projects/project_name"
        String foundryProjectEndpoint = "your_project_endpoint";

        // Create responses client to call Foundry API
        ResponsesClient responsesClient = new AgentsClientBuilder()
                .credential(new DefaultAzureCredentialBuilder().build())
                .endpoint(foundryProjectEndpoint)
                .buildResponsesClient();

        // Run a responses API call
        ResponseCreateParams responseRequest = new ResponseCreateParams.Builder()
                .input("What is the size of France in square miles?")
                .model("gpt-5-mini")
                .build();
        Response response = responsesClient.getResponseService().create(responseRequest);
        System.out.println(response.output());
    }
}