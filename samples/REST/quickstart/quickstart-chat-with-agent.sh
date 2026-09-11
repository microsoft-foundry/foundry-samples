# Generate a response using the agent

curl -X POST "https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/agents/${FOUNDRY_AGENT_NAME}/endpoint/protocols/openai/responses?api-version=v1" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AZURE_AI_AUTH_TOKEN" \
  -d '{
    "input": [{"role": "user", "content": "What is the size of France in square miles?"}]
  }'

# Optional Step: Create a conversation to use with the agent
curl -X POST "https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/agents/${FOUNDRY_AGENT_NAME}/endpoint/protocols/openai/conversations?api-version=v1" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AZURE_AI_AUTH_TOKEN" \
  -d '{
    "items": [
      {
        "type": "message",
        "role": "user",
        "content": [
          {
            "type": "input_text",
            "text": "What is the size of France in square miles?"
          }
        ]
      }
    ]
  }'

# Lets say Conversation ID created is conv_123456789. Use this in the next step

#Optional Step: Ask a follow-up question in the same conversation
curl -X POST "https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/agents/${FOUNDRY_AGENT_NAME}/endpoint/protocols/openai/responses?api-version=v1" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AZURE_AI_AUTH_TOKEN" \
  -d '{
    "conversation": "<CONVERSATION_ID>",
    "input": [{"role": "user", "content": "And what is the capital?"}]
  }'