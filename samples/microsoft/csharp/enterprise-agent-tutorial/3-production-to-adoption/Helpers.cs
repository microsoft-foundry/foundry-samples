using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;

namespace Microsoft.Azure.Samples.ProductionToAdoption
{
    /// <summary>
    /// Helper utilities for the Production to Adoption tutorial.
    /// Provides common functionality used across modules.
    /// </summary>
    public static class Helpers
    {
        /// <summary>
        /// Prints a formatted header.
        /// </summary>
        public static void PrintHeader(string title, int width = 70)
        {
            Console.WriteLine("\n" + new string('=', width));
            Console.WriteLine(title);
            Console.WriteLine(new string('=', width));
        }

        /// <summary>
        /// Prints a success message with formatting.
        /// </summary>
        public static void PrintSuccess(string message)
        {
            Console.WriteLine($"✅ {message}");
        }

        /// <summary>
        /// Prints an error message with formatting.
        /// </summary>
        public static void PrintError(string message)
        {
            Console.WriteLine($"❌ {message}");
        }

        /// <summary>
        /// Prints a warning message with formatting.
        /// </summary>
        public static void PrintWarning(string message)
        {
            Console.WriteLine($"⚠️  {message}");
        }

        /// <summary>
        /// Prints an info message with formatting.
        /// </summary>
        public static void PrintInfo(string message)
        {
            Console.WriteLine($"ℹ️  {message}");
        }

        /// <summary>
        /// Prints a list of items.
        /// </summary>
        public static void PrintListItems(IEnumerable<string> items)
        {
            foreach (var item in items)
            {
                Console.WriteLine($"   • {item}");
            }
        }

        /// <summary>
        /// Formats a timestamp.
        /// </summary>
        public static string FormatTimestamp()
        {
            return DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ss.fffZ");
        }

        /// <summary>
        /// Formats currency value.
        /// </summary>
        public static string FormatCurrency(double amount)
        {
            return $"${amount:F2}";
        }

        /// <summary>
        /// Saves object as JSON file.
        /// </summary>
        public static void SaveJson(object obj, string filename)
        {
            var json = JsonSerializer.Serialize(obj, new JsonSerializerOptions 
            { 
                WriteIndented = true 
            });
            File.WriteAllText(filename, json);
            PrintSuccess($"Saved {filename}");
        }

        /// <summary>
        /// Prints trace summary.
        /// </summary>
        public static void PrintTraceSummary(Dictionary<string, object> analysis)
        {
            Console.WriteLine("\n📊 Trace Analysis Summary:");
            Console.WriteLine($"   Total Traces: {analysis["total_traces"]}");
            Console.WriteLine($"   Average Latency: {analysis["avg_latency_ms"]:F0}ms");
            Console.WriteLine($"   Error Rate: {analysis["error_rate"]:F1}%");
        }

        /// <summary>
        /// Prints feedback summary.
        /// </summary>
        public static void PrintFeedbackSummary(Dictionary<string, object> analysis)
        {
            var stats = (Dictionary<string, object>)analysis["statistics"];
            Console.WriteLine("\n📊 Feedback Analysis Summary:");
            Console.WriteLine($"   Total Feedback: {stats["total_feedback"]}");
            Console.WriteLine($"   Satisfaction Rate: {Convert.ToDouble(stats["satisfaction_rate"]):P1}");
            Console.WriteLine($"   Positive: {stats["positive_count"]}");
            Console.WriteLine($"   Negative: {stats["negative_count"]}");
        }

        /// <summary>
        /// Prints fine-tuning summary.
        /// </summary>
        public static void PrintFineTuningSummary(Dictionary<string, object> result)
        {
            var config = (Dictionary<string, object>)result["config"];
            Console.WriteLine("\n📊 Fine-Tuning Configuration:");
            Console.WriteLine($"   Training Examples: {config["training_examples"]}");
            Console.WriteLine($"   Validation Examples: {config["validation_examples"]}");
            Console.WriteLine($"   Base Model: {config["base_model"]}");
            Console.WriteLine($"   Job ID: {result["job_id"]}");
        }

        /// <summary>
        /// Prints evaluation insights.
        /// </summary>
        public static void PrintEvaluationInsights(Dictionary<string, object> insights)
        {
            Console.WriteLine("\n📊 Evaluation Insights:");
            var patterns = (List<Dictionary<string, object>>)insights["failure_patterns"];
            Console.WriteLine($"   Failure Patterns Identified: {patterns.Count}");
            
            var trends = (Dictionary<string, object>)insights["quality_trends"];
            Console.WriteLine($"   Current Quality: {Convert.ToDouble(trends["current_month"]):P1}");
        }

        /// <summary>
        /// Prints gateway summary.
        /// </summary>
        public static void PrintGatewaySummary(Dictionary<string, object> config)
        {
            var cfg = (Dictionary<string, object>)config["configuration"];
            Console.WriteLine("\n📊 Gateway Configuration:");
            Console.WriteLine($"   Endpoint: {cfg["endpoint"]}");
            Console.WriteLine($"   Rate Limit: {cfg["rate_limit"]}");
            Console.WriteLine($"   Caching: {cfg["caching_enabled"]}");
        }

        /// <summary>
        /// Prints monitoring summary.
        /// </summary>
        public static void PrintMonitoringSummary(Dictionary<string, object> config)
        {
            var schedule = (Dictionary<string, object>)config["schedule"];
            Console.WriteLine("\n📊 Monitoring Configuration:");
            Console.WriteLine($"   Schedules Configured: {schedule.Count}");
            
            var alerts = (List<Dictionary<string, object>>)config["alerts"];
            Console.WriteLine($"   Alerts Configured: {alerts.Count}");
        }

        /// <summary>
        /// Prints governance summary.
        /// </summary>
        public static void PrintGovernanceSummary(Dictionary<string, object> report)
        {
            var stats = (Dictionary<string, object>)report["statistics"];
            Console.WriteLine("\n📊 Fleet Governance Report:");
            Console.WriteLine($"   Total Agents: {stats["total_agents"]}");
            Console.WriteLine($"   Active Users: {stats["active_users"]}");
            Console.WriteLine($"   Compliance Rate: {Convert.ToDouble(stats["compliance_rate"]):P1}");
        }

        /// <summary>
        /// Prints cost summary.
        /// </summary>
        public static void PrintCostSummary(Dictionary<string, object> report)
        {
            var totals = (Dictionary<string, object>)report["totals"];
            Console.WriteLine("\n📊 Cost Analysis:");
            Console.WriteLine($"   Total Cost: {FormatCurrency(Convert.ToDouble(totals["total_cost"]))}");
            Console.WriteLine($"   Period: {totals["period"]}");
            Console.WriteLine($"   Potential Savings: {FormatCurrency(Convert.ToDouble(report["projected_savings"]))}");
        }

        /// <summary>
        /// Creates summary report.
        /// </summary>
        public static Dictionary<string, object> CreateSummaryReport(Dictionary<string, object?> moduleResults)
        {
            return new Dictionary<string, object>
            {
                ["timestamp"] = FormatTimestamp(),
                ["tutorial"] = "Production to Adoption",
                ["modules_executed"] = moduleResults.Count,
                ["module_results"] = moduleResults
            };
        }

        /// <summary>
        /// Prints completion summary.
        /// </summary>
        public static void PrintCompletionSummary(Dictionary<string, object> summary)
        {
            Console.WriteLine("\n" + new string('=', 70));
            Console.WriteLine("📊 TUTORIAL EXECUTION SUMMARY");
            Console.WriteLine(new string('=', 70));
            Console.WriteLine($"Modules Executed: {summary["modules_executed"]}");
            Console.WriteLine($"Timestamp: {summary["timestamp"]}");
        }
    }
}
