package com.azure.ai.foundry.samples;

import com.azure.ai.foundry.samples.utils.ConfigLoader;
import com.azure.ai.projects.AIProjectClientBuilder;
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;

import java.lang.reflect.Method;

/**
 * Example demonstrating project creation with Azure AI Projects SDK.
 */
public class CreateProject {
    public static void main(String[] args) {
        // Load environment variables
        String endpoint = ConfigLoader.getAzureEndpoint();
        String projectName = System.getenv("PROJECT_NAME");
        String projectDescription = System.getenv("PROJECT_DESCRIPTION");
        String deploymentName = System.getenv("DEPLOYMENT_NAME");
        String modelName = System.getenv("MODEL_DEPLOYMENT_NAME");
        
        // Validate and set defaults for required environment variables
        if (endpoint == null) {
            System.err.println("ERROR: ConfigLoader.getAzureEndpoint() returned null");
            System.err.println("Make sure .env file exists with AZURE_ENDPOINT defined");
            return;
        }
        
        if (projectName == null) {
            projectName = "My Sample Project";
            System.out.println("PROJECT_NAME not set, using default: " + projectName);
        }
        
        if (projectDescription == null) {
            projectDescription = "A project created using the Java SDK";
            System.out.println("PROJECT_DESCRIPTION not set, using default description");
        }
        
        if (deploymentName == null) {
            deploymentName = "my-deployment";
            System.out.println("DEPLOYMENT_NAME not set, using default: " + deploymentName);
        }
        
        if (modelName == null) {
            modelName = "gpt4o";  // Default to gpt4o instead of gpt-35-turbo
            System.out.println("MODEL_DEPLOYMENT_NAME not set, using default: " + modelName);
        }

        DefaultAzureCredential credential = new DefaultAzureCredentialBuilder().build();

        // Create projects client
        System.out.println("\nCreating AI project client...");
        var clientBuilder = new AIProjectClientBuilder()
            .endpoint(endpoint)
            .credential(credential);

        try {
            // Try to find the build method using reflection
            Method buildMethod = findBuildMethod(AIProjectClientBuilder.class);
            if (buildMethod == null) {
                System.err.println("Could not find a build method on AIProjectClientBuilder");
                System.err.println("Available methods on AIProjectClientBuilder:");
                for (Method method : AIProjectClientBuilder.class.getMethods()) {
                    if (method.getDeclaringClass() == AIProjectClientBuilder.class) {
                        System.err.println("- " + method.getName());
                    }
                }
                return;
            }
            
            // Invoke the build method
            var client = buildMethod.invoke(clientBuilder);
            
            // Find and invoke the createProject method
            Method createProjectMethod = findMethod(client.getClass(), "createProject", 2);
            if (createProjectMethod == null) {
                System.err.println("Could not find createProject method");
                return;
            }
            
            // Create a new project
            System.out.println("Creating project: " + projectName);
            var project = createProjectMethod.invoke(client, projectName, projectDescription);
            System.out.println("Project created with ID: " + project.getClass().getMethod("getId").invoke(project));

            // Find the DeploymentOptions class
            Class<?> deploymentOptionsClass = null;
            try {
                deploymentOptionsClass = Class.forName("com.azure.ai.projects.models.DeploymentOptions");
            } catch (ClassNotFoundException e) {
                try {
                    deploymentOptionsClass = Class.forName("com.azure.ai.projects.models.deployment.DeploymentOptions");
                } catch (ClassNotFoundException e2) {
                    System.err.println("Could not find DeploymentOptions class");
                    return;
                }
            }
            
            // Create deployment options
            Object options = deploymentOptionsClass.getDeclaredConstructor().newInstance();
            deploymentOptionsClass.getMethod("setName", String.class).invoke(options, deploymentName);
            deploymentOptionsClass.getMethod("setModel", String.class).invoke(options, modelName);
            deploymentOptionsClass.getMethod("setDescription", String.class).invoke(options, "Sample model deployment");

            // Find and invoke the createDeployment method
            Method createDeploymentMethod = findMethodWithParameterTypes(client.getClass(), "createDeployment", 
                String.class, deploymentOptionsClass);
            if (createDeploymentMethod == null) {
                System.err.println("Could not find createDeployment method");
                return;
            }
            
            // Deploy a model to the project
            System.out.println("\nDeploying model: " + modelName);
            var deployment = createDeploymentMethod.invoke(client, project.getClass().getMethod("getId").invoke(project), options);
            System.out.println("Deployment created with ID: " + deployment.getClass().getMethod("getId").invoke(deployment));
            
            System.out.println("\nProject and deployment created successfully!");
        } catch (Exception e) {
            System.err.println("Error: " + e.getMessage());
            e.printStackTrace();
        }
    }
    
    // Helper method to find a build method in a builder class
    private static Method findBuildMethod(Class<?> builderClass) {
        for (Method method : builderClass.getMethods()) {
            String name = method.getName().toLowerCase();
            if ((name.equals("build") || name.equals("buildclient") || name.contains("build")) && 
                    method.getParameterCount() == 0) {
                return method;
            }
        }
        return null;
    }
    
    // Helper method to find a method with a specific number of parameters
    private static Method findMethod(Class<?> cls, String methodNameFragment, int parameterCount) {
        for (Method method : cls.getMethods()) {
            if (method.getName().contains(methodNameFragment) && 
                    method.getParameterCount() == parameterCount) {
                return method;
            }
        }
        return null;
    }
    
    // Helper method to find a method with specific parameter types
    private static Method findMethodWithParameterTypes(Class<?> cls, String methodNameFragment, 
                                                       Class<?>... parameterTypes) {
        for (Method method : cls.getMethods()) {
            if (method.getName().contains(methodNameFragment) && 
                    method.getParameterCount() == parameterTypes.length) {
                Class<?>[] methodParamTypes = method.getParameterTypes();
                boolean match = true;
                for (int i = 0; i < parameterTypes.length; i++) {
                    if (!methodParamTypes[i].isAssignableFrom(parameterTypes[i])) {
                        match = false;
                        break;
                    }
                }
                if (match) {
                    return method;
                }
            }
        }
        return null;
    }
}