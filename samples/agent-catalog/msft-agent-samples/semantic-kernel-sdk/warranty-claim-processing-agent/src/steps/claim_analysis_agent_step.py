import os
import traceback

from azure.identity import DefaultAzureCredential
from dotenv import find_dotenv, load_dotenv
from semantic_kernel.agents import AzureAIAgent, AzureAIAgentThread
from semantic_kernel.contents import ChatHistory
from semantic_kernel.functions import kernel_function
from semantic_kernel.processes.kernel_process import KernelProcessStep
from utils.logger import Logger


# Claim Analysis Agent Step invokes an AI agent in Azure AI Agent service to analyze the claim data.
# It assesses the eligibility, risk, and recommended action for the claim. It also provides a summary of the claim and the analysis.
class ClaimAnalysisAgentStep(KernelProcessStep):
    _stepName = "ClaimAnalysisAgentStep"

    @kernel_function
    async def execute(self, claim_data_to_analyze):
        Logger.log_step_start(self._stepName)
        
        AZURE_AI_AGENT_ENDPOINT = os.getenv("AZURE_AI_AGENT_ENDPOINT")
        AZURE_AI_AGENT_AGENT_ID = os.getenv("AZURE_AI_AGENT_AGENT_ID")
        AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME = os.getenv("AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME")
        AGENT_INSTRUCTIONS_PATH = os.getenv("AGENT_INSTRUCTIONS_PATH")

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
                    name="WarrantyClaimAnalysisAgentSample",
                    description="Agent to analyze warranty claims and recommend actions.",
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

        # Create a message for the agent
        user_inputs = [
            "Analyze the provided claim and recommended an action. Claim details are as follows: \n" + 
            claim_data_to_analyze
        ]

        # Create a thread for the agent
        thread: AzureAIAgentThread = AzureAIAgentThread(
            messages=ChatHistory(), client=client
        )

        try:
            analysis_text = await agent.get_response(
                messages=user_inputs[0], thread=thread
            )
        except Exception as e:
            # Handle the exception
            stack_trace = traceback.format_exc()
            print(stack_trace)
        finally:
            await thread.delete() if thread else None
            await client.close() if client else None

        Logger.log_step_result(analysis_text)
        Logger.log_step_completion(self._stepName)

        return analysis_text

# Mocked Claim Analysis Agent Step returns hardcoded data to simulate claim analysis.
class MockClaimAnalysisAgentStep(KernelProcessStep):
    _stepName = "MockClaimAnalysisAgentStep"

    @kernel_function
    async def execute(self, claim_data_to_analyze):
        Logger.log_step_start(self._stepName)

        analysis_text = """
        {
            "claim_severity": "high",
            "risk_score": "medium",
            "recommended_action": "investigate",
            "claim_summary": "Hurricane caused roof damage, leaks, and appliance issues.",
            "analysis_summary": "Claim from severe hurricane damages to property; significant repairs needed. Medium risk based on location and value; requires investigation to confirm details."
        }
        """

        Logger.log_step_result(analysis_text)
        Logger.log_step_completion(self._stepName)

        return analysis_text