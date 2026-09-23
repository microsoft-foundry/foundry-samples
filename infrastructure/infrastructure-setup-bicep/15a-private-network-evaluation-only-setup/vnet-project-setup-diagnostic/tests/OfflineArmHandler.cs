using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

// No sockets: exercises the actual HttpClient transport against synthetic replies.
public sealed class OfflineArmHandler : HttpMessageHandler
{
    public readonly Queue<int> Codes = new Queue<int>();
    public readonly List<string> Requests = new List<string>();
    public readonly Dictionary<string, string> Bodies = new Dictionary<string, string>();
    public string Body = "{}";
    public string Location;
    public int DelayMilliseconds;
    public bool AuthorizationPresent;
    public int LastCode;
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        Requests.Add(request.Method + " " + request.RequestUri);
        AuthorizationPresent = request.Headers.Authorization?.Scheme == "Bearer"
            && !string.IsNullOrEmpty(request.Headers.Authorization.Parameter);
        if (DelayMilliseconds > 0) await Task.Delay(DelayMilliseconds, cancellationToken);
        LastCode = Codes.Count > 0 ? Codes.Dequeue() : 200;
        var body = Bodies.TryGetValue(request.RequestUri.AbsolutePath, out var value) ? value : Body;
        var response = new HttpResponseMessage((HttpStatusCode)LastCode) { Content = new StringContent(body) };
        if (Location != null) response.Headers.Location = new Uri(Location);
        return response;
    }
}
