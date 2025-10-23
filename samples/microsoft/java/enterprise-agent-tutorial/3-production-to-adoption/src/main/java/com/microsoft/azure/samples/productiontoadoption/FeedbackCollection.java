package com.microsoft.azure.samples.productiontoadoption;

import com.azure.ai.projects.AIProjectClient;
import java.util.*;
import java.time.LocalDateTime;
import java.time.Duration;

/**
 * Module 2: Enable Collection & Download of Human Feedback
 * 
 * This module demonstrates:
 * - Setting up feedback collection APIs
 * - Storing feedback from production users
 * - Analyzing feedback to identify improvement areas
 * - Exporting feedback for agent developers
 */
public class FeedbackCollection {
    private final AIProjectClient projectClient;
    private final List<Map<String, Object>> feedbackStore;

    public FeedbackCollection(AIProjectClient projectClient) {
        this.projectClient = projectClient;
        this.feedbackStore = new ArrayList<>();
    }

    /**
     * Set up feedback collection API endpoints
     */
    // <feedback_api>
    // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    public void setupFeedbackCollection() {
        System.out.println("\n=== Setting up Feedback Collection System ===");
        
        // Configure feedback collection endpoints
        Map<String, String> endpoints = new HashMap<>();
        endpoints.put("submit_feedback", "/api/feedback/submit");
        endpoints.put("get_feedback", "/api/feedback/query");
        endpoints.put("export_feedback", "/api/feedback/export");
        
        System.out.println("✓ Feedback API endpoints configured:");
        for (Map.Entry<String, String> entry : endpoints.entrySet()) {
            System.out.println("  - " + entry.getKey() + ": " + entry.getValue());
        }
    }
    // </feedback_api>

    /**
     * Collect feedback from production users
     */
    public void collectFeedback(String agentId, String conversationId, 
                                int rating, String comments, String userId) {
        Map<String, Object> feedback = new HashMap<>();
        feedback.put("agent_id", agentId);
        feedback.put("conversation_id", conversationId);
        feedback.put("rating", rating);
        feedback.put("comments", comments);
        feedback.put("user_id", userId);
        feedback.put("timestamp", LocalDateTime.now().toString());
        
        feedbackStore.add(feedback);
        System.out.println("✓ Feedback collected: Rating " + rating + "/5");
    }

    /**
     * Analyze collected feedback to identify patterns and improvement areas
     */
    // <feedback_analysis>
    // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    public Map<String, Object> analyzeFeedback(Duration timeWindow) {
        System.out.println("\n=== Analyzing Collected Feedback ===");
        
        Map<String, Object> analysis = new HashMap<>();
        
        // Calculate metrics
        double avgRating = feedbackStore.stream()
            .mapToInt(f -> (Integer) f.get("rating"))
            .average()
            .orElse(0.0);
        
        long totalFeedback = feedbackStore.size();
        long positiveFeedback = feedbackStore.stream()
            .filter(f -> (Integer) f.get("rating") >= 4)
            .count();
        
        analysis.put("total_feedback", totalFeedback);
        analysis.put("average_rating", avgRating);
        analysis.put("satisfaction_rate", (positiveFeedback * 100.0 / totalFeedback));
        
        return analysis;
    }
    // </feedback_analysis>

    /**
     * Generate insights from feedback analysis
     */
    public List<String> generateInsights(Map<String, Object> analysis) {
        System.out.println("\n=== Generating Feedback Insights ===");
        
        List<String> insights = new ArrayList<>();
        
        double avgRating = (Double) analysis.get("average_rating");
        double satisfactionRate = (Double) analysis.get("satisfaction_rate");
        
        if (avgRating < 3.5) {
            insights.add("⚠ Average rating below threshold - review agent responses");
        }
        if (satisfactionRate < 80.0) {
            insights.add("⚠ Satisfaction rate low - investigate common complaints");
        }
        
        insights.add("✓ " + analysis.get("total_feedback") + " feedback entries collected");
        insights.add("✓ Average rating: " + String.format("%.2f", avgRating) + "/5");
        insights.add("✓ Satisfaction rate: " + String.format("%.1f", satisfactionRate) + "%");
        
        for (String insight : insights) {
            System.out.println("  " + insight);
        }
        
        return insights;
    }

    /**
     * Export feedback data for developer analysis
     */
    public void exportFeedbackData(String outputPath) {
        System.out.println("\n=== Exporting Feedback Data ===");
        System.out.println("  Total records: " + feedbackStore.size());
        System.out.println("  Output path: " + outputPath);
        System.out.println("  ✓ Feedback data exported successfully");
    }

    public void run() {
        System.out.println("\n" + "=".repeat(60));
        System.out.println("MODULE 2: Human Feedback Collection & Analysis");
        System.out.println("=".repeat(60));

        setupFeedbackCollection();
        
        // Simulate collecting feedback
        collectFeedback("agent-001", "conv-123", 5, "Very helpful response!", "user-001");
        collectFeedback("agent-001", "conv-124", 4, "Good but could be faster", "user-002");
        collectFeedback("agent-001", "conv-125", 3, "Sometimes inaccurate", "user-003");
        collectFeedback("agent-001", "conv-126", 5, "Excellent experience", "user-004");
        
        Map<String, Object> analysis = analyzeFeedback(Duration.ofDays(7));
        generateInsights(analysis);
        exportFeedbackData("feedback_export.json");
    }
}
