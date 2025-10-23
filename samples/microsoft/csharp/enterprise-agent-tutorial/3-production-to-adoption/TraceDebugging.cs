using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Azure.AI.Projects;

namespace Microsoft.Azure.Samples.ProductionToAdoption
{
    /// <summary>
    /// Trace Debugging Module
    /// 
    /// This module demonstrates how to collect and analyze trace data from production
    /// agent runs using Application Insights integration.
    /// 
    /// Key Features:
    /// - Application Insights configuration
    /// - Trace collection from production
    /// - Performance analysis (latency, errors, bottlenecks)
    /// - Pattern detection in failures
    /// </summary>
    public class TraceDebugging
    {
        private readonly AIProjectClient? _projectClient;
        private readonly string _agentId;

        public TraceDebugging(AIProjectClient? projectClient, string agentId)
        {
            _projectClient = projectClient;
            _agentId = agentId;
        }

        // <application_insights_setup>
        // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
        /// <summary>
        /// Configure Application Insights for trace collection.
        /// </summary>
        public Dictionary<string, object> ConfigureApplicationInsights()
        {
            Helpers.PrintInfo("Configuring Application Insights for trace collection...");

            // In production, would use actual Application Insights SDK
            var config = new Dictionary<string, object>
            {
                ["instrumentation_key"] = Environment.GetEnvironmentVariable("APPINSIGHTS_INSTRUMENTATION_KEY") ?? "demo-key",
                ["connection_string"] = Environment.GetEnvironmentVariable("APPINSIGHTS_CONNECTION_STRING") ?? "InstrumentationKey=demo-key",
                ["sampling_percentage"] = 100,
                ["enable_live_metrics"] = true,
                ["track_dependencies"] = true
            };

            Helpers.PrintSuccess("Application Insights configured");
            return config;
        }
        // </application_insights_setup>

        // <trace_analysis>
        // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
        /// <summary>
        /// Collect and analyze traces from production runs.
        /// </summary>
        public Dictionary<string, object> CollectAndAnalyzeTraces(int days = 7)
        {
            Helpers.PrintInfo($"Collecting traces from last {days} days...");

            // Generate synthetic trace data for demonstration
            var random = new Random();
            var totalTraces = random.Next(800, 1200);

            var traces = Enumerable.Range(0, totalTraces).Select(i => new Dictionary<string, object>
            {
                ["trace_id"] = $"trace-{i:D6}",
                ["agent_id"] = _agentId,
                ["timestamp"] = DateTime.UtcNow.AddDays(-random.Next(0, days)).ToString("o"),
                ["duration_ms"] = random.Next(500, 5000),
                ["status"] = random.Next(100) < 95 ? "success" : "error",
                ["tokens_used"] = random.Next(100, 1500),
                ["model"] = "gpt-4o-mini"
            }).ToList();

            Helpers.PrintSuccess($"Collected {totalTraces} traces");

            // Analyze traces
            Helpers.PrintInfo("Analyzing trace patterns...");

            var successTraces = traces.Where(t => (string)t["status"] == "success").ToList();
            var errorTraces = traces.Where(t => (string)t["status"] == "error").ToList();

            var avgLatency = traces.Average(t => Convert.ToInt32(t["duration_ms"]));
            var p95Latency = traces.Select(t => Convert.ToInt32(t["duration_ms"]))
                                  .OrderBy(x => x)
                                  .ElementAt((int)(traces.Count * 0.95));
            var errorRate = (double)errorTraces.Count / totalTraces * 100;

            // Identify bottlenecks
            var bottlenecks = new List<Dictionary<string, object>>();
            if (avgLatency > 2000)
            {
                bottlenecks.Add(new Dictionary<string, object>
                {
                    ["type"] = "High Average Latency",
                    ["value"] = $"{avgLatency:F0}ms",
                    ["recommendation"] = "Consider caching frequently requested data"
                });
            }

            if (p95Latency > 4000)
            {
                bottlenecks.Add(new Dictionary<string, object>
                {
                    ["type"] = "High P95 Latency",
                    ["value"] = $"{p95Latency}ms",
                    ["recommendation"] = "Optimize long-running queries or implement timeout handling"
                });
            }

            var analysis = new Dictionary<string, object>
            {
                ["total_traces"] = totalTraces,
                ["successful_traces"] = successTraces.Count,
                ["failed_traces"] = errorTraces.Count,
                ["avg_latency_ms"] = avgLatency,
                ["p95_latency_ms"] = p95Latency,
                ["p99_latency_ms"] = traces.Select(t => Convert.ToInt32(t["duration_ms"]))
                                          .OrderBy(x => x)
                                          .ElementAt((int)(traces.Count * 0.99)),
                ["error_rate"] = errorRate,
                ["bottlenecks"] = bottlenecks,
                ["recommendations"] = new List<string>
                {
                    bottlenecks.Count > 0 ? "Address identified bottlenecks" : "Performance is within acceptable limits",
                    errorRate > 5 ? "Investigate error patterns" : "Error rate is acceptable",
                    "Set up alerts for latency spikes",
                    "Monitor token usage trends"
                }
            };

            return analysis;
        }
        // </trace_analysis>

        /// <summary>
        /// Execute complete trace debugging workflow.
        /// </summary>
        public Dictionary<string, object> Run()
        {
            Helpers.PrintHeader("Trace Data Collection & Debugging");

            // Configure Application Insights
            var config = ConfigureApplicationInsights();

            // Collect and analyze traces
            var analysis = CollectAndAnalyzeTraces();

            // Display results
            Helpers.PrintTraceSummary(analysis);

            // Save results
            var result = new Dictionary<string, object>
            {
                ["configuration"] = config,
                ["analysis"] = analysis,
                ["timestamp"] = Helpers.FormatTimestamp()
            };

            Helpers.SaveJson(result, "trace_analysis.json");

            return analysis;
        }
    }
}
