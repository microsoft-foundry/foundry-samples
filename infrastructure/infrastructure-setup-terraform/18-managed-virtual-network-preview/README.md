# AI Foundry with Managed VNet - Terraform

This Terraform configuration deploys an Azure AI Foundry environment with complete private networking, including:

- Virtual Network with private endpoints subnet
- Private DNS Zones for complete private connectivity
- **Azure AI Foundry with Project-level Capability Host** for Agents workloads
- Storage Account, Cosmos DB, and AI Search with private endpoints
- **Managed Virtual Network with outbound rules** for secure agent connectivity
- Role assignments with RBAC and ABAC conditions for secure access

## Recent Updates

### December 2024 - Enhanced Capability Host Configuration
- ✅ **Project-level Capability Host**: Aligned with Bicep template architecture
- ✅ **Connection-based Configuration**: Explicit storage, vector store, and thread storage connections
- ✅ **Enhanced RBAC**: Complete role assignments matching Bicep configuration
- ✅ **Post-Deployment RBAC**: Storage Blob Data Owner with ABAC conditions
- ✅ **Cosmos DB Built-in Data Contributor**: Container-level access after capability host creation
- ✅ **VM and Bastion Removed**: Focused deployment on AI Foundry core infrastructure

## Prerequisites

- Azure subscription
- Terraform >= 1.0
- Azure CLI installed and authenticated (`az login`)
- Appropriate Azure RBAC permissions to create resources

## Configuration

1. Copy the example variables file:
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```

2. Edit `terraform.tfvars` with your values:
   - Resource group name (must already exist)
   - Location
   - Network configuration
   - VM credentials (use secure values!)

3. ReSubscription ID
   - Resource group name
   - Location
   - Feature flags (enable_networking, enable_storage, enable_cosmos, enable_aisearch, enable_dns)
   - Network configuration (if enabling networking
### Initial Deployment

1. **Initialize Terraform:**
   ```bash
   terraform init
   ```

2. **Review the planned changes:**
   ```bash
   terraform plan -out=tfplan
   ```

3. **Apply the configuration:**
   ```bash
   terraform apply tfplan
   ```

   The deployment will crprivate endpoints subnet (if enabled)
   - Private DNS zones (if enabled)
   - Storage Account, Cosmos DB, AI Search (if enabled)
   - AI Foundry account with managed network
   - Private endpoints for all services (if networking enabled)
   - **Project Capability Host** with proper role assignments
   - All required RBAC role assignments with proper dependencie
   - **Project Capability Host** with proper role assignments

### Updating Existing Infrastructure

If you already have infrastructure deployed and want to add the new features:

1. **Review changes:**
   ```bash
   terraform plan -out=tfplan
   ```

2. **Apply updates:**
   ```bash
   terraform apply tfplan
   ```

   **Expected Changes:**
   - **New Resources**: 
     - Project Capability Host
     - Network Connection Approver role assignment (AI Foundry account)
     - Cosmos DB Account Reader role assignment
     - Cosmos DB Operator role assignment
     - Storage Blob Data Owner role (with ABAC condition)
     - Cosmos DB Built-in Data Contributor role

3. **Important Notes:**
   - ✅ **Role Propagation**: Role assignments may take 5-10 minutes to take effect
   - ✅ **Dependency Management**: Terraform handles proper sequencing of role assignments
   - ⚠️ **Feature Flags**: Use variables to control which components are deployed

## Post-Deployment Configuration

### Verify Capability Host Configuration

The deployment automatically configures the AI Foundry Project Capability Host with:
- **Storage Connections**: Links to Azure Storage Account
- **Thread Storage Connections**: Links to Cosmos DB for conversation history
- **Vector Store Connections**: Links to AI Search for vector storage

Verify in Azure Portal:
1. Navigate to AI Foundry resource
2. Go to **Projects** > **firstProject**
3. Check **Capability Hosts** section
4. Verify connections are configured

### Role Assignments Summary

The following roles are automatically assigned:

**Before Capability Host Creation:**
- ✅ Storage Blob Data Contributor (Project → Storage)
- ✅ Search Index Data Contributor (Project → AI Search)
- AI Foundry Account Identity:**
- ✅ **Contributor** (Account → Resource Group) - *Network connection approver role*
- ✅ **Storage Blob Data Contributor** (Account → Storage) - *If storage enabled*
- ✅ **Contributor** (Account → Storage) - *Storage management permissions*

**Before Capability Host Creation:**
- ✅ **Storage Blob Data Contributor** (Project → Storage)
- ✅ **Search Index Data Contributor** (Project → AI Search)
- ✅ **Search Service Contributor** (Project → AI Search)
- ✅ **Cosmos DB Account Reader Role** (Project → Cosmos DB)
- ✅ **Cosmos DB Operator** (Project → Cosmos DB) - *Required for capability host*

**After Capability Host Creation:**
- ✅ **Storage Blob Data Owner** (Project → Storage) - *With ABAC condition for agent containers*
- ✅ **Cosmos DB Built-in Data Contributor** (Project → Cosmos DB) - *For thread storage*
If you need additional managed VNet outbound rules (e.g., for Cosmos DB or AI Search), configure them using Azure CLI:

**For Cosmos DB:**
```bash
COSMOS_ID=$(terraform output -raw cosmos_account_id)
AI_FOUNDRY_NAME=$(terraform output -raw ai_foundry_name)
RG_NAME=$(terraform output -raw resource_group_name)
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

az rest --method PUT \
  --uri "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RG_NAME}/providers/Microsoft.CognitiveServices/accounts/${AI_FOUNDRY_NAME}/managedNetworks/default/outboundRules/cosmos-pe-rule?api-version=2025-10-01-preview" \
  --body '{
    "properties": {
      "type": "PrivateEndpoint",
      "destination": {
        "serviceResourceId": "'${COSMOS_ID}'",
        "subresourceTarget": "Sql"
      },
      "category": "UserDefined"
    }
  }'
```

**For AI Search:**
```bash
SEARCH_ID=$(terraform output -raw aisearch_id)

az rest --method PUT \
  --uri "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RG_NAME}/providers/Microsoft.CognitiveServices/accounts/${AI_FOUNDRY_NAME}/managedNetworks/default/outboundRules/search-pe-rule?api-version=2025-10-01-preview" \
  --body '{
    "properties": {
      "type": "PrivateEndpoint",
      "destination": {
        "serviceResourceId": "'${SEARCH_ID}'",
        "subresourceTarget": "searchService"
      },
      "category": "UserDefined"
    }
  }'
```

**Note:** The storage outbound rule is already created by Terraform. Additional rules are only needed for specific scenarios.

## Connecting to the VM
```
┌─────────────────────────────────────────────────────────┐
│                   Virtual Network                        │
│                    10.0.0.0/16                          │
│                                                          │
│  ┌────────────────────────────────────────────┐        │
│  │  Private Endpoints Subnet (10.0.1.0/24)   │        │
│  │  - AI Foundry Private Endpoint             │        │
│  │  - Storage Blob Private Endpoint           │        │
│  │  - Storage File Private Endpoint           │        │
│  │  - Storage Table Private Endpoint          │        │
│  │  - Storage Queue Private Endpoint          │        │
│  │  - Cosmos DB Private Endpoint              │        │
│  │  - AI Search Private Endpoint              │        │
│  └────────────────────────────────────────────┘        │
│                                                          │
│  ┌────────────────────────────────────────────┐        │
│  │  VM Subnet (10.0.2.0/24)                  │        │
│  │  - Windows Server 2025 VM                 │        │
│  │    + System Managed Identity              │        │
│  │    + AADLoginForWindows Extension         │        │
│  │    + No Public IP                         │        │
│  └────────────────────────────────────────────┘        │
│                                                          │
│  ┌────────────────────────────────────────────┐        │
│  │  Azure Bastion Subnet (10.0.3.0/26)       │        │
│  │  - Azure Bastion Standard                 │        │
│  │    + Tunneling Enabled                    │        │
│  │    + File Copy Enabled                    │        │
│  │    + IP Connect Enabled                   │        │
│  └────────────────────────────────────────────┘        │
│                                                          │
└─────────────────────────────────────────────────────────┘
                        │
                        │ Private Endpoints
                        ▼
        ┌───────────────────────────────┐
        │   Azure AI Foundry            │
        │   + System Managed Identity   │
        │   + Managed Network V2        │
        │   + Project: firstProject     │
        │     - Capability Host         │
        │     - Storage Connection      │
        │     - Cosm(Optional)                             │
│                                                          │
│  ┌────────────────────────────────────────────┐        │
│  │  Private Endpoints Subnet (10.0.1.0/24)   │        │
│  │  - AI Foundry Private Endpoint             │        │
│  │  - Storage Blob Private Endpoint           │        │
│  │  - Storage File Private Endpoint           │        │
│  │  - Storage Table Private Endpoint          │        │
│  │  - Storage Queue Private Endpoint          │        │
│  │  - Cosmos DB Private Endpoint              │        │
│  │  - AI Search Private Endpoint              │        │
│  └────────────────────────────────────────────┘        │
│                                                          │
└─────────────────────────────────────────────────────────┘
                        │
                        │ Private Endpoints
                        ▼
        ┌───────────────────────────────┐
        │   Azure AI Foundry            │
        │   + System Managed Identity   │
        │   + Managed Network V2        │
        │   + Project: firstProject     │
        │     - Capability Host         │
        │     - Storage Connection      │
        │     - Cosmos DB Connection    │
        │     - AI Search Connection    │
        └───────────────────────────────┘
                        │
                        │ Managed Outbound (PE)
                        ▼
        ┌───────────────────────────────┐
        │   Storage Account             │
        │   (Private Access Only)       │
        │   + Blob, File, Table, Queue  │
        └───────────────────────────────┘
                        
        ┌───────────────────────────────┐
        │   Cosmos DB for NoSQL         │
        │   (Thread Storage)            │
        └───────────────────────────────┘
        
        ┌───────────────────────────────┐
        │   AI Search                   │
        │   (Vector Store)              │
        └───────────────────────────────┘
```

## Key Features

| Feature | This Configuration |
|---------|-------------------|
| Capability Host Level | ✅ **Project** |
| Connection References | ✅ **Explicit** |
| AI Foundry Account RBAC | ✅ **Network Connection Approver + Storage Permissions** |
| Project Identity RBAC | ✅ **Complete role assignments** |
| Cosmos DB RBAC | ✅ **Account Reader + Operator + Built-in Contributor** |
| Storage RBAC | ✅ **Blob Contributor + Blob Owner (ABAC)** |
| Agent Workloads | ✅ **Ready** |
| Private Networking | ✅ **Optional (via feature flags)** |
| Modular Deployment | ✅ **Feature flags for all components**
   az vm extension list --resource-group <rg> --vm-name <vm-name>
   ```
2. Check role assignment exists:
   ```bash
   az role assignment list --assignee <your-user-id> --scope <vm-id>
   ```
3. Wait 5-10 minutes for role propagation

### Capability Host Connection Issues
1. Verify connections exist in Azure Portal: AI Foundry → Projects → Connections
2. Check role assignments are complete:
   ```bash
   terraform output
   az role assignment list --scope <storage-id>
   ```
3. Ensure Cosmos DB Operator role was assigned before capability host creation

```

## Cleanup

To destroy all resources:

```bash
terraform destroy
```

Confirm by typing `yes` when prompted.

## Security Considerations

- All PaaS services have public network access disabled
- VM has no public IP address - access only via Bastion
- Storage account is only accessible via private endpoints
- AI Foundry uses managed network with controlled outbound rules
- All DNS resolution happens via private DNS zones
- Managed identity with RBAC for service-to-service authentication

## Files

- `providers.tf` - Provider configuration
- `variables.tf` - Input variables
- `main.tf` - Data sources and locals
- `network.tf` - VNet and private endpoints subnet
- `dns.tf` - Private DNS zones and VNet links
- `storage.tf` - Storage account and private endpoints (blob, file, table, queue)
- `cosmos.tf` - Cosmos DB account and private endpoint
- `aisearch.tf` - AI Search service and private endpoint
- `ai-foundry.tf` - AI Foundry account, project, capability host, connections, and complete

## Notes
Uses project-level capability host matching Bicep template
- **Workspace ID Formatting**: Automatically extracts and formats project workspace ID for ABAC conditions
- **Role Assignment Timing**: 
  - Network Connection Approver assigned to AI Foundry account identity
  - Cosmos DB Operator and Account Reader must be assigned **before** capability host creation
  - Storage Blob Data Owner and Cosmos Built-in Contributor assigned **after**
- **ABAC Conditions**: Storage role includes condition for agent-specific containers
- **Role Propagation**: RBAC assignments may take 5-10 minutes to fully propagate
- **Managed Network**: Uses Managed Virtual Network V2 with AllowInternetOutbound isolation mode
- **Feature Flags**: All major components can be enabled/disabled via variables
- **Modular Design**: Deploy only what you need using feature flags
- Azure resources: Check Azure Portal for resource status
- Private connectivity: Verify DNS resolution from the VM using `nslookup`
- Managed network: Use Azure Portal or REST API to verify outbound rules
 (when networking enabled)
- Storage account is only accessible via private endpoints (when networking enabled)
- AI Foundry uses managed network with controlled outbound rules
- All DNS resolution happens via private DNS zones (when DNS enabled)
- Managed identity with RBAC for service-to-service authentication
- ABAC conditions limit Storage Blob Data Owner to specific container patterns
- Network Connection Approver role enables AI Foundry to manage connections
- No VM or Bastion included - focused on AI Foundry infrastructur