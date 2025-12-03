# <chat_completion>

curl --request POST --url 'https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-10-21' \
-h 'authorization: Bearer $AZURE_AI_AUTH_TOKEN' \
-h 'content-type: application/json' \
-d '{
        "messages": [
            {"role": "system", 
            "content": "You are a helpful writing assistant"},
            {"role": "user", 
            "content": "Write me a poem about flowers"}
        ],
        "model": "gpt-4o"
    }'

# </chat_completion>

# <create_and_run_agent>

# Create agent
curl --request POST --url "https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/assistants?api-version=v1" \
    -h "authorization: Bearer $AZURE_AI_AUTH_TOKEN" \
    -h "content-type: application/json" \
    -d '{
            "model": "gpt-4o",
            "name": "my-agent",
            "instructions": "You are a helpful writing assistant"
        }'
#Lets say agent ID created is asst_123456789. Use this to run the agent

# Create thread
curl --request POST --url 'https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/threads?api-version=v1' \
    -h 'authorization: Bearer $AZURE_AI_AUTH_TOKEN' \
    -h 'content-type: application/json'

#Lets say thread ID created is thread_123456789. Use this in the next step

# Create message using thread ID
curl --request POST --url 'https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/threads/thread_123456789/messages?api-version=v1' \
    -h 'authorization: Bearer $AZURE_AI_AUTH_TOKEN' \
    -h 'content-type: application/json' \
    -d '{
            "role": "user",
            "content": "Write me a poem about flowers"
        }'

# Run thread with the agent - use both agent id and thread id
curl --request POST --url 'https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/threads/thread_123456789/runs?api-version=v1' \
    -h 'authorization: Bearer $AZURE_AI_AUTH_TOKEN' \
    -h 'content-type: application/json' \
    --data '{
        "assistant_id": "asst_123456789"
    }'

# List the messages in the thread using thread ID
curl --request GET --url 'https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/threads/thread_123456789/messages?api-version=v1' \
    -h 'authorization: Bearer $AZURE_AI_AUTH_TOKEN' \
    -h 'content-type: application/json'

# Delete agent once done using agent id
curl --request DELETE --url 'https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/assistants/asst_123456789?api-version=v1' \
    -h 'authorization: Bearer $AZURE_AI_AUTH_TOKEN' \
    -h 'content-type: application/json'

# </create_and_run_agent>



# <create_filesearch_agent>
#Upload the file
curl --request POST --url 'https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/files?api-version=v1' \ 
    -h 'authorization: Bearer $AZURE_AI_AUTH_TOKEN' \ 
    -f purpose="assistant" \
    -f file="@product_info_1.md" #File object (not file name) to be uploaded.
#Lets say file ID created is assistant-123456789. Use this in the next step

# create vector store
curl --request POST --url 'https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/vector_stores?api-version=v1' \ 
-h 'authorization: Bearer $AZURE_AI_AUTH_TOKEN' \ 
-h 'content-type: application/json' \ 
-d '{
        "name": "my_vectorstore",
        "file_ids": ["assistant-123456789"]
    }'
#Lets say Vector Store ID created is vs_123456789. Use this in the next step

# Create Agent for File Search
curl --request POST --url 'https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/assistants?api-version=v1' \
    -h 'authorization: Bearer $AZURE_AI_AUTH_TOKEN' \ 
    -h 'content-type: application/json' \ 
    -d '{
        "model": "gpt-4o",
        "name": "my-assistant",
        "instructions": "You are a helpful assistant and can search information from uploaded files",
        "tools": [{"type": "file_search"}],
        "tool_resources": {"file_search": {"vector_store_ids": ["vs_123456789"]}}
    }'
#Lets say agent ID created is asst_123456789. Use this to run the agent

# Create thread
curl --request POST --url 'https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/threads?api-version=v1' \
    -h 'authorization: Bearer $AZURE_AI_AUTH_TOKEN' \
    -h 'content-type: application/json'
#Lets say thread ID created is thread_123456789. Use this in the next step

# Create message using thread ID
curl --request POST --url 'https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/threads/thread_123456789/messages?api-version=v1' \
    -h 'authorization: Bearer $AZURE_AI_AUTH_TOKEN' \
    -h 'content-type: application/json' \
    -d '{
            "role": "user",
            "content": "Hello, what Contoso products do you know?"
        }'

# Run thread with the agent - use both agent id and thread id
curl --request POST --url 'https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/threads/thread_123456789/runs?api-version=v1' \
    -h 'authorization: Bearer $AZURE_AI_AUTH_TOKEN' \
    -h 'content-type: application/json' \
    --data '{
        "assistant_id": "asst_123456789"
    }'

# List the messages in the thread using thread ID
curl --request GET --url 'https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/threads/thread_123456789/messages?api-version=v1' \
    -h 'authorization: Bearer $AZURE_AI_AUTH_TOKEN' \
    -h 'content-type: application/json'

# Delete agent once done using agent id
curl --request DELETE --url 'https://YOUR-FOUNDRY-RESOURCE-NAME.services.ai.azure.com/api/projects/YOUR-PROJECT-NAME/assistants/asst_123456789?api-version=v1' \
    -h 'authorization: Bearer $AZURE_AI_AUTH_TOKEN' \
    -h 'content-type: application/json'

# </create_filesearch_agent>