#!/bin/bash
# Docker migration runner with automatic token authentication (Unix/Linux/macOS)
# This script handles token generation and Docker execution automatically
# REQUIRES: --production-resource, --production-subscription, --production-tenant

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

echo -e "${BLUE}🐳 Running v1 to v2 assistant migration in DOCKER with automatic authentication${NC}"
echo "======================================================================================"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running. Please start Docker and try again.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker is running${NC}"

# Check if Azure CLI is available and authenticated
if ! command -v az &> /dev/null; then
    echo -e "${RED}❌ Azure CLI not found. Install from https://docs.microsoft.com/cli/azure/${NC}"
    exit 1
fi

# Check Azure CLI authentication
if ! az account show > /dev/null 2>&1; then
    echo -e "${RED}❌ Azure CLI not authenticated. Run 'az login' first.${NC}"
    exit 1
fi

ACCOUNT_INFO=$(az account show --query "user.name" -o tsv 2>/dev/null)
echo -e "${GREEN}✅ Azure CLI authenticated as: ${ACCOUNT_INFO}${NC}"

# Parse arguments to check for project connection string and production parameters
NEED_BETA_VERSION="false"
SOURCE_TENANT=""
PRODUCTION_RESOURCE=""
PRODUCTION_SUBSCRIPTION=""
PRODUCTION_TENANT=""

for arg in "$@"; do
    if [[ "$arg" == *"--project-connection-string"* ]]; then
        NEED_BETA_VERSION="true"
    elif [[ "$arg" == --source-tenant* ]]; then
        SOURCE_TENANT="${arg#*=}"
        if [ -z "$SOURCE_TENANT" ]; then
            shift
            SOURCE_TENANT="$1"
        fi
    elif [[ "$arg" == --production-resource* ]]; then
        PRODUCTION_RESOURCE="${arg#*=}"
        if [ -z "$PRODUCTION_RESOURCE" ]; then
            shift
            PRODUCTION_RESOURCE="$1"
        fi
    elif [[ "$arg" == --production-subscription* ]]; then
        PRODUCTION_SUBSCRIPTION="${arg#*=}"
        if [ -z "$PRODUCTION_SUBSCRIPTION" ]; then
            shift
            PRODUCTION_SUBSCRIPTION="$1"
        fi
    elif [[ "$arg" == --production-tenant* ]]; then
        PRODUCTION_TENANT="${arg#*=}"
        if [ -z "$PRODUCTION_TENANT" ]; then
            shift
            PRODUCTION_TENANT="$1"
        fi
    fi
done

# Validate required production parameters
if [ -z "$PRODUCTION_RESOURCE" ] || [ -z "$PRODUCTION_SUBSCRIPTION" ] || [ -z "$PRODUCTION_TENANT" ]; then
    echo -e "${RED}❌ Missing required production parameters!${NC}"
    echo ""
    echo "REQUIRED parameters:"
    echo "  --production-resource <resource-name>       (e.g., nextgen-eastus)"
    echo "  --production-subscription <subscription-id> (e.g., b1615458-c1ea-49bc-8526-cafc948d3c25)"
    echo "  --production-tenant <tenant-id>            (e.g., 33e577a9-b1b8-4126-87c0-673f197bf624)"
    echo ""
    echo "Example:"
    echo "  ./run-migration-docker-auth.sh --use-api \\"
    echo "    --source-tenant 72f988bf-86f1-41af-91ab-2d7cd011db47 \\"
    echo "    --production-resource nextgen-eastus \\"
    echo "    --production-subscription b1615458-c1ea-49bc-8526-cafc948d3c25 \\"
    echo "    --production-tenant 33e577a9-b1b8-4126-87c0-673f197bf624 \\"
    echo "    asst_wBMH6Khnqbo1J7W1G6w3p1rN"
    exit 1
fi

# Production parameters are required - always in production mode
PRODUCTION_MODE="true"

# Generate source token
if [ -n "$SOURCE_TENANT" ]; then
    echo -e "${BLUE}🔑 Generating source Azure AI token for tenant: ${SOURCE_TENANT}${NC}"
    SOURCE_TOKEN=$(az account get-access-token --tenant "$SOURCE_TENANT" --scope https://ai.azure.com/.default --query accessToken -o tsv 2>/dev/null)
    
    if [ $? -ne 0 ] || [ -z "$SOURCE_TOKEN" ] || [ ${#SOURCE_TOKEN} -lt 100 ]; then
        echo -e "${RED}❌ Failed to generate source token or token is invalid${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Source token generated successfully (length: ${#SOURCE_TOKEN})${NC}"
else
    echo -e "${BLUE}🔑 Generating Azure AI token...${NC}"
    SOURCE_TOKEN=$(az account get-access-token --scope https://ai.azure.com/.default --query accessToken -o tsv 2>/dev/null)
    
    if [ $? -ne 0 ] || [ -z "$SOURCE_TOKEN" ] || [ ${#SOURCE_TOKEN} -lt 100 ]; then
        echo -e "${RED}❌ Failed to generate token or token is invalid${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Token generated successfully (length: ${#SOURCE_TOKEN})${NC}"
fi

# Generate production token (REQUIRED)
PRODUCTION_TOKEN=""
echo -e "${BLUE}🏭 Production v2 API Configuration:${NC}"
echo -e "${BLUE}   🎯 Resource: ${PRODUCTION_RESOURCE}${NC}"
echo -e "${BLUE}   📋 Subscription: ${PRODUCTION_SUBSCRIPTION}${NC}"
echo -e "${BLUE}   🔐 Tenant: ${PRODUCTION_TENANT}${NC}"
echo -e "${BLUE}🔐 Switching to production tenant: ${PRODUCTION_TENANT}${NC}"
    
# Switch to production tenant
CURRENT_TENANT=$(az account show --query "tenantId" -o tsv 2>/dev/null)
if [ "$CURRENT_TENANT" = "$PRODUCTION_TENANT" ]; then
    echo -e "${GREEN}✅ Already authenticated with production tenant${NC}"
else
    echo -e "${YELLOW}🔄 Switching from tenant ${CURRENT_TENANT} to ${PRODUCTION_TENANT}${NC}"
    az login --tenant "$PRODUCTION_TENANT" --only-show-errors 2>&1
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Failed to authenticate with production tenant${NC}"
        exit 1
    fi
fi

echo -e "${BLUE}🔑 Generating production Azure AI token...${NC}"
PRODUCTION_TOKEN=$(az account get-access-token --scope https://ai.azure.com/.default --query accessToken -o tsv 2>/dev/null)

if [ $? -ne 0 ] || [ -z "$PRODUCTION_TOKEN" ] || [ ${#PRODUCTION_TOKEN} -lt 100 ]; then
    echo -e "${RED}❌ Failed to generate production token or token is invalid${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Production token generated successfully (length: ${#PRODUCTION_TOKEN})${NC}"

# Switch back to source tenant if different (for reading v1 assistants)
if [ -n "$SOURCE_TENANT" ] && [ "$SOURCE_TENANT" != "$PRODUCTION_TENANT" ]; then
    echo -e "${BLUE}🔄 Switching back to source tenant for reading operations: ${SOURCE_TENANT}${NC}"
    az login --tenant "$SOURCE_TENANT" --only-show-errors 2>&1
    if [ $? -ne 0 ]; then
        echo -e "${YELLOW}⚠️  Warning: Could not switch back to source tenant${NC}"
    fi
elif [ "$CURRENT_TENANT" != "$PRODUCTION_TENANT" ]; then
    echo -e "${BLUE}🔄 Switching back to original tenant for reading operations${NC}"
    az login --tenant "$CURRENT_TENANT" --only-show-errors 2>&1
    if [ $? -ne 0 ]; then
        echo -e "${YELLOW}⚠️  Warning: Could not switch back to original tenant${NC}"
    fi
fi

# Check if image exists
if ! docker image inspect v1-to-v2-migration > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Docker image 'v1-to-v2-migration' not found.${NC}"
    echo -e "${BLUE}🔨 Building Docker image...${NC}"
    docker build -t v1-to-v2-migration .
fi

# Load environment variables from .env if it exists
if [ -f .env ]; then
    echo -e "${GREEN}✅ Loading environment variables from .env file${NC}"
    export $(cat .env | grep -v '^#' | grep -v '^$' | xargs)
else
    echo -e "${YELLOW}⚠️  No .env file found. Using environment variables or defaults.${NC}"
fi

# Run the container with token authentication
echo -e "${GREEN}🏃 Running migration in Docker container with token authentication...${NC}"
echo -e "${YELLOW}Arguments: $@${NC}"

# Build Docker run command with required production tokens
DOCKER_CMD="docker run --rm -it \
    --network host \
    -e DOCKER_CONTAINER=true \
    -e LOCAL_HOST=host.docker.internal:5001 \
    -e COSMOS_CONNECTION_STRING=\"$COSMOS_CONNECTION_STRING\" \
    -e COSMOS_DB_CONNECTION_STRING=\"$COSMOS_DB_CONNECTION_STRING\" \
    -e COSMOS_DB_DATABASE_NAME=\"$COSMOS_DB_DATABASE_NAME\" \
    -e COSMOS_DB_CONTAINER_NAME=\"$COSMOS_DB_CONTAINER_NAME\" \
    -e ASSISTANT_API_BASE=\"$ASSISTANT_API_BASE\" \
    -e ASSISTANT_API_VERSION=\"$ASSISTANT_API_VERSION\" \
    -e ASSISTANT_API_KEY=\"$ASSISTANT_API_KEY\" \
    -e PROJECT_ENDPOINT_URL=\"$PROJECT_ENDPOINT_URL\" \
    -e PROJECT_CONNECTION_STRING=\"$PROJECT_CONNECTION_STRING\" \
    -e V2_API_BASE=\"$V2_API_BASE\" \
    -e V2_API_VERSION=\"$V2_API_VERSION\" \
    -e V2_API_KEY=\"$V2_API_KEY\" \
    -e AZURE_TENANT_ID=\"$AZURE_TENANT_ID\" \
    -e AZURE_CLIENT_ID=\"$AZURE_CLIENT_ID\" \
    -e AZURE_CLIENT_SECRET=\"$AZURE_CLIENT_SECRET\" \
    -e AZURE_SUBSCRIPTION_ID=\"$AZURE_SUBSCRIPTION_ID\" \
    -e AZURE_RESOURCE_GROUP=\"$AZURE_RESOURCE_GROUP\" \
    -e AZURE_PROJECT_NAME=\"$AZURE_PROJECT_NAME\" \
    -e NEED_BETA_VERSION=\"$NEED_BETA_VERSION\" \
    -e AZ_TOKEN=\"$SOURCE_TOKEN\" \
    -e PRODUCTION_TOKEN=\"$PRODUCTION_TOKEN\""

echo -e "${GREEN}🏭 Passing both source and production tokens to container${NC}"

# Add beta version flag message
if [ "$NEED_BETA_VERSION" = "true" ]; then
    echo -e "${BLUE}📦 Using azure-ai-projects version 1.0.0b10 (beta - for connection string support)${NC}"
else
    echo -e "${GREEN}✅ Using standard azure-ai-projects version 1.0.0${NC}"
fi

# Complete the Docker command
DOCKER_CMD="$DOCKER_CMD \
    -v \"$HOME/.azure:/home/migration/.azure\" \
    v1-to-v2-migration"

# Add script arguments
for arg in "$@"; do
    DOCKER_CMD="$DOCKER_CMD \"$arg\""
done

# Execute Docker command
echo ""
eval $DOCKER_CMD

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ Migration completed successfully!${NC}"
else
    echo ""
    echo -e "${RED}❌ Migration failed with exit code: $EXIT_CODE${NC}"
fi

exit $EXIT_CODE