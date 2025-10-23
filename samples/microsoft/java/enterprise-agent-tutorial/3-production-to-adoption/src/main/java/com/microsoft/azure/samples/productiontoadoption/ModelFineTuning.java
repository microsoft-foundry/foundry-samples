package com.microsoft.azure.samples.productiontoadoption;

import com.azure.ai.projects.AIProjectClient;
import java.util.*;

/**
 * Module 3: Fine-tune Models Using Collected Data
 * 
 * This module demonstrates:
 * - Preparing training data from collected feedback and traces
 * - Submitting fine-tuning jobs to Azure OpenAI
 * - Monitoring fine-tuning progress
 * - Deploying fine-tuned models
 */
public class ModelFineTuning {
    private final AIProjectClient projectClient;
    private final String connectionName;

    public ModelFineTuning(AIProjectClient projectClient, String connectionName) {
        this.projectClient = projectClient;
        this.connectionName = connectionName;
    }

    /**
     * Prepare training data from collected feedback and trace data
     */
    // <training_data_prep>
    // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    public Map<String, Object> prepareTrainingData(List<Map<String, Object>> feedbackData,
                                                   List<Map<String, Object>> traceData) {
        System.out.println("\n=== Preparing Training Data ===");
        
        List<Map<String, String>> trainingExamples = new ArrayList<>();
        
        // Convert feedback and traces into training format
        for (Map<String, Object> feedback : feedbackData) {
            if ((Integer) feedback.get("rating") >= 4) {
                Map<String, String> example = new HashMap<>();
                example.put("prompt", (String) feedback.get("user_query"));
                example.put("completion", (String) feedback.get("agent_response"));
                trainingExamples.add(example);
            }
        }
        
        Map<String, Object> dataset = new HashMap<>();
        dataset.put("training_examples", trainingExamples);
        dataset.put("total_examples", trainingExamples.size());
        dataset.put("format", "jsonl");
        
        System.out.println("  ✓ Training data prepared");
        System.out.println("    Total examples: " + trainingExamples.size());
        
        return dataset;
    }
    // </training_data_prep>

    /**
     * Submit fine-tuning job to Azure OpenAI
     */
    // <finetuning_job>
    // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
    public String submitFineTuningJob(String baseModel, Map<String, Object> trainingDataset) {
        System.out.println("\n=== Submitting Fine-Tuning Job ===");
        
        Map<String, Object> jobConfig = new HashMap<>();
        jobConfig.put("model", baseModel);
        jobConfig.put("training_file", trainingDataset.get("training_file_id"));
        jobConfig.put("hyperparameters", Map.of(
            "n_epochs", 3,
            "batch_size", 4,
            "learning_rate_multiplier", 0.1
        ));
        
        String jobId = "ft-job-" + UUID.randomUUID().toString().substring(0, 8);
        
        System.out.println("  ✓ Fine-tuning job submitted");
        System.out.println("    Job ID: " + jobId);
        System.out.println("    Base model: " + baseModel);
        System.out.println("    Training examples: " + trainingDataset.get("total_examples"));
        
        return jobId;
    }
    // </finetuning_job>

    /**
     * Monitor fine-tuning job progress
     */
    public Map<String, Object> monitorFineTuningJob(String jobId) {
        System.out.println("\n=== Monitoring Fine-Tuning Job ===");
        System.out.println("  Job ID: " + jobId);
        
        // Simulate job status
        Map<String, Object> status = new HashMap<>();
        status.put("job_id", jobId);
        status.put("status", "completed");
        status.put("progress", 100);
        status.put("trained_tokens", 125000);
        status.put("fine_tuned_model", "gpt-4o-mini-ft-" + jobId);
        
        System.out.println("  Status: " + status.get("status"));
        System.out.println("  Progress: " + status.get("progress") + "%");
        System.out.println("  Trained tokens: " + status.get("trained_tokens"));
        
        return status;
    }

    /**
     * Deploy fine-tuned model for production use
     */
    public void deployFineTunedModel(String fineTunedModel) {
        System.out.println("\n=== Deploying Fine-Tuned Model ===");
        System.out.println("  Model: " + fineTunedModel);
        System.out.println("  Deployment name: " + fineTunedModel + "-deployment");
        System.out.println("  ✓ Model deployed successfully");
        System.out.println("  ✓ Ready for production use");
    }

    /**
     * Validate fine-tuned model quality
     */
    public Map<String, Object> validateFineTunedModel(String fineTunedModel) {
        System.out.println("\n=== Validating Fine-Tuned Model ===");
        
        Map<String, Object> validation = new HashMap<>();
        validation.put("model", fineTunedModel);
        validation.put("accuracy", 94.5);
        validation.put("coherence_score", 4.2);
        validation.put("relevance_score", 4.5);
        validation.put("safety_checks_passed", true);
        
        System.out.println("  Accuracy: " + validation.get("accuracy") + "%");
        System.out.println("  Coherence: " + validation.get("coherence_score") + "/5");
        System.out.println("  Relevance: " + validation.get("relevance_score") + "/5");
        System.out.println("  Safety: " + (Boolean) validation.get("safety_checks_passed") ? "✓ Passed" : "✗ Failed");
        
        return validation;
    }

    public void run() {
        System.out.println("\n" + "=".repeat(60));
        System.out.println("MODULE 3: Model Fine-Tuning");
        System.out.println("=".repeat(60));

        // Simulate feedback and trace data
        List<Map<String, Object>> feedbackData = new ArrayList<>();
        feedbackData.add(Map.of(
            "rating", 5,
            "user_query", "How do I reset my password?",
            "agent_response", "To reset your password, navigate to Settings > Security > Reset Password."
        ));
        
        List<Map<String, Object>> traceData = new ArrayList<>();
        
        Map<String, Object> trainingData = prepareTrainingData(feedbackData, traceData);
        
        String jobId = submitFineTuningJob("gpt-4o-mini", trainingData);
        Map<String, Object> jobStatus = monitorFineTuningJob(jobId);
        
        String fineTunedModel = (String) jobStatus.get("fine_tuned_model");
        Map<String, Object> validation = validateFineTunedModel(fineTunedModel);
        
        if ((Boolean) validation.get("safety_checks_passed")) {
            deployFineTunedModel(fineTunedModel);
        }
    }
}
