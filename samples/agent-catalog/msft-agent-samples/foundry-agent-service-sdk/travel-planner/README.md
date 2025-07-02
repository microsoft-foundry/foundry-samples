# Travel Planner Agent

This code sample enables creating an agent to help users receive up-to-date travel recommendations by leveraging both the **Bing Grounding Tool** and the **TripAdvisor API**. The agent summarizes relevant information clearly and offers to create a custom itinerary based on the user's travel duration.

**IMPORTANT NOTE:** Starter templates, instructions, code samples and resources in this msft-agent-samples file (“samples”) are designed to assist in accelerating development of agents for specific scenarios. It is important that you review all provided resources and carefully test Agent behavior in the context of your use case: ([Learn More](https://learn.microsoft.com/en-us/legal/cognitive-services/agents/transparency-note?context=%2Fazure%2Fai-services%2Fagents%2Fcontext%2Fcontext)). 

Certain Agent offerings may be subject to legal and regulatory requirements, may require licenses, or may not be suitable for all industries, scenarios, or use cases. By using any sample, you are acknowledging that Agents or other output created using that sample are solely your responsibility, and that you will comply with all applicable laws, regulations, and relevant safety standards, terms of service, and codes of conduct.  

## Use Cases
1. **Vacation Planning**: Travelers can get up-to-date suggestions on destinations, hotels, and activities.
2. **Business Travel**: Professionals receive efficient recommendations tailored to time-sensitive trips.
3. **Local Exploration**: Residents or tourists can find trending events, attractions, or day-trip ideas in their vicinity.

## Architecture Overview
The system consists of:
- An AI Agent created with Azure AI Agent Service using `gpt-4o` as the base model.
- A Bing Grounding Tool integrated via Azure Bing Account and connected to the agent.
- A TripAdvisor API tool integrated via OpenAPI.
- A Bicep template to automate provisioning of Azure resources.

```text
+----------------+                         
|   User Query   |                         
| (Travel Only)  |                         
+-------+--------+                         
        |                                  
        v                                  
+-------------------+        invokes        +----------------------------+
|  Travel Planner   | ------------------->  | Bing Grounding Tool (API)  |
|     (AI Agent)    | <-------------------  | TripAdvisor API (OpenAPI)  |
+-------------------+        results        +----------------------------+
        |                                  
        v                                  
+------------------------------+           
| Agent Response with summary  |           
| and optional itinerary prompt|           
+------------------------------+           
```

## Setup Instructions

### Prerequisites

1. Azure subscription with the following permissions
   - Contributor or Cognitive Services Contributor role (for resource deployment)
   - Azure AI Developer and Cognitive Services user role (for agent creation)
2. Agent setup: deploy the latest agent setup using this ([custom deployment](https://www.aka.ms/basic-agent-deployment)).
   - The above creates:
      - AI Services resource
      - AI Project
      - Model deployment
3. Python 3.8+
4. Azure CLI
   
### Template specific requirements:
5. Bing Grounding resource ([Documentation](https://learn.microsoft.com/en-us/azure/ai-services/agents/how-to/tools/bing-grounding?tabs=python&pivots=overview))
6. TripAdvisor API connection (via OpenAPI) (For setup and API key: ([Tripadviser documentation](https://tripadvisor-content-api.readme.io/reference/overview))

### Steps
1. **Clone the Repository**

2. **Set Environment Variables**
```bash
PROJECT_ENDPOINT="<your-project-endpoint>" # (https://<your-ai-services-account-name>.services.ai.azure.com/api/projects/<your-project-name>)
MODEL_DEPLOYMENT_NAME="<your-model-deployment-name>"
BING_CONNECTION_ID="<your-bing-connection-id>"
TRIPADVISOR_CONNECTION_ID="<your-tripadvisor-connection-id>"
```

3. **Deploy Resources Using Bicep**
```bash
 az deployment group create    --resource-group <your-rg>    --template-file bing-grounding.bicep    --parameters      bingAccountName="bing-grounding-agent"      bingSku="S1"      connectionName="bing-grounding-conn"      amlWorkspaceResourceName="<AI-Project-Name>"
```

4. **Run the Agent Script**
```bash
 python agent.py
```

## ⚙️ Configuration Guide
| Parameter Name             | Description                                                       |
|----------------------------|-------------------------------------------------------------------|
| `bingAccountName`          | Unique name for the Bing grounding resource                       |
| `bingSku`                  | Pricing tier (e.g., `S1`)                                         |
| `connectionName`           | Name for the AML connection to Bing                               |
| `bingTargetEndpoint`       | Bing API endpoint (defaults to `https://api.bing.microsoft.com/`) |
| `tripadvisor_connection_id`| Azure connection ID for the TripAdvisor OpenAPI tool key          |
| `isSharedToAll`            | Whether the connection is shared with all users                   |

## Sample Data Instructions
This repo contains a `sample_data/` directory with:
- Sample user travel queries
- Example travel agent responses (mocked for offline testing)

You can test the interaction by invoking the agent with prompts like:

## Example Agent Interaction

#### 🧑 User:
Hey, I’m visiting Mountain View this weekend with my partner. We like nature, good coffee, and local food. Can you suggest things to do?

#### 🤖 Travel Agent:
Here are some tailored suggestions for your weekend visit to Mountain View, California.

**Things to Do**
Shoreline Lake at Shoreline Park:
A great spot for nature enthusiasts. You can rent kayaks, pedal boats, or simply enjoy walking trails around the lake.
It's a peaceful, scenic area ideal for couples who love being outdoors.
Pros: Calm environment and beautiful views.
Cons: Crowds on weekends and limited parking.
Computer History Museum:
A fascinating attraction showcasing a history of Silicon Valley innovation. Check out artifacts and interactive exhibits.
While this is tech-focused, there are outdoor areas and cafés nearby for a mix of activities.
Pros: Educational and unique to the area.
Cons: Might be less engaging if you prefer nature exclusively.
Stevens Creek Trail:
This scenic trail is perfect for a leisurely or more active outing. Walk, bike, or jog surrounded by greenery and creek views.
It's well-maintained and close to downtown Mountain View.
Pros: Easy access and natural setting.
Cons: Limited amenities along the trail.
 

**Coffee Shops**
Red Rock Coffee:
A warm, cozy spot with locally roasted coffee and occasional live music. Ideal for relaxing after a hike or walk.
Pros: Great atmosphere and high-quality coffee.
Cons: Sometimes crowded.
Dana Street Roasting Company:
Known for their expertly roasted beans and a hip ambiance. You might find occasional local events here.
Pros: Local favorite with outdoor seating.
Cons: Noise levels can be high if busy.
 

**Restaurants**
Castronovo's:
A top Italian spot with farm-to-table ingredients, perfect for a romantic dinner. Seasonal food with an emphasis on local flavors.
Pros: Pacific ambiance and incredible dishes.
Cons: Reservations recommended.
Xanh Bistro:
Fusion-style Vietnamese food, offering fresh ingredients and a trendy vibe. Don't miss their fresh rolls or craft cocktails.
Pros: Unique flavors and vegetarian-friendly options.
Cons: Prices on the higher side.
Ava's Downtown Market & Deli:
For the freshest local ingredients, explore their deli. Perfect for grabbing a picnic feast before heading to Shoreline Park.
Pros: Authentic flavors and affordable prices.
Cons: Limited seating.
 

Weather & Additional Info
To ensure your comfort, let me confirm Mountain View's weather this weekend and any ongoing events worth visiting.

Would you like me to do this for you?

#### 🧑 User:
Yes please.

#### 🤖 Travel Agent:
Here’s the latest for Mountain View this weekend, May 17-19:

**Weather Forecast**
Saturday, May 17: Sunny, highs around 75°F (24°C), light breeze—great for outdoor activities.
Sunday, May 18: Partly cloudy, highs around 72°F (22°C), similar conditions.
Recommend carrying light jackets for evening outings as it could feel cooler.
 

**Local Events**
KidStock Family Festival (Saturday, May 17, 10:00 AM - 12:00 PM):
A lively family-friendly music and arts festival at Civic Center Plaza, 500 Castro St., Mountain View.
Includes games, crafts, and fun live performances from local bands.
Free to attend, making it a great cultural outing even without kids.
Shoreline Amphitheatre Events:
Check for live concerts or movie screenings here; it could tie in with your visit to Shoreline Park.
Mountain View Farmers' Market (Sunday, May 18, 9:00 AM - 1:00 PM):
Browse local produce, artisan goods, and street-food stalls downtown. Ideal for enjoying fresh, local treats.

This mix of good weather, outdoor experiences, and local events should make for an enjoyable weekend! Let me know if you want tips on transportation or booking recommendations.

## Customization Tips
- Modify the system instructions in `template.py` to enable the agent to provide the best responses as needed.
- Extend the agent with other useful tools or APIs (using OpenAPI spec) such as getting live flight details.

## License
This project is licensed under the MIT License. See the [LICENSE](./LICENSE) file for details.
