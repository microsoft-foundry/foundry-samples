// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Text;
using Azure.AI.AgentServer.Invocations;
using Azure.AI.AgentServer.Invocations.Voice;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging.Abstractions;
using NUnit.Framework;

namespace VoiceHostedAgent.Tests;

[TestFixture]
public class ResponseLifecycleTests
{
    private static readonly TimeSpan Timeout = TimeSpan.FromSeconds(3);
    private const string Token = "data: {\"type\":\"token\",\"content\":\"hello\"}\n\n";
    private const string Done = "data: {\"type\":\"done\",\"full_text\":\"hello\"}\n\n";

    [TestCase("response")]
    [TestCase("stream")]
    [TestCase("writer")]
    [TestCase("start")]
    [TestCase("complete")]
    [TestCase("empty_flush")]
    [TestCase("writer_complete")]
    public async Task StartingCallbacks_RunOnceInReverseOrder_BeforeOutput(string api)
    {
        var sequence = new List<string>();
        var handler = new Handler(async response =>
        {
            response.OnStarting(state =>
            {
                Assert.That(response.HasStarted, Is.False);
                sequence.Add((string)state);
                response.ContentType = "text/event-stream";
                return Task.CompletedTask;
            }, "first");
            response.OnStarting(async () => { await Task.Yield(); sequence.Add("second"); });
            response.OnCompleted(() => { sequence.Add("completed"); return Task.CompletedTask; });
            if (api == "start") { await response.StartAsync(); }
            if (api == "empty_flush")
            {
                await response.BodyWriter.FlushAsync();
                Assert.That(response.HasStarted, Is.True);
                Assert.That(sequence, Is.EqualTo(new[] { "second", "first" }));
            }
            if (api == "writer_complete")
            {
                Buffer(response, Token + Done);
                await response.BodyWriter.CompleteAsync();
            }
            else if (api == "writer" || api == "complete")
            {
                Buffer(response, Token + Done);
                if (api == "writer") { await response.BodyWriter.FlushAsync(); }
                else { await response.CompleteAsync(); }
            }
            else if (api == "stream")
            {
                await response.Body.WriteAsync(Encoding.UTF8.GetBytes(Token + Done));
                await response.Body.FlushAsync();
            }
            else { await response.WriteAsync(Token + Done); }
            Assert.That(response.HasStarted, Is.True);
            Assert.Throws<InvalidOperationException>(() =>
                response.OnStarting(() => Task.CompletedTask));
            await response.StartAsync();
            sequence.Add("handler");
        });
        Assert.That(await Collect(handler).WaitAsync(Timeout), Is.EqualTo("hello"));
        Assert.That(sequence, Is.EqualTo(new[] { "second", "first", "handler", "completed" }));
    }

    [Test]
    public async Task StartingCallbacks_DoNotWaitForHandlerReturn()
    {
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var handler = new Handler(async response =>
        {
            response.OnStarting(async () =>
            {
                await Task.Yield();
                response.ContentType = "text/event-stream";
            });
            await response.WriteAsync(Token);
            await release.Task;
            await response.WriteAsync(Done);
        });
        await using var iterator = new InvocationAdapter(handler)
            .Stream(new CapturingVoiceSession(), "in_stream", "input").GetAsyncEnumerator();
        try
        {
            Assert.That(await iterator.MoveNextAsync().AsTask().WaitAsync(Timeout), Is.True);
            Assert.That(iterator.Current, Is.EqualTo("hello"));
        }
        finally { release.TrySetResult(); }
        Assert.That(await iterator.MoveNextAsync().AsTask().WaitAsync(Timeout), Is.False);
    }

    [TestCase(false, false)]
    [TestCase(true, false)]
    [TestCase(false, true)]
    [TestCase(true, true)]
    public async Task StartingFailure_CannotBeIgnored_AndCompletionStillRuns(
        bool catchFailure, bool emptyFlush)
    {
        var starts = 0;
        var completions = 0;
        var handler = new Handler(async response =>
        {
            response.ContentType = "text/event-stream";
            response.OnCompleted(() => { completions++; return Task.CompletedTask; });
            response.OnStarting(() =>
            {
                starts++;
                throw new ApplicationException("primary startup failure");
            });
            try
            {
                if (emptyFlush) { await response.BodyWriter.FlushAsync(); }
                else { await response.WriteAsync(Token + Done); }
            }
            catch (ApplicationException) when (catchFailure) { }
        });
        var error = Assert.CatchAsync(async () => await Collect(handler).WaitAsync(Timeout));
        Assert.That(error, Is.TypeOf<ApplicationException>());
        Assert.That(error!.Message, Is.EqualTo("primary startup failure"));
        Assert.That(starts, Is.EqualTo(1));
        Assert.That(completions, Is.EqualTo(1));
        Assert.That(await Collect(new EchoHttpAgent()), Is.EqualTo("retry"));
    }

    [TestCase(false)]
    [TestCase(true)]
    public async Task LifecycleFailure_IsNotCeSuccess_AndNextResponseStillWorks(bool startupFailure)
    {
        var handler = new Handler(async response =>
        {
            response.ContentType = "text/event-stream";
            if (startupFailure)
            {
                response.OnStarting(() => throw new OperationCanceledException("local startup failure"));
            }
            await response.WriteAsync(Token + Done);
            if (!startupFailure) { Buffer(response, Token); }
        });
        var session = new CapturingVoiceSession();
        var state = ActiveState();
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        coordinator.StartResponse(session, state, "in_fail",
            new ResponsePlan(new InvocationAdapter(handler).Stream(session, "in_fail", "input"), true, null));
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(session.Messages.OfType<VoiceResponseCreatedMessage>().Count(), Is.EqualTo(1));
        Assert.That(session.Messages.OfType<VoiceErrorMessage>().Single().Code, Is.EqualTo("generation_failed"));
        Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>(), Is.Empty);
        Assert.That(session.Messages.OfType<VoiceResponseOutputTextDoneMessage>(), Is.Empty);
        Assert.That(state.TryGetResponseForInput("in_fail", out _), Is.False);
        coordinator.StartResponse(session, state, "in_next", ResponsePlan.Fixed("next"));
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>().Count(), Is.EqualTo(1));
        Assert.That(session.Messages.Last(), Is.TypeOf<VoiceResponseDoneMessage>());
    }

    [Test]
    public async Task CancellationDuringStartup_RetainsHandler_WithoutOldOutputOrTerminal()
    {
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var finalized = false;
        var handler = new Handler(async response =>
        {
            response.OnCompleted(() => { finalized = true; return Task.CompletedTask; });
            response.OnStarting(async () =>
            {
                started.TrySetResult();
                await release.Task;
                response.ContentType = "text/event-stream";
            });
            await response.WriteAsync(Token + Done, response.HttpContext.RequestAborted);
        });
        var session = new CapturingVoiceSession();
        var state = ActiveState();
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        coordinator.StartResponse(session, state, "in_old",
            new ResponsePlan(new InvocationAdapter(handler).Stream(session, "in_old", "input"), true, null));
        await started.Task.WaitAsync(Timeout);
        state.TryGetResponseForInput("in_old", out var oldId);
        try
        {
            coordinator.CancelOperation(state, oldId, ResponseOutcome.Cancelled);
            coordinator.StartResponse(session, state, "in_next", ResponsePlan.Fixed("next"));
            using var timeout = new CancellationTokenSource(Timeout);
            while (!session.Messages.OfType<VoiceResponseDoneMessage>().Any())
            {
                await Task.Delay(1, timeout.Token);
            }
            Assert.That(state.TryGetOperation(oldId, out _), Is.True);
            Assert.That(finalized, Is.False);
        }
        finally { release.TrySetResult(); await coordinator.DrainAsync().WaitAsync(Timeout); }
        Assert.That(finalized, Is.True);
        Assert.That(state.TryGetOperation(oldId, out _), Is.False);
        Assert.That(session.Messages.OfType<VoiceResponseOutputTextDeltaMessage>()
            .Any(frame => frame.ResponseId == oldId), Is.False);
        Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>()
            .Any(frame => frame.ResponseId == oldId), Is.False);
        Assert.That(session.Messages.OfType<VoiceErrorMessage>(), Is.Empty);
    }

    [TestCase(false)]
    [TestCase(true)]
    public async Task BufferedTail_IsFlushedBeforePipeCompletion(bool invalidTail)
    {
        var completed = 0;
        var handler = new Handler(async response =>
        {
            response.ContentType = "text/event-stream";
            response.OnCompleted(() => { completed++; return Task.CompletedTask; });
            await response.WriteAsync(Token + (invalidTail ? Done : ""));
            // Exceed the pipe's backpressure threshold: finalization must run alongside its reader.
            Buffer(response, new string(':', 20_000) + "\n\n" +
                (invalidTail ? Token : Done));
        });
        if (invalidTail)
        {
            var error = Assert.CatchAsync(async () => await Collect(handler).WaitAsync(Timeout));
            Assert.That(error!.Message, Is.EqualTo("SSE event after done."));
        }
        else { Assert.That(await Collect(handler).WaitAsync(Timeout), Is.EqualTo("hello")); }
        Assert.That(completed, Is.EqualTo(1));
        Assert.That(await Collect(new EchoHttpAgent()), Is.EqualTo("retry"));
    }

    [Test]
    public async Task HandlerFailure_RemainsPrimary_WhenBodyFinalizationAlsoFails()
    {
        var completed = 0;
        var handler = new Handler(response =>
        {
            response.OnStarting(() => throw new ApplicationException("secondary startup failure"));
            response.OnCompleted(() => { completed++; return Task.CompletedTask; });
            throw new InvalidOperationException("primary handler failure");
        });
        var error = Assert.CatchAsync(async () => await Collect(handler).WaitAsync(Timeout));
        Assert.That(error!.Message, Is.EqualTo("primary handler failure"));
        Assert.That(completed, Is.EqualTo(1));
        Assert.That(await Collect(new EchoHttpAgent()), Is.EqualTo("retry"));
    }

    [TestCase(false)]
    [TestCase(true)]
    public async Task ExplicitWriterFailure_CannotBecomeSuccess(bool synchronous)
    {
        var completions = 0;
        var handler = new Handler(async response =>
        {
            response.ContentType = "text/event-stream";
            response.OnCompleted(() => { completions++; return Task.CompletedTask; });
            await response.WriteAsync(Token + Done);
            var failure = new ApplicationException("explicit body failure");
            if (synchronous) { response.BodyWriter.Complete(failure); }
            else { await response.BodyWriter.CompleteAsync(failure); }
        });
        var error = Assert.CatchAsync(async () => await Collect(handler).WaitAsync(Timeout));
        Assert.That(error!.Message, Is.EqualTo("explicit body failure"));
        Assert.That(completions, Is.EqualTo(1));
        Assert.That(await Collect(new EchoHttpAgent()), Is.EqualTo("retry"));
    }

    private static void Buffer(HttpResponse response, string text)
    {
        var bytes = Encoding.UTF8.GetBytes(text);
        bytes.CopyTo(response.BodyWriter.GetMemory(bytes.Length));
        response.BodyWriter.Advance(bytes.Length);
    }

    private static VoiceConnectionState ActiveState()
    {
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        return state;
    }

    private static async Task<string> Collect(InvocationHandler handler)
    {
        var output = new StringBuilder();
        await foreach (var chunk in new InvocationAdapter(handler)
            .Stream(new CapturingVoiceSession(), "in_retry", "retry"))
        {
            output.Append(chunk);
        }
        return output.ToString();
    }

    private sealed class Handler(Func<HttpResponse, Task> callback) : InvocationHandler
    {
        public override Task HandleAsync(HttpRequest request, HttpResponse response,
            InvocationContext context, CancellationToken cancellationToken) => callback(response);
    }
}
