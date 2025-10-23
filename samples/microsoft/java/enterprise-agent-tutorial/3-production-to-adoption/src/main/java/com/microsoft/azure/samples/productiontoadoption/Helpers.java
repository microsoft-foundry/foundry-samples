package com.microsoft.azure.samples.productiontoadoption;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import java.io.FileWriter;
import java.io.IOException;
import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * Helper utilities for the Production to Adoption tutorial.
 * Provides common functionality used across modules.
 */
public class Helpers {
    private static final Gson gson = new GsonBuilder().setPrettyPrinting().create();

    public static void printHeader(String title) {
        System.out.println("\n" + "=".repeat(70));
        System.out.println(title);
        System.out.println("=".repeat(70));
    }

    public static void printSuccess(String message) {
        System.out.println("✅ " + message);
    }

    public static void printError(String message) {
        System.out.println("❌ " + message);
    }

    public static void printWarning(String message) {
        System.out.println("⚠️  " + message);
    }

    public static void printInfo(String message) {
        System.out.println("ℹ️  " + message);
    }

    public static void printListItems(List<String> items) {
        items.forEach(item -> System.out.println("   • " + item));
    }

    public static String formatTimestamp() {
        return Instant.now().toString();
    }

    public static String formatCurrency(double amount) {
        return String.format("$%.2f", amount);
    }

    public static void saveJson(Object obj, String filename) {
        try (FileWriter writer = new FileWriter(filename)) {
            gson.toJson(obj, writer);
            printSuccess("Saved " + filename);
        } catch (IOException e) {
            printError("Failed to save " + filename + ": " + e.getMessage());
        }
    }

    public static void printTraceSummary(Map<String, Object> analysis) {
        System.out.println("\n📊 Trace Analysis Summary:");
        System.out.println("   Total Traces: " + analysis.get("total_traces"));
        System.out.println("   Average Latency: " + String.format("%.0fms", analysis.get("avg_latency_ms")));
        System.out.println("   Error Rate: " + String.format("%.1f%%", analysis.get("error_rate")));
    }

    @SuppressWarnings("unchecked")
    public static void printFeedbackSummary(Map<String, Object> analysis) {
        Map<String, Object> stats = (Map<String, Object>) analysis.get("statistics");
        System.out.println("\n📊 Feedback Analysis Summary:");
        System.out.println("   Total Feedback: " + stats.get("total_feedback"));
        System.out.println("   Satisfaction Rate: " + String.format("%.1f%%", ((Number)stats.get("satisfaction_rate")).doubleValue() * 100));
        System.out.println("   Positive: " + stats.get("positive_count"));
        System.out.println("   Negative: " + stats.get("negative_count"));
    }

    @SuppressWarnings("unchecked")
    public static void printFineTuningSummary(Map<String, Object> result) {
        Map<String, Object> config = (Map<String, Object>) result.get("config");
        System.out.println("\n📊 Fine-Tuning Configuration:");
        System.out.println("   Training Examples: " + config.get("training_examples"));
        System.out.println("   Validation Examples: " + config.get("validation_examples"));
        System.out.println("   Base Model: " + config.get("base_model"));
        System.out.println("   Job ID: " + result.get("job_id"));
    }

    @SuppressWarnings("unchecked")
    public static void printEvaluationInsights(Map<String, Object> insights) {
        System.out.println("\n📊 Evaluation Insights:");
        List<Map<String, Object>> patterns = (List<Map<String, Object>>) insights.get("failure_patterns");
        System.out.println("   Failure Patterns Identified: " + patterns.size());
        Map<String, Object> trends = (Map<String, Object>) insights.get("quality_trends");
        System.out.println("   Current Quality: " + String.format("%.1f%%", ((Number)trends.get("current_month")).doubleValue() * 100));
    }

    @SuppressWarnings("unchecked")
    public static void printGatewaySummary(Map<String, Object> config) {
        Map<String, Object> cfg = (Map<String, Object>) config.get("configuration");
        System.out.println("\n📊 Gateway Configuration:");
        System.out.println("   Endpoint: " + cfg.get("endpoint"));
        System.out.println("   Rate Limit: " + cfg.get("rate_limit"));
        System.out.println("   Caching: " + cfg.get("caching_enabled"));
    }

    @SuppressWarnings("unchecked")
    public static void printMonitoringSummary(Map<String, Object> config) {
        Map<String, Object> schedule = (Map<String, Object>) config.get("schedule");
        System.out.println("\n📊 Monitoring Configuration:");
        System.out.println("   Schedules Configured: " + schedule.size());
        List<Map<String, Object>> alerts = (List<Map<String, Object>>) config.get("alerts");
        System.out.println("   Alerts Configured: " + alerts.size());
    }

    @SuppressWarnings("unchecked")
    public static void printGovernanceSummary(Map<String, Object> report) {
        Map<String, Object> stats = (Map<String, Object>) report.get("statistics");
        System.out.println("\n📊 Fleet Governance Report:");
        System.out.println("   Total Agents: " + stats.get("total_agents"));
        System.out.println("   Active Users: " + stats.get("active_users"));
        System.out.println("   Compliance Rate: " + String.format("%.1f%%", ((Number)stats.get("compliance_rate")).doubleValue() * 100));
    }

    @SuppressWarnings("unchecked")
    public static void printCostSummary(Map<String, Object> report) {
        Map<String, Object> totals = (Map<String, Object>) report.get("totals");
        System.out.println("\n📊 Cost Analysis:");
        System.out.println("   Total Cost: " + formatCurrency(((Number)totals.get("total_cost")).doubleValue()));
        System.out.println("   Period: " + totals.get("period"));
        System.out.println("   Potential Savings: " + formatCurrency(((Number)report.get("projected_savings")).doubleValue()));
    }

    public static Map<String, Object> createSummaryReport(Map<String, Object> moduleResults) {
        return Map.of(
            "timestamp", formatTimestamp(),
            "tutorial", "Production to Adoption",
            "modules_executed", moduleResults.size(),
            "module_results", moduleResults
        );
    }

    public static void printCompletionSummary(Map<String, Object> summary) {
        System.out.println("\n" + "=".repeat(70));
        System.out.println("📊 TUTORIAL EXECUTION SUMMARY");
        System.out.println("=".repeat(70));
        System.out.println("Modules Executed: " + summary.get("modules_executed"));
        System.out.println("Timestamp: " + summary.get("timestamp"));
    }
}
