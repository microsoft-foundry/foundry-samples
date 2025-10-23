using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Azure.AI.Projects;

namespace Microsoft.Azure.Samples.ProductionToAdoption
{
    public class FeedbackCollection
    {
        private readonly AIProjectClient? _projectClient;
        private readonly string _agentId;

        public FeedbackCollection(AIProjectClient? projectClient, string agentId)
        {
            _projectClient = projectClient;
            _agentId = agentId;
        }

        // <feedback_api>
        // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
        public List<Dictionary<string, object>> CollectFeedbackFromProduction(int days = 30)
        {
            Helpers.PrintInfo($"Collecting user feedback from last {days} days...");
            
            var random = new Random();
            var numFeedback = random.Next(700, 900);
            var feedbackList = new List<Dictionary<string, object>>();

            for (int i = 0; i < numFeedback; i++)
            {
                var rating = random.Next(100) < 87 ? "positive" : "negative";
                feedbackList.Add(new Dictionary<string, object>
                {
                    ["feedback_id"] = $"fb-{i:D6}",
                    ["conversation_id"] = $"conv-{random.Next(1000, 9999)}",
                    ["timestamp"] = DateTime.UtcNow.AddDays(-random.Next(0, days)).ToString("o"),
                    ["rating"] = rating,
                    ["feedback_text"] = rating == "positive" ? "Great response!" : "Could be better",
                    ["user_id"] = $"user{random.Next(1, 50)}@company.com"
                });
            }

            Helpers.PrintSuccess($"Collected {feedbackList.Count} feedback items");
            return feedbackList;
        }
        // </feedback_api>

        // <feedback_analysis>
        // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
        public Dictionary<string, object> AnalyzeFeedback(List<Dictionary<string, object>> feedbackList)
        {
            Helpers.PrintInfo("Analyzing user feedback...");
            
            var total = feedbackList.Count;
            var positive = feedbackList.Count(f => (string)f["rating"] == "positive");
            var negative = total - positive;

            var analysis = new Dictionary<string, object>
            {
                ["statistics"] = new Dictionary<string, object>
                {
                    ["total_feedback"] = total,
                    ["positive_count"] = positive,
                    ["negative_count"] = negative,
                    ["satisfaction_rate"] = (double)positive / total
                },
                ["recommendations"] = new List<string>
                {
                    positive > negative ? "Maintain current quality" : "Address user concerns"
                }
            };

            return analysis;
        }
        // </feedback_analysis>

        public Dictionary<string, object> Run()
        {
            Helpers.PrintHeader("Human Feedback Collection & Analysis");
            var feedback = CollectFeedbackFromProduction();
            var analysis = AnalyzeFeedback(feedback);
            Helpers.PrintFeedbackSummary(analysis);
            Helpers.SaveJson(analysis, "feedback_summary.json");
            return analysis;
        }
    }
}
