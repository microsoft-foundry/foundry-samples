# V1 to V2 Agent Migration - Docker Container

This directory contains the containerized version of the v1 to v2 agent migration script.

## Quick Start

### Prerequisites
- Docker installed and running
- Azure CLI installed and authenticated (`az login`)
- Access to source data (Cosmos DB, API, or Project)

### Build and Run

#### Option 1: Using the helper scripts (Recommended)

**Linux/macOS:**
```bash
# Make the script executable
chmod +x run-migration.sh

# Run migration with arguments
./run-migration.sh --help
./run-migration.sh --use-api --use-v2-api
./run-migration.sh asst_abc123 --project-connection-string "eastus.api.azureml.ms;...;...;..."
```

**Windows:**
```cmd
# Run migration with arguments
run-migration.bat --help
run-migration.bat --use-api --use-v2-api
run-migration.bat asst_abc123 --project-connection-string "eastus.api.azureml.ms;...;...;..."
```

#### Option 2: Using Docker directly

```bash
# Build the image
docker build -t v1-to-v2-migration .

# Run with arguments
docker run --rm -it \
  --network host \
  -v ~/.azure:/home/migration/.azure:ro \
  -v "$(pwd)/output:/app/output" \
  -e COSMOS_CONNECTION_STRING \
  v1-to-v2-migration --help
```

#### Option 3: Using Docker Compose

```bash
# Create .env file from example
cp .env.example .env
# Edit .env with your values

# Run with Docker Compose
docker-compose run --rm v1-to-v2-migration --help
docker-compose run --rm v1-to-v2-migration --use-api --use-v2-api
```

## Configuration

### Environment Variables

The container supports all the same environment variables as the standalone script:

- `COSMOS_CONNECTION_STRING`: Cosmos DB connection string
- `AGENTS_HOST`: API host (default: eastus.api.azureml.ms)
- `AGENTS_SUBSCRIPTION`: Azure subscription ID
- `AGENTS_RESOURCE_GROUP`: Resource group for v1 API
- `AGENTS_RESOURCE_GROUP_V2`: Resource group for v2 API
- `AGENTS_WORKSPACE`: Workspace for v1 API
- `AGENTS_WORKSPACE_V2`: Workspace for v2 API
- `AGENTS_API_VERSION`: API version (default: 2025-05-15-preview)
- `AZ_TOKEN`: Optional Azure token (will use Azure CLI if not provided)

### Volume Mounts

- `~/.azure:/home/migration/.azure:ro`: Azure CLI configuration (read-only)
- `./output:/app/output`: Output directory for logs and results

## Usage Examples

### Test Tool Injection
```bash
# Test all tool types
./run-migration.sh --add-test-function --add-test-mcp --add-test-computer --add-test-imagegen --add-test-azurefunction --use-api

# Test specific tool combinations
./run-migration.sh --add-test-mcp --add-test-computer --project-connection-string "eastus.api.azureml.ms;...;...;..."
```

### Migration Workflows
```bash
# Migrate all assistants from API to v2 API
./run-migration.sh --use-api --use-v2-api

# Migrate specific assistant from Cosmos DB to Cosmos DB
./run-migration.sh asst_abc123

# Migrate from project connection to v2 API
./run-migration.sh --project-connection-string "eastus.api.azureml.ms;...;...;..." --use-v2-api
```

## Features

✅ **Complete Migration Pipeline**: All 4 input methods, 2 output methods  
✅ **Tool Testing**: 5 different test tool types for validation  
✅ **Azure CLI Integration**: Automatic token management  
✅ **Security**: Non-root user, read-only mounts  
✅ **Cross-Platform**: Works on Linux, macOS, and Windows  
✅ **Flexible Configuration**: Environment variables, volume mounts  
✅ **Network Access**: Host networking for localhost v2 API access  

## Troubleshooting

### Docker Issues
- Ensure Docker is running: `docker info`
- Check image build: `docker images | grep v1-to-v2-migration`

### Authentication Issues
- Verify Azure CLI: `az account show`
- Check token: `az account get-access-token --scope https://ai.azure.com/.default`

### Network Issues
- For localhost v2 API, ensure `--network host` is used
- Check firewall settings for container network access

### Permission Issues
- Ensure Azure CLI config is readable: `ls -la ~/.azure`
- Check output directory permissions: `ls -la ./output`

## Development

To modify the container:

1. Edit the migration script: `v1_to_v2_migration.py`
2. Update dependencies: `requirements.txt`
3. Rebuild the image: `docker build -t v1-to-v2-migration .`
4. Test changes: `./run-migration.sh --help`