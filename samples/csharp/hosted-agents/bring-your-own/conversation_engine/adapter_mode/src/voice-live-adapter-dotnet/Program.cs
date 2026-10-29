// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

using Azure.AI.AgentServer.Invocations.Voice;
using VoiceHostedAgent;

VoiceServer.Run<VoiceAgent>(args, builder =>
{
    // The HTTP-shaped business handler is called in process, never registered as an endpoint.
    builder.Services.AddSingleton(new InvocationAdapter(new EchoHttpAgent()));
    builder.Services.AddOpenTelemetry()
        .WithTracing(tracing => tracing
            .AddSource(ResponseTelemetry.SourceName));
});
