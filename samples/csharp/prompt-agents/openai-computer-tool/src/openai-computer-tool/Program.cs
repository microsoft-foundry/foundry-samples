// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

using OpenAIComputerTool.Scenarios;
using OpenAIComputerTool.Utils;

bool createAgent = false;
bool deleteAgent = false;
string? customPrompt = null;

for (int i = 0; i < args.Length; i++)
{
    switch (args[i])
    {
        case "--create-agent":
        case "create-agent":
            createAgent = true;
            break;

        case "--delete":
        case "--delete-agent":
        case "delete-agent":
            deleteAgent = true;
            break;

        case "--prompt":
            if (i + 1 >= args.Length)
            {
                throw new ArgumentException("Missing value for --prompt.");
            }

            customPrompt = args[++i];
            break;

        case "-h":
        case "--help":
            PrintUsage();
            return;
    }
}

if (deleteAgent)
{
    await AgentFactory.DeleteAgentAsync();
    return;
}

if (createAgent)
{
    await AgentFactory.ProvisionAgentAsync();
    return;
}

await PaintSmileyScenario.RunPaintScenarioAsync(customPrompt);

static void PrintUsage()
{
    Console.WriteLine("Usage:");
    Console.WriteLine("  dotnet run -- --create-agent          Create/initialize the Prompt Agent in Microsoft Foundry");
    Console.WriteLine("  dotnet run                            Run the default MS Paint colored smiley scenario");
    Console.WriteLine("  dotnet run -- --prompt \"<task>\"       Run a custom desktop task prompt");
    Console.WriteLine("  dotnet run -- --delete                Delete all versions of the Prompt Agent");
}
