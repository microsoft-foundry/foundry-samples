using 'main.bicep'

var azdEnvironmentName = readEnvironmentVariable('AZURE_ENV_NAME', 'local')

param foundryProjectName = azdEnvironmentName
param environmentName = azdEnvironmentName
param location = readEnvironmentVariable('AZURE_LOCATION', 'westus2')
param principalId = ''
param resourceGroupName = readEnvironmentVariable('AZURE_RESOURCE_GROUP', 'rg-${azdEnvironmentName}')
param resourceTokenSalt = azdEnvironmentName
param deployModel = readEnvironmentVariable('deployModel', 'false') == 'true'
param existingModelResponsesEndpoint = readEnvironmentVariable('existingModelResponsesEndpoint', '')
param modelDeploymentName = readEnvironmentVariable('modelDeploymentName', 'gpt-5-mini')
param modelName = readEnvironmentVariable('modelName', 'gpt-5-mini')
param modelVersion = readEnvironmentVariable('modelVersion', '2025-08-07')
param modelSkuName = readEnvironmentVariable('modelSkuName', 'GlobalStandard')
param modelCapacity = int(readEnvironmentVariable('modelCapacity', '10'))
