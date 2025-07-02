import asyncio
import os
from datetime import datetime
from pathlib import Path

from agents.sop_forge_agent import SOPForgeAgent
from dotenv import find_dotenv, load_dotenv
from tools.content_understanding_tool import ContentUnderstandingTool


async def run_agent():
    # Load environment variables from .env file
    load_dotenv(find_dotenv())

    # Create the agent
    agent = SOPForgeAgent()

    # Create output directory
    output_folder = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_directory = os.path.join(os.getenv("OUTPUT_DIR"), output_folder)
    Path(output_directory).mkdir(exist_ok=True)

    # Invoke the Content Understanding tool to convert PDF contracts to markdown
    tool = ContentUnderstandingTool()
    analyzer_id = tool.create_analyzer()
    analyzed_video_steps = tool.analyze(
        intput_file_path='./assets/input/VideoExample480p.mp4',
        analyzer_id=analyzer_id,
        output_directory=output_directory)
    tool.delete_analyzer(analyzer_id)

    # Execute the agent with the contracts
    response = await agent.execute(analyzed_video_steps)
    
    # Save the response to a markdown file
    output_file_path = os.path.join(output_directory, "readme.md")
    with open(output_file_path, "w", encoding="utf-8") as output_file:
        output_file.write(response)

if __name__ == "__main__":
    asyncio.run(run_agent())