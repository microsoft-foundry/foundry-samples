// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

using System.ClientModel.Primitives;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;
using OpenAI.Responses;

namespace OpenAIComputerTool.Utils;

/// <summary>
/// Provision or delete the Azure AI Foundry Prompt Agent with the GA OpenAI Computer Tool (<c>{"type": "computer"}</c>).
/// </summary>
public static class AgentFactory
{
    private const string ComputerToolJson = """{"type":"computer"}""";

    public static async Task ProvisionAgentAsync(string? agentName = null)
    {
        string resolvedAgentName = agentName ?? Settings.AgentName;
        string endpoint = Settings.GetProjectEndpoint();
        string model = Settings.GetModelDeploymentName();
        string instructions = Settings.LoadAgentInstructions();

        ResponseTool computerTool = ModelReaderWriter.Read<ResponseTool>(BinaryData.FromString(ComputerToolJson))
            ?? throw new InvalidOperationException("Failed to construct ComputerTool definition.");

        DeclarativeAgentDefinition definition = new(model)
        {
            Instructions = instructions,
        };
        definition.Tools.Add(computerTool);

        Console.WriteLine($"Provisioning Prompt Agent '{resolvedAgentName}' on {endpoint} ...");
        Console.WriteLine($"  Model        : {model}");
        Console.WriteLine($"  Tool         : {ComputerToolJson}");
        Console.WriteLine($"  Instructions : prompts/base.md");

        AIProjectClient projectClient = Settings.GetProjectClient();
        ProjectsAgentVersion agent = await projectClient.AgentAdministrationClient.CreateAgentVersionAsync(
            resolvedAgentName,
            new ProjectsAgentVersionCreationOptions(definition));

        Console.WriteLine($"Agent created (id={agent.Id}, name={agent.Name}, version={agent.Version})");
    }

    public static async Task DeleteAgentAsync(string? agentName = null)
    {
        string resolvedAgentName = agentName ?? Settings.AgentName;
        AIProjectClient projectClient = Settings.GetProjectClient();
        AgentAdministrationClient agentsClient = projectClient.AgentAdministrationClient;

        int deletedCount = 0;
        await foreach (ProjectsAgentVersion version in agentsClient.GetAgentVersionsAsync(resolvedAgentName))
        {
            await agentsClient.DeleteAgentVersionAsync(resolvedAgentName, version.Version);
            deletedCount++;
        }

        Console.WriteLine($"Deleted {deletedCount} version(s) of '{resolvedAgentName}'.");
    }
}
