// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

using DotNetEnv;

namespace OpenAIComputerToolHostedAgent;

/// <summary>
/// Environment configuration and system instructions for the C# OpenAI Computer Tool Hosted Agent.
/// </summary>
public static class Settings
{
    public const string SystemPrompt = """
        You are a desktop automation agent running on Microsoft Foundry and equipped with the `computer` tool (`{"type": "computer"}`).

        Inspect the desktop screenshot before taking action and after each batch of actions. Use batched `computer_call` actions (`click`, `double_click`, `triple_click`, `move`, `drag`, `scroll`, `type`, `keypress`, `wait`, `screenshot`) to complete the user's task, verify the result visually on screen, and then provide a concise summary.
        """;

    static Settings()
    {
        Env.NoClobber().TraversePath().Load();
    }

    public static string GetProjectEndpoint() =>
        GetFirstEnv("FOUNDRY_PROJECT_ENDPOINT", "PROJECT_ENDPOINT", "AZURE_AI_PROJECT_ENDPOINT")
        ?? throw new InvalidOperationException(
            "Required environment variable FOUNDRY_PROJECT_ENDPOINT is not set.");

    public static string GetModelDeploymentName() =>
        GetFirstEnv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "AZURE_AI_MODEL_DEPLOYMENT_NAME", "MODEL_DEPLOYMENT_NAME")
        ?? "gpt-5.4";

    public static string GetSystemPrompt() => SystemPrompt;

    public static string GetWritableOutputPath(string filename)
    {
        string workDir = Directory.GetCurrentDirectory();
        try
        {
            string candidate = Path.Combine(workDir, filename);
            string testProbe = Path.Combine(workDir, $".write_probe_{Guid.NewGuid():N}");
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
}
