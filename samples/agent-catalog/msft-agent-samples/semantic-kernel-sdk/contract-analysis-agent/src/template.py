import asyncio

from agents.contract_analysis_agent import ContractAnalysisAgent
from dotenv import find_dotenv, load_dotenv
from tools.content_understanding_tool import ContentUnderstandingTool


async def run_agent():
    # Load environment variables from .env file
    load_dotenv(find_dotenv())

    # Create the agent
    agent = ContractAnalysisAgent()

    # Invoke the Content Understanding tool to convert PDF contracts to markdown
    tool = ContentUnderstandingTool()
    analyzer_id = tool.create_analyzer()
    contract1 = tool.analyze(
        './assets/input/123LogisticsContract.pdf',
        analyzer_id)
    contract2 = tool.analyze(
        './assets/input/ABCContract.pdf',
        analyzer_id)
    tool.delete_analyzer(analyzer_id)

    # Execute the agent with the contracts
    response = await agent.execute([contract1, contract2])

if __name__ == "__main__":
    asyncio.run(run_agent())