// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.AgentServer.Activity;
using CopilotSample;

ActivityServer.Run<CopilotAgent>(args, configure: builder =>
{
    builder.Services.AddSingleton<TaskStore>();
    builder.Services.AddHttpClient<FileTransfers>()
        .ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler { AllowAutoRedirect = false });
    builder.Services.AddSingleton<CopilotAssistant>();
    builder.Services.AddSingleton<IAssistant>(services => services.GetRequiredService<CopilotAssistant>());
    builder.Services.AddHostedService(services => services.GetRequiredService<CopilotAssistant>());
});
