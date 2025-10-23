using System;
using System.Collections.Generic;
using System.Linq;
using Azure.AI.Projects;

namespace Microsoft.Azure.Samples.ProductionToAdoption
{
    public class ModelFineTuning
    {
        private readonly AIProjectClient? _projectClient;
        private readonly string _agentId;

        public ModelFineTuning(AIProjectClient? projectClient, string agentId)
        {
            _projectClient = projectClient;
            _agentId = agentId;
        }

        // <training_data_prep>
        // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
        public List<Dictionary<string, object>> PrepareTrainingData()
        {
            Helpers.PrintInfo("Preparing training data from conversations...");
            var random = new Random();
            var examples = Enumerable.Range(0, random.Next(2000, 2500))
                .Select(i => new Dictionary<string, object>
                {
                    ["messages"] = new List<Dictionary<string, string>>
                    {
                        new() { ["role"] = "system", ["content"] = "You are a helpful workplace assistant." },
                        new() { ["role"] = "user", ["content"] = "What is our company policy?" },
                        new() { ["role"] = "assistant", ["content"] = "Based on our policies..." }
                    }
                }).ToList();
            Helpers.PrintSuccess($"Prepared {examples.Count} training examples");
            return examples;
        }
        // </training_data_prep>

        // <finetuning_job>
        // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
        public Dictionary<string, object> CreateFineTuningJob()
        {
            Helpers.PrintInfo("Creating fine-tuning job...");
            var config = new Dictionary<string, object>
            {
                ["job_id"] = $"ftjob-{new Random().Next(100000, 999999)}",
                ["status"] = "pending",
                ["base_model"] = "gpt-4o-mini"
            };
            Helpers.PrintSuccess($"Fine-tuning job created: {config["job_id"]}");
            return config;
        }
        // </finetuning_job>

        public Dictionary<string, object> Run()
        {
            Helpers.PrintHeader("Model Fine-Tuning Pipeline");
            var training = PrepareTrainingData();
            var job = CreateFineTuningJob();
            var result = new Dictionary<string, object>
            {
                ["config"] = new Dictionary<string, object>
                {
                    ["training_examples"] = training.Count,
                    ["validation_examples"] = training.Count / 10,
                    ["base_model"] = "gpt-4o-mini"
                },
                ["job_id"] = job["job_id"]
            };
            Helpers.PrintFineTuningSummary(result);
            Helpers.SaveJson(result, "finetuning_config.json");
            return result;
        }
    }
}
