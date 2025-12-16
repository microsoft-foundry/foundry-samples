# Azure API Management Setup Guide for Foundry Agents

> **🎯 Step-by-Step Configuration**  
> This guide shows you how to configure Azure API Management (APIM) to make it ready for use by Foundry Agents as a connection.

## 🏗️ Prerequisites: APIM Instance Setup

Before configuring APIM for Foundry Agents, you need an Azure API Management instance. Choose one of the following options:

### Option 1: 🏢 Use Existing APIM Instance

If you already have an Azure API Management instance (Standard v2 or Premium tier), you can proceed directly to the configuration steps below.

### Option 2: 🔒 Deploy New Private APIM Setup

For a fully secured private network setup, use the Bicep template mentioned in the [Private Network APIM Setup guide](https://github.com/azure-ai-foundry/foundry-samples/tree/main/infrastructure/infrastructure-setup-bicep/16-private-network-standard-agent-apim-setup-preview).

This template provides:
- **🔐 Secure Network Configuration**: Private network setup with Agents BYO VNet
- **🏢 Enterprise-Ready**: Production-ready APIM gateway configuration
- **🛡️ Network Security**: Fully isolated network access for enterprise scenarios

---

## 🚀 Configuration Steps

### Step 1: 📥 Import AI APIs into APIM

To use AI models through APIM with Foundry Agents, you need to import the appropriate APIs into your APIM instance. Use the official Microsoft documentation for guidance:

#### 📚 API Import Resources

| Resource | Description | Link |
|----------|-------------|------|
| **🔗 Azure AI Foundry API in APIM** | Official guide for integrating Azure AI Foundry APIs with Azure API Management | [Azure AI Foundry API](https://learn.microsoft.com/en-in/azure/api-management/azure-ai-foundry-api) |
| **🔗 Azure OpenAI API from Specification** | Official guide for importing Azure OpenAI APIs into Azure API Management from specification | [Azure OpenAI API Import](https://learn.microsoft.com/en-in/azure/api-management/azure-openai-api-from-specification) |

#### 🎯 Choose Your Import Method

- **🏢 Azure AI Foundry API**: Use this if you want to import and manage Azure AI Foundry resources through APIM
- **🤖 Azure OpenAI API**: Use this if you want to import Azure OpenAI services directly from their API specification

### Step 2: 🧪 Test Chat Completions API

Foundry Agents are specifically interested in **chat completions APIs** for AI model interactions. After importing your API:

1. **📍 Navigate to Chat Completions**: In your APIM instance, go to the imported API and locate the **chat completions** operation
2. **🔧 Use APIM Test Feature**: Use the built-in test functionality in APIM to verify the chat completions endpoint works correctly
3. **✅ Verify Response**: Ensure the API returns proper chat completion responses before proceeding with connection setup

> **💡 Important**: Agents will primarily use the chat completions endpoint, so it's crucial to verify this specific operation is working through APIM before creating the Foundry connection.

### Step 3: 🔍 Configure Model Discovery

Once chat completions are working, you need to configure how Foundry Agents will discover available models. You have two options:

#### Option 1: 📋 Static Model List

**✅ Advantages:**
- **🚀 Better Performance**: Agents don't need to call APIM to fetch model details
- **🔧 Simpler Setup**: No additional APIM configuration required
- **💰 Cost Effective**: Reduces API calls to your APIM instance

**📝 Implementation**: Configure the static model list directly in the connection metadata when creating the Foundry connection. No additional APIM setup needed for this approach.

**Example Static Model Configuration**:
```json
{
  "staticModels": [
    {
      "name": "my-gpt-4o-deployment-name",
      "properties": {
        "model": {
          "name": "gpt-4o",
          "version": "2024-11-20",
          "format": "OpenAI"
        }
      }
    },
    {
      "name": "my-gpt-5-deployment-name",
      "properties": {
        "model": {
          "name": "gpt-5", 
          "version": "",
          "format": "OpenAI"
        }
      }
    }
  ]
}
```
- How to set model.format field
1. Use `OpenAI` if you are using an OpenAI model (hosted anywhere OpenAI, AzureOpenAI, Foundry or any other host provider), 
2. Use `OpenAI` for Gemini models if you are using openai chat completions supported gemini endpoint.
3. Use `Anthropic` if you are using an Anthropic model's /message API, use `OpenAI` if you are using Anthropic's /chat/completions API.
4. Use `NonOpenAI` for everything else. 

#### Option 2: 🌐 Dynamic Model Discovery via APIM

**📋 When to Use:**
- Static model configuration is not feasible for your scenario
- You need dynamic model discovery capabilities
- Models change frequently and need real-time discovery

**🔧 Implementation**: Configure list deployments and get deployment APIs in APIM to enable dynamic model discovery.

##### 📝 Dynamic Discovery Setup Instructions

If you choose dynamic discovery, you need to manually add **2 operations** to your API in APIM:

1. **📋 List Deployments Operation** - Returns all available models/deployments
2. **🎯 Get Deployment Operation** - Returns details for a specific model/deployment

##### 🛠️ Adding Get Deployment Operation

1. **📍 Navigate to Your API**: In APIM, go to your imported API (e.g., `agent-aoai`)
2. **➕ Add Operation**: Click **"Add operation"** button
3. **📋 Configure Operation Details**:
   - **Display name**: `Get Deployment By Name`
   - **Name**: `get-deployment-by-name`
   - **URL**: `GET /deployments/{deploymentName}`
   - **Description**: (Optional) Add description for the operation
   - **Tags**: (Optional) Add relevant tags like `xyz`

4. **💾 Save**: Click **"Save"** to create the operation

##### 🔧 Configure Get Deployment Policy

After creating the operation, you need to configure a policy to route the request to the Azure Management endpoint:

1. **🎯 Select the Operation**: Click on the **"Get Deployment"** operation you just created
2. **📝 Edit Policy**: Click on **"Policies"** to edit the policy for this specific operation
3. **⚠️ Ensure Operation-Level Policy**: Make sure the policy is applied to **this operation only**, not at the API level
4. **📋 Add Policy XML**: Replace the policy content with the following XML:

```xml
<!--
    - Policies are applied in the order they appear.
    - Position <base/> inside a section to inherit policies from the outer scope.
    - Comments within policies are not preserved.
-->
<!-- Add policies as children to the <inbound>, <outbound>, <backend>, and <on-error> elements -->
<policies>
    <!-- Throttle, authorize, validate, cache, or transform the requests -->
    <inbound>
        <authentication-managed-identity resource="https://management.azure.com/" />
        <rewrite-uri template="/deployments/{deploymentName}?api-version=2023-05-01" copy-unmatched-params="false" />
        <!--Azure Resource Manager-->
        <set-backend-service base-url="https://management.azure.com/subscriptions/YOUR-SUBSCRIPTION-ID/resourceGroups/YOUR-RESOURCE-GROUP/providers/Microsoft.CognitiveServices/accounts/YOUR-COGNITIVE-SERVICE-ACCOUNT" />
    </inbound>
    <!-- Control if and how the requests are forwarded to services  -->
    <backend>
        <base />
    </backend>
    <!-- Customize the responses -->
    <outbound>
        <base />
    </outbound>
    <!-- Handle exceptions and customize error responses  -->
    <on-error>
        <base />
    </on-error>
</policies>
```

> **🔧 Important**: Update the `set-backend-service` base-url with your actual Azure resource details:
> - Replace `YOUR-SUBSCRIPTION-ID` with your Azure subscription ID
> - Replace `YOUR-RESOURCE-GROUP` with your resource group name  
> - Replace `YOUR-COGNITIVE-SERVICE-ACCOUNT` with your Cognitive Services account name

5. **💾 Save Policy**: Save the policy configuration

This policy will route the get deployment request to the Azure Management endpoint to retrieve deployment details.

##### 🛠️ Adding List Deployments Operation

Now create the second operation for listing all deployments:

1. **📍 Navigate to Your API**: Go back to your API operations list
2. **➕ Add Operation**: Click **"Add operation"** button again
3. **📋 Configure Operation Details**:
   - **Display name**: `List Deployments`
   - **Name**: `list-deployments`
   - **URL**: `GET /deployments`
   - **Description**: (Optional) Add description for the operation
   - **Tags**: (Optional) Add relevant tags

4. **💾 Save**: Click **"Save"** to create the operation

##### 🔧 Configure List Deployments Policy

Configure the policy for the list deployments operation:

1. **🎯 Select the Operation**: Click on the **"List Deployments"** operation you just created
2. **📝 Edit Policy**: Click on **"Policies"** to edit the policy for this specific operation
3. **⚠️ Ensure Operation-Level Policy**: Make sure the policy is applied to **this operation only**
4. **📋 Add Policy XML**: Replace the policy content with the following XML:

```xml
<!--
    - Policies are applied in the order they appear.
    - Position <base/> inside a section to inherit policies from the outer scope.
    - Comments within policies are not preserved.
-->
<!-- Add policies as children to the <inbound>, <outbound>, <backend>, and <on-error> elements -->
<policies>
    <!-- Throttle, authorize, validate, cache, or transform the requests -->
    <inbound>
        <authentication-managed-identity resource="https://management.azure.com/" />
        <rewrite-uri template="/deployments?api-version=2023-05-01" copy-unmatched-params="false" />
        <!--Azure Resource Manager-->
        <set-backend-service base-url="https://management.azure.com/subscriptions/YOUR-SUBSCRIPTION-ID/resourceGroups/YOUR-RESOURCE-GROUP/providers/Microsoft.CognitiveServices/accounts/YOUR-COGNITIVE-SERVICE-ACCOUNT" />
    </inbound>
    <!-- Control if and how the requests are forwarded to services  -->
    <backend>
        <base />
    </backend>
    <!-- Customize the responses -->
    <outbound>
        <base />
    </outbound>
    <!-- Handle exceptions and customize error responses  -->
    <on-error>
        <base />
    </on-error>
</policies>
```

> **🔧 Important**: Update the `set-backend-service` base-url with your actual Azure resource details (same as the get deployment operation).

5. **💾 Save Policy**: Save the policy configuration

This policy will route the list deployments request to the Azure Management endpoint to retrieve all available deployments.

### Step 4: 📋 Gather Connection Details

Once your APIM operations are configured, you need to collect the following details to create your Foundry connection:

#### 🎯 1. Target URL

1. **📍 Navigate to Chat Completions**: Go to your chat completions operation in APIM
2. **🧪 Open Test Tab**: Click on the **"Test"** tab for the chat completions operation
3. **🔍 Check Request URL**: Look at the endpoint URL that **you are hitting** during the test
4. **✂️ Extract Base URL**: Take everything **before** `/chat/completions` or `/deployments/{deploymentId}/chat/completions`

**Examples:**
- If endpoint is: `https://my-apim.azure-api.net/foundry/models/chat/completions` or `https://my-apim.azure-api.net/foundry/models/deployments/gpt-4o/chat/completions`
- Target URL would be: `https://my-apim.azure-api.net/foundry/models`

#### 🔧 2. Inference API Version

1. **📋 Check API Version Parameter**: In the chat completions test, look for an **api-version** parameter
2. **📝 Note the Value**: If an API version is required when hitting chat completions, record that value
3. **📄 Common Values**: Typically values like `2024-02-01`, `2023-12-01-preview`, etc.

#### 🛤️ 3. Deployment in Path

Determine if your chat completions URL includes the deployment name in the path:

- **✅ Set to "true"**: If your URL is like `/deployments/{deploymentName}/chat/completions`
- **❌ Set to "false"**: If your URL is like `/chat/completions` (deployment passed as parameter)

**Examples:**
- `"true"`: `/deployments/gpt-4/chat/completions`
- `"false"`: `/chat/completions?deployment=gpt-4`

> **📝 Note**: These values will be used when creating your APIM connection in Foundry using the Bicep templates.

---

## 📚 Additional Resources

- **🔗 [APIM Connection Objects Documentation](APIM-Connection-Objects.md)** - Read up on more configurations available for APIM connections
- **📖 [APIM README](README.md)** - Next steps for deploying your APIM connections