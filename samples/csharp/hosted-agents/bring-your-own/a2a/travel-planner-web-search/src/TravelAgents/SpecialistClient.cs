// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using A2A;
using Azure.Core;

namespace TravelAgents;

public sealed record SpecialistAnswer(string Agent, string TaskId, string Answer);

public sealed class SpecialistClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly string _project;
    private readonly bool _hosted;

    public SpecialistClient(string project, bool hosted, TokenCredential credential, string? callId, Activity? activity)
    {
        _project = project;
        _hosted = hosted;
        _http = new HttpClient(new AuthenticationHandler(project, hosted, credential, callId, activity)
        {
            InnerHandler = new HttpClientHandler { AllowAutoRedirect = false }
        })
        { Timeout = TimeSpan.FromMinutes(4) };
    }

    public async Task<(AgentCard Card, Uri Endpoint)> DiscoverAsync(string url, CancellationToken cancellationToken)
    {
        Uri endpoint = Settings.ValidateAgentUrl(url, _project, _hosted);
        var baseUrl = new UriBuilder(endpoint) { Query = "", Path = endpoint.AbsolutePath.TrimEnd('/') + "/" }.Uri;
        string path = endpoint.Scheme == "https" ? "agentCard/v1.0?api-version=v1" : ".well-known/agent-card.json";
        var card = await new A2ACardResolver(baseUrl, _http, path).GetAgentCardAsync(cancellationToken);
        var advertised = card.SupportedInterfaces.FirstOrDefault(item =>
            item.ProtocolBinding == "JSONRPC" && item.ProtocolVersion == "1.0");
        if (string.IsNullOrWhiteSpace(card.Name) || card.Skills.Count == 0 || advertised is null)
            throw new InvalidOperationException("Specialist card must advertise a name, skills and JSONRPC A2A 1.0.");
        var selected = Settings.ValidateAgentUrl(advertised.Url, _project, _hosted);
        if (selected.Scheme != endpoint.Scheme) throw new InvalidOperationException("Agent Card changed transport scheme.");
        if (selected.Scheme == "https" && selected.Query.Length == 0)
            selected = new UriBuilder(selected) { Query = "api-version=v1" }.Uri;
        return (card, selected);
    }

    public async Task<SpecialistAnswer> ConsultAsync(
        AgentCard card, Uri endpoint, TripRequirements requirements, CancellationToken cancellationToken)
    {
        using var native = new A2AClient(endpoint, _http);
        var response = await native.SendMessageAsync(new SendMessageRequest
        {
            Configuration = new SendMessageConfiguration { ReturnImmediately = false },
            Message = new Message
            {
                MessageId = Guid.NewGuid().ToString(),
                Role = Role.User,
                Parts = [Part.FromText(System.Text.Json.JsonSerializer.Serialize(requirements))]
            }
        }, cancellationToken);
        if (response.Task is not { } task || task.Status.State != TaskState.Completed || string.IsNullOrEmpty(task.Id))
            throw new InvalidOperationException($"{card.Name} did not return a completed A2A Task.");
        string answer = string.Join("\n", (task.Artifacts ?? []).Where(artifact => artifact.Name == "answer")
            .SelectMany(artifact => artifact.Parts)
            .Where(part => part.Text is not null).Select(part => part.Text));
        if (string.IsNullOrWhiteSpace(answer)) throw new InvalidOperationException($"{card.Name} returned no answer.");
        return new(card.Name, task.Id, answer);
    }

    public void Dispose() => _http.Dispose();

    private sealed class AuthenticationHandler(
        string project, bool hosted, TokenCredential credential, string? callId, Activity? activity) : DelegatingHandler
    {
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var uri = Settings.ValidateAgentUrl(request.RequestUri!.ToString(), project, hosted);
            if (!request.Headers.Contains("A2A-Version"))
                request.Headers.TryAddWithoutValidation("A2A-Version", "1.0");
            foreach (var header in Settings.Headers(callId, activity)) request.Headers.TryAddWithoutValidation(header.Key, header.Value);
            if (uri.Scheme == "https")
            {
                var token = await credential.GetTokenAsync(new TokenRequestContext(["https://ai.azure.com/.default"]), cancellationToken);
                request.Headers.Authorization = new("Bearer", token.Token);
            }
            var response = await base.SendAsync(request, cancellationToken);
            response.EnsureSuccessStatusCode();
            return response;
        }
    }
}
