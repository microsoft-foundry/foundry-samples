# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

"""
DESCRIPTION:
    This sample demonstrates how to use call agent, capable to use tools using a2a protocol.

USAGE:
    python agent_a2a_with_tools.py

    Before running the sample:

    pip install azure-ai-agents azure-identity a2a-sdk

    Set these environment variables with your own values:
    1) PROJECT_ENDPOINT - The Azure AI Project endpoint, as found in the Overview
                          page of your Azure AI Foundry portal.
    2) MODEL_DEPLOYMENT_NAME - The deployment name of the AI model, as found under the "Name" column in
       the "Models + endpoints" tab in your Azure AI Foundry project.
"""

import asyncio
import os
import uuid
import httpx
from a2a.client.client import A2AClient
from a2a.types import SendMessageRequest, MessageSendParams
from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import (
    AsyncFunctionTool,
    AsyncToolSet,
    FilePurpose,
    FileSearchTool,
    ListSortOrder,
)
from azure.identity.aio import DefaultAzureCredential


class AzureTokenAuth(httpx.Auth):
    """
    The azure token authenticator.

    :param scopes: Authorization scopes
    :type scopes: list(str)
    :param token_provider: The Azure token provider.
    :type token_provider: TokenCredential
    :param async_token_provider: The Asynchronous Azure token provider
    :type async_token_provider: AsyncTokenCredential
    """

    def __init__(self, scopes, token_provider=None, async_token_provider=None):
        self.token_provider = token_provider
        self.async_token_provider = async_token_provider
        self.scopes = scopes

    def _raise_no_token_maybe(self, token, text):
        """The internal method to raise the error."""
        if token is None:
            raise RuntimeError(f"No {text} token provider were supplied.")
    
    def sync_auth_flow(self, request):
        """Provide token in synchronous scenario."""
        self._raise_no_token_maybe(self.token_provider, "synchronous")
        request.headers["Authorization"] = f"Bearer {self.token_provider.get_token(self.scopes[0]).token}"
        yield request

    async def async_auth_flow(self, request):
        """Provide token in asynchronous scenario."""
        self._raise_no_token_maybe(self.async_token_provider, "asynchronous")
        token = await self.async_token_provider.get_token(self.scopes[0])
        request.headers["Authorization"] = f"Bearer {token.token}"
        yield request


def get_function(agent_id, creds, credential_scopes, endpoint, api_version):
    """
    Get the response from an agent using a2a protocal.

    :param agent_id: The ID if an agent.
    :param creds: The credential used to take token from.
    :param credential_scopes: The scopes to be used.
    :param endpoint: agent endpoint.
    :param api_version: The api version to be used by an agent.
    :return: The function, taking message as a parameter and calling endpoint by a2a protocol.
    """
    
    async def get_a2a_response(message):
        """
        Get the information about Contoso products.

        :param message: The question to ask about cotoso product.
        :return: The response based on the data in the file.
        """
        async with httpx.AsyncClient(
              auth=AzureTokenAuth(
                  scopes=credential_scopes,
                  async_token_provider=creds
              ),
          ) as httpx_client:
            a2a_client = A2AClient(
                httpx_client=httpx_client,
                url=f"{endpoint}/workflows/a2a/agents/{agent_id}?api-version={api_version}"
            )
            
            send_message_payload = {
                'message': {
                    'role': 'user',
                    'parts': [
                        {'kind': 'text', 'text': message}
                    ],
                    'messageId': uuid.uuid4().hex,
                },
            }
            
            request = SendMessageRequest(
                id=str(uuid.uuid4()),
                params=MessageSendParams(**send_message_payload)
            )
            response = await a2a_client.send_message(request)
            return response.model_dump(mode='json', excluse_none=True)
        
            
    return get_a2a_response

async def main():
    creds = DefaultAzureCredential()
    endpoint = os.environ["PROJECT_ENDPOINT"]
    async with AgentsClient(
          endpoint=endpoint,
          credential=creds,
      ) as agents_client:
        asset_file_path =os.path.join( os.path.dirname(__file__), 'sample_data', 'product_info_1.md')
        # Upload file and create vector store
        file = await agents_client.files.upload_and_poll(file_path=asset_file_path, purpose=FilePurpose.AGENTS)
        print(f"Uploaded file, file ID: {file.id}")
    
        vector_store = await agents_client.vector_stores.create_and_poll(file_ids=[file.id], name="my_vectorstore")
        print(f"Created vector store, vector store ID: {vector_store.id}")
    
        # Create file search tool with resources followed by creating agent
        file_search = FileSearchTool(vector_store_ids=[vector_store.id])
        # Create the agent used for the file search.
        search_tool_agent = await agents_client.create_agent(
            model=os.environ["MODEL_DEPLOYMENT_NAME"],
            name="my-agent",
            instructions="Hello, you are helpful agent and can search information from uploaded files",
            tools=file_search.definitions,
            tool_resources=file_search.resources,
        )
        print(f"Created agent for file search, agent ID: {search_tool_agent.id}")
        
        # Create an agent, using function tool to call file search agent using a2a protocol.
        # Get the function and use it to create a function tool.
        functions = AsyncFunctionTool(functions={get_function(
            agent_id=search_tool_agent.id,
            creds=creds,
            credential_scopes=agents_client._config.credential_scopes,
            endpoint=endpoint,
            api_version=agents_client._config.api_version
        )})
        toolset = AsyncToolSet()
        toolset.add(functions)
        
        # To enable tool calls executed automatically
        agents_client.enable_auto_function_calls(toolset)
        
        # Create agent, capable of calling function
        agent = await agents_client.create_agent(
            model=os.environ["MODEL_DEPLOYMENT_NAME"],
            name="my-agent",
            instructions=("Hello, you are helpful agent. "
                          "When asked about Contoso project "
                          "please send the question to the function tool and return the response."),
            toolset=toolset,
        )
        print(f"Created agent, agent ID: {agent.id}")
        
        # Create thread for communication
        thread = await agents_client.threads.create()
        print(f"Created thread, ID: {thread.id}")
    
        # Create message to thread
        message = await agents_client.messages.create(
            thread_id=thread.id, role="user", content="Hello, what Contoso products do you know?"
        )
        print(f"Created message, ID: {message.id}")
    
        # Create and process agent run in thread with tools
        run = await agents_client.runs.create_and_process(
            thread_id=thread.id,
            agent_id=agent.id,
        )
        print(f"Run finished with status: {run.status}")
    
        if run.status == "failed":
            # Check if you got "Rate limit is exceeded.", then you want to get more quota
            print(f"Run failed: {run.last_error}")
        
        # Fetch and log all messages
        messages = agents_client.messages.list(
            thread_id=thread.id, order=ListSortOrder.ASCENDING)
        async for msg in messages:
            if msg.text_messages:
                last_text = msg.text_messages[-1]
                print(f"{msg.role}: {last_text.text.value}")
        
        # Clean up the resources.
        # Delete uploaded file.
        await agents_client.files.delete(file.id)
        print("Deleted file")
        
        # Delete vector store.
        await agents_client.vector_stores.delete(vector_store.id)
        print("Deleted vector store")
        
        # Delete file search agent.
        await agents_client.delete_agent(search_tool_agent.id)
        print("Deleted agent")
        
        # Delete the agent, calling function.
        await agents_client.delete_agent(agent.id)
        print("Deleted agent")


if __name__ == '__main__':
    asyncio.run(main())