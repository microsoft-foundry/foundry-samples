#:package Azure.Identity@1.17.1
#:package OpenAI@2.14.0
#:property CopyLocalLockFileAssemblies=true

using System.ClientModel;
using System.ClientModel.Primitives;
using System.Text.Json;
using Azure.Identity;
using OpenAI;
using OpenAI.Responses;

#pragma warning disable OPENAI001

try
{
    var tenantId = Required("AZURE_TENANT_ID");
    var blueprintId = Required("GREETING_BLUEPRINT_ID");
    var clientId = Required("GREETING_CLIENT_ID");
    var endpoint = new Uri(Required("GREETING_AGENT_ENDPOINT"));
    if (endpoint.Scheme != Uri.UriSchemeHttps)
    {
        throw new InvalidOperationException("The agent endpoint must use HTTPS.");
    }

    var credential = new DeviceCodeCredential(new DeviceCodeCredentialOptions
    {
        TenantId = tenantId,
        ClientId = clientId
    });
    var client = new ResponsesClient(
        new BearerTokenPolicy(credential, $"api://{blueprintId}/access_agent"),
        new ResponsesClientOptions { Endpoint = endpoint });
    CreateResponseOptions options = new();
    options.InputItems.Add(ResponseItem.CreateUserMessageItem(
        "Call the greet tool once and report its greeting and invocation ID verbatim."));
    ClientResult<ResponseResult> result = await client.CreateResponseAsync(options);
    if (FindConsentLink(result) is { } consentUri)
    {
        Console.Error.WriteLine($"The MCP tool needs your consent. Open this link, sign in as the same user, and review the requested permission: {consentUri}");
        Console.Error.WriteLine("After consenting, run the client again.");
        return 2;
    }
    ResponseResult response = result;
    var text = response.GetOutputText();
    if (string.IsNullOrWhiteSpace(text))
    {
        throw new InvalidOperationException("The agent did not return an answer.");
    }
    Console.WriteLine(text);
    return 0;
}
catch (AuthenticationFailedException error)
{
    Console.Error.WriteLine($"Sign-in failed: {error.Message}");
    return 1;
}
catch (ClientResultException error)
{
    Console.Error.WriteLine($"The agent request failed: HTTP {error.Status}. {error.Message}");
    return 1;
}
catch (Exception error) when (error is InvalidOperationException or ArgumentException)
{
    Console.Error.WriteLine($"Sample failed: {error.Message}");
    return 1;
}

static string Required(string name) =>
    Environment.GetEnvironmentVariable(name) is { Length: > 0 } value
        ? value
        : throw new InvalidOperationException($"Set {name} before running the client.");

static Uri? FindConsentLink(ClientResult<ResponseResult> result)
{
    using var document = JsonDocument.Parse(result.GetRawResponse().Content.ToString());
    if (!document.RootElement.TryGetProperty("output", out var output) ||
        output.ValueKind != JsonValueKind.Array)
    {
        return null;
    }
    foreach (var item in output.EnumerateArray())
    {
        if (item.ValueKind != JsonValueKind.Object ||
            !item.TryGetProperty("type", out var type) ||
            type.GetString() != "oauth_consent_request")
        {
            continue;
        }
        if (!item.TryGetProperty("consent_link", out var link) ||
            link.ValueKind != JsonValueKind.String ||
            !Uri.TryCreate(link.GetString(), UriKind.Absolute, out var consentUri) ||
            consentUri.Scheme != Uri.UriSchemeHttps)
        {
            throw new InvalidOperationException("The agent requested MCP consent without a valid HTTPS consent link.");
        }
        return consentUri;
    }
    return null;
}
