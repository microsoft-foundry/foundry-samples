# Azure API Management Setup Guide for Foundry Agents

> **⚠️ IMPORTANT: Test Your Configuration First**  
> **Before executing your APIM connection bicep in Azure AI Foundry, [jump to the validation section](#-connection-validation) to test your configuration and ensure it works with the Agents SDK.**
> 
> **🆘 Need Help?** If you encounter issues, check the [Troubleshooting Guide](./troubleshooting-guide.md) for solutions and use the validation script mentioned below.

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

### Step 2.5: 🔐 Configure Managed Identity Authentication (Optional)

If you want to use **Azure Managed Identity authentication** instead of APIM subscription keys, you need to configure APIM to validate and forward Entra ID tokens.

#### 🔍 How Authentication Flow Works

The policy checks if a subscription key is present (`context.Subscription`). If a **valid APIM subscription key exists**, it's used for authentication. If **no subscription key is provided**, the policy validates the Authorization header token, ensuring it's a valid Entra ID token with the correct audience (`https://cognitiveservices.azure.com`).

> **⚠️ Important**: To enable this dual authentication mode, you must **disable the "Subscription required" setting** on your APIM API to allow requests without subscription keys.

#### 🛠️ Setup Instructions

Add these policies to your APIM API's **inbound** section:

1. **📍 Navigate to Your API**: Go to your imported API in APIM (e.g., `agent-aoai`)
2. **📝 Edit API-Level Policy**: Click on **"All operations"** and then **"Policies"**
3. **📋 Add Authentication Policies**: Add the following XML to the `<inbound>` section:

```xml
<inbound>
    <choose>
        <when condition="@(context.Subscription == null)">
            <!-- Token authentication - validate token -->
            <validate-azure-ad-token 
                tenant-id="YOUR-TENANT-ID" 
                header-name="Authorization" 
                failed-validation-httpcode="401" 
                failed-validation-error-message="Unauthorized. Valid Entra token is required." 
                output-token-variable-name="jwt">
                <audiences>
                    <audience>https://cognitiveservices.azure.com</audience>
                </audiences>
                <required-claims>
                    <claim name="xms_mirid" match="any">
                        <value>/subscriptions/YOUR-SUBSCRIPTION-ID/resourcegroups/YOUR-RESOURCE-GROUP/providers/Microsoft.CognitiveServices/accounts/YOUR-FOUNDRY-ACCOUNT/projects/YOUR-FOUNDRY-PROJECT</value>
                    </claim>
                </required-claims>
            </validate-azure-ad-token>
        </when>
        <otherwise>
            <!-- API Key authentication - set backend-id -->
            <set-backend-service id="apim-generated-policy" backend-id="YOUR-BACKEND-ID" />
        </otherwise>
    </choose>
    <base />
</inbound>
```

> **🔧 Required Configuration**:
> - **`YOUR-TENANT-ID`**: Your Azure Entra ID tenant ID
> - **`YOUR-BACKEND-ID`**: Your APIM backend ID for Cognitive Services
> - **`YOUR-SUBSCRIPTION-ID`**: Your Azure subscription ID
> - **`YOUR-RESOURCE-GROUP`**: Resource group name (case-sensitive)
> - **`YOUR-FOUNDRY-ACCOUNT`**: Your Foundry account name
> - **`YOUR-FOUNDRY-PROJECT`**: Your Foundry project name

#### 🔒 Understanding Required Claims

The `<required-claims>` section validates that tokens come from your specific Foundry project, preventing unauthorized access from other projects or accounts.


4. **💾 Save Policy**: Save the policy configuration

#### 🔍 How It Works

- **Token Flow**: When no subscription key is provided, validates the Entra ID token at the API level. Backend routing is configured at the operation level (see completions and management operations below)
- **API Key Flow**: When an APIM subscription key is provided, requests are routed using the configured backend-id

#### 🎯 Configure Chat Completions Operation

For the **chat completions operation**, you need to validate the token and configure backend routing:

1. **📍 Navigate to Completions Operation**: Go to your chat completions operation in APIM
2. **📝 Edit Operation-Level Policy**: Click on **"Policies"** for this specific operation
3. **📋 Add Token Validation and Backend Configuration**: Add the following XML to the `<inbound>` section:

```xml
<inbound>
    <base />
    <set-backend-service base-url="YOUR-COGNITIVE-SERVICES-URL" />
</inbound>
```

> **🔧 Important**: Replace `YOUR-COGNITIVE-SERVICES-URL` with your Cognitive Services endpoint URL (e.g., `https://your-account.openai.azure.com`)

4. **💾 Save Policy**: Save the policy configuration

**🔍 How This Works**: For token-based requests (already validated at API level), this sets the backend URL and forwards the token to the Cognitive Services backend for end-to-end managed identity authentication. For Api key based requests, the API level policy sets the backend id, which configures APIM to use its own identity on this call.


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
3. Use `OpenAI` if your Gateway's chat completion endpoint is fully compatible with OpenAI API contract (supports tools, tool_choice, reasoning_effort, response_format etc.).
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

> **📝 Note**: The setup below is specific to using Azure OpenAI or Azure Foundry AI Service resource as APIM backend. For any other backend services, ensure you properly setup and test it out, otherwise use static discovery for simplicity.

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

1. **📋 Check API Version Parameter**: In the chat completions test, look for an **api-version** parameter. If not required, this will need to be kept an empty string.
2. **📝 Note the Value**: If an API version is required when hitting chat completions, record that value
3. **📄 Common Values**: Typically values like `2024-02-01`, `2023-12-01-preview` etc.

#### 🛤️ 3. Deployment in Path

Determine if your chat completions URL includes the deployment name in the path:

- **✅ Set to "true"**: If your URL is like `/deployments/{deploymentName}/chat/completions`
- **❌ Set to "false"**: If your URL is like `/chat/completions` (deployment passed in chat completions request body as `model` field)

**Examples:**
- `"true"`: `/deployments/gpt-4/chat/completions`
- `"false"`: `/chat/completions`

> **📝 Note**: These values will be used when creating your APIM connection in Foundry using the Bicep templates.

---

## ✅ Connection Validation

Before creating your APIM connection in Azure AI Foundry, follow these steps to validate your configuration:

### 1. **Choose your parameter file** based on your APIM setup:
   - `samples/parameters-static-models.json` - For APIM with predefined static models
   - `samples/parameters-dynamic-discovery.json` - For APIM with dynamic model discovery
   - `samples/parameters-custom-auth-config.json` - For custom authentication headers
   - `samples/parameters-custom-headers.json` - For custom headers configuration

### 2. **Update the parameter file** with your actual configuration values
   Use the rest of this guide to decide the correct parameter values for your APIM setup.

### 3. **Test your configuration** using the validation script:

First, install the required Python package:
```bash
pip install requests
```

Then run the validation script (use ONE of the authentication methods):
```bash
# For ApiKey authentication (uses APIM subscription key):
python3 test_apim_connection.py --params samples/YOUR_CHOSEN_FILE.json --api-key YOUR_APIM_SUBSCRIPTION_KEY --deployment-name YOUR_DEPLOYMENT --target-url YOUR_APIM_BASE_URL

# For ProjectManagedIdentity authentication (uses Authorization header):
python3 test_apim_connection.py --params samples/YOUR_CHOSEN_FILE.json --authorization "Bearer YOUR_TOKEN" --deployment-name YOUR_DEPLOYMENT --target-url YOUR_APIM_BASE_URL
```

**Example:**
```bash
# ApiKey auth example
python3 test_apim_connection.py --params samples/parameters-static-models.json --api-key abc123def456 --deployment-name gpt-4o --target-url https://my-apim.azure-api.net/foundry/models

# ProjectManagedIdentity auth example (with Bearer token)
python3 test_apim_connection.py --params samples/parameters-static-models.json --authorization "Bearer eyJ0eXAi..." --deployment-name gpt-4o --target-url https://my-apim.azure-api.net/foundry/models
```

This validation script tests:
- ✅ Parameter validation and APIM-specific configuration parsing
- ✅ Model discovery (static models or dynamic discovery via APIM)
- ✅ APIM subscription key authentication and API access
- ✅ Chat completions endpoint functionality through APIM
- ✅ Provider format compatibility (AzureOpenAI vs OpenAI responses)

**Testing saves time and prevents deployment issues! This validation ensures your APIM connection will work correctly when used with the Agents SDK.**

**Key APIM-Specific Validations:**
- APIM subscription key authentication
- APIM gateway URL construction and accessibility
- APIM API policies and routing functionality
- Model deployment access through APIM policies

---

## 📚 Additional Resources

- **🔗 [APIM Connection Objects Documentation](APIM-Connection-Objects.md)** - Read up on more configurations available for APIM connections
- **📖 [APIM README](README.md)** - Next steps for deploying your APIM connections