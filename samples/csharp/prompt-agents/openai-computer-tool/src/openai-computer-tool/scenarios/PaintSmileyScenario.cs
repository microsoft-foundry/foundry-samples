// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

using OpenAIComputerTool.Utils;

namespace OpenAIComputerTool.Scenarios;

/// <summary>
/// MS Paint colored smiley face scenario for the OpenAI Computer Tool Prompt Agent.
/// The agent opens Microsoft Paint itself by using Windows Search (or pressing the
/// Windows key, searching for Paint, and pressing Enter), draws a centered yellow
/// smiley face on a clean white canvas, and saves the drawing to <c>paint_smiley_&lt;timestamp&gt;.png</c>.
/// </summary>
public static class PaintSmileyScenario
{
    public static string BuildPaintPrompt(string outputFile) =>
        "Open Microsoft Paint from Windows Search, draw a cheerful yellow smiley face " +
        "centered on a clean white canvas with a black outline, two black oval eyes, and a curved smile, " +
        $"and save the image to '{outputFile}'.";

    public static async Task<string> RunPaintScenarioAsync(string? prompt = null)
    {
        string timestamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
        string outputFile = Path.Combine(Directory.GetCurrentDirectory(), $"paint_smiley_{timestamp}.png");
        string taskPrompt = string.IsNullOrWhiteSpace(prompt)
            ? BuildPaintPrompt(outputFile)
            : prompt;

        await AgentRunner.RunCuaLoopAsync(
            prompt: taskPrompt,
            handleAction: DesktopAutomationHelper.HandleAction,
            takeScreenshot: DesktopAutomationHelper.TakeDesktopScreenshot,
            maxTurns: 40);

        if (File.Exists(outputFile))
        {
            FileInfo info = new(outputFile);
            Console.WriteLine($"\nSaved image ({info.Name}): {outputFile} ({info.Length} bytes)");
        }

        return outputFile;
    }
}
