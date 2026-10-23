// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

using Azure.AI.Projects;
using Azure.Identity;
using DotNetEnv;

namespace OpenAIComputerTool.Utils;

/// <summary>
/// Shared configuration and client helpers for the OpenAI Computer Tool Prompt Agent sample.
/// </summary>
public static class Settings
{
    public static readonly string SrcDir = ResolveSrcDir();
    public static readonly string SampleRootDir = Path.GetFullPath(Path.Combine(SrcDir, "..", ".."));
    public static readonly string PromptsPath = Path.Combine(SrcDir, "prompts", "base.md");

    static Settings()
    {
        string localEnv = Path.Combine(SrcDir, ".env");
        if (File.Exists(localEnv))
        {
            Env.Load(localEnv);
        }

        string rootEnv = Path.Combine(SampleRootDir, ".env");
        if (File.Exists(rootEnv))
        {
            Env.Load(rootEnv);
        }
    }

    public static string AgentName =>
        GetOptionalEnv("AGENT_NAME", "openai-computer-agent");

    public static string LoadAgentInstructions()
    {
        if (File.Exists(PromptsPath))
        {
            return File.ReadAllText(PromptsPath).Trim();
        }

        string outputPromptsPath = Path.Combine(AppContext.BaseDirectory, "prompts", "base.md");
        if (File.Exists(outputPromptsPath))
        {
            return File.ReadAllText(outputPromptsPath).Trim();
        }

        throw new FileNotFoundException($"Could not find agent instructions file at '{PromptsPath}'.");
    }

    public static string GetProjectEndpoint()
    {
        string? endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")?.Trim().TrimEnd('/');
        if (string.IsNullOrEmpty(endpoint))
        {
            throw new InvalidOperationException(
                "Set AZURE_AI_PROJECT_ENDPOINT in .env or via `azd env set`.");
        }

        return endpoint;
    }

    public static string GetModelDeploymentName() =>
        GetOptionalEnv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4");

    public static AIProjectClient GetProjectClient() =>
        new(new Uri(GetProjectEndpoint()), new DefaultAzureCredential());

    private static string GetOptionalEnv(string name, string fallback)
    {
        string? value = Environment.GetEnvironmentVariable(name)?.Trim();
        return string.IsNullOrEmpty(value) ? fallback : value;
    }

    private static string ResolveSrcDir()
    {
        string current = Directory.GetCurrentDirectory();
        if (File.Exists(Path.Combine(current, "openai-computer-tool.csproj")))
        {
            return current;
        }

        string candidate = Path.Combine(current, "src", "openai-computer-tool");
        if (File.Exists(Path.Combine(candidate, "openai-computer-tool.csproj")))
        {
            return candidate;
        }

        DirectoryInfo? dir = new(AppContext.BaseDirectory);
        while (dir is not null)
        {
            if (File.Exists(Path.Combine(dir.FullName, "openai-computer-tool.csproj")))
            {
                return dir.FullName;
            }

            dir = dir.Parent;
        }

        return current;
    }
}
