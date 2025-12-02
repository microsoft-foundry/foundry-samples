namespace HelloWorldA365.Services;

using Azure.Core;
using Azure.Identity;
using Microsoft.Identity.Client;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.Json;

public class AgentTokenHelper(ILogger<AgentTokenHelper> logger)
{
    /// <summary>
    /// Performs the three-step agentic user identity token acquisition process
    /// </summary>
    /// <param name="agentAppId">The Agent Application ID</param>
    /// <param name="agentAppInstanceId">The Agent Application Instance ID</param>
    /// <param name="userUpn">The user's UPN</param>
    /// <param name="certificateData">Base64 encoded certificate data</param>
    /// <param name="tenantId">The Azure AD tenant ID</param>
    /// <param name="scopes">The scopes to request for the token</param>
    /// <returns>The final user token for Graph API calls</returns>
    public async Task<string> GetAgenticUserTokenAsync(string agentAppId, string agentAppInstanceId, string userUpn, string certificateData, string tenantId, string[] scopes)
    {
        // Return value will look like:
        // {"token_type":"Bearer","expires_in":3599,"ext_expires_in":3599,"access_token":"eyJ0eX..."}
        try
        {
            var isClientSecret = false;
            var useManagedIdentity = string.IsNullOrEmpty(certificateData);
            X509Certificate2? certificate = null;
            AuthenticationResult? agentTokenResult = null;
            // Parse certificate data

            if (!useManagedIdentity)
            {
                try
                {
                    var certificateBytes = Convert.FromBase64String(certificateData);
                    certificate = X509CertificateLoader.LoadPkcs12(certificateBytes, null);
                }
                catch (Exception ex)
                {
                    logger.LogError(ex, "Error loading certificate from provided data.");
                    isClientSecret = true;
                }
            }


            // FIRST: Get AAD token for AgentAppId
            //
            // client_id : AgentAppId
            // scope : api://AzureAdTokenExchange/.default
            // grant_type : client_credentials
            // fmi_path : AgentAppInstanceId
            // client_secret : Secret
            //
            // However, implementation is changed to use certificate instead of direct secret
            //
            if (isClientSecret)
            {
                agentTokenResult = await GetTokenWithCustomParametersAsync(
                    agentAppId,
                    tenantId,
                    certificateData,
                    ["api://AzureAdTokenExchange/.default"],
                    new Dictionary<string, string> { { "fmi_path", agentAppInstanceId } });
            }
            else
            {
                agentTokenResult = await GetTokenWithCustomParametersAsync(
                    agentAppId,
                    tenantId,
                    ["api://AzureAdTokenExchange/.default"],
                    new Dictionary<string, string> { { "fmi_path", agentAppInstanceId } },
                    certificate);
            }

            // SECOND: Get AAD token for AgentAppInstanceId
            //
            // client_id : AgentAppInstanceId
            // scope : api://AzureAdTokenExchange/.default
            // client_assertion_type : urn:ietf:params:oauth:client-assertion-type:jwt-bearer
            // client_assertion : JWT from FIRST step
            // grant_type : client_credentials
            //
            var instanceApp = ConfidentialClientApplicationBuilder
                .Create(agentAppInstanceId)
                .WithClientAssertion((AssertionRequestOptions _) => Task.FromResult(agentTokenResult.AccessToken))
                .WithAuthority(new Uri($"https://login.microsoftonline.com/{tenantId}"))
                .Build();

            var instanceTokenResult = await instanceApp
                .AcquireTokenForClient(["api://AzureAdTokenExchange/.default"])
                .ExecuteAsync();

            // THIRD: Get combined user token
            //
            // client_id : AgentAppInstanceId
            // scope : Team.ReadBasic.All
            // client_assertion_type : urn:ietf:params:oauth:client-assertion-type:jwt-bearer
            // client_assertion : JWT from FIRST step
            // username : userUpn
            // user_federated_identity_credential : JWT from SECOND step
            // grant_type : user_fic
            //
            var userToken = await GetUserFederatedIdentityTokenAsync(
                agentAppInstanceId,
                tenantId,
                agentTokenResult.AccessToken,
                instanceTokenResult.AccessToken,
                userUpn,
                scopes);

            return userToken;
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Error acquiring agentic user token");
            throw;
        }
    }

    private async Task<AuthenticationResult> GetTokenWithCustomParametersAsync(
        string clientId,
        string tenantId,
        string[] scopes,
        Dictionary<string, string> extraParameters,
        X509Certificate2? certificate)
    {
        using var httpClient = new HttpClient();

        var tokenEndpoint = $"https://login.microsoftonline.com/{tenantId}/oauth2/v2.0/token";

        // Create client assertion JWT using the certificate
        string clientAssertion;
        if (certificate == null)
        {
            var credential = new DefaultAzureCredential();
            var msiTokenResponse = await credential.GetTokenAsync(new TokenRequestContext(new[] { "api://AzureADTokenExchange/.default" }));
            clientAssertion = msiTokenResponse.Token;
        }
        else
        {
            clientAssertion = CreateClientAssertion(clientId, tokenEndpoint, certificate);
        }

        var parameters = new Dictionary<string, string>
        {
            { "client_id", clientId },
            { "scope", string.Join(" ", scopes) },
            { "grant_type", "client_credentials" },
            { "client_assertion_type", "urn:ietf:params:oauth:client-assertion-type:jwt-bearer" },
            { "client_assertion", clientAssertion }
        };

        // Add extra parameters to the request body
        foreach (var param in extraParameters)
        {
            parameters[param.Key] = param.Value;
        }

        var content = new FormUrlEncodedContent(parameters);
        var response = await httpClient.PostAsync(tokenEndpoint, content);

        if (!response.IsSuccessStatusCode)
        {
            var errorContent = await response.Content.ReadAsStringAsync();
            throw new InvalidOperationException($"Failed to acquire token: {errorContent}");
        }

        var responseContent = await response.Content.ReadAsStringAsync();
        var tokenResponse = JsonSerializer.Deserialize<Dictionary<string, object>>(responseContent);

        if (tokenResponse != null && tokenResponse.TryGetValue("access_token", out var accessToken))
        {
            // Create a mock AuthenticationResult for compatibility
            return new MockAuthenticationResult(accessToken?.ToString() ?? throw new InvalidOperationException("Access token is null"));
        }

        throw new InvalidOperationException("Failed to parse access token from response");
    }

    private async Task<AuthenticationResult> GetTokenWithCustomParametersAsync(
        string clientId,
        string tenantId,
        string clientSecret,
        string[] scopes,
        Dictionary<string, string> extraParameters)
    {
        using var httpClient = new HttpClient();

        var tokenEndpoint = $"https://login.microsoftonline.com/{tenantId}/oauth2/v2.0/token";

        var parameters = new Dictionary<string, string>
        {
            { "client_id", clientId },
            { "scope", string.Join(" ", scopes) },
            { "grant_type", "client_credentials" },
            // { "client_assertion_type", "urn:ietf:params:oauth:client-assertion-type:jwt-bearer" },
            { "client_secret", clientSecret }
        };

        // Add extra parameters to the request body
        foreach (var param in extraParameters)
        {
            parameters[param.Key] = param.Value;
        }

        var content = new FormUrlEncodedContent(parameters);
        var response = await httpClient.PostAsync(tokenEndpoint, content);

        if (!response.IsSuccessStatusCode)
        {
            var errorContent = await response.Content.ReadAsStringAsync();
            throw new InvalidOperationException($"Failed to acquire token: {errorContent}");
        }

        var responseContent = await response.Content.ReadAsStringAsync();
        var tokenResponse = JsonSerializer.Deserialize<Dictionary<string, object>>(responseContent);

        if (tokenResponse != null && tokenResponse.TryGetValue("access_token", out var accessToken))
        {
            // Create a mock AuthenticationResult for compatibility
            return new MockAuthenticationResult(accessToken?.ToString() ?? throw new InvalidOperationException("Access token is null"));
        }

        throw new InvalidOperationException("Failed to parse access token from response");
    }

    private async Task<string> GetUserFederatedIdentityTokenAsync(
        string clientId,
        string tenantId,
        string clientAssertion,
        string userFederatedIdentityCredential,
        string username,
        string[] scopes)
    {
        using var httpClient = new HttpClient();

        var tokenEndpoint = $"https://login.microsoftonline.com/{tenantId}/oauth2/v2.0/token";

        var parameters = new Dictionary<string, string>
        {
            { "client_id", clientId },
            { "scope", string.Join(" ", scopes) },
            { "client_assertion_type", "urn:ietf:params:oauth:client-assertion-type:jwt-bearer" },
            { "client_assertion", clientAssertion },
            // { "username", username },
            { "user_federated_identity_credential", userFederatedIdentityCredential },
            { "grant_type", "user_fic" }
        };

        if (username.Contains('@'))
        {
            parameters["username"] = username;
        }
        else
        {
            parameters["user_id"] = username;
        }


        var content = new FormUrlEncodedContent(parameters);
        var response = await httpClient.PostAsync(tokenEndpoint, content);

        if (!response.IsSuccessStatusCode)
        {
            var errorContent = await response.Content.ReadAsStringAsync();
            throw new InvalidOperationException($"Failed to acquire user federated identity token: {errorContent}");
        }

        var responseContent = await response.Content.ReadAsStringAsync();
        var tokenResponse = JsonSerializer.Deserialize<Dictionary<string, object>>(responseContent);

        if (tokenResponse != null && tokenResponse.TryGetValue("access_token", out var accessToken))
        {
            var token = accessToken?.ToString();
            return token ?? throw new InvalidOperationException("Access token is null");
        }

        throw new InvalidOperationException("Failed to parse access token from response");
    }

    private string CreateClientAssertion(string clientId, string audience, X509Certificate2 certificate)
    {
        // This is a simplified JWT creation - in production you might want to use a proper JWT library
        var header = new { alg = "RS256", typ = "JWT", x5t = Convert.ToBase64String(certificate.GetCertHash()) };
        var payload = new
        {
            iss = clientId,
            sub = clientId,
            aud = audience,
            jti = Guid.NewGuid().ToString(),
            nbf = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            exp = DateTimeOffset.UtcNow.AddMinutes(10).ToUnixTimeSeconds()
        };

        var headerJson = JsonSerializer.Serialize(header);
        var payloadJson = JsonSerializer.Serialize(payload);

        var headerBytes = Encoding.UTF8.GetBytes(headerJson);
        var payloadBytes = Encoding.UTF8.GetBytes(payloadJson);

        var headerBase64 = Convert.ToBase64String(headerBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');
        var payloadBase64 = Convert.ToBase64String(payloadBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');

        var signatureInput = $"{headerBase64}.{payloadBase64}";
        var signatureInputBytes = Encoding.UTF8.GetBytes(signatureInput);

        using var rsa = certificate.GetRSAPrivateKey();
        var signature = rsa!.SignData(signatureInputBytes, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        var signatureBase64 = Convert.ToBase64String(signature).TrimEnd('=').Replace('+', '-').Replace('/', '_');

        return $"{headerBase64}.{payloadBase64}.{signatureBase64}";
    }

    private class MockAuthenticationResult(string accessToken) : AuthenticationResult(
        accessToken, false, null,
        DateTimeOffset.UtcNow.AddHours(1), DateTimeOffset.UtcNow.AddHours(1), null, null, null, null,
        Guid.NewGuid());


}