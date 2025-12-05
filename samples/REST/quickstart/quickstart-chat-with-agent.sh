# Optional Step: Create a conversation to use with the agent
curl -X POST https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/openai/conversations?api-version=2025-11-15-preview \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AZURE_AI_AUTH_TOKEN" \
  -d '{}'
# Lets say Conversation ID created is conv_123456789. Use this in the next step

#Chat with the agent to answer questions
curl -X POST https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/openai/responses?api-version=2025-11-15-preview \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AZURE_AI_AUTH_TOKEN" \
  -d '{
        "agent": {"type": "agent_reference", "name": "MyAgent"},
        "conversation" : "<YOUR_CONVERSATION_ID>",
        "input" : "What is the size of France in square miles?"
    }'

#Optional Step: Ask a follow-up question in the same conversation
curl -X POST https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/openai/responses?api-version=2025-11-15-preview \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AZURE_AI_AUTH_TOKEN" \
  -d '{
        "agent": {"type": "agent_reference", "name": "MyAgent"},
        "conversation" : "<YOUR_CONVERSATION_ID>",
        "input" : "And what is the capital city?"
    }'