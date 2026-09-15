# Tools Behind VNet (Terraform)

Deploy agent tools on the private VNet after the base Template 19 infrastructure is up. Each tool runs on the MCP or integration subnet and is accessible to Foundry agents through the DataProxy.

These tools are the Terraform equivalents of the [Bicep 19 tool deployments](../../../infrastructure-setup-bicep/19-private-network-agent-tools/).

## Available Tools

| Tool | Infra Template | App Code | Description |
|------|----------------|----------|-------------|
| **[Azure Function](azure-function/)** | Terraform (`main.tf`) | [Shared](../../../infrastructure-setup-bicep/19-private-network-agent-tools/azure-function-server/) | Python Function App with VNet Integration + storage private endpoints |
| **MCP Server** | CLI (see below) | [Shared](../../../infrastructure-setup-bicep/19-private-network-agent-tools/mcp-http-server/) | Multi-auth MCP server on Container Apps |
| **OpenAPI Server** | CLI (see below) | [Shared](../../../infrastructure-setup-bicep/19-private-network-agent-tools/openapi-server/) | FastAPI calculator on Container Apps |
| **A2A Server** | CLI (see below) | [Shared](../../../infrastructure-setup-bicep/19-private-network-agent-tools/a2a-server/) | Agent-to-Agent server on Container Apps |

## Azure Function (Terraform)

The Azure Function has its own Terraform template since it requires infrastructure (App Service Plan, Storage PEs, VNet Integration subnet). See [azure-function/](azure-function/) for full details.

```bash
cd azure-function
cp example.tfvars terraform.tfvars
# Edit terraform.tfvars with your base deployment outputs
terraform init
terraform plan -var-file="terraform.tfvars" -out=tfplan
terraform apply tfplan
```

## Container App Tools (CLI)

MCP, OpenAPI, and A2A servers run as Container Apps on the MCP subnet. These are deployed via Azure CLI after the base infrastructure is up — no additional Terraform template is needed.

### 1. Build and Push Container Images

Build images from the shared Bicep 19 app code and push to ACR.

```bash
BICEP_TOOLS="../../../infrastructure-setup-bicep/19-private-network-agent-tools"
ACR_NAME="<your-acr-name>"   # e.g. acr0500
```

**Option A — `az acr build` (remote build)**

> **Note**: `az acr build` will fail if your ACR has `defaultAction: Deny` because the
> remote build agent's IP is not in the allowlist. Use Option B instead.

```bash
# OpenAPI server
az acr build --registry $ACR_NAME --image openapi-server:latest $BICEP_TOOLS/openapi-server

# A2A server
az acr build --registry $ACR_NAME --image a2a-server:latest $BICEP_TOOLS/a2a-server

# MCP server (import pre-built image)
az acr import --name $ACR_NAME \
  --source retrievaltestacr.azurecr.io/multi-auth-mcp/api-multi-auth-mcp-env:latest \
  --image multi-auth-mcp:latest
```

**Option B — Local `docker build` + `docker push` (when ACR has firewall rules)**

```bash
az acr login --name $ACR_NAME

# OpenAPI server
docker build -t $ACR_NAME.azurecr.io/openapi-server:latest $BICEP_TOOLS/openapi-server
docker push $ACR_NAME.azurecr.io/openapi-server:latest

# A2A server
docker build -t $ACR_NAME.azurecr.io/a2a-server:latest $BICEP_TOOLS/a2a-server
docker push $ACR_NAME.azurecr.io/a2a-server:latest

# MCP server (import pre-built image — works even with firewall)
az acr import --name $ACR_NAME \
  --source retrievaltestacr.azurecr.io/multi-auth-mcp/api-multi-auth-mcp-env:latest \
  --image multi-auth-mcp:latest
```

### 2. Create Container Apps Environment

```bash
cd ../code
RG_NAME=$(terraform output -raw resource_group_name)
LOCATION="<your-azure-region>"  # must match the base Template 19 deployment

# Construct the MCP subnet ID from the VNet ID (mcp_subnet_id is not a TF output)
VNET_ID=$(terraform output -raw vnet_id)
MCP_SUBNET_ID="${VNET_ID}/subnets/mcp-subnet"  # if using BYO networking, replace with your MCP subnet resource ID

# Create an internal-only Container Apps environment on the MCP subnet
az containerapp env create \
  --resource-group $RG_NAME \
  --name "mcp-env" \
  --location $LOCATION \
  --infrastructure-subnet-resource-id $MCP_SUBNET_ID \
  --internal-only true
```

The environment gets a static IP and a custom domain (e.g. `<name>.<region>.azurecontainerapps.io`). Note these for the DNS step.

```bash
# Get environment domain and static IP
az containerapp env show -g $RG_NAME -n mcp-env \
  --query "{domain:properties.defaultDomain, staticIp:properties.staticIp}" -o table
```

### 3. Deploy Container Apps

Each app needs `--registry-server` and `--registry-identity system` for managed identity-based ACR pull.

> **Note**: The correct flag is `--registry-identity system`, not `--registry-identity system-environment`.

```bash
ACR_NAME="<your-acr-name>"

# OpenAPI server
az containerapp create \
  --resource-group $RG_NAME \
  --name "openapi-server" \
  --environment "mcp-env" \
  --image $ACR_NAME.azurecr.io/openapi-server:latest \
  --registry-server $ACR_NAME.azurecr.io \
  --registry-identity system \
  --target-port 8080 \
  --ingress external \
  --min-replicas 1

# MCP server
az containerapp create \
  --resource-group $RG_NAME \
  --name "mcp-server" \
  --environment "mcp-env" \
  --image $ACR_NAME.azurecr.io/multi-auth-mcp:latest \
  --registry-server $ACR_NAME.azurecr.io \
  --registry-identity system \
  --target-port 8080 \
  --ingress external \
  --min-replicas 1 \
  --env-vars PORT=8080

# A2A server
az containerapp create \
  --resource-group $RG_NAME \
  --name "a2a-server" \
  --environment "mcp-env" \
  --image $ACR_NAME.azurecr.io/a2a-server:latest \
  --registry-server $ACR_NAME.azurecr.io \
  --registry-identity system \
  --target-port 8080 \
  --ingress external \
  --min-replicas 1
```

> **Note on `--ingress external`**: App-level `--ingress external` is external to the app within the Container Apps environment boundary. It does **not** create an internet-reachable endpoint when the environment is `--internal-only` and public network access is disabled. Internal Container Apps environments have no public endpoint — the FQDN only resolves within the VNet.

### 4. Configure Private DNS for Container Apps

Since the environment is `--internal-only`, its FQDNs resolve only inside the VNet. Create a private DNS zone so the DataProxy (and VPN clients) can reach them.

```bash
# Get the environment domain
ENV_DOMAIN=$(az containerapp env show -g $RG_NAME -n mcp-env \
  --query "properties.defaultDomain" -o tsv)
ENV_STATIC_IP=$(az containerapp env show -g $RG_NAME -n mcp-env \
  --query "properties.staticIp" -o tsv)
VNET_NAME=$(az network vnet list -g $RG_NAME --query "[0].name" -o tsv)

# Create private DNS zone for the Container Apps domain
az network private-dns zone create \
  --resource-group $RG_NAME \
  --name $ENV_DOMAIN

# Link DNS zone to VNet
az network private-dns zone vnet-link create \
  --resource-group $RG_NAME \
  --zone-name $ENV_DOMAIN \
  --name "mcp-env-link" \
  --virtual-network $VNET_NAME \
  --registration-enabled false

# Wildcard A record → all *.domain resolves to the environment static IP
az network private-dns record-set a add-record \
  --resource-group $RG_NAME \
  --zone-name $ENV_DOMAIN \
  --record-set-name "*" \
  --ipv4-address $ENV_STATIC_IP
```

After this, Container App FQDNs (e.g. `mcp-server.<domain>`) resolve to the environment's private IP from within the VNet.

## Testing

End-to-end test scripts for all tools are in the [Bicep 19 tests/ directory](../../../infrastructure-setup-bicep/19-private-network-agent-tools/tests/). These tests work with both Bicep and Terraform deployments — they only need the endpoint URLs.

```bash
cd ../../../infrastructure-setup-bicep/19-private-network-agent-tools/tests

# Test Azure Function as OpenAPI tool
python test_azure_function_agents_v2.py --test all --retry 3

# Test MCP tools
python test_mcp_tools_agents_v2.py --test all --retry 3

# Test OpenAPI tools
python test_openapi_tool_agents_v2.py --test all --retry 3
```

## Reference

- [Bicep 19 tools](../../../infrastructure-setup-bicep/19-private-network-agent-tools/) — Shared app code and Bicep templates
- [Base TF 19 deployment](../) — Deploy the base infrastructure first
- [Microsoft Foundry Agent tools documentation](https://learn.microsoft.com/azure/ai-foundry/agents/how-to/virtual-networks)
