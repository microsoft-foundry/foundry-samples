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
public class CompletionCallbackTests
{
    private static readonly TimeSpan Timeout = TimeSpan.FromSeconds(3);

    private static VoiceConnectionState ActiveState()
    {
        var state = new VoiceConnectionState();
        state.TryBeginStart();
        state.Activate();
        return state;
    }

    [Test]
    public async Task CompletionCallbacks_RunInReverseOrder_WithTheirState_BeforeCeSuccess()
    {
        var sequence = new List<string>();
        var handler = new Handler(async (_, response, _, token) =>
        {
            response.OnCompleted(state =>
            {
                sequence.Add((string)state);
                return Task.CompletedTask;
            }, "first");
            response.OnCompleted(() =>
            {
                Assert.That(response.HttpContext.RequestAborted.IsCancellationRequested, Is.False);
                sequence.Add("second");
                return Task.CompletedTask;
            });
            await WriteValid(response, token);
            sequence.Add("handler");
        });
        var session = new CapturingVoiceSession();
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        var state = ActiveState();
        coordinator.StartResponse(session, state, "in_callbacks",
            new ResponsePlan(new InvocationAdapter(handler).Stream(session, "in_callbacks", "input"), true, null));
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(sequence, Is.EqualTo(new[] { "handler", "second", "first" }));
        Assert.That(session.Messages.Last(), Is.TypeOf<VoiceResponseDoneMessage>());
        Assert.That(session.Messages.OfType<VoiceErrorMessage>(), Is.Empty);
        coordinator.StartResponse(session, state, "in_next", ResponsePlan.Fixed("next"));
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>().Count(), Is.EqualTo(2));
    }

    [TestCase(false)]
    [TestCase(true)]
    public async Task CeSuccess_WaitsForCompletion_AndCallbackFailureDoesNotSkipOthers(bool fail)
    {
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var sequence = new List<string>();
        var handler = new Handler(async (_, response, _, token) =>
        {
            response.OnCompleted(() => { sequence.Add("last"); return Task.CompletedTask; });
            response.OnCompleted(async () =>
            {
                started.TrySetResult();
                await release.Task;
                sequence.Add("gated");
                if (fail) { throw new InvalidOperationException("controlled completion failure"); }
            });
            await WriteValid(response, token);
        });
        var session = new CapturingVoiceSession();
        var state = ActiveState();
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        coordinator.StartResponse(session, state, "in_gated",
            new ResponsePlan(new InvocationAdapter(handler).Stream(session, "in_gated", "input"), true, null));
        try
        {
            await started.Task.WaitAsync(Timeout);
            Assert.That(state.TryGetResponseForInput("in_gated", out _), Is.True);
            Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>(), Is.Empty);
            Assert.That(session.Messages.OfType<VoiceResponseOutputTextDoneMessage>(), Is.Empty);
        }
        finally { release.TrySetResult(); await coordinator.DrainAsync().WaitAsync(Timeout); }
        Assert.That(sequence, Is.EqualTo(new[] { "gated", "last" }));
        Assert.That(state.TryGetResponseForInput("in_gated", out _), Is.False);
        Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>().Count(), Is.EqualTo(fail ? 0 : 1));
        Assert.That(session.Messages.OfType<VoiceErrorMessage>().Count(), Is.EqualTo(fail ? 1 : 0));
        coordinator.StartResponse(session, state, "in_next", ResponsePlan.Fixed("retry"));
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(session.Messages.Last(), Is.TypeOf<VoiceResponseDoneMessage>());
    }

    [Test]
    public async Task MalformedBody_RemainsThePrimaryError_WhenCompletionAlsoFails()
    {
        var callbacks = 0;
        var handler = new Handler(async (_, response, _, token) =>
        {
            response.OnCompleted(() =>
            {
                callbacks++;
                throw new ApplicationException("secondary completion failure");
            });
            response.ContentType = "text/event-stream";
            await response.WriteAsync("data: not-json\n\n", token);
        });
        var caught = Assert.CatchAsync(async () =>
        {
            await foreach (var _ in new InvocationAdapter(handler)
                .Stream(new CapturingVoiceSession(), "in_bad", "input")) { }
        });
        Assert.That(caught, Is.InstanceOf<System.Text.Json.JsonException>());
        Assert.That(callbacks, Is.EqualTo(1));
        Assert.That(await Collect(new InvocationAdapter(new EchoHttpAgent())), Is.EqualTo("retry"));
    }

    [Test]
    public async Task EarlyDisposal_DrainsHandlerAndCompletionCallbacks()
    {
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var handlerClosed = false;
        var callbackClosed = false;
        var handler = new Handler(async (_, response, _, token) =>
        {
            response.OnCompleted(async () =>
            {
                Assert.That(handlerClosed, Is.True);
                started.TrySetResult();
                await release.Task;
                callbackClosed = true;
            });
            response.ContentType = "text/event-stream";
            try
            {
                await response.WriteAsync("data: {\"type\":\"token\",\"content\":\"first\"}\n\n", token);
                await response.Body.FlushAsync(token);
                await Task.Delay(System.Threading.Timeout.InfiniteTimeSpan, token);
            }
            finally { handlerClosed = true; }
        });
        var iterator = new InvocationAdapter(handler)
            .Stream(new CapturingVoiceSession(), "in_close", "input").GetAsyncEnumerator();
        Assert.That(await iterator.MoveNextAsync().AsTask().WaitAsync(Timeout), Is.True);
        var disposal = iterator.DisposeAsync().AsTask();
        try
        {
            await started.Task.WaitAsync(Timeout);
            Assert.That(disposal.IsCompleted, Is.False);
        }
        finally { release.TrySetResult(); await disposal.WaitAsync(Timeout); }
        Assert.That(callbackClosed, Is.True);
        Assert.That(await Collect(new InvocationAdapter(new EchoHttpAgent())), Is.EqualTo("retry"));
    }


    [TestCase(false)]
    [TestCase(true)]
    public async Task CompletionFailures_AreNotSuccess_EvenForLocalCancellation(bool localCancellation)
    {
        var handler = new Handler(async (_, response, _, token) =>
        {
            response.OnCompleted(() => throw (localCancellation
                ? new OperationCanceledException("local completion cancellation")
                : new InvalidOperationException("completion failure")));
            await WriteValid(response, token);
        });
        var session = new CapturingVoiceSession();
        var state = ActiveState();
        var coordinator = new VoiceResponseCoordinator(NullLogger<VoiceAgent>.Instance);
        coordinator.StartResponse(session, state, "in_failure",
            new ResponsePlan(new InvocationAdapter(handler).Stream(session, "in_failure", "input"), true, null));
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>(), Is.Empty);
        Assert.That(session.Messages.OfType<VoiceErrorMessage>().Single().Code, Is.EqualTo("generation_failed"));
        coordinator.StartResponse(session, state, "in_next", ResponsePlan.Fixed("retry"));
        await coordinator.DrainAsync().WaitAsync(Timeout);
        Assert.That(session.Messages.Last(), Is.TypeOf<VoiceResponseDoneMessage>());
    }

    [Test]
    public async Task CancelDuringCompletion_RetainsCleanup_AndCannotEmitAnOldError()
    {
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var handler = new Handler(async (_, response, _, token) =>
        {
            response.OnCompleted(async () =>
            {
                started.TrySetResult();
                await release.Task;
                throw new InvalidOperationException("cancelled completion failure");
            });
            await WriteValid(response, token);
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
        }
        finally
        {
            release.TrySetResult();
            await coordinator.DrainAsync().WaitAsync(Timeout);
        }
        Assert.That(session.Messages.OfType<VoiceResponseDoneMessage>()
            .Any(frame => frame.ResponseId == oldId), Is.False);
        Assert.That(session.Messages.OfType<VoiceErrorMessage>(), Is.Empty);
        Assert.That(state.TryGetOperation(oldId, out _), Is.False);
    }

    [Test]
    public async Task HandlerFailure_IsNotReplacedByCompletionFailure()
    {
        var callbackRan = false;
        var handler = new Handler((_, response, _, _) =>
        {
            response.OnCompleted(() =>
            {
                callbackRan = true;
                throw new ApplicationException("secondary completion failure");
            });
            throw new InvalidOperationException("primary handler failure");
        });
        var caught = Assert.CatchAsync(async () => await Collect(new InvocationAdapter(handler)));
        Assert.That(caught!.Message, Is.EqualTo("primary handler failure"));
        Assert.That(callbackRan, Is.True);
        Assert.That(await Collect(new InvocationAdapter(new EchoHttpAgent())), Is.EqualTo("retry"));
    }

    private static async Task WriteValid(HttpResponse response, CancellationToken token)
    {
        response.ContentType = "text/event-stream";
        await response.WriteAsync(
            "data: {\"type\":\"token\",\"content\":\"hello\"}\n\n" +
            "data: {\"type\":\"done\",\"full_text\":\"hello\"}\n\n", token);
    }

    private static async Task<string> Collect(InvocationAdapter adapter)
    {
        var output = new StringBuilder();
        await foreach (var chunk in adapter.Stream(new CapturingVoiceSession(), "in_retry", "retry"))
        {
            output.Append(chunk);
        }
        return output.ToString();
    }

    private sealed class Handler(
        Func<HttpRequest, HttpResponse, InvocationContext, CancellationToken, Task> callback) : InvocationHandler
    {
        public override Task HandleAsync(HttpRequest request, HttpResponse response,
            InvocationContext context, CancellationToken cancellationToken) =>
            callback(request, response, context, cancellationToken);
    }
}
