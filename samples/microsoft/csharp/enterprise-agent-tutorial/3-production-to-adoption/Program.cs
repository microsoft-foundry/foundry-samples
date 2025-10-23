using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;

namespace Microsoft.Azure.Samples.ProductionToAdoption
{
    /*
     * Azure AI Foundry Agent Sample - Tutorial 3: Production to Adoption
     * 
     * This tutorial demonstrates production operations for enterprise AI agents:
     * - Debug & improve agents using collected trace data
     * - Enable collection & download of human feedback from production
     * - Fine-tune models using collected data
     * - Insight analysis on offline evaluation results
     * - Integrate an AI gateway to centrally manage agent interactions
     * - Monitor agent quality & performance (continuous/scheduled evals)
     * - Monitor and govern agent access (across the fleet)
     * - Monitor costs
     */

    class Program
    {
        static async Task Main(string[] args)
        {
            Env.Load();

            Console.WriteLine("=" + new string('=', 69));
            Console.WriteLine("🚀 Azure AI Foundry - Production to Adoption");
            Console.WriteLine("Tutorial 3: Enterprise AI Operations & Continuous Improvement");
            Console.WriteLine("=" + new string('=', 69));
            Console.WriteLine("\nThis tutorial demonstrates production operations for enterprise AI agents:");
            Helpers.PrintListItems(new[]
            {
                "Trace data collection and performance debugging",
                "Human feedback collection and analysis",
                "Model fine-tuning with production data",
                "Evaluation insights and pattern detection",
                "AI gateway integration (API Management)",
                "Continuous monitoring with scheduled evaluations",
                "Fleet-wide governance and compliance",
                "Cost monitoring and optimization"
            });
            Console.WriteLine("=" + new string('=', 69));

            var moduleResults = new Dictionary<string, object?>();

            try
            {
                // <authentication_setup>
                // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
                // Initialize Azure AI Project Client
                var projectEndpoint = Environment.GetEnvironmentVariable("PROJECT_ENDPOINT");
                AIProjectClient? projectClient = null;

                if (string.IsNullOrEmpty(projectEndpoint))
                {
                    Helpers.PrintWarning("PROJECT_ENDPOINT not set. Using mock client for demonstration.");
                }
                else
                {
                    Helpers.PrintInfo("Initializing Azure AI Project Client...");
                    projectClient = new AIProjectClient(
                        new Uri(projectEndpoint),
                        new DefaultAzureCredential()
                    );
                    Helpers.PrintSuccess("Project client initialized");
                }
                // </authentication_setup>

                var agentId = Environment.GetEnvironmentVariable("AGENT_ID") ?? "demo-agent-123";

                // <module_orchestration>
                // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
                // Module 1: Trace Data Collection & Debugging
                try
                {
                    var traceDebugger = new TraceDebugging(projectClient, agentId);
                    moduleResults["trace_debugging"] = traceDebugger.Run();
                }
                catch (Exception ex)
                {
                    Helpers.PrintError($"Trace debugging failed: {ex.Message}");
                    moduleResults["trace_debugging"] = null;
                }

                // Module 2: Human Feedback Collection
                try
                {
                    var feedbackCollector = new FeedbackCollection(projectClient, agentId);
                    moduleResults["feedback_collection"] = feedbackCollector.Run();
                }
                catch (Exception ex)
                {
                    Helpers.PrintError($"Feedback collection failed: {ex.Message}");
                    moduleResults["feedback_collection"] = null;
                }

                // Module 3: Model Fine-Tuning Pipeline
                try
                {
                    var finetuner = new ModelFineTuning(projectClient, agentId);
                    moduleResults["model_finetuning"] = finetuner.Run();
                }
                catch (Exception ex)
                {
                    Helpers.PrintError($"Model fine-tuning failed: {ex.Message}");
                    moduleResults["model_finetuning"] = null;
                }

                // Module 4: Evaluation Insights Analysis
                try
                {
                    var insightsAnalyzer = new EvaluationInsights(projectClient, agentId);
                    moduleResults["evaluation_insights"] = insightsAnalyzer.Run();
                }
                catch (Exception ex)
                {
                    Helpers.PrintError($"Evaluation insights failed: {ex.Message}");
                    moduleResults["evaluation_insights"] = null;
                }

                // Module 5: AI Gateway Integration
                try
                {
                    var gateway = new GatewayIntegration(projectClient, agentId);
                    moduleResults["gateway_integration"] = gateway.Run();
                }
                catch (Exception ex)
                {
                    Helpers.PrintError($"Gateway integration failed: {ex.Message}");
                    moduleResults["gateway_integration"] = null;
                }

                // Module 6: Continuous Monitoring
                try
                {
                    var monitoring = new ContinuousMonitoring(projectClient, agentId);
                    moduleResults["continuous_monitoring"] = monitoring.Run();
                }
                catch (Exception ex)
                {
                    Helpers.PrintError($"Continuous monitoring failed: {ex.Message}");
                    moduleResults["continuous_monitoring"] = null;
                }

                // Module 7: Fleet-Wide Governance
                try
                {
                    var governance = new FleetGovernance(projectClient, agentId);
                    moduleResults["fleet_governance"] = governance.Run();
                }
                catch (Exception ex)
                {
                    Helpers.PrintError($"Fleet governance failed: {ex.Message}");
                    moduleResults["fleet_governance"] = null;
                }

                // Module 8: Cost Monitoring & Optimization
                try
                {
                    var costOptimizer = new CostOptimization(projectClient, agentId);
                    moduleResults["cost_optimization"] = costOptimizer.Run();
                }
                catch (Exception ex)
                {
                    Helpers.PrintError($"Cost optimization failed: {ex.Message}");
                    moduleResults["cost_optimization"] = null;
                }
                // </module_orchestration>

                // Generate summary report
                var summaryReport = Helpers.CreateSummaryReport(moduleResults);
                Helpers.SaveJson(summaryReport, "tutorial_summary.json");

                // Display completion summary
                Helpers.PrintCompletionSummary(summaryReport);

                // Final message
                Console.WriteLine("\n" + new string('=', 70));
                Helpers.PrintSuccess("Tutorial 3 completed successfully!");
                Console.WriteLine(new string('=', 70));
                Console.WriteLine("\n🎉 Congratulations! You've completed the full Enterprise Agent Tutorial series!");
                Console.WriteLine("\nYour Modern Workplace Assistant is now:");
                Helpers.PrintListItems(new[]
                {
                    "✅ Production-ready with safety and governance",
                    "✅ Continuously monitored with automated evaluations",
                    "✅ Optimized through human feedback and fine-tuning",
                    "✅ Cost-efficient with optimization recommendations",
                    "✅ Compliant with fleet-wide governance",
                    "✅ Gateway-managed for centralized access control"
                });

                Console.WriteLine("\n📚 Next Steps:");
                Helpers.PrintListItems(new[]
                {
                    "Deploy monitoring functions to Azure Functions",
                    "Implement feedback collection in your production UI",
                    "Review and act on optimization recommendations",
                    "Set up Application Insights dashboards",
                    "Configure cost alerts and budgets",
                    "Monitor fine-tuning job progress",
                    "Scale to additional agents and use cases"
                });

                Console.WriteLine("\n✨ Thank you for completing the Enterprise Agent Tutorial series!");
            }
            catch (Exception ex)
            {
                Helpers.PrintError($"An error occurred: {ex.Message}");
                Console.WriteLine($"\nStack trace:\n{ex.StackTrace}");
                Environment.Exit(1);
            }
        }
    }
}
