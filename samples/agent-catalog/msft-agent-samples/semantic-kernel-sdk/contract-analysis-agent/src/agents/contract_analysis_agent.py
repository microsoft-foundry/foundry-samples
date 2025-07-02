import os
import traceback

from azure.identity import DefaultAzureCredential
from dotenv import find_dotenv, load_dotenv
from semantic_kernel.agents import AzureAIAgent, AzureAIAgentThread
from semantic_kernel.contents import ChatHistory
from utils.logger import Logger


# Contract Analysis agent is an Azure AI Agent Service agent that analyzes versions of a contract and generates a summary of the differences.
class ContractAnalysisAgent:
    _agentName = "ContractAnalysisAgent"

    async def execute(self, contracts_readme: list[str]) -> str:        
        Logger.log_start(self._agentName)

        AGENT_INSTRUCTIONS_PATH = os.getenv("AGENT_INSTRUCTIONS_PATH")
        AZURE_AI_AGENT_ENDPOINT = os.getenv("AZURE_AI_AGENT_ENDPOINT")
        AZURE_AI_AGENT_AGENT_ID = os.getenv("AZURE_AI_AGENT_AGENT_ID")
        AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME = os.getenv("AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME")

        analysis_text = ""

        # Create an Azure AI agent client
        client = AzureAIAgent.create_client(
            credential=DefaultAzureCredential(),
            endpoint=AZURE_AI_AGENT_ENDPOINT)
        
        agent_definition = None

        if not AZURE_AI_AGENT_AGENT_ID:
            with open(AGENT_INSTRUCTIONS_PATH, 'r') as file:
                instructions = file.read()
                # Create a new agent if no agent ID is provided
                agent_definition = await client.agents.create_agent(
                    name="ContractAnalysisAgentSample",
                    description="Agent to analyze contracts.",
                    instructions=instructions,
                    model=AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME,
                )
        else:
            # Retrieve an existing agent
            agent_definition = await client.agents.get_agent(
                agent_id=AZURE_AI_AGENT_AGENT_ID
            )

        # Create a Semantic Kernel agent for the Azure AI agent
        agent = AzureAIAgent(
            client=client, definition=agent_definition,
        )

        # Create a thread for the agent
        thread: AzureAIAgentThread = AzureAIAgentThread(
            messages=ChatHistory(), client=client
        )

        try:
            analysis_text = await agent.get_response(
                messages=contracts_readme,
                thread=thread
            )
            analysis_text = analysis_text.content.content
        except Exception as e:
            # Handle the exception
            stack_trace = traceback.format_exc()
            # print(stack_trace)
        finally:
            await thread.delete() if thread else None
            await client.close() if client else None

        Logger.log_result(analysis_text)
        Logger.log_completion(self._agentName)

        return analysis_text