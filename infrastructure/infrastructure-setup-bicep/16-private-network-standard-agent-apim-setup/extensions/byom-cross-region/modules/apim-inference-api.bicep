/*
  apim-inference-api.bicep
  ------------------------
  Defines the /inference API on APIM and the chat-completions operation.
  Requests for mockModelName return a deterministic OpenAI-compatible
  response directly from APIM. Every other model request is sent to the
  backend Foundry account with the full policy chain in place:

    1. validate-azure-ad-token  — verifies the inbound token presented by
       the Foundry project's managed identity.

    2. choose — returns the mock response or selects the real backend path.

    3. authentication-managed-identity  — APIM mints its OWN Entra token
       for the backend Foundry resource using APIM's system-assigned MI,
       which is RBAC'd to "Cognitive Services User" on the backend
       account by deploy-time role assignment.

    4. set-backend-service  — rewrites the upstream URL to the backend
       account's privatelink FQDN, which resolves to the private IP of
       the cross-region private endpoint inside the project VNet.

    5. set-header  — emits x-aigw-backend / x-aigw-region /
       x-aigw-route for tracing.

  The API has subscriptionRequired: false because authentication is
  handled by the MI token chain — no APIM subscription keys are needed.
*/

@description('Name of the APIM service the API is created on.')
param apimName string

@description('Tenant ID used to validate inbound Entra tokens from the Foundry project MI.')
param tenantId string = subscription().tenantId

@description('Application (client) ID of the Foundry project managed identity that is allowed to call this API. Must match the appId behind the project MI principalId.')
param projectMiClientId string

@description('Audience the Foundry project requested its token for. Must match the Audience set on the Foundry model connection. Default is the standard Cognitive Services audience.')
param tokenAudience string = 'https://cognitiveservices.azure.com/'

@description('Backend Foundry account name — used to compose the privatelink FQDN.')
param backendAccountName string

@description('Backend Foundry account region — emitted on x-aigw-region trace header.')
param backendRegion string

@description('Project region — emitted on x-aigw-region trace header for visibility into cross-region routing.')
param projectRegion string

@description('Optional model name that APIM handles locally with a deterministic mock response. Empty disables the mock branch.')
param mockModelName string = ''

@description('Inference API path under the APIM gateway. Default = inference, so the full URL is https://<apim>.azure-api.net/inference/deployments/{deploymentName}/chat/completions.')
param apiPath string = 'inference'

// privatelink FQDN that resolves to the cross-region PE inside the VNet.
var backendBaseUrl = 'https://${backendAccountName}.openai.azure.com/openai'

var inboundPolicyXml = '''
<policies>
  <inbound>
    <base />
    <validate-azure-ad-token tenant-id="${TENANT_ID}" header-name="Authorization" failed-validation-httpcode="401" failed-validation-error-message="Unauthorized: Foundry project MI token failed validation.">
      <client-application-ids>
        <application-id>${PROJECT_MI_CLIENT_ID}</application-id>
      </client-application-ids>
      <audiences>
        <audience>${TOKEN_AUDIENCE}</audience>
      </audiences>
    </validate-azure-ad-token>
    <choose>
      <when condition="@(&quot;${MOCK_MODEL_NAME}&quot;.Equals((string)context.Request.MatchedParameters[&quot;deploymentName&quot;], StringComparison.OrdinalIgnoreCase))">
        <set-variable name="mockStream" value="@((bool?)context.Request.Body.As&lt;JObject&gt;(preserveContent: true)[&quot;stream&quot;] == true)" />
        <set-variable name="mockIncludeUsage" value="@((bool?)context.Request.Body.As&lt;JObject&gt;(preserveContent: true)[&quot;stream_options&quot;]?[&quot;include_usage&quot;] == true)" />
        <return-response>
          <set-status code="200" reason="OK" />
          <set-header name="Content-Type" exists-action="override">
            <value>@((bool)context.Variables["mockStream"] ? "text/event-stream" : "application/json")</value>
          </set-header>
          <set-header name="x-aigw-backend" exists-action="override">
            <value>${APIM_NAME} / local-mock</value>
          </set-header>
          <set-header name="x-aigw-region" exists-action="override">
            <value>${PROJECT_REGION}</value>
          </set-header>
          <set-header name="x-aigw-route" exists-action="override">
            <value>mock</value>
          </set-header>
          <set-body>@{
            var completion = new JObject(
              new JProperty("id", "chatcmpl-apim-mock"),
              new JProperty("object", "chat.completion"),
              new JProperty("created", 0),
              new JProperty("model", "${MOCK_MODEL_NAME}"),
              new JProperty("choices", new JArray(new JObject(
                new JProperty("index", 0),
                new JProperty("message", new JObject(
                  new JProperty("role", "assistant"),
                  new JProperty("content", "This is a deterministic mock response generated by Azure API Management.")
                )),
                new JProperty("finish_reason", "stop")
              ))),
              new JProperty("usage", new JObject(
                new JProperty("prompt_tokens", 0),
                new JProperty("completion_tokens", 0),
                new JProperty("total_tokens", 0)
              ))
            );
            if ((bool)context.Variables["mockStream"]) {
              var choice = (JObject)completion["choices"][0];
              var message = choice["message"];
              var usage = completion["usage"];
              completion.Remove("usage");
              completion["object"] = "chat.completion.chunk";
              choice.Remove("message");
              choice["delta"] = message;
              choice["finish_reason"] = JValue.CreateNull();
              var first = completion.ToString(Newtonsoft.Json.Formatting.None);
              choice["delta"] = new JObject();
              choice["finish_reason"] = "stop";
              var events = "data: " + first + "\n\n"
                + "data: " + completion.ToString(Newtonsoft.Json.Formatting.None) + "\n\n";
              if ((bool)context.Variables["mockIncludeUsage"]) {
                completion["choices"] = new JArray();
                completion["usage"] = usage;
                events += "data: " + completion.ToString(Newtonsoft.Json.Formatting.None) + "\n\n";
              }
              return events + "data: [DONE]\n\n";
            }
            return completion.ToString(Newtonsoft.Json.Formatting.None);
          }</set-body>
        </return-response>
      </when>
      <otherwise>
        <set-backend-service base-url="${BACKEND_BASE_URL}" />
        <authentication-managed-identity resource="${TOKEN_AUDIENCE}" />
        <set-header name="x-aigw-backend" exists-action="override">
          <value>${APIM_NAME} / ${BACKEND_ACCOUNT_NAME}</value>
        </set-header>
        <set-header name="x-aigw-region" exists-action="override">
          <value>${PROJECT_REGION} to ${BACKEND_REGION}</value>
        </set-header>
      </otherwise>
    </choose>
  </inbound>
  <backend><base /></backend>
  <outbound>
    <base />
    <set-header name="x-aigw-backend" exists-action="override">
      <value>${APIM_NAME} / ${BACKEND_ACCOUNT_NAME}</value>
    </set-header>
    <set-header name="x-aigw-region" exists-action="override">
      <value>${PROJECT_REGION} to ${BACKEND_REGION}</value>
    </set-header>
    <set-header name="x-aigw-route" exists-action="override">
      <value>real</value>
    </set-header>
  </outbound>
  <on-error><base /></on-error>
</policies>
'''

var renderedPolicy = replace(
  replace(
    replace(
      replace(
        replace(
          replace(
            replace(inboundPolicyXml, '\${TENANT_ID}', tenantId),
            '\${PROJECT_MI_CLIENT_ID}', projectMiClientId
          ),
          '\${TOKEN_AUDIENCE}', tokenAudience
        ),
        '\${BACKEND_BASE_URL}', backendBaseUrl
      ),
      '\${APIM_NAME}', apimName
    ),
    '\${BACKEND_ACCOUNT_NAME}', backendAccountName
  ),
  '\${PROJECT_REGION}', projectRegion
)
var renderedPolicyWithBackendRegion = replace(renderedPolicy, '\${BACKEND_REGION}', backendRegion)
var renderedPolicyFinal = replace(renderedPolicyWithBackendRegion, '\${MOCK_MODEL_NAME}', mockModelName)

resource apim 'Microsoft.ApiManagement/service@2024-05-01' existing = {
  name: apimName
}

resource inferenceApi 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: apim
  name: apiPath
  properties: {
    displayName: 'Foundry inference (AI Gateway)'
    path: apiPath
    protocols: [
      'https'
    ]
    subscriptionRequired: false
    serviceUrl: backendBaseUrl
  }
}

resource chatCompletionsOperation 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: inferenceApi
  name: 'chat-completions'
  properties: {
    displayName: 'Chat Completions'
    method: 'POST'
    urlTemplate: '/deployments/{deploymentName}/chat/completions'
    templateParameters: [
      {
        name: 'deploymentName'
        type: 'string'
        description: 'Model deployment name on the backend Foundry account'
        required: true
      }
    ]
    request: {
      queryParameters: [
        {
          name: 'api-version'
          type: 'string'
          required: false
        }
      ]
    }
  }
}

resource apiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = {
  parent: inferenceApi
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: renderedPolicyFinal
  }
}

output apiId string = inferenceApi.id
output apiName string = inferenceApi.name
