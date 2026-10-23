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
        "Open Windows Search (click the Start/Search button on the taskbar or press the WIN key), " +
        "search for 'Paint' (mspaint), and press Enter to open MS Paint (press Ctrl+N if needed for a clean canvas). " +
        "In MS Paint, draw a cheerful, polished smiley face centered on a clean white canvas. " +
        "Use a large yellow circle with a smooth black outline, two evenly spaced black oval eyes, " +
        "and a curved black smile. Keep the features balanced and the lines neat. " +
        "Use the ellipse and curve tools where possible, and leave some white space around the face. " +
        "Don’t add text or extra decorations. " +
        $"When finished drawing, save the image (press Ctrl+S, type the full path '{outputFile}', and press Enter).";

    public static async Task<string> RunPaintScenarioAsync(string? prompt = null)
    {
        string timestamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
        string outputFile = Path.Combine(Settings.SrcDir, $"paint_smiley_{timestamp}.png");
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
