// <imports_and_includes>
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Azure;
using Azure.AI.Agents;
using Azure.Core;
using Azure.Identity;
using DotNetEnv;
using OpenAI;
using OpenAI.Responses;
// </imports_and_includes>

class EvaluateProgram
{
    static async Task Main(string[] args)
    {
        // Load environment variables from shared directory
        Env.Load("../shared/.env");

        var projectEndpoint = Environment.GetEnvironmentVariable("PROJECT_ENDPOINT");
        var modelDeploymentName = Environment.GetEnvironmentVariable("MODEL_DEPLOYMENT_NAME");
        var sharepointConnectionId = Environment.GetEnvironmentVariable("SHAREPOINT_CONNECTION_ID");
        var mcpServerUrl = Environment.GetEnvironmentVariable("MCP_SERVER_URL");
        var tenantId = Environment.GetEnvironmentVariable("AI_FOUNDRY_TENANT_ID");

        // Use tenant-specific credential if provided
        TokenCredential credential;
        if (!string.IsNullOrEmpty(tenantId))
        {
            credential = new AzureCliCredential(new AzureCliCredentialOptions { TenantId = tenantId });
        }
        else
        {
            credential = new DefaultAzureCredential();
        }

        AgentsClient client = new(new Uri(projectEndpoint), credential);

        Console.WriteLine("🧪 Modern Workplace Assistant Evaluation\n");

        List<ToolDefinition> tools = new();

        // Add SharePoint tool if configured
        if (!string.IsNullOrEmpty(sharepointConnectionId))
        {
            try
            {
                SharepointToolDefinition sharepointTool = new(new SharepointGroundingToolParameters(sharepointConnectionId));
                tools.Add(sharepointTool);
                Console.WriteLine("✅ SharePoint configured for evaluation");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"⚠️  SharePoint unavailable: {ex.Message}");
            }
        }

        // Add MCP tool if configured
        if (!string.IsNullOrEmpty(mcpServerUrl))
        {
            try
            {
                MCPToolDefinition mcpTool = new("microsoft_learn", mcpServerUrl);
                tools.Add(mcpTool);
                Console.WriteLine("✅ MCP configured for evaluation");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"⚠️  MCP unavailable: {ex.Message}");
            }
        }

        Console.WriteLine();

        var instructions = @"You are a Modern Workplace Assistant for Contoso Corporation.
Answer questions using available tools and provide specific, detailed responses.";

        AgentDefinition agentDefinition = new PromptAgentDefinition(modelDeploymentName)
        {
            Instructions = instructions,
            Tools = tools
        };

        AgentVersion agent = await client.CreateAgentVersionAsync(
            "Evaluation Agent",
            agentDefinition
        );

        // <load_test_data>
        var questions = File.ReadAllLines("../shared/questions.jsonl")
            .Select(line => JsonSerializer.Deserialize<JsonElement>(line))
            .ToList();
        // </load_test_data>

        // <run_batch_evaluation>
        // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
        var results = new List<object>();

        Console.WriteLine($"Running {questions.Count} evaluation questions...\n");

        for (int i = 0; i < questions.Count; i++)
        {
            var q = questions[i];
            var question = q.GetProperty("question").GetString()!;
            
            string[] expectedKeywords = Array.Empty<string>();
            if (q.TryGetProperty("expected_keywords", out var keywordsElem))
            {
                expectedKeywords = keywordsElem.EnumerateArray()
                    .Select(e => e.GetString()!)
                    .ToArray();
            }
            
            Console.WriteLine($"Question {i + 1}/{questions.Count}: {question}");

            // Get OpenAI client from the agents client
            OpenAIClient openAIClient = client.GetOpenAIClient();
            OpenAIResponseClient responseClient = openAIClient.GetOpenAIResponseClient(modelDeploymentName);

            // Create a conversation to maintain state
            AgentConversation conversation = await client.GetConversationsClient().CreateConversationAsync();

            // Set up response creation options with agent and conversation references
            ResponseCreationOptions responseCreationOptions = new();
            responseCreationOptions.SetAgentReference(agent.Name);
            responseCreationOptions.SetConversationReference(conversation);

            // Create the user message item
            List<ResponseItem> items = [ResponseItem.CreateUserMessageItem(question)];

            string response = "";
            try
            {
                // Create response from the agent
                OpenAIResponse openAIResponse = await responseClient.CreateResponseAsync(items, responseCreationOptions);
                response = openAIResponse.GetOutputText();
            }
            catch (Exception ex)
            {
                Console.WriteLine($"   ⚠️  Error: {ex.Message}");
                response = "";
            }

            bool passed = response.Length > 50;
            if (expectedKeywords.Length > 0)
            {
                passed = passed && expectedKeywords.Any(k => response.Contains(k, StringComparison.OrdinalIgnoreCase));
            }

            Console.WriteLine($"   Status: {(passed ? "✅ PASS" : "❌ FAIL")}");
            Console.WriteLine($"   Response length: {response.Length} characters\n");

            results.Add(new
            {
                question,
                response,
                passed,
                response_length = response.Length
            });
        }
        // </run_batch_evaluation>

        // Cleanup - Note: In SDK 2.0, agents are versioned and managed differently
        // await client.DeleteAgentAsync(agent.Name); // Uncomment if you want to delete

        // <evaluation_results>
        // NOTE: This code is a non-runnable snippet of the larger sample code from which it is taken.
        var summary = new
        {
            total_questions = questions.Count,
            passed = results.Count(r => ((dynamic)r).passed),
            failed = results.Count(r => !((dynamic)r).passed),
            results
        };

        var json = JsonSerializer.Serialize(summary, new JsonSerializerOptions { WriteIndented = true });
        File.WriteAllText("evaluation_results.json", json);

        Console.WriteLine($"📊 Evaluation Complete:");
        Console.WriteLine($"   Total: {summary.total_questions}");
        Console.WriteLine($"   Passed: {summary.passed}");
        Console.WriteLine($"   Failed: {summary.failed}");
        Console.WriteLine($"\n📄 Results saved to evaluation_results.json");
        // </evaluation_results>
    }
}
