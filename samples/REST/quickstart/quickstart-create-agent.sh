curl -X POST https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/agents?api-version=2025-11-15-preview \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AZURE_AI_AUTH_TOKEN" \
  -d '{
        "name": "MyAgent",
        "definition": {
            "kind": "prompt",
            "model": "gpt-4.1-mini", 
            "instructions": "You are a helpful assistant that answers general questions"
        }
    }'