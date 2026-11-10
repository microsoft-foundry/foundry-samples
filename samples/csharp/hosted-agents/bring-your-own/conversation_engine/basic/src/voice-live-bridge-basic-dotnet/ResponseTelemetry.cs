// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using System.Diagnostics;

namespace VoiceHostedAgent;

internal enum ResponseOutcome
{
    Response,
    None,
    Cancelled,
    Timeout,
    Error,
    EndCall,
    TransportError,
    Abandoned,
}

internal static class ResponseTelemetry
{
    internal const string SourceName = "VoiceHostedAgent.Response";
    internal const string ResponseDurationTag = "voice_agent.hosted_agent.response_duration_ms";
    internal const string ResponseIdTag = "gen_ai.response.id";
    internal const string InputItemIdTag = "voice_agent.input.item_id";
    internal const string OutcomeTag = "voice_agent.hosted_agent.outcome";
    private static readonly ActivitySource s_activitySource = new(SourceName);

    internal static Activity? Start(string responseId, string inputItemId)
    {
        var activity = s_activitySource.StartActivity("process_response", ActivityKind.Internal);
        activity?.SetTag(ResponseIdTag, responseId);
        activity?.SetTag(InputItemIdTag, inputItemId);
        return activity;
    }

    internal static void RecordOutcome(
        Activity? activity,
        TimeSpan responseDuration,
        ResponseOutcome outcome)
    {
        activity?.SetTag(ResponseDurationTag, responseDuration.TotalMilliseconds);
        activity?.SetTag(OutcomeTag, OutcomeValue(outcome));
        activity?.SetStatus(outcome is ResponseOutcome.Abandoned or
            ResponseOutcome.Error or
            ResponseOutcome.Timeout or
            ResponseOutcome.TransportError
                ? ActivityStatusCode.Error
                : ActivityStatusCode.Ok);
        activity?.Stop();
    }

    internal static void RecordErrorType(Activity? activity, Exception exception) =>
        activity?.SetTag("error.type", exception.GetType().FullName);

    private static string OutcomeValue(ResponseOutcome outcome) => outcome switch
    {
        ResponseOutcome.Response => "response",
        ResponseOutcome.None => "none",
        ResponseOutcome.Cancelled => "cancelled",
        ResponseOutcome.Timeout => "timeout",
        ResponseOutcome.Error => "error",
        ResponseOutcome.EndCall => "end_call",
        ResponseOutcome.TransportError => "transport_error",
        ResponseOutcome.Abandoned => "abandoned",
        _ => throw new ArgumentOutOfRangeException(nameof(outcome)),
    };
}
