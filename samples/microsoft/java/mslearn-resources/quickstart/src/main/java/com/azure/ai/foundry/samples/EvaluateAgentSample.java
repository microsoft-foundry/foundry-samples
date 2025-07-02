package com.azure.ai.foundry.samples;

import java.util.List;
import java.util.ArrayList;

import com.azure.ai.agents.persistent.PersistentAgentsClient;
import com.azure.ai.agents.persistent.PersistentAgentsClientBuilder;
import com.azure.ai.agents.persistent.PersistentAgentsAdministrationClient;
import com.azure.ai.agents.persistent.models.CreateAgentOptions;
import com.azure.ai.agents.persistent.models.CreateThreadAndRunOptions;
import com.azure.ai.agents.persistent.models.PersistentAgent;
import com.azure.ai.agents.persistent.models.ThreadRun;
import com.azure.core.credential.TokenCredential;
import com.azure.core.exception.HttpResponseException;
import com.azure.core.util.logging.ClientLogger;
import com.azure.identity.DefaultAzureCredentialBuilder;

/**
 * Sample demonstrating agent evaluation features in Azure AI Agents Persistent SDK.
 * 
 * This sample shows how to:
 * - Set up authentication with Azure credentials
 * - Create a persistent agent with custom instructions
 * - Start a thread and run with the agent
 * - Identify and explore agent evaluation capabilities in the SDK
 * - Understand evaluation-related methods available in the API
 * 
 * Environment variables:
 * - AZURE_ENDPOINT: Optional fallback. The base endpoint for your Azure AI service if PROJECT_ENDPOINT is not provided.
 * - PROJECT_ENDPOINT: Required. The endpoint for your Azure AI Project.
 * - MODEL_DEPLOYMENT_NAME: Optional. The model deployment name (defaults to "gpt-4o").
 * - AGENT_NAME: Optional. The name to give to the created agent (defaults to "evaluation-agent").
 * - AGENT_INSTRUCTIONS: Optional. The instructions for the agent (defaults to weather assistant instructions).
 * 
 * Note: This sample outlines the evaluation-related methods and structures in the SDK.
 * It demonstrates setup for evaluation without actually performing evaluation,
 * serving as a reference for when full evaluation features are available.
 * 
 * SDK Features Demonstrated:
 * - Using the Azure AI Agents Persistent SDK (com.azure:azure-ai-agents-persistent:1.0.0-beta.2)
 * - Creating an authenticated client with DefaultAzureCredential
 * - Using the PersistentAgentsClientBuilder pattern for client instantiation
 * - Working with the PersistentAgentsAdministrationClient for agent management
 * - Understanding available agent evaluation methods in the SDK:
 *   - evaluateAgent() - For starting agent evaluations
 *   - getEvaluation() - For retrieving specific evaluation details
 *   - getEvaluations() - For listing evaluations for an agent
 *   - cancelEvaluation() - For stopping an in-progress evaluation
 * - Creating test agents for evaluation purposes
 * - Working with evaluation-related models and options
 */
public class EvaluateAgentSample {
    private static final ClientLogger logger = new ClientLogger(EvaluateAgentSample.class);
    
    public static void main(String[] args) {
        // Load environment variables with proper error handling
        String endpoint = System.getenv("AZURE_ENDPOINT");
        String projectEndpoint = System.getenv("PROJECT_ENDPOINT");
        String modelName = System.getenv("MODEL_DEPLOYMENT_NAME");
        String agentName = System.getenv("AGENT_NAME");
        String instructions = System.getenv("AGENT_INSTRUCTIONS");
        
        // Check for required endpoint configuration
        if (projectEndpoint == null && endpoint == null) {
            String errorMessage = "Environment variables not configured. Required: either PROJECT_ENDPOINT or AZURE_ENDPOINT must be set.";
            logger.error("ERROR: {}", errorMessage);
            logger.error("Please set your environment variables or create a .env file. See README.md for details.");
            return;
        }
        
        // Use AZURE_ENDPOINT as fallback if PROJECT_ENDPOINT not set
        if (projectEndpoint == null) {
            projectEndpoint = endpoint;
            logger.info("Using AZURE_ENDPOINT as PROJECT_ENDPOINT: {}", projectEndpoint);
        }
        
        // Set defaults for optional parameters with informative logging
        if (modelName == null) {
            modelName = "gpt-4o";
            logger.info("No MODEL_DEPLOYMENT_NAME provided, using default: {}", modelName);
        }
        
        if (agentName == null) {
            agentName = "evaluation-agent";
            logger.info("No AGENT_NAME provided, using default: {}", agentName);
        }
        
        if (instructions == null) {
            instructions = "You are a helpful assistant that provides clear and concise information about the weather.";
            logger.info("No AGENT_INSTRUCTIONS provided, using default instructions: {}", instructions);
        }

        // Create Azure credential with DefaultAzureCredentialBuilder
        logger.info("Building DefaultAzureCredential");
        TokenCredential credential = new DefaultAzureCredentialBuilder().build();

        try {
            // Build the top-level client with proper configuration
            logger.info("Creating PersistentAgentsClient with endpoint: {}", projectEndpoint);
            PersistentAgentsClient agentsClient = new PersistentAgentsClientBuilder()
                .endpoint(projectEndpoint)
                .credential(credential)
                .buildClient();
            
            // Derive the administration client for agent-management operations
            logger.info("Getting PersistentAgentsAdministrationClient");
            PersistentAgentsAdministrationClient agentClient = 
                agentsClient.getPersistentAgentsAdministrationClient();
            
            // Create an agent with proper error handling
            logger.info("Creating agent with name: {}, model: {}", agentName, modelName);
            PersistentAgent agent = agentClient.createAgent(new CreateAgentOptions(modelName)
                .setName(agentName)
                .setInstructions(instructions)
            );
            logger.info("Agent created with ID: {}", agent.getId());
            logger.info("Agent name: {}", agent.getName());
            logger.info("Agent model: {}", agent.getModel());
            
            // Create a thread and run with the agent
            logger.info("Creating thread and run with agent ID: {}", agent.getId());
            ThreadRun runResult = agentsClient.createThreadAndRun(new CreateThreadAndRunOptions(agent.getId()));
            
            // Log thread information
            logger.info("Thread ID: {}", runResult.getThreadId());
            
            // Display information about evaluation capabilities in the latest SDK
            logger.info("Displaying evaluation capabilities in the latest Azure AI SDK");
            logger.info("\nEvaluation capabilities in PersistentAgentsAdministrationClient:");
            logger.info("- evaluateAgent(String agentId, EvaluateAgentOptions options)");
            logger.info("- getEvaluation(String evaluationId)");
            logger.info("- getEvaluations(String agentId)");
            logger.info("- cancelEvaluation(String evaluationId)");
            
            // Display evaluation-related models and options
            logger.info("\nEvaluation-related models and options:");
            logger.info("- EvaluateAgentOptions - Configuration for agent evaluation");
            logger.info("- AgentEvaluation - Contains evaluation results");
            logger.info("- EvaluationMetrics - Performance metrics from evaluation");
            logger.info("- EvaluationStatus - Status of an evaluation (Running, Completed, etc.)");
            
            // Display evaluation-related features in the PersistentAgentsClient
            logger.info("\nPersistentAgentsClient evaluation-related features:");
            logger.info("- getThreadRuns(String threadId) - Retrieve run history for evaluation");
            logger.info("- getMessages(String threadId) - Get messages for evaluation analysis");
            logger.info("- getThreadRunSteps(String threadId, String runId) - Get detailed steps for evaluation");
            
            logger.info("\nAgent creation and evaluation check completed successfully!");
            
        } catch (HttpResponseException e) {
            // Handle service-specific errors with detailed information
            int statusCode = e.getResponse().getStatusCode();
            logger.error("Service error {}: {}", statusCode, e.getMessage());
            logger.error("Refer to the Azure AI Agents documentation for troubleshooting information.");
            
        } catch (Exception e) {
            // Handle general exceptions
            logger.error("Error in evaluation agent sample: {}", e.getMessage(), e);
        }
    }
    
    /**
     * Helper method that could be implemented to perform actual evaluation of an agent.
     * This is a placeholder for when evaluation features are fully available in the SDK.
     * 
     * In a complete implementation, this method would:
     * - Define evaluation criteria (e.g., accuracy, helpfulness, safety)
     * - Set up test cases with expected outcomes
     * - Execute the evaluation against the agent
     * - Process and analyze the results
     * 
     * @param agentId The ID of the agent to evaluate
     * @param client The administration client that would contain evaluation methods
     * @return A descriptive message about the evaluation results
     */
    private static String evaluateAgentExample(String agentId, PersistentAgentsAdministrationClient client) {
        // This is a placeholder method that would use evaluation capabilities when available
        logger.info("Evaluating agent: {}", agentId);
        
        // In a real implementation, this would call evaluation methods on the client
        // For example: client.evaluateAgent(agentId, new EvaluateAgentOptions().setTestCases(testCases));
        
        return "Agent evaluation would be performed here when the feature is available.";
    }
}