// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.RegularExpressions;
using A2A;

namespace EchoA2A;

public sealed class EchoAgent(ILogger<EchoAgent> logger) : IAgentHandler
{
    public async Task ExecuteAsync(RequestContext context, AgentEventQueue eventQueue, CancellationToken cancellationToken)
    {
        string text = string.Join("\n", context.Message.Parts.Where(part => part.Text is not null).Select(part => part.Text));
        if (!context.Message.Parts.Any(part => part.Text is not null))
        {
            throw new A2AException("Echo requires a text part.", A2AErrorCode.InvalidParams);
        }

        logger.LogInformation("A2A_REQUEST_RECEIVED message_id={MessageId} task_id={TaskId} context_id={ContextId}",
            context.Message.MessageId, context.TaskId, context.ContextId);
        var updater = new TaskUpdater(eventQueue, context.TaskId, context.ContextId);
        if (context.Task is null)
        {
            await updater.SubmitAsync(cancellationToken: cancellationToken);
        }

        string reply = $"Echo: {text}";
        bool demo = context.Message.Metadata?.TryGetValue("streaming_demo", out JsonElement flag) == true
            && flag.ValueKind == JsonValueKind.True;
        if (demo)
        {
            await updater.StartWorkAsync(cancellationToken: cancellationToken);
            var chunks = BuildChunks(reply);
            string artifactId = Guid.NewGuid().ToString();
            for (int index = 0; index < chunks.Count; index++)
            {
                if (index > 0)
                {
                    await Task.Delay(TimeSpan.FromMilliseconds(500), cancellationToken);
                }

                await updater.AddArtifactAsync(
                    [Part.FromText(chunks[index])], artifactId: artifactId, name: "streaming-echo",
                    append: index > 0, lastChunk: index == chunks.Count - 1, cancellationToken: cancellationToken);
                logger.LogInformation("A2A_ECHO_CHUNK task_id={TaskId} index={Index} total={Total}",
                    context.TaskId, index + 1, chunks.Count);
            }
        }
        else
        {
            await updater.AddArtifactAsync([Part.FromText(reply)], cancellationToken: cancellationToken);
        }

        await updater.CompleteAsync(cancellationToken: cancellationToken);
        logger.LogInformation("A2A_ECHO_COMPLETED task_id={TaskId} context_id={ContextId}", context.TaskId, context.ContextId);
    }

    public static IReadOnlyList<string> BuildChunks(string text)
    {
        var lines = Regex.Matches(text, @".*?(?:\r\n|\r|\n|\z)", RegexOptions.Singleline)
            .Select(match => match.Value).Where(line => line.Length > 0).ToArray();
        int batchSize = Math.Max(1, (lines.Length + 15) / 16);
        return lines.Chunk(batchSize).Select(batch => string.Concat(batch)).ToArray();
    }

    public static AgentCard CreateCard(string url) => new()
    {
        Name = "Foundry A2A Echo Agent (.NET)",
        Description = "Echoes text as a completed native A2A Task artifact.",
        Version = "1.0.0",
        SupportedInterfaces = [new AgentInterface { Url = url, ProtocolBinding = "JSONRPC", ProtocolVersion = "1.0" }],
        DefaultInputModes = ["text/plain"],
        DefaultOutputModes = ["text/plain"],
        Capabilities = new AgentCapabilities { Streaming = true, PushNotifications = false },
        Skills = [new AgentSkill
        {
            Id = "echo", Name = "Echo", Description = "Returns the supplied text with an Echo prefix.",
            Tags = ["echo"], Examples = ["hello"],
        }],
    };
}
