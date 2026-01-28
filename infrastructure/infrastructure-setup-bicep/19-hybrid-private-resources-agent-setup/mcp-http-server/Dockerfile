# Multi-Auth MCP Server Image
# 
# This Dockerfile simply references the pre-built multi-auth MCP image.
# The source image is maintained at: retrievaltestacr.azurecr.io/multi-auth-mcp/api-multi-auth-mcp-env
#
# To use this image:
# 1. Import to your ACR:
#    az acr import --name <your-acr> --source retrievaltestacr.azurecr.io/multi-auth-mcp/api-multi-auth-mcp-env:latest --image multi-auth-mcp:latest
#
# 2. Or build locally using this Dockerfile:
#    docker build -t multi-auth-mcp:latest .
#
# The MCP server exposes the following endpoints:
# - /noauth/mcp - No authentication required (for testing)
# - /mcp - Requires authentication
# - /healthz - Health check endpoint
#
# Environment variables (optional):
# - PORT: Server port (default: 8080)
# - TENANT_ID: Azure AD tenant ID
# - MCP_APP_ID: MCP application ID
# - API_KEYS: Comma-separated API keys for authentication

FROM retrievaltestacr.azurecr.io/multi-auth-mcp/api-multi-auth-mcp-env:latest

# The base image already configures everything, just expose the port
EXPOSE 8080
