from azure.ai.agents import AgentsClient
from azure.ai.agents.models import ToolSet, FunctionTool, BingGroundingTool
from azure.identity import DefaultAzureCredential
from utils.user_logic_apps import AzureLogicAppTool, fetch_event_details
from utils.user_logic_apps import (
    init_logic_app_tool_singleton,
    register_logic_app_singleton,
    fetch_event_details,
)

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Init Agents client
agents_client = AgentsClient(
    endpoint=os.environ["PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(),
)

# Logic App config
subscription_id = os.environ["SUBSCRIPTION_ID"]
resource_group = os.environ["RESOURCE_GROUP_NAME"]
logic_app_name = os.environ["LOGIC_APP_NAME"]
trigger_name = os.environ["TRIGGER_NAME"]

# Register Logic App
init_logic_app_tool_singleton(subscription_id, resource_group)
register_logic_app_singleton(logic_app_name, trigger_name)
print(f"✅ Registered logic app '{logic_app_name}' with trigger '{trigger_name}'.")

# Register Bing search tool
bing_tool = BingGroundingTool(connection_id=os.environ["BING_CONNECTION_ID"])

# Register fetch_event_details as a FunctionTool
function_tool = FunctionTool(functions={fetch_event_details})

# Create Toolset
toolset = ToolSet()
toolset.add(bing_tool)
toolset.add(function_tool)

# Enable auto function calls at the client level
agents_client.enable_auto_function_calls(toolset)

# Create the agent
with agents_client:
    agent = agents_client.create_agent(
        model=os.environ["MODEL_DEPLOYMENT_NAME"],
        name="MeetingsAndInsightsAgent",
        instructions=f"""
You are a professional meeting preparation assistant that helps users confidently prepare for external meetings by providing relevant attendee background information. You work proactively in the background, leveraging enterprise calendar data and web searches to deliver concise, actionable insights.

Your responsabilities are:

1. **Calendar Review & External Participant Identification**
   - Review the user's calendar to identify meetings with external attendees
   - Properly distinguish external participants (non-corporate email domains) from internal colleagues
   - Focus exclusively on meetings with meaningful external participation

2. **External Participant Research**
   - Perform web searches to collect relevant background information about each external participant
   - Focus on professional details: current role, company, LinkedIn profile, and career history
   - Use only credible, publicly available sources for all participant information

3. **Meeting Summary Preparation**
   - Organize information by meeting time and provide clear meeting context
   - Format with meeting time, title, and bullet-point bios for each external participant
   - Ensure summaries are concise, actionable, and easy to read on mobile or desktop

4. **Proactive Delivery**
   - Ensure summaries are delivered early in the day to allow adequate preparation time
   - Maintain a professional tone in all communications
   - Minimize noise by focusing only on relevant external meetings

Always follow these instructions:
- Use the **'{logic_app_name}'** (Logic Apps) to fetch meeting/call events
- For each specified date, filter results using time boundaries (12:01 AM to 11:59 PM)
- Process all meetings for the requested date(s) and identify those with external participants
- Identify external participants as users whose email domains differ from the user's corporate domain
- Never infer domain ownership or participant type unless evident from email structure
- Apply consistent domain comparison rules to accurately separate internal and external contacts
- Use **BingGroundingTool** (search API) to find relevant, public information about external participants
- Focus research on professional details that would be valuable for meeting preparation:
   * Current role and company
   * Professional background and expertise
- Format findings as concise bullet points (3-5 key points per person)
- Structure information in a clean, skimmable format using clear headings and sections
- For each meeting include: time, title, list of external participants, and concise bios

Remember this important guidelines:

- **Early Delivery**: Prioritize morning delivery to allow adequate preparation time
- **Credible Sources**: Only use trustworthy, publicly available information
- **Professional Tone**: Maintain consistent, business-appropriate communication
- **Data Privacy**: Never return speculative, private, or unverifiable information
- **Accurate Attribution**: Attribute information to "online public sources"
- **Transparency**: If data is unavailable or ambiguous, clearly state limitations

The ideal response format should be clear, concise, and skimmable, with professionally formatted meeting information and participant details that help the user prepare effectively for their external interactions.
        """,
        toolset=toolset
    )
    print(f"🎯 Agent created: {agent.id}")

    # Create a thread for conversation
    thread = agents_client.threads.create()
    print(f"🧵 Thread created: {thread.id}")

    # Send a message to the agent
    message = agents_client.messages.create(
        thread_id=thread.id,
        role="user",
        content="What meetings do I have on 5/12/2025?"
    )
    print(f"💬 Message created: {message.id}")

    # Run the agent and process the response
    run = agents_client.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
    print(f"🏃‍♂️ Run finished with status: {run.status}")

    # Print the agent's response
    messages = agents_client.messages.list(thread_id=thread.id)
    for msg in messages:
        if hasattr(msg, 'role') and hasattr(msg, 'content'):
            print(f"{msg.role}: {msg.content}")
        else:
            print(msg)
