// ------------------------------------
// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.
// ------------------------------------

using System;
using System.ClientModel;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading;
using Azure.AI.Projects;
using Azure.Identity;

namespace Evaluate;

public class Program
{
    public static void Main(string[] args)
    {
        // <configure_evaluation>
        // Load environment variables
        var endpoint = Environment.GetEnvironmentVariable("PROJECT_ENDPOINT")
            ?? throw new InvalidOperationException("PROJECT_ENDPOINT not set");
        var modelDeploymentName = Environment.GetEnvironmentVariable("MODEL_DEPLOYMENT_NAME")
            ?? "gpt-4o-mini";

        // Create clients
        AIProjectClient projectClient = new(new Uri(endpoint), new DefaultAzureCredential());
        EvaluationClient evaluationClient = projectClient.OpenAI.GetEvaluationClient();

        // Create or retrieve the agent to evaluate
        PromptAgentDefinition agentDefinition = new(model: modelDeploymentName)
        {
            Instructions = "You are a helpful Modern Workplace Assistant that answers questions about company policies and technical guidance."
        };
        AgentVersion agentVersion = projectClient.Agents.CreateAgentVersion(
            agentName: "Modern Workplace Assistant",
            options: new(agentDefinition));
        Console.WriteLine($"Agent created (id: {agentVersion.Id}, name: {agentVersion.Name}, version: {agentVersion.Version})");

        // Define testing criteria with built-in evaluators
        // data_mapping: sample.output_text = agent string response, sample.output_items = structured JSON with tool calls
        object[] testingCriteria = [
            new {
                type = "azure_ai_evaluator",
                name = "violence_detection",
                evaluator_name = "builtin.violence",
                data_mapping = new { query = "{{item.query}}", response = "{{sample.output_text}}" }
            },
            new {
                type = "azure_ai_evaluator",
                name = "fluency",
                evaluator_name = "builtin.fluency",
                initialization_parameters = new { deployment_name = modelDeploymentName },
                data_mapping = new { query = "{{item.query}}", response = "{{sample.output_text}}" }
            },
            new {
                type = "azure_ai_evaluator",
                name = "task_adherence",
                evaluator_name = "builtin.task_adherence",
                initialization_parameters = new { deployment_name = modelDeploymentName },
                data_mapping = new { query = "{{item.query}}", response = "{{sample.output_items}}" }
            },
        ];

        // Define the data schema
        object dataSourceConfig = new
        {
            type = "custom",
            item_schema = new
            {
                type = "object",
                properties = new { query = new { type = "string" } },
                required = new[] { "query" }
            },
            include_sample_schema = true
        };

        // Create evaluation data payload
        BinaryData evaluationData = BinaryData.FromObjectAsJson(new
        {
            name = "Agent Evaluation",
            data_source_config = dataSourceConfig,
            testing_criteria = testingCriteria
        });

        // Create the evaluation object
        using BinaryContent evaluationDataContent = BinaryContent.Create(evaluationData);
        ClientResult evaluation = evaluationClient.CreateEvaluation(evaluationDataContent);
        Dictionary<string, string> fields = ParseClientResult(evaluation, ["name", "id"]);
        string evaluationName = fields["name"];
        string evaluationId = fields["id"];
        Console.WriteLine($"Evaluation created (id: {evaluationId}, name: {evaluationName})");
        // </configure_evaluation>

        // <run_cloud_evaluation>
        // Define the data source for the evaluation run
        // This targets the agent with test queries
        object dataSource = new
        {
            type = "azure_ai_target_completions",
            source = new
            {
                type = "file_content",
                content = new[]
                {
                    new { item = new { query = "What is Contoso's remote work policy?" } },
                    new { item = new { query = "What are the security requirements for remote employees?" } },
                    new { item = new { query = "According to Microsoft Learn, how do I configure Azure AD Conditional Access?" } },
                    new { item = new { query = "Based on our company policy, how should I configure Azure security to comply?" } },
                }
            },
            input_messages = new
            {
                type = "template",
                template = new[]
                {
                    new
                    {
                        type = "message",
                        role = "user",
                        content = new { type = "input_text", text = "{{item.query}}" }
                    }
                }
            },
            target = new
            {
                type = "azure_ai_agent",
                name = agentVersion.Name,
                // Version is optional. Defaults to latest version if not specified.
                version = agentVersion.Version,
            }
        };

        // Create evaluation run payload
        BinaryData runData = BinaryData.FromObjectAsJson(new
        {
            eval_id = evaluationId,
            name = $"Evaluation Run for Agent {agentVersion.Name}",
            data_source = dataSource
        });

        // Submit the evaluation run
        using BinaryContent runDataContent = BinaryContent.Create(runData);
        ClientResult run = evaluationClient.CreateEvaluationRun(evaluationId: evaluationId, content: runDataContent);
        fields = ParseClientResult(run, ["id", "status"]);
        string runId = fields["id"];
        string runStatus = fields["status"];
        Console.WriteLine($"Evaluation run created (id: {runId})");
        // </run_cloud_evaluation>

        // <retrieve_evaluation_results>
        // Poll until the evaluation run completes
        while (runStatus != "failed" && runStatus != "completed")
        {
            Thread.Sleep(TimeSpan.FromMilliseconds(5000));
            run = evaluationClient.GetEvaluationRun(evaluationId: evaluationId, evaluationRunId: runId, options: new());
            runStatus = ParseClientResult(run, ["status"])["status"];
            Console.WriteLine($"Waiting for eval run to complete... current status: {runStatus}");
        }

        if (runStatus == "failed")
        {
            throw new InvalidOperationException($"Evaluation run failed with error: {GetErrorMessageOrEmpty(run)}");
        }

        // Output results
        Console.WriteLine("\n✓ Evaluation run completed successfully!");
        Console.WriteLine($"Result Counts: {GetResultsCounts(run)}");

        List<string> evaluationResults = GetResultsList(
            client: evaluationClient,
            evaluationId: evaluationId,
            evaluationRunId: runId);

        Console.WriteLine($"\nOUTPUT ITEMS (Total: {evaluationResults.Count})");
        Console.WriteLine($"{new string('-', 60)}");
        foreach (string result in evaluationResults)
        {
            Console.WriteLine(result);
        }
        Console.WriteLine($"{new string('-', 60)}");

        // Cleanup
        evaluationClient.DeleteEvaluation(evaluationId, new System.ClientModel.Primitives.RequestOptions());
        Console.WriteLine("Evaluation deleted");

        projectClient.Agents.DeleteAgentVersion(agentName: agentVersion.Name, agentVersion: agentVersion.Version);
        Console.WriteLine("Agent deleted");
        // </retrieve_evaluation_results>
    }

    // <helper_methods>
    /// <summary>
    /// Parses string values from top-level JSON properties in a ClientResult.
    /// </summary>
    private static Dictionary<string, string> ParseClientResult(ClientResult result, string[] expectedProperties)
    {
        Dictionary<string, string> results = new();
        Utf8JsonReader reader = new(result.GetRawResponse().Content.ToMemory().ToArray());
        JsonDocument document = JsonDocument.ParseValue(ref reader);

        foreach (JsonProperty prop in document.RootElement.EnumerateObject())
        {
            foreach (string key in expectedProperties)
            {
                if (prop.NameEquals(Encoding.UTF8.GetBytes(key)) && prop.Value.ValueKind == JsonValueKind.String)
                {
                    results[key] = prop.Value.GetString()!;
                }
            }
        }

        List<string> notFoundItems = expectedProperties.Where(key => !results.ContainsKey(key)).ToList();
        if (notFoundItems.Count > 0)
        {
            throw new InvalidOperationException($"Keys not found in result: {string.Join(", ", notFoundItems)}");
        }
        return results;
    }

    /// <summary>
    /// Gets error message from a ClientResult if present.
    /// </summary>
    private static string GetErrorMessageOrEmpty(ClientResult result)
    {
        Utf8JsonReader reader = new(result.GetRawResponse().Content.ToMemory().ToArray());
        JsonDocument document = JsonDocument.ParseValue(ref reader);
        string? code = null;
        string? message = null;

        foreach (JsonProperty prop in document.RootElement.EnumerateObject())
        {
            if (prop.NameEquals("error"u8) && prop.Value.ValueKind != JsonValueKind.Null)
            {
                foreach (JsonProperty errorNode in prop.Value.EnumerateObject())
                {
                    if (errorNode.Value.ValueKind == JsonValueKind.String)
                    {
                        if (errorNode.NameEquals("code"u8)) code = errorNode.Value.GetString();
                        else if (errorNode.NameEquals("message"u8)) message = errorNode.Value.GetString();
                    }
                }
            }
        }
        return string.IsNullOrEmpty(message) ? "" : $"Message: {message}, Code: {code ?? "<None>"}";
    }

    /// <summary>
    /// Formats the result_counts property from a ClientResult.
    /// </summary>
    private static string GetResultsCounts(ClientResult result)
    {
        Utf8JsonReader reader = new(result.GetRawResponse().Content.ToMemory().ToArray());
        JsonDocument document = JsonDocument.ParseValue(ref reader);
        StringBuilder sb = new("{\n");

        foreach (JsonProperty prop in document.RootElement.EnumerateObject())
        {
            if (prop.NameEquals("result_counts"u8) && prop.Value is JsonElement countsElement)
            {
                foreach (JsonProperty count in countsElement.EnumerateObject())
                {
                    if (count.Value.ValueKind == JsonValueKind.Number)
                    {
                        sb.Append($"    {count.Name}: {count.Value.GetInt32()}\n");
                    }
                }
            }
        }
        sb.Append('}');
        return sb.ToString();
    }

    /// <summary>
    /// Retrieves all output items from an evaluation run (handles pagination).
    /// </summary>
    private static List<string> GetResultsList(EvaluationClient client, string evaluationId, string evaluationRunId)
    {
        List<string> resultJsons = new();
        bool hasMore;

        do
        {
            ClientResult resultList = client.GetEvaluationRunOutputItems(
                evaluationId: evaluationId,
                evaluationRunId: evaluationRunId,
                limit: null,
                order: "asc",
                after: default,
                outputItemStatus: default,
                options: new());

            Utf8JsonReader reader = new(resultList.GetRawResponse().Content.ToMemory().ToArray());
            JsonDocument document = JsonDocument.ParseValue(ref reader);
            hasMore = false;

            foreach (JsonProperty topProperty in document.RootElement.EnumerateObject())
            {
                if (topProperty.NameEquals("has_more"u8))
                {
                    hasMore = topProperty.Value.GetBoolean();
                }
                else if (topProperty.NameEquals("data"u8) && topProperty.Value.ValueKind == JsonValueKind.Array)
                {
                    foreach (JsonElement dataElement in topProperty.Value.EnumerateArray())
                    {
                        resultJsons.Add(dataElement.ToString());
                    }
                }
            }
        } while (hasMore);

        return resultJsons;
    }
    // </helper_methods>
}
