// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

package com.microsoft.azure.samples;

// <imports_and_includes>
import com.azure.ai.agents.AgentsClient;
import com.azure.ai.agents.AgentsClientBuilder;
import com.azure.ai.agents.ConversationsClient;
import com.azure.ai.agents.ResponsesClient;
import com.azure.ai.agents.models.*;
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.openai.models.conversations.Conversation;
import com.openai.models.conversations.items.ItemCreateParams;
import com.openai.models.responses.EasyInputMessage;
import com.openai.models.responses.Response;
import io.github.cdimascio.dotenv.Dotenv;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
// </imports_and_includes>

/**
 * Evaluation Script for Modern Workplace Assistant
 * Tests the agent with predefined business scenarios to assess quality.
 * 
 * Note: This Java implementation uses the Agent SDK v2 beta which has limited
 * tool support compared to the Python SDK. Tool integration (SharePoint, MCP)
 * is not yet available in the Java SDK v2 beta.
 */
public class EvaluateAgent {

    private static Dotenv dotenv;
    private static AgentsClient agentsClient;
    private static ResponsesClient responsesClient;
    private static ConversationsClient conversationsClient;
    private static final Gson gson = new GsonBuilder().setPrettyPrinting().create();

    public static void main(String[] args) {
        System.out.println("🧪 Modern Workplace Assistant - Evaluation");
        System.out.println("=".repeat(50));

        try {
            // Load environment variables from current directory
            dotenv = Dotenv.configure()
                    .directory("./")
                    .ignoreIfMissing()
                    .load();

            // Create agent
            AgentVersionObject agent = createWorkplaceAssistant();
            
            // Run evaluation
            List<EvaluationResult> results = runEvaluation(agent);
            
            // Save results
            saveResults(results);
            
            System.out.println("💾 Results saved to evaluation_results.json");
            
        } catch (Exception e) {
            System.err.println("❌ Evaluation failed: " + e.getMessage());
            e.printStackTrace();
        }
    }

    // <load_test_data>
    /**
     * Load test questions from JSONL file
     */
    private static List<TestQuestion> loadTestQuestions(String filepath) throws IOException {
        List<TestQuestion> questions = new ArrayList<>();
        
        try (BufferedReader reader = new BufferedReader(new FileReader(filepath))) {
            String line;
            while ((line = reader.readLine()) != null) {
                line = line.trim();
                if (!line.isEmpty()) {
                    JsonObject json = JsonParser.parseString(line).getAsJsonObject();
                    TestQuestion q = new TestQuestion();
                    q.question = json.get("question").getAsString();
                    
                    // Parse expected keywords array
                    if (json.has("expected_keywords")) {
                        json.getAsJsonArray("expected_keywords").forEach(elem -> 
                            q.expectedKeywords.add(elem.getAsString())
                        );
                    }
                    
                    questions.add(q);
                }
            }
        }
        
        return questions;
    }
    // </load_test_data>

    // <run_batch_evaluation>
    /**
     * Run evaluation with test questions
     */
    private static List<EvaluationResult> runEvaluation(AgentVersionObject agent) {
        List<TestQuestion> questions;
        try {
            questions = loadTestQuestions("questions.jsonl");
        } catch (IOException e) {
            System.err.println("⚠️  Could not load questions.jsonl, using default questions");
            questions = getDefaultQuestions();
        }
        
        List<EvaluationResult> results = new ArrayList<>();
        
        System.out.println("🧪 Running evaluation with " + questions.size() + " test questions...");
        System.out.println("⚠️  Note: Evaluation uses Java SDK v2 beta (limited tool support)");
        
        for (int i = 0; i < questions.size(); i++) {
            TestQuestion q = questions.get(i);
            System.out.println(String.format("\n📝 Question %d/%d: %s", i + 1, questions.size(), q.question));
            
            ChatResult chatResult = chatWithAssistant(agent, q.question);
            
            // Simple evaluation: check if response contains expected keywords
            boolean containsExpected = false;
            if (chatResult.response != null) {
                String responseLower = chatResult.response.toLowerCase();
                containsExpected = q.expectedKeywords.stream()
                        .anyMatch(keyword -> responseLower.contains(keyword.toLowerCase()));
            }
            
            EvaluationResult result = new EvaluationResult();
            result.question = q.question;
            result.response = chatResult.response;
            result.status = chatResult.status;
            result.containsExpected = containsExpected;
            result.expectedKeywords = q.expectedKeywords;
            
            results.add(result);
            
            String statusIcon = containsExpected ? "✅" : "⚠️";
            System.out.println(String.format("%s Response length: %d chars (Status: %s)", 
                    statusIcon, chatResult.response != null ? chatResult.response.length() : 0, chatResult.status));
            
            // Show a preview of the response
            if (chatResult.response != null && chatResult.response.length() > 0) {
                String preview = chatResult.response.length() > 150 
                        ? chatResult.response.substring(0, 150) + "..." 
                        : chatResult.response;
                System.out.println("   Response preview: " + preview);
            }
        }
        
        return results;
    }
    // </run_batch_evaluation>

    // <evaluation_results>
    /**
     * Save evaluation results to JSON file
     */
    private static void saveResults(List<EvaluationResult> results) throws IOException {
        // Calculate pass rate
        long passed = results.stream().filter(r -> r.containsExpected).count();
        double passRate = (double) passed / results.size() * 100;
        
        System.out.println("\n" + "=".repeat(50));
        System.out.println("📊 Evaluation Results Summary");
        System.out.println("=".repeat(50));
        System.out.println(String.format("Total Questions: %d", results.size()));
        System.out.println(String.format("Passed: %d", passed));
        System.out.println(String.format("Failed: %d", results.size() - passed));
        System.out.println(String.format("Pass Rate: %.1f%%", passRate));
        System.out.println("=".repeat(50));
        
        try (FileWriter writer = new FileWriter("evaluation_results.json")) {
            gson.toJson(results, writer);
        }
    }
    // </evaluation_results>

    /**
     * Default test questions if file not found
     */
    private static List<TestQuestion> getDefaultQuestions() {
        List<TestQuestion> questions = new ArrayList<>();
        
        TestQuestion q1 = new TestQuestion();
        q1.question = "What is a typical enterprise remote work policy regarding security requirements?";
        q1.expectedKeywords.add("remote");
        q1.expectedKeywords.add("security");
        q1.expectedKeywords.add("policy");
        questions.add(q1);
        
        TestQuestion q2 = new TestQuestion();
        q2.question = "How do I set up Azure Active Directory conditional access?";
        q2.expectedKeywords.add("azure");
        q2.expectedKeywords.add("conditional");
        q2.expectedKeywords.add("access");
        questions.add(q2);
        
        TestQuestion q3 = new TestQuestion();
        q3.question = "What collaboration tools are recommended for secure internal use?";
        q3.expectedKeywords.add("teams");
        q3.expectedKeywords.add("sharepoint");
        q3.expectedKeywords.add("collaboration");
        questions.add(q3);
        
        TestQuestion q4 = new TestQuestion();
        q4.question = "What Azure AD configuration should I implement for secure remote work?";
        q4.expectedKeywords.add("azure");
        q4.expectedKeywords.add("mfa");
        q4.expectedKeywords.add("conditional");
        questions.add(q4);
        
        return questions;
    }

    /**
     * Create workplace assistant for evaluation
     */
    private static AgentVersionObject createWorkplaceAssistant() {
        System.out.println("🤖 Creating Modern Workplace Assistant for evaluation...");

        // Authentication setup
        String endpoint = dotenv.get("PROJECT_ENDPOINT");
        String modelDeploymentName = dotenv.get("MODEL_DEPLOYMENT_NAME");
        
        TokenCredential credential = new DefaultAzureCredentialBuilder().build();

        // Build clients
        AgentsClientBuilder builder = new AgentsClientBuilder()
                .credential(credential)
                .endpoint(endpoint);

        agentsClient = builder.buildClient();
        responsesClient = builder.buildResponsesClient();
        conversationsClient = builder.buildConversationsClient();

        System.out.println("✅ Connected to: " + endpoint);

        // Agent creation instructions
        String instructions = """
You are a Modern Workplace Assistant for Contoso Corporation specializing in Azure and Microsoft 365 guidance.

CAPABILITIES:
- Provide detailed Azure and Microsoft 365 technical guidance
- Explain enterprise security policies and implementation steps
- Help with Azure AD, Conditional Access, MFA, and security configurations
- Recommend best practices for remote work security

RESPONSE STRATEGY:
- Provide comprehensive technical guidance
- Include step-by-step implementation instructions
- Reference best practices and security considerations
- Explain common enterprise policies and how to implement them
- Always cite relevant Azure/M365 services and features

EVALUATION FOCUS:
Your responses will be evaluated on:
1. Accuracy of technical information
2. Completeness of implementation steps
3. Relevance to enterprise scenarios
4. Use of appropriate technical terminology
""";

        // Create agent definition (no tools in Java SDK v2 beta)
        PromptAgentDefinition definition = new PromptAgentDefinition(modelDeploymentName)
                .setInstructions(instructions);

        AgentVersionObject agent = agentsClient.createAgentVersion(
                "Modern_Workplace_Assistant_Eval",
                definition
        );

        System.out.println("✅ Agent created for evaluation");
        System.out.println("   Agent ID: " + agent.getId());
        System.out.println("   Agent Name: " + agent.getName());
        System.out.println("   Agent Version: " + agent.getVersion());
        
        System.out.println("\n⚠️  Note: Java SDK v2 beta limitations:");
        System.out.println("   - Tool integration (SharePoint, MCP) not available");
        System.out.println("   - Evaluation tests core agent conversation functionality");
        
        return agent;
    }

    /**
     * Chat with assistant for evaluation
     */
    private static ChatResult chatWithAssistant(AgentVersionObject agent, String message) {
        try {
            // Create conversation
            Conversation conversation = conversationsClient.getOpenAIClient().create();

            // Add user message
            conversationsClient.getOpenAIClient().items().create(
                    ItemCreateParams.builder()
                            .conversationId(conversation.id())
                            .addItem(EasyInputMessage.builder()
                                    .role(EasyInputMessage.Role.USER)
                                    .content(message)
                                    .build())
                            .build()
            );

            // Get response
            AgentReference agentReference = new AgentReference(agent.getName())
                    .setVersion(agent.getVersion());
            
            Response response = responsesClient.createWithAgentConversation(
                    agentReference,
                    conversation.id()
            );

            // Extract response text
            if (response != null && response.output() != null && !response.output().isEmpty()) {
                String fullResponse = response.output().toString();
                return new ChatResult(fullResponse, "completed");
            }
            
            return new ChatResult("No response from assistant", "completed");

        } catch (Exception e) {
            return new ChatResult("Error in conversation: " + e.getMessage(), "failed");
        }
    }

    // Helper classes
    private static class TestQuestion {
        String question;
        List<String> expectedKeywords = new ArrayList<>();
    }

    private static class EvaluationResult {
        String question;
        String response;
        String status;
        boolean containsExpected;
        List<String> expectedKeywords;
    }

    private static class ChatResult {
        String response;
        String status;

        ChatResult(String response, String status) {
            this.response = response;
            this.status = status;
        }
    }
}
