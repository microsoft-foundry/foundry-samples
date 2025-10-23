package com.microsoft.azure.samples.productiontoadoption;

import com.azure.ai.projects.AIProjectClient;
import com.azure.ai.projects.AIProjectClientBuilder;
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;

/**
 * Azure AI Foundry Enterprise Agent Tutorial - Stage 3: Production to Adoption
 * 
 * This sample demonstrates production operations capabilities for enterprise AI agents:
 * 1. Debug & improve agents using collected trace data
 * 2. Enable collection & download of human feedback from production
 * 3. Fine-tune models using collected data
 * 4. Insight analysis on offline evaluation results
 * 5. Integrate an AI gateway (Azure API Management)
 * 6. Monitor agent quality & performance (continuous/scheduled evals)
 * 7. Monitor and govern agent access (across the fleet)
 * 8. Monitor costs
 */
public class Main {
    
    public static void main(String[] args) {
        try {
            System.out.println("\n" + "=".repeat(80));
            System.out.println("Azure AI Foundry Enterprise Agent Tutorial");
            System.out.println("Stage 3: Production to Adoption");
            System.out.println("=".repeat(80));
            
            // Load configuration
            String projectEndpoint = Helpers.getEnvVar("PROJECT_ENDPOINT");
            String subscriptionId = Helpers.getEnvVar("SUBSCRIPTION_ID");
            String resourceGroupName = Helpers.getEnvVar("RESOURCE_GROUP_NAME");
            String projectName = Helpers.getEnvVar("PROJECT_NAME");
            String connectionName = Helpers.getEnvVar("CONNECTION_NAME");
            String appInsightsConnectionString = Helpers.getEnvVar("APPLICATIONINSIGHTS_CONNECTION_STRING");
            String apimEndpoint = Helpers.getEnvVar("APIM_ENDPOINT", "");
            
            // <authentication_setup>
            // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
            System.out.println("\n=== Authenticating with Azure AI Foundry ===");
            
            TokenCredential credential = new DefaultAzureCredentialBuilder().build();
            
            AIProjectClient projectClient = new AIProjectClientBuilder()
                .credential(credential)
                .endpoint(projectEndpoint)
                .buildClient();
            
            System.out.println("✓ Successfully authenticated");
            System.out.println("  Project: " + projectName);
            System.out.println("  Resource Group: " + resourceGroupName);
            // </authentication_setup>
            
            // <module_orchestration>
            // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
            System.out.println("\n" + "=".repeat(80));
            System.out.println("Running Production to Adoption Modules");
            System.out.println("=".repeat(80));
            
            // Module 1: Trace Debugging
            TraceDebugging traceDebugging = new TraceDebugging(projectClient, appInsightsConnectionString);
            traceDebugging.run();
            
            // Module 2: Feedback Collection
            FeedbackCollection feedbackCollection = new FeedbackCollection(projectClient);
            feedbackCollection.run();
            
            // Module 3: Model Fine-Tuning
            ModelFineTuning modelFineTuning = new ModelFineTuning(projectClient, connectionName);
            modelFineTuning.run();
            
            // Module 4: Evaluation Insights
            EvaluationInsights evaluationInsights = new EvaluationInsights(projectClient);
            evaluationInsights.run();
            
            // Module 5: Gateway Integration
            if (!apimEndpoint.isEmpty()) {
                GatewayIntegration gatewayIntegration = new GatewayIntegration(projectClient, apimEndpoint);
                gatewayIntegration.run();
            } else {
                System.out.println("\n" + "=".repeat(60));
                System.out.println("MODULE 5: AI Gateway Integration - SKIPPED (No APIM endpoint configured)");
                System.out.println("=".repeat(60));
            }
            
            // Module 6: Continuous Monitoring
            ContinuousMonitoring continuousMonitoring = new ContinuousMonitoring(projectClient);
            continuousMonitoring.run();
            
            // Module 7: Fleet Governance
            FleetGovernance fleetGovernance = new FleetGovernance(projectClient);
            fleetGovernance.run();
            
            // Module 8: Cost Optimization
            CostOptimization costOptimization = new CostOptimization(projectClient);
            costOptimization.run();
            // </module_orchestration>
            
            System.out.println("\n" + "=".repeat(80));
            System.out.println("✓ All Production to Adoption modules completed successfully!");
            System.out.println("=".repeat(80));
            
            printSummary();
            
        } catch (Exception e) {
            System.err.println("\n✗ Error: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }
    }
    
    /**
     * Print summary of production operations capabilities
     */
    private static void printSummary() {
        System.out.println("\n=== Production Operations Summary ===");
        System.out.println("\nThis sample demonstrated:");
        System.out.println("  ✓ Trace debugging with Application Insights");
        System.out.println("  ✓ Human feedback collection and analysis");
        System.out.println("  ✓ Model fine-tuning with collected data");
        System.out.println("  ✓ Evaluation insights and pattern detection");
        System.out.println("  ✓ AI gateway integration (Azure API Management)");
        System.out.println("  ✓ Continuous quality monitoring");
        System.out.println("  ✓ Fleet governance and compliance");
        System.out.println("  ✓ Cost monitoring and optimization");
        
        System.out.println("\n=== Next Steps ===");
        System.out.println("  • Review the generated insights and recommendations");
        System.out.println("  • Set up automated monitoring pipelines");
        System.out.println("  • Configure alerts for quality and cost thresholds");
        System.out.println("  • Implement governance policies across your agent fleet");
        System.out.println("  • Continuously iterate based on production feedback");
        
        System.out.println("\n=== Resources ===");
        System.out.println("  • Azure AI Foundry Documentation: https://learn.microsoft.com/azure/ai-studio/");
        System.out.println("  • Application Insights: https://learn.microsoft.com/azure/azure-monitor/app/app-insights-overview");
        System.out.println("  • Azure API Management: https://learn.microsoft.com/azure/api-management/");
        System.out.println("  • Azure OpenAI Fine-tuning: https://learn.microsoft.com/azure/ai-services/openai/how-to/fine-tuning");
    }
}
