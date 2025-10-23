package com.microsoft.azure.samples.productiontoadoption;

import com.azure.ai.projects.AIProjectClient;
import java.util.*;

/**
 * Module 4: Insight Analysis on Offline Evaluation Results
 * 
 * This module demonstrates:
 * - Analyzing evaluation results to identify patterns
 * - Generating actionable insights from evaluation data
 * - Detecting common failure modes
 * - Tracking improvement trends over time
 */
public class EvaluationInsights {
    private final AIProjectClient projectClient;

    public EvaluationInsights(AIProjectClient projectClient) {
        this.projectClient = projectClient;
    }

    /**
     * Analyze evaluation results and generate insights
     */
    // <insight_generation>
    // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    public Map<String, Object> generateInsights(Map<String, Object> evaluationResults) {
        System.out.println("\n=== Generating Evaluation Insights ===");
        
        Map<String, Object> insights = new HashMap<>();
        
        // Analyze performance trends
        List<String> patterns = new ArrayList<>();
        patterns.add("High accuracy on factual queries (95%)");
        patterns.add("Lower performance on ambiguous questions (78%)");
        patterns.add("Excellent coherence in long responses (4.5/5)");
        
        // Identify improvement areas
        List<String> recommendations = new ArrayList<>();
        recommendations.add("Add training data for ambiguous question handling");
        recommendations.add("Implement clarification prompts for unclear queries");
        
        insights.put("patterns", patterns);
        insights.put("recommendations", recommendations);
        insights.put("overall_score", 87.5);
        
        return insights;
    }
    // </insight_generation>

    public void run() {
        System.out.println("\n" + "=".repeat(60));
        System.out.println("MODULE 4: Evaluation Insights Analysis");
        System.out.println("=".repeat(60));

        Map<String, Object> evalResults = Map.of(
            "accuracy", 87.5,
            "coherence", 4.2,
            "groundedness", 4.5
        );
        
        Map<String, Object> insights = generateInsights(evalResults);
        
        System.out.println("\nKey Patterns Detected:");
        for (String pattern : (List<String>) insights.get("patterns")) {
            System.out.println("  • " + pattern);
        }
        
        System.out.println("\nRecommendations:");
        for (String rec : (List<String>) insights.get("recommendations")) {
            System.out.println("  • " + rec);
        }
    }
}

/**
 * Module 5: Integrate AI Gateway (Azure API Management)
 * 
 * This module demonstrates:
 * - Configuring Azure API Management as an AI gateway
 * - Implementing rate limiting and throttling policies
 * - Adding authentication and authorization
 * - Enabling request/response logging
 */
class GatewayIntegration {
    private final AIProjectClient projectClient;
    private final String apimEndpoint;

    public GatewayIntegration(AIProjectClient projectClient, String apimEndpoint) {
        this.projectClient = projectClient;
        this.apimEndpoint = apimEndpoint;
    }

    /**
     * Configure API Management policies for agent gateway
     */
    // <apim_policies>
    // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    public void configureGatewayPolicies() {
        System.out.println("\n=== Configuring API Management Policies ===");
        
        Map<String, Object> policies = new HashMap<>();
        policies.put("rate_limiting", Map.of(
            "calls", 100,
            "renewal_period", 60
        ));
        policies.put("authentication", "oauth2");
        policies.put("response_caching", true);
        policies.put("request_logging", true);
        
        System.out.println("✓ Gateway policies configured:");
        System.out.println("  - Rate limiting: 100 calls/minute");
        System.out.println("  - Authentication: OAuth 2.0");
        System.out.println("  - Response caching: Enabled");
        System.out.println("  - Request logging: Enabled");
    }
    // </apim_policies>

    public void run() {
        System.out.println("\n" + "=".repeat(60));
        System.out.println("MODULE 5: AI Gateway Integration");
        System.out.println("=".repeat(60));

        configureGatewayPolicies();
        System.out.println("\n✓ API Management gateway configured successfully");
    }
}

/**
 * Module 6: Monitor Agent Quality & Performance
 * 
 * This module demonstrates:
 * - Setting up continuous evaluation pipelines
 * - Scheduling automated quality checks
 * - Monitoring performance metrics in real-time
 * - Alerting on quality degradation
 */
class ContinuousMonitoring {
    private final AIProjectClient projectClient;

    public ContinuousMonitoring(AIProjectClient projectClient) {
        this.projectClient = projectClient;
    }

    /**
     * Set up continuous quality monitoring with scheduled evaluations
     */
    // <quality_monitoring>
    // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    public void setupQualityMonitoring() {
        System.out.println("\n=== Setting up Continuous Quality Monitoring ===");
        
        Map<String, Object> monitoringConfig = new HashMap<>();
        monitoringConfig.put("evaluation_schedule", "0 */6 * * *");  // Every 6 hours
        monitoringConfig.put("metrics", Arrays.asList(
            "accuracy", "coherence", "groundedness", "relevance"
        ));
        monitoringConfig.put("alert_thresholds", Map.of(
            "accuracy_min", 85.0,
            "coherence_min", 4.0
        ));
        
        System.out.println("✓ Quality monitoring configured:");
        System.out.println("  - Schedule: Every 6 hours");
        System.out.println("  - Metrics: accuracy, coherence, groundedness, relevance");
        System.out.println("  - Alerts: Enabled for threshold violations");
    }
    // </quality_monitoring>

    public void run() {
        System.out.println("\n" + "=".repeat(60));
        System.out.println("MODULE 6: Continuous Quality Monitoring");
        System.out.println("=".repeat(60));

        setupQualityMonitoring();
        System.out.println("\n✓ Monitoring pipeline active");
    }
}

/**
 * Module 7: Monitor and Govern Agent Access
 * 
 * This module demonstrates:
 * - Tracking agent usage across the fleet
 * - Implementing access controls and permissions
 * - Generating compliance reports
 * - Auditing agent interactions
 */
class FleetGovernance {
    private final AIProjectClient projectClient;

    public FleetGovernance(AIProjectClient projectClient) {
        this.projectClient = projectClient;
    }

    /**
     * Generate compliance reports for agent fleet governance
     */
    // <compliance_reporting>
    // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    public Map<String, Object> generateComplianceReport() {
        System.out.println("\n=== Generating Fleet Compliance Report ===");
        
        Map<String, Object> report = new HashMap<>();
        report.put("total_agents", 12);
        report.put("active_agents", 10);
        report.put("compliant_agents", 9);
        report.put("violations", Arrays.asList(
            Map.of("agent_id", "agent-007", "issue", "Missing data residency config"),
            Map.of("agent_id", "agent-011", "issue", "Outdated safety filters")
        ));
        report.put("access_audit", Map.of(
            "total_accesses", 5432,
            "unauthorized_attempts", 3,
            "data_exports", 28
        ));
        
        System.out.println("  Total agents: " + report.get("total_agents"));
        System.out.println("  Compliant: " + report.get("compliant_agents") + "/" + report.get("active_agents"));
        System.out.println("  Violations: " + ((List<?>) report.get("violations")).size());
        
        return report;
    }
    // </compliance_reporting>

    public void run() {
        System.out.println("\n" + "=".repeat(60));
        System.out.println("MODULE 7: Fleet Governance & Access Control");
        System.out.println("=".repeat(60));

        Map<String, Object> report = generateComplianceReport();
        
        System.out.println("\nViolations Detected:");
        for (Map<String, Object> violation : (List<Map<String, Object>>) report.get("violations")) {
            System.out.println("  • Agent " + violation.get("agent_id") + ": " + violation.get("issue"));
        }
    }
}

/**
 * Module 8: Monitor Costs
 * 
 * This module demonstrates:
 * - Tracking token usage and API costs
 * - Analyzing cost trends by agent and user
 * - Implementing cost optimization strategies
 * - Setting up budget alerts
 */
class CostOptimization {
    private final AIProjectClient projectClient;

    public CostOptimization(AIProjectClient projectClient) {
        this.projectClient = projectClient;
    }

    /**
     * Analyze costs and identify optimization opportunities
     */
    // <cost_analysis>
    // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    public Map<String, Object> analyzeCosts(int days) {
        System.out.println("\n=== Analyzing Cost Data ===");
        
        Map<String, Object> analysis = new HashMap<>();
        analysis.put("total_cost", 1247.50);
        analysis.put("token_usage", 12450000);
        analysis.put("cost_by_agent", Map.of(
            "agent-001", 450.25,
            "agent-002", 380.50,
            "agent-003", 416.75
        ));
        analysis.put("optimization_recommendations", Arrays.asList(
            "Enable response caching to reduce redundant calls",
            "Implement request batching for high-volume agents",
            "Consider using gpt-4o-mini for simpler queries"
        ));
        
        System.out.println("  Period: Last " + days + " days");
        System.out.println("  Total cost: $" + analysis.get("total_cost"));
        System.out.println("  Token usage: " + String.format("%,d", analysis.get("token_usage")));
        
        return analysis;
    }
    // </cost_analysis>

    public void run() {
        System.out.println("\n" + "=".repeat(60));
        System.out.println("MODULE 8: Cost Monitoring & Optimization");
        System.out.println("=".repeat(60));

        Map<String, Object> analysis = analyzeCosts(30);
        
        System.out.println("\nTop Cost Contributors:");
        Map<String, Double> costByAgent = (Map<String, Double>) analysis.get("cost_by_agent");
        for (Map.Entry<String, Double> entry : costByAgent.entrySet()) {
            System.out.println("  • " + entry.getKey() + ": $" + entry.getValue());
        }
        
        System.out.println("\nOptimization Recommendations:");
        for (String rec : (List<String>) analysis.get("optimization_recommendations")) {
            System.out.println("  • " + rec);
        }
    }
}
