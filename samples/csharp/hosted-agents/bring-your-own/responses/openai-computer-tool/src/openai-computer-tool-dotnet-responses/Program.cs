// Copyright (c) Microsoft Corporation.
// Licensed under the MIT License.

using System.Runtime.CompilerServices;
using System.Text;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;

namespace OpenAIComputerToolHostedAgent;

public class Program
{
    public static async Task Main(string[] args)
    {
        // Support direct CLI execution (`dotnet run -- --local [paint_smiley]`)
        if (args.Any(a => string.Equals(a, "--local", StringComparison.OrdinalIgnoreCase)))
        {
            string promptArg = string.Join(
                " ",
                args.Where(a => !string.Equals(a, "--local", StringComparison.OrdinalIgnoreCase)));
            CuaLoopResult result = await PaintSmileyScenario.RunPaintScenarioAsync(promptArg);
            Console.WriteLine($"\n=== Final Output ===\n{result.FinalText}");
            Console.WriteLine($"Saved PNG: {result.OutputFile}");
            return;
        }

        // Start the Azure AI Hosted Agent Responses server on port 8088
        ResponsesServer.Run<ComputerToolHandler>(args);
    }
}

/// <summary>
/// Hosted Agent <see cref="ResponseHandler"/> that receives <c>POST /responses</c> requests,
/// runs the GA OpenAI Computer Tool (<c>{"type": "computer"}</c>) loop against the in-container
/// <see cref="VirtualPaintDesktop"/> (<c>1280x800</c>), and streams the result back.
/// </summary>
public sealed class ComputerToolHandler : ResponseHandler
{
    public override async IAsyncEnumerable<ResponseStreamEvent> CreateAsync(
        CreateResponse request,
        ResponseContext context,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        string userInput = (await context.GetInputTextAsync(cancellationToken: cancellationToken)).Trim();
        bool verbose = userInput.Contains("/verbose", StringComparison.OrdinalIgnoreCase);
        string cleanedInput = userInput
            .Replace("/verbose", string.Empty, StringComparison.OrdinalIgnoreCase)
            .Trim();

        CuaLoopResult result = await PaintSmileyScenario.RunPaintScenarioAsync(
            cleanedInput,
            maxTurns: 25,
            cancellationToken: cancellationToken);

        StringBuilder reply = new();
        if (verbose && result.TurnLogs.Count > 0)
        {
            reply.AppendLine("Executed OpenAI Computer Tool (`{\"type\": \"computer\"}`) on container Virtual Paint Desktop (1280x800):");
            foreach (string log in result.TurnLogs)
            {
                reply.AppendLine($"- {log}");
            }

            reply.AppendLine();
        }

        reply.AppendLine(result.FinalText);
        if (File.Exists(result.OutputFile))
        {
            FileInfo fileInfo = new(result.OutputFile);
            reply.Append($"Saved image: {result.OutputFile} ({fileInfo.Length} bytes)");
        }

        var stream = new ResponseEventStream(context, request);
        yield return stream.EmitCreated();

        var message = stream.AddOutputItemMessage();
        yield return message.EmitAdded();

        var text = message.AddTextContent();
        yield return text.EmitAdded();

        string finalReply = reply.ToString().Trim();
        yield return text.EmitDelta(finalReply);
        yield return text.EmitTextDone(finalReply);
        yield return text.EmitDone();

        yield return message.EmitDone();
        yield return stream.EmitCompleted();
    }
}
