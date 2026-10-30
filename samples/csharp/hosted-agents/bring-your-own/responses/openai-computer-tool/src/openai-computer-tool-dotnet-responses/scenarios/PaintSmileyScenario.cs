// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

namespace OpenAIComputerToolHostedAgent;

/// <summary>
/// Paint Smiley scenario prompt and runner for the C# OpenAI Computer Tool Hosted Agent.
/// </summary>
public static class PaintSmileyScenario
{
    public static string BuildPaintPrompt(string outputFile) =>
        "Draw a cheerful yellow smiley face centered on the white Paint canvas with a black outline, " +
        "two black oval eyes, and a curved smile. " +
        $"When finished, click Save (or press Ctrl+S) to save the image to '{outputFile}'.";

    public static Task<CuaLoopResult> RunPaintScenarioAsync(
        string? customPrompt = null,
        int maxTurns = 25,
        CancellationToken cancellationToken = default) =>
        AgentRunner.RunPaintSmileyLoopAsync(customPrompt, maxTurns, cancellationToken);
}
