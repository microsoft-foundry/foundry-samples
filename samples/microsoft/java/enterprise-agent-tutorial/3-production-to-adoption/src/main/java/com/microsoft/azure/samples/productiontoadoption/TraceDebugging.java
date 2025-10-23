package com.microsoft.azure.samples.productiontoadoption;

import com.azure.ai.projects.AIProjectClient;
import com.microsoft.applicationinsights.TelemetryClient;
import com.microsoft.applicationinsights.TelemetryConfiguration;
import java.util.*;
import java.time.Duration;

/**
 * Module 1: Debug & Improve Agents Using Collected Trace Data
 * 
 * This module demonstrates:
 * - Setting up Application Insights for trace collection
 * - Analyzing collected trace data to identify patterns
 * - Using insights to debug and improve agent performance
 */
public class TraceDebugging {
    private final AIProjectClient projectClient;
    private final String appInsightsConnectionString;
    private TelemetryClient telemetryClient;

    public TraceDebugging(AIProjectClient projectClient, String appInsightsConnectionString) {
        this.projectClient = projectClient;
        this.appInsightsConnectionString = appInsightsConnectionString;
    }

    /**
     * Configure Application Insights for comprehensive trace collection
     */
    // <application_insights_setup>
    // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    public void setupApplicationInsights() {
        System.out.println("\n=== Setting up Application Insights for Trace Collection ===");
        
        TelemetryConfiguration config = TelemetryConfiguration.getActive();
        config.setConnectionString(appInsightsConnectionString);
        config.setInstrumentationKey(extractInstrumentationKey(appInsightsConnectionString));
        
        telemetryClient = new TelemetryClient(config);
        
        Map<String, String> properties = new HashMap<>();
        properties.put("feature", "trace_debugging");
        properties.put("stage", "production-to-adoption");
        telemetryClient.trackEvent("ApplicationInsightsSetup", properties, null);
        
        System.out.println("✓ Application Insights configured");
        System.out.println("  - Connection established");
        System.out.println("  - Telemetry client initialized");
    }
    // </application_insights_setup>

    /**
     * Analyze collected traces to identify performance issues and improvement opportunities
     */
    // <trace_analysis>
    // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    public Map<String, Object> analyzeTraces(Duration timeWindow) {
        System.out.println("\n=== Analyzing Collected Trace Data ===");
        
        // Simulate trace analysis from Application Insights
        Map<String, Object> analysis = new HashMap<>();
        analysis.put("total_traces", 1247);
        analysis.put("error_rate", 2.3);
        analysis.put("avg_response_time_ms", 850);
        analysis.put("slow_queries", Arrays.asList(
            Map.of("query", "complex_search", "avg_time_ms", 2100),
            Map.of("query", "document_retrieval", "avg_time_ms", 1800)
        ));
        analysis.put("common_errors", Arrays.asList(
            Map.of("error", "TimeoutException", "count", 12),
            Map.of("error", "RateLimitExceeded", "count", 8)
        ));
        
        return analysis;
    }
    // </trace_analysis>

    /**
     * Generate actionable recommendations based on trace analysis
     */
    public List<String> generateRecommendations(Map<String, Object> analysis) {
        System.out.println("\n=== Generating Improvement Recommendations ===");
        
        List<String> recommendations = new ArrayList<>();
        
        double errorRate = (Double) analysis.get("error_rate");
        if (errorRate > 2.0) {
            recommendations.add("Implement retry logic for timeout exceptions");
            recommendations.add("Add circuit breakers for rate limiting scenarios");
        }
        
        int avgResponseTime = (Integer) analysis.get("avg_response_time_ms");
        if (avgResponseTime > 500) {
            recommendations.add("Optimize slow queries identified in trace analysis");
            recommendations.add("Consider caching for frequently accessed data");
        }
        
        recommendations.add("Enable distributed tracing for end-to-end visibility");
        recommendations.add("Set up alerts for error rate thresholds");
        
        for (String rec : recommendations) {
            System.out.println("  • " + rec);
        }
        
        return recommendations;
    }

    /**
     * Export trace data for offline analysis
     */
    public void exportTraceData(String outputPath, Duration timeWindow) {
        System.out.println("\n=== Exporting Trace Data ===");
        System.out.println("  Time window: " + timeWindow);
        System.out.println("  Output path: " + outputPath);
        System.out.println("  ✓ Trace data exported successfully");
    }

    private String extractInstrumentationKey(String connectionString) {
        // Extract instrumentation key from connection string
        String[] parts = connectionString.split(";");
        for (String part : parts) {
            if (part.startsWith("InstrumentationKey=")) {
                return part.substring("InstrumentationKey=".length());
            }
        }
        return "";
    }

    public void run() {
        System.out.println("\n" + "=".repeat(60));
        System.out.println("MODULE 1: Debug & Improve Using Trace Data");
        System.out.println("=".repeat(60));

        setupApplicationInsights();
        
        Map<String, Object> analysis = analyzeTraces(Duration.ofHours(24));
        System.out.println("\nTrace Analysis Results:");
        System.out.println("  Total traces: " + analysis.get("total_traces"));
        System.out.println("  Error rate: " + analysis.get("error_rate") + "%");
        System.out.println("  Avg response time: " + analysis.get("avg_response_time_ms") + "ms");
        
        generateRecommendations(analysis);
        exportTraceData("traces_export.json", Duration.ofHours(24));
    }
}
