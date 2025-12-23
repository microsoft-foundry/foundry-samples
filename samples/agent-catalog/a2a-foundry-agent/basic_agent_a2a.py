# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

"""
DESCRIPTION:
    This sample demonstrates how to use call agent using a2a protocol.

USAGE:
    python basic_agent_a2a.py

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


async def main():
    creds = DefaultAzureCredential()
    endpoint = os.environ["PROJECT_ENDPOINT"]
    async with AgentsClient(
            endpoint=endpoint,
            credential=creds,
        ) as agents_client:
    
        agent = await agents_client.create_agent(
            model=os.environ["MODEL_DEPLOYMENT_NAME"],
            name="my-agent",
            instructions="You are helpful agent",
        )
        print(f"Created agent, agent ID: {agent.id}")
        
        async with httpx.AsyncClient(
              auth=AzureTokenAuth(
                  scopes=agents_client._config.credential_scopes,
                  async_token_provider=creds
              ),
          ) as httpx_client:
        
            a2a_client = A2AClient(
                httpx_client=httpx_client,
                url=f"{endpoint}/workflows/a2a/agents/{agent.id}?api-version={agents_client._config.api_version}"
            )
            
            send_message_payload = {
                'message': {
                    'role': 'user',
                    'parts': [
                        {'kind': 'text', 'text': "Hello, tell me a joke"}
                    ],
                    'messageId': uuid.uuid4().hex,
                },
            }
            
            request = SendMessageRequest(
                id=str(uuid.uuid4()),
                params=MessageSendParams(**send_message_payload)
            )
            
            response = await a2a_client.send_message(request)
            print(response.model_dump(mode='json', excluse_none=True))
        
            await agents_client.delete_agent(agent.id)
            print("Deleted agent")


if __name__ == '__main__':
    asyncio.run(main())
