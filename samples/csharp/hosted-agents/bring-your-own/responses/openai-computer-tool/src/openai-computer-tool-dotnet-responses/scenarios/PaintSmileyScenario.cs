// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

namespace OpenAIComputerToolHostedAgent;

/// <summary>
/// Paint Smiley scenario prompt and runner for the C# OpenAI Computer Tool Hosted Agent.
/// </summary>
public static class PaintSmileyScenario
{
    public static string BuildPaintPrompt(string outputFile) =>
        "You are looking at the 1280x800 'Paint - OpenAI Computer Tool Virtual Desktop' window. " +
        "Draw a cheerful, polished yellow smiley face centered on the white canvas using the toolbar buttons at the top:\n" +
        "1. Click 'Oval' (around x=48, y=62) and click 'Yellow' (around x=320, y=62), then drag on the canvas from (x=440, y=200) to (x=840, y=600) to draw a large yellow circle with a black outline.\n" +
        "2. Click 'Black' (around x=415, y=62) while keeping 'Oval' selected, then drag two evenly spaced oval eyes: left eye from (x=540, y=310) to (x=585, y=370), and right eye from (x=695, y=310) to (x=740, y=370).\n" +
        "3. Click 'Brush' (around x=135, y=62), then drag a smooth curved smile across points (x=530, y=460) -> (x=580, y=515) -> (x=640, y=530) -> (x=700, y=515) -> (x=750, y=460).\n" +
        $"4. Click 'Save' (around x=860, y=62) or press Ctrl+S to save the image to '{outputFile}'.";

    public static Task<CuaLoopResult> RunPaintScenarioAsync(
        string? customPrompt = null,
        int maxTurns = 25,
        CancellationToken cancellationToken = default) =>
        AgentRunner.RunPaintSmileyLoopAsync(customPrompt, maxTurns, cancellationToken);
}
