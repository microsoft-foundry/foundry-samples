Set-Location  "$($PSScriptRoot)/../src/hello_world_a365_agent"

Remove-Item "./publish" -Recurse -Force -ErrorAction SilentlyContinue

dotnet publish -c Release -o "./publish"


$authorityEndpoint = "https://login.microsoftonline.com/$($env:TENANT_ID)"
$azureOpenAIEndpoint = "https://$($env:ACCOUNT_NAME).openai.azure.com/"
    
$projectClientId = az ad sp show --id $env:PROJECT_PRINCIPAL_ID --query appId -o tsv

# if the projectClientId is null or empty, throw an error
if ([string]::IsNullOrEmpty($projectClientId)) {
    throw "Failed to get project client ID for principal ID $($env:PROJECT_PRINCIPAL_ID)"
}

docker build -t hello-world-a365-agent:a365preview001 --build-arg BLUEPRINT_CLIENT_ID=$env:AGENT_IDENTITY_BLUEPRINT_ID --build-arg AUTHORITY_ENDPOINT=$authorityEndpoint --build-arg FEDERATED_CLIENT_ID=$projectClientId --build-arg AZURE_OPENAI_ENDPOINT=$azureOpenAIEndpoint --build-arg MODEL_DEPLOYMENT='gpt-4o' -f "./foundry-infra/Dockerfile" .

$acrLoginServer = $env:AZURE_CONTAINER_REGISTRY_ENDPOINT

# split the login server to get the registry name
$registryName = $acrLoginServer.Split(".")[0]

docker tag hello-world-a365-agent:a365preview001 $acrLoginServer/hello-world-a365-agent:a365preview001

az acr login --name $registryName

docker push $acrLoginServer/hello-world-a365-agent:a365preview001

Remove-Item "./publish" -Recurse -Force -ErrorAction SilentlyContinue
