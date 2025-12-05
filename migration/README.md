# V1 to V2 Assistant Migration Tool

A comprehensive tool for migrating OpenAI v1 assistants to Azure AI v2 agents with Docker containerization support, extensive test capabilities, and cross-platform compatibility.

## 🚀 Quick Start

### Prerequisites

- **Docker Desktop** installed and running
- **Azure CLI** installed on your host system
- **Azure account** with appropriate permissions
- **Python 3.11+** (if running locally without Docker)

### Authentication Setup

Choose your platform and run the authentication setup script:

**Windows (PowerShell):**
```powershell
.\setup-azure-auth.bat
```

**Linux/macOS (Bash):**
```bash
./setup-azure-auth.sh
```

This script will:
- ✅ Verify Docker is running
- ✅ Check Azure CLI installation
- ✅ Handle Azure authentication
- ✅ Build the Docker image
- ✅ Test authentication in container

### Running Migrations

After authentication setup, use the platform-specific runner:

**Windows (PowerShell):**
```powershell
# Regular output
.\run-migration.bat --help

# Verbose output
.\run-migration-verbose.bat --help

# Docker-based with automatic authentication (recommended)
.\run-migration-docker-auth.ps1 --help
```

**Linux/macOS (Bash):**
```bash
./run-migration.sh --help
```

## 📋 Usage Examples

### 1. Production Migration with Dual-Tenant Authentication (REQUIRED)

**All migrations require production parameters:**

```powershell
# Windows PowerShell - Migrate from v1 API to production v2 API
.\run-migration-docker-auth.ps1 `
  --use-api `
  --source-tenant "72f988bf-86f1-41af-91ab-2d7cd011db47" `
  --production-resource "nextgen-eastus" `
  --production-subscription "b1615458-c1ea-49bc-8526-cafc948d3c25" `
  --production-tenant "33e577a9-b1b8-4126-87c0-673f197bf624" `
  asst_abc123def456

# Linux/macOS - Same command structure
./run-migration-docker-auth.sh \
  --use-api \
  --source-tenant "72f988bf-86f1-41af-91ab-2d7cd011db47" \
  --production-resource "nextgen-eastus" \
  --production-subscription "b1615458-c1ea-49bc-8526-cafc948d3c25" \
  --production-tenant "33e577a9-b1b8-4126-87c0-673f197bf624" \
  asst_abc123def456
```

**Required Parameters:**
- `--production-resource`: Azure AI resource name (e.g., "nextgen-eastus")
- `--production-subscription`: Subscription ID for production tenant
- `--production-tenant`: Production tenant ID for writing agents
- `--source-tenant`: Source tenant ID for reading assistants (optional, defaults to Microsoft tenant)

### 2. Migrate Using Project Connection String (Beta)
```bash
# Connection string format: region.api.azureml.ms;subscription-id;resource-group;project-name
./run-migration-docker-auth.sh \
  --project-connection-string "eastus.api.azureml.ms;abc-123;my-rg;my-project" \
  --production-resource "nextgen-eastus" \
  --production-subscription "b1615458-c1ea-49bc-8526-cafc948d3c25" \
  --production-tenant "33e577a9-b1b8-4126-87c0-673f197bf624" \
  asst_abc123def456

# Windows PowerShell
.\run-migration-docker-auth.ps1 `
  --project-connection-string "eastus.api.azureml.ms;abc-123;my-rg;my-project" `
  --production-resource "nextgen-eastus" `
  --production-subscription "b1615458-c1ea-49bc-8526-cafc948d3c25" `
  --production-tenant "33e577a9-b1b8-4126-87c0-673f197bf624" `
  asst_abc123def456
```
> **Note**: Connection string support requires `azure-ai-projects==1.0.0b10` (beta). The script automatically detects and installs the correct version. Production parameters are always required.

### 3. Migrate from Project Endpoint to Production v2 API
```bash
# Using project endpoint (production parameters required)
./run-migration-docker-auth.sh \
  --project-endpoint "https://your-project.cognitiveservices.azure.com" \
  --production-resource "nextgen-eastus" \
  --production-subscription "b1615458-c1ea-49bc-8526-cafc948d3c25" \
  --production-tenant "33e577a9-b1b8-4126-87c0-673f197bf624" \
  assistant-id
```

### 4. Add Test Tools to Migration
```bash
# Add function calling test (production parameters required)
./run-migration-docker-auth.sh \
  --use-api \
  --add-test-function \
  --production-resource "nextgen-eastus" \
  --production-subscription "b1615458-c1ea-49bc-8526-cafc948d3c25" \
  --production-tenant "33e577a9-b1b8-4126-87c0-673f197bf624" \
  assistant-id

# Add multiple test tools
./run-migration-docker-auth.sh \
  --use-api \
  --add-test-function \
  --add-test-mcp \
  --add-test-computer \
  --production-resource "nextgen-eastus" \
  --production-subscription "b1615458-c1ea-49bc-8526-cafc948d3c25" \
  --production-tenant "33e577a9-b1b8-4126-87c0-673f197bf624" \
  assistant-id
```

### 5. Environment Variables Support
Create a `.env` file in the project directory:
```env
# Azure Project Configuration
PROJECT_ENDPOINT_URL=https://your-project.cognitiveservices.azure.com
PROJECT_CONNECTION_STRING=your-connection-string

# Cosmos DB Configuration (optional)
# Use either COSMOS_CONNECTION_STRING (recommended) or individual parameters
COSMOS_CONNECTION_STRING=AccountEndpoint=https://...;AccountKey=...;
# OR (legacy - still supported)
COSMOS_DB_CONNECTION_STRING=your-cosmos-connection-string
COSMOS_DB_DATABASE_NAME=your-database
COSMOS_DB_CONTAINER_NAME=your-container

# v1 API Configuration (optional)
ASSISTANT_API_BASE=https://api.openai.com/v1
ASSISTANT_API_KEY=your-openai-key
ASSISTANT_API_VERSION=v1

# v2 API Configuration (optional)
V2_API_BASE=https://your-v2-api.cognitiveservices.azure.com
V2_API_KEY=your-v2-key
V2_API_VERSION=2024-05-01-preview

# Azure Authentication (optional)
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
AZURE_SUBSCRIPTION_ID=your-subscription-id
AZURE_RESOURCE_GROUP=your-resource-group
AZURE_PROJECT_NAME=your-project-name
```

## 🛠️ Command Line Options

### Input Methods (choose one)
- `--use-api` - Read from v1 API (recommended)
- `--project-endpoint URL` - Use Azure AI Project endpoint
- `--project-connection-string STRING` - Use Azure AI Project connection string
- `--cosmos` - Read from Cosmos DB (legacy)

### Output Methods
- Always uses **production v2 API** (requires production parameters)

### Test Tool Options (optional, can use multiple)
- `--add-test-tool function` - Add function calling test
- `--add-test-tool mcp` - Add Model Context Protocol test
- `--add-test-tool computer-use` - Add computer use test
- `--add-test-tool image-gen` - Add image generation test
- `--add-test-tool azure-function` - Add Azure Function test

### Production Migration Options (REQUIRED for Docker Auth Scripts)
- `--production-resource RESOURCE_NAME` - **REQUIRED** Production Azure AI resource name (e.g., "nextgen-eastus")
- `--production-subscription SUBSCRIPTION_ID` - **REQUIRED** Production subscription ID
- `--production-tenant TENANT_ID` - **REQUIRED** Production tenant for writing agents
- `--source-tenant TENANT_ID` - *Optional* Source tenant for reading assistants (defaults to Microsoft tenant: 72f988bf-86f1-41af-91ab-2d7cd011db47)

### Configuration Options
- `--v1-api-version VERSION` - v1 API version (default: v1)
- `--v2-api-version VERSION` - v2 API version (default: 2024-05-01-preview)
- `--cosmos-database DATABASE` - Cosmos database name
- `--cosmos-container CONTAINER` - Cosmos container name

## � Unsupported Classic Assistant Features

The migration tool will **continue migration** for classic assistants (v1) that use features not supported in new agents (v2), but will **skip the unsupported tools** and display warnings:

### Connected Agent Tool
```
⚠️  WARNING: Your classic agent includes connected agents, which aren't supported in the new experience.
ℹ️  These connected agents won't be carried over when you create the new agent.
💡 To orchestrate multiple agents, use a workflow instead.
📋 Unsupported tools that will be skipped: connected_agent
```
**What happens**: The connected_agent tool is skipped during migration. The new agent is created successfully without this tool.

**Recommendation**: Use **new agent workflows** to connect multiple agents together.

### Event Binding Tool
```
⚠️  WARNING: Your classic agent uses 'event_binding' which isn't supported in the new experience.
ℹ️  This tool won't be carried over when you create the new agent.
📋 Unsupported tools that will be skipped: event_binding
```
**What happens**: The event_binding tool is skipped during migration. The new agent is created successfully without this tool.

**Recommendation**: This feature has no direct equivalent in new agents.

### Output Binding Tool
```
⚠️  WARNING: Your classic agent uses 'output_binding' which isn't supported in the new experience.
ℹ️  This tool won't be carried over when you create the new agent.
💡 Consider using 'capture_structured_outputs' in your new agent instead.
📋 Unsupported tools that will be skipped: output_binding
```
**What happens**: The output_binding tool is skipped during migration. The new agent is created successfully without this tool.

**Recommendation**: Use **`capture_structured_outputs`** in new agents for structured output capture.

> **Note**: Migration completes successfully even when unsupported tools are present. Only the unsupported tools are excluded from the new agent. All other tools and properties are migrated normally.

## �🐳 Docker Architecture

### Container Features
- **Base Image**: Python 3.11-slim with Azure CLI
- **Non-root User**: Runs as `migration` user for security
- **Volume Mounts**: Azure CLI config directory for authentication
- **Network**: Host networking for localhost API access
- **Environment**: Comprehensive environment variable support

### Dynamic Package Installation
The container automatically installs the correct `azure-ai-projects` package version based on your usage:

- **Standard version (1.0.0)**: Used for project endpoints and most scenarios
- **Beta version (1.0.0b10)**: Automatically installed when using `--project-connection-string`
  - Required for `from_connection_string()` method support
  - Detection and installation happens at container startup
  - No manual intervention needed

The script detects connection string usage and sets the `NEED_BETA_VERSION` flag automatically.

### Dual-Tenant Authentication (REQUIRED)
The `run-migration-docker-auth.ps1` and `run-migration-docker-auth.sh` scripts require production parameters for all migrations:

- **Production-First Architecture**: All migrations write to production v2 API (no localhost mode)
- **Required Production Parameters**: Must specify production resource, subscription, and tenant
- **Source Tenant Authentication**: Reads assistants from source tenant (defaults to Microsoft tenant)
- **Production Tenant Authentication**: Writes agents to production tenant
- **Automatic Token Management**: Generates and manages separate tokens for each tenant
- **Seamless Tenant Switching**: Handles Azure CLI tenant switching automatically
- **Token Isolation**: Source and production tokens are isolated for security
- **Cross-Platform Support**: Both PowerShell (Windows) and Bash (Linux/macOS) versions

### Security Considerations
- Non-root container execution
- Read-write Azure CLI directory for token management
- Environment variable injection for sensitive data
- Host network isolation when possible

## 🧪 Test Tool Capabilities

The migration tool can inject various test tools into migrated agents:

### Function Calling Test
```python
def get_weather(location: str) -> str:
    """Get current weather for a location."""
    return f"Weather in {location}: 72°F, sunny"
```

### Model Context Protocol (MCP) Test
```python
def mcp_filesystem_tool(action: str, path: str) -> str:
    """MCP filesystem operations."""
    return f"MCP {action} operation on {path} completed"
```

### Computer Use Test
```python
def computer_screenshot() -> str:
    """Take a screenshot of the current screen."""
    return "Screenshot taken: desktop_1024x768.png"
```

### Image Generation Test
```python
def generate_image(prompt: str) -> str:
    """Generate an image from a text prompt."""
    return f"Generated image for: {prompt}"
```

### Azure Function Test
```python
def azure_function_call(function_name: str, data: dict) -> str:
    """Call an Azure Function."""
    return f"Azure Function {function_name} called with {data}"
```

## 🏗️ Architecture Details

### Core Components

1. **Migration Engine** (`v1_to_v2_migration.py`)
   - Smart parameter extraction from endpoints
   - Multi-input/output method support
   - Comprehensive error handling
   - Test tool injection capabilities

2. **Docker Container** (`Dockerfile`)
   - Multi-stage build process
   - Azure CLI integration
   - Proper user permissions
   - Environment configuration

3. **Platform Scripts**
   - Windows: `setup-azure-auth.bat`, `run-migration.bat`, `run-migration-verbose.bat`
   - Linux/macOS: `setup-azure-auth.sh`, `run-migration.sh`

### Data Flow

```
Input Sources → Migration Engine → Output Destinations
     ↓               ↓                    ↓
- Cosmos DB    → Transform v1→v2 →   - Cosmos DB
- v1 API       → Add test tools  →   - v2 API
- Project EP   → Parameter extract
- Connection   → Error handling
```

### Parameter Extraction

The tool automatically extracts Azure AI project parameters from endpoints and connection strings:

**From Project Endpoint:**
```
https://projectname-region.cognitiveservices.azure.com
→ subscription_id, resource_group_name, project_name
```

**From Connection String:**
```
endpoint=https://...;subscriptionid=...;resourcegroupname=...;projectname=...
→ Parsed individual components
```

## 🔧 Troubleshooting

### Common Issues

1. **Docker Not Running**
   ```
   ❌ Docker is not running. Please start Docker and try again.
   ```
   **Solution**: Start Docker Desktop

2. **Azure CLI Not Authenticated**
   ```
   ⚠️ Not authenticated to Azure CLI
   ```
   **Solution**: Run `az login` or use the setup script

3. **Unsupported Tool Types**
   ```
   WARNING: Your classic agent includes connected agents...
   ```
   **Solution**: Migration will continue but unsupported tools will be skipped. See the "Unsupported Classic Assistant Features" section above for details and alternatives

4. **Connection String Format**
   ```
   Failed to parse connection string
   ```
   **Solution**: Use format `region.api.azureml.ms;subscription-id;resource-group;project-name`

5. **Dual-Tenant Authentication Issues**
   ```
   Token tenant does not match resource tenant
   ```
   **Solution**: Ensure correct source and production tenant IDs are specified

6. **Agent Name Case Sensitivity**
   ```
   400 Bad Request on production endpoint
   ```
   **Solution**: Agent names are automatically converted to lowercase with proper formatting

5. **Container Authentication Fails**
   ```
   Authentication test failed
   ```
   **Solution**: Ensure Azure CLI directory has proper permissions

6. **Network Connection Issues**
   ```
   Connection refused to localhost
   ```
   **Solution**: Use `--network host` flag (included in scripts)

### Debug Mode

Use verbose scripts for detailed output:
```powershell
# Windows
.\run-migration-verbose.bat --help

# Linux/macOS
./run-migration.sh --help  # Already verbose
```

### Manual Docker Commands

If scripts fail, run manually:
```bash
# Build image
docker build -t v1-to-v2-migration .

# Run with debugging
docker run --rm -it \
    --network host \
    -v ~/.azure:/home/migration/.azure \
    v1-to-v2-migration \
    /bin/bash
```

## 📚 API Compatibility

### Supported Azure AI Project APIs
- **2024-05-01-preview** (default)
- **2024-02-15-preview**
- **2023-12-01-preview**

### Supported OpenAI v1 APIs
- **OpenAI API v1**
- **Azure OpenAI v1**
- **Compatible third-party APIs**

## 🤝 Contributing

### Development Setup
1. Clone repository
2. Install dependencies: `pip install -r requirements.txt`
3. Run tests: `python -m pytest`
4. Build Docker: `docker build -t v1-to-v2-migration .`

### Adding New Test Tools
1. Add tool definition to `TEST_TOOLS` dictionary
2. Update `inject_test_tools()` function
3. Add command-line option handling
4. Update documentation

## 📄 License

MIT License - see LICENSE file for details

## 🆘 Support

For issues and questions:
1. Check troubleshooting section
2. Run with verbose output
3. Check Docker and Azure CLI status
4. Verify authentication setup

---

**Made with ❤️ for seamless AI agent migration**