// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

using DotNetEnv;

namespace OpenAIComputerToolHostedAgent;

/// <summary>
/// Environment configuration and prompt loader for the C# OpenAI Computer Tool Hosted Agent.
/// </summary>
public static class Settings
{
    public static readonly string SrcDir = ResolveSrcDir();

    static Settings()
    {
        string envFile = Path.Combine(SrcDir, ".env");
        if (File.Exists(envFile))
        {
            Env.Load(envFile);
        }
    }

    public static string GetProjectEndpoint() =>
        GetFirstEnv("FOUNDRY_PROJECT_ENDPOINT", "PROJECT_ENDPOINT", "AZURE_AI_PROJECT_ENDPOINT")
        ?? throw new InvalidOperationException(
            "Required environment variable FOUNDRY_PROJECT_ENDPOINT or PROJECT_ENDPOINT is not set.");

    public static string GetModelDeploymentName() =>
        GetFirstEnv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "MODEL_DEPLOYMENT_NAME")
        ?? "gpt-5.4";

    public static string GetSystemPrompt()
    {
        string promptPath = Path.Combine(SrcDir, "prompts", "base.md");
        if (!File.Exists(promptPath))
        {
            promptPath = Path.Combine(AppContext.BaseDirectory, "prompts", "base.md");
        }

        if (!File.Exists(promptPath))
        {
            return "You are a helpful computer-use agent running inside a Microsoft Foundry Hosted Agent container.";
        }

        return File.ReadAllText(promptPath).Trim();
    }

    public static string GetWritableOutputPath(string filename)
    {
        try
        {
            string candidate = Path.Combine(SrcDir, filename);
            string testProbe = Path.Combine(SrcDir, $".write_probe_{Guid.NewGuid():N}");
            File.WriteAllText(testProbe, string.Empty);
            File.Delete(testProbe);
            return candidate;
        }
        catch
        {
            return Path.Combine(Path.GetTempPath(), filename);
        }
    }

    private static string? GetFirstEnv(params string[] names)
    {
        foreach (string name in names)
        {
            string? val = Environment.GetEnvironmentVariable(name);
            if (!string.IsNullOrWhiteSpace(val))
            {
                return val.Trim();
            }
        }

        return null;
    }

    private static string ResolveSrcDir()
    {
        DirectoryInfo? dir = new(AppContext.BaseDirectory);
        while (dir is not null)
        {
            if (File.Exists(Path.Combine(dir.FullName, "openai-computer-tool.csproj")))
            {
                return dir.FullName;
            }

            dir = dir.Parent;
        }

        return Directory.GetCurrentDirectory();
    }
}
