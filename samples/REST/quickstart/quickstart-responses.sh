curl -X POST https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/openai/responses?api-version=2025-11-15-preview \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AZURE_AI_AUTH_TOKEN" \
-d '{
        "model": "gpt-4.1-mini",
        "input": "What is the size of France in square miles?"
}'