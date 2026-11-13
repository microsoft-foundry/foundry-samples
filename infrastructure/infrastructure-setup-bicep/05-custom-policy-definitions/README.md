# Custom Azure Policy Samples for AI Foundry

Azure Policy enables you to put guardrails on resource configurations and enable self-serve resource creation in your organization. This repository shows examples for common scenarios in Azure AI Foundry.

## Available Policies

### 1. Deny Disallowed Connections (`deny-disallowed-connections.json`)
This policy restricts AI Foundry project connections to only allow specific categories. By default, it only allows `CognitiveSearch` connections, but this can be customized via parameters.

**Policy Effect**: Deny

**Scope**: Microsoft.CognitiveServices/accounts/projects/connections

### 2. Deny Key Authentication Connections (`deny-key-auth-connections.json`)
This policy prevents the creation of connections that use key-based authentication methods.

### 3. Audit Enabled VNet Injection (`audit-enabled-vnet-injection.json`)
This policy audits whether VNet injection is properly enabled for AI Foundry resources.

### 4. Restrict Admin-Connected Models to Approved APIM Targets (`deny-disallowed-admin-connected-models.json`)
This policy restricts `ModelGateway` and `ApiManagement` connections to APIM base URLs supplied through the `allowedApimTargets` parameter. Each configured base URL matches the exact URL and paths beneath it, such as `/inference`; enter base URLs without a trailing slash. An empty target list blocks all matching connections.

**Policy Effect**: Configurable (`Deny`, `Audit`, or `Disabled`)

**Scope**: Microsoft.CognitiveServices/accounts/connections and Microsoft.CognitiveServices/accounts/projects/connections

### 5. Deny Spoke Model Deployments (`deny-spoke-model-deployments.json`)
This policy makes a spoke Foundry account consumer-only by preventing creation of `Microsoft.CognitiveServices/accounts/deployments` resources. Spokes can continue consuming models exposed through approved hub gateway connections.

**Policy Effect**: Configurable (`Deny`, `Audit`, or `Disabled`)

**Scope**: Microsoft.CognitiveServices/accounts/deployments

## Deployment

### Prerequisites
- Azure CLI or Azure PowerShell
- Appropriate permissions to create Azure Policy definitions and assignments
- For subscription-level policies: Owner or Resource Policy Contributor role at subscription level
- For management group-level policies: Owner or Resource Policy Contributor role at management group level

### Deploy using Azure CLI

1. **Login to Azure**
   ```bash
   az login
   az account set --subscription "<your-subscription-id>"
   ```

2. **Deploy the policy definition only**
   ```bash
   az deployment sub create \
     --location "East US 2" \
     --template-file main.bicep \
     --parameters main.bicepparam
   ```

3. **Deploy with policy assignment**
   ```bash
   az deployment sub create \
     --location "East US 2" \
     --template-file main.bicep \
     --parameters main.bicepparam \
     --parameters assignPolicy=true
   ```

### Deploy using Azure PowerShell

1. **Login to Azure**
   ```powershell
   Connect-AzAccount
   Set-AzContext -SubscriptionId "<your-subscription-id>"
   ```

2. **Deploy the policy definition only**
   ```powershell
   New-AzSubscriptionDeployment `
     -Location "East US 2" `
     -TemplateFile "main.bicep" `
     -TemplateParameterFile "main.bicepparam"
   ```

3. **Deploy with policy assignment**
   ```powershell
   New-AzSubscriptionDeployment `
     -Location "East US 2" `
     -TemplateFile "main.bicep" `
     -TemplateParameterFile "main.bicepparam" `
     -assignPolicy $true
   ```

### Customization

You can customize the deployment by modifying the parameters in `main.bicepparam`:

- **`policyName`**: Name for the policy definition
- **`allowedCategories`**: Array of allowed connection categories (default: `['CognitiveSearch']`)
- **`assignPolicy`**: Set to `true` to automatically assign the policy to the subscription
- **`assignmentName`**: Name for the policy assignment (if enabled)
- **`assignmentDisplayName`**: Display name for the policy assignment

### Alternative: Deploy using JSON policy definitions directly

If you prefer to use the JSON policy definitions directly without Bicep:

```bash
# Create policy definition
az policy definition create \
  --name "deny-disallowed-connections" \
  --display-name "Foundry Developer Platform Connections Can only be AIService" \
  --description "Foundry Developer Platform Connections Can only be AIService" \
  --rules "deny-disallowed-connections.json" \
  --mode "All"

# Assign the policy (optional)
az policy assignment create \
  --name "deny-disallowed-connections-assignment" \
  --display-name "Assignment: Foundry Developer Platform Connections Can only be AIService" \
  --policy "deny-disallowed-connections" \
  --params '{"allowedCategories":{"value":["CognitiveSearch"]}}'
```

## Policy Testing

After deployment, you can test the policy by attempting to create a connection with a disallowed category:

1. Navigate to your AI Foundry project in the Azure portal
2. Try to create a new connection with a category not in the allowed list
3. The operation should be denied with a policy violation message

## Monitoring and Compliance

- Use Azure Policy compliance dashboard to monitor policy compliance
- Set up alerts for policy violations
- Review policy assignment effects regularly to ensure they meet your governance requirements
