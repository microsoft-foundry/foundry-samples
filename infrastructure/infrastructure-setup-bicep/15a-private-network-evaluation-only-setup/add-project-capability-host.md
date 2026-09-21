# Add a project capability host to template 15a

Use this procedure for an existing network-injected [template 15a](README.md) environment, not full template 15.

New template 15a deployments create a project capability host by default. Use this procedure only when the existing project has no capability host, for example after deploying with `deployCapabilityHost=false`.

1. **Set the existing account and project names.**

   Sign in to Azure CLI with deployment permissions and use PowerShell.

   Confirm that the account, project and implicit account capability host are `Succeeded`, and that no project capability host already exists.

   Replace the placeholders with actual deployed names and choose a host name.

   ```powershell
   $subscription = "<subscription-id>"
   $resourceGroup = "<resource-group>"
   $accountName = "<existing-account-name>"
   $projectName = "<existing-project-name>"
   $projectCapHost = "caphostproj"
   ```

2. **Download and deploy the unmodified standalone module.**

   Download the pinned module and pass the account name, project name and chosen host name.

   ```powershell
   $revision = "1dea30fe7da7aeace17a4dd35c6f2499f6cf423c"
   $baseUrl = "https://raw.githubusercontent.com/microsoft-foundry/foundry-samples"
   $path = "infrastructure/infrastructure-setup-bicep/15a-private-network-evaluation-only-setup/modules-network-secured/add-project-capability-host.bicep"
   $module = ".\add-project-capability-host.bicep"

   Invoke-WebRequest "$baseUrl/$revision/$path" -OutFile $module -ErrorAction Stop

   $parameters = @(
     "accountName=$accountName"
     "projectName=$projectName"
     "projectCapHost=$projectCapHost"
   )

   az deployment group validate --resource-group $resourceGroup `
     --template-file $module --parameters $parameters `
     --subscription $subscription
   if ($LASTEXITCODE -ne 0) { throw "Validation failed." }

   az deployment group what-if --resource-group $resourceGroup `
     --template-file $module --parameters $parameters `
     --subscription $subscription
   if ($LASTEXITCODE -ne 0) { throw "What-if failed." }
   ```

   Confirm that the preview creates only the project capability host, then deploy.

   ```powershell
   az deployment group create `
     --name ("add-project-caphost-" + (Get-Date -Format "yyyyMMdd-HHmmss")) `
     --resource-group $resourceGroup --mode Incremental `
     --template-file $module --parameters $parameters `
     --subscription $subscription
   if ($LASTEXITCODE -ne 0) { throw "Deployment failed." }
   ```

   Leave the existing template, networking, model, connections and RBAC unchanged.

3. **Verify the host and automatically populated DataProxy metadata.**

   Query the host and confirm `kind: Agents` and `state: Succeeded`.

   ```powershell
   $projectId = "/subscriptions/$subscription/resourceGroups/$resourceGroup/providers/Microsoft.CognitiveServices/accounts/$accountName/projects/$projectName"

   az rest --method get `
     --url "https://management.azure.com$projectId/capabilityHosts/$projectCapHost`?api-version=2025-04-01-preview" `
     --subscription $subscription `
     --query "{name:name,kind:properties.capabilityHostKind,state:properties.provisioningState}" `
     -o json
   if ($LASTEXITCODE -ne 0) { throw "Host verification failed." }
   ```

   Allow the platform to provision the backing DataProxy Azure Container App and populate these fields automatically.

   | Field | Populated value |
   |---|---|
   | `ContainerApplicationFqdn` | Project DataProxy hostname |
   | `ContainerApplicationIngressIp` | Service-managed ingress IP |
   | `InfraVirtualSubnet` | Infrastructure subnet resource ID |
   | `ContainerAppId` | DataProxy Container App resource ID |

   Do not manually create the DataProxy or patch these fields.

   Verify internal metadata through support-assisted telemetry when required; public ARM responses may not expose it.

   Run a small evaluation from your private-access environment and use route/relay telemetry to confirm MT-VNet execution, rather than assuming it from a passing evaluation.

   Allow cached metadata to expire naturally if an immediate run still uses the previous route.
