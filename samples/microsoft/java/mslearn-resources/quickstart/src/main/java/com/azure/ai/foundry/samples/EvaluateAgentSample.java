package com.azure.ai.foundry.samples;

import com.azure.ai.foundry.samples.utils.ConfigLoader;
import com.azure.ai.agents.persistent.PersistentAgentsAdministrationClient;
import com.azure.ai.agents.persistent.PersistentAgentsAdministrationClientBuilder;
import com.azure.ai.agents.persistent.models.CreateAgentOptions;
import com.azure.ai.agents.persistent.models.CreateThreadAndRunOptions;
import com.azure.ai.agents.persistent.models.PersistentAgent;
import com.azure.ai.agents.persistent.models.ThreadRun;
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

/**
 * Example demonstrating agent creation and run.
 * This class also explores the available API surface to identify evaluation capabilities.
 */
public class EvaluateAgentSample {
    public static void main(String[] args) {
        // Load environment variables
        String endpoint = ConfigLoader.getAzureEndpoint();
        String projectEndpoint = System.getenv("PROJECT_ENDPOINT");
        String modelName = System.getenv("MODEL_DEPLOYMENT_NAME");
        
        // Validate required environment variables
        if (projectEndpoint == null) {
            System.err.println("ERROR: Set PROJECT_ENDPOINT environment variable");
            return;
        }
        if (modelName == null) {
            modelName = "gpt4o";  // Default if not provided
            System.out.println("MODEL_DEPLOYMENT_NAME not set, using default: " + modelName);
        }

        DefaultAzureCredential credential = new DefaultAzureCredentialBuilder().build();

        // Create agent administration client
        System.out.println("Creating agent administration client...");
        PersistentAgentsAdministrationClient agentClient = new PersistentAgentsAdministrationClientBuilder()
            .endpoint(projectEndpoint)
            .credential(credential)
            .buildClient();

        // Create an agent
        System.out.println("\nCreating weather assistant agent...");
        PersistentAgent agent = agentClient.createAgent(new CreateAgentOptions(modelName)
            .setName("Weather Assistant")
            .setInstructions("You are a weather assistant. Provide accurate information about weather conditions.")
        );
        System.out.println("Agent created with ID: " + agent.getId());

        // Create thread and run
        System.out.println("\nCreating thread and run...");
        ThreadRun threadRun = agentClient.createThreadAndRun(new CreateThreadAndRunOptions(agent.getId()));
        String threadId = threadRun.getThreadId();
        System.out.println("Thread created with ID: " + threadId);
        
        // Use reflection to explore API surface for evaluation capabilities
        System.out.println("\n=== API EXPLORATION ===");
        
        // Check for evaluation methods in PersistentAgentsAdministrationClient
        List<String> evaluationMethods = findEvaluationMethods(PersistentAgentsAdministrationClient.class);
        System.out.println("\nPersistentAgentsAdministrationClient evaluation methods:");
        if (evaluationMethods.isEmpty()) {
            System.out.println("No evaluation-related methods found.");
        } else {
            evaluationMethods.forEach(method -> System.out.println("- " + method));
        }
        
        // Check for evaluation classes
        System.out.println("\nLooking for evaluation-related model classes:");
        List<Class<?>> evaluationClasses = findEvaluationClasses("com.azure.ai.agents.persistent.models");
        if (evaluationClasses.isEmpty()) {
            System.out.println("No evaluation-related model classes found.");
        } else {
            evaluationClasses.forEach(cls -> System.out.println("- " + cls.getName()));
        }
        
        // Print ThreadRun methods
        System.out.println("\nAll methods on ThreadRun class:");
        for (Method method : ThreadRun.class.getMethods()) {
            if (method.getDeclaringClass() != Object.class) {
                System.out.println("- " + method.getName() +
                        "(" + getParameterTypes(method) + ")");
            }
        }
        
        System.out.println("\nDemo completed!");
        System.out.println("Note: For evaluation capabilities, please contact the SDK developers.");
    }
    
    // Helper method to find evaluation-related methods in a class
    private static List<String> findEvaluationMethods(Class<?> cls) {
        List<String> methods = new ArrayList<>();
        for (Method method : cls.getMethods()) {
            String name = method.getName().toLowerCase();
            if (name.contains("evaluat") || name.contains("score") || name.contains("assess") ||
                    name.contains("metric") || name.contains("measure")) {
                methods.add(method.getName() + "(" + getParameterTypes(method) + ")");
            }
        }
        return methods;
    }
    
    // Helper method to find evaluation-related classes in a package
    private static List<Class<?>> findEvaluationClasses(String packageName) {
        List<Class<?>> classes = new ArrayList<>();
        
        // This is just a template - actual implementation would require
        // scanning the classpath, which is complex. Instead, we'll
        // mention what to look for.
        
        System.out.println("  (Note: This method would need classpath scanning, but you should look for classes with 'Evaluat'");
        System.out.println("   in their names in the " + packageName + " package.)");
        
        return classes;
    }
    
    // Helper method to get parameter types as a readable string
    private static String getParameterTypes(Method method) {
        StringBuilder sb = new StringBuilder();
        Class<?>[] types = method.getParameterTypes();
        for (int i = 0; i < types.length; i++) {
            if (i > 0) sb.append(", ");
            sb.append(types[i].getSimpleName());
        }
        return sb.toString();
    }
}